"""AWS Secrets Manager fetch for runtime credential assembly.

App Runner's `RuntimeEnvironmentSecrets` injects the full secret value
into an env var. For string secrets (JWT_SECRET, OPENAI_API_KEY) that's
fine — the env var is the value. For the RDS secret it isn't: the
secret is JSON (`{username, password, host, port, dbname, ...}`) and
the backend wants a fully-formed `postgresql+asyncpg://` DSN.

The Settings validator calls `resolve_database_url_from_rds_secret`
during startup: if `RDS_SECRET_ARN` is set, fetch the secret, parse,
assemble the DSN, override `database_url`. Local dev keeps the
compose-default DSN by not setting the env var.

`boto3` adds ~50MB to the image and is the canonical AWS-Python
integration. The fetch happens once at process startup; no runtime
overhead.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, cast


@lru_cache(maxsize=1)
def _client() -> Any:
    """Lazy boto3 client. Cached so concurrent calls share one session.

    Region is picked up from `AWS_REGION` env var (App Runner sets it;
    config.py default is `us-east-1`). Typed as `Any` because boto3
    ships no type stubs by default and pulling `boto3-stubs` for one
    call site is more dep churn than it's worth.
    """
    import boto3  # type: ignore[import-untyped]  # local import keeps import time low

    return boto3.client("secretsmanager")


def fetch_secret_json(secret_arn: str) -> dict[str, str | int]:
    """Fetch a JSON-shaped Secrets Manager secret and return its parsed dict.

    Raises `ValueError` if the secret doesn't exist or isn't JSON.
    Callers wrap in try/except — fatal startup failures are fine.
    """
    response = _client().get_secret_value(SecretId=secret_arn)
    payload = response.get("SecretString")
    if not payload:
        raise ValueError(f"Secret {secret_arn} has no SecretString payload.")
    try:
        return cast(dict[str, str | int], json.loads(payload))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Secret {secret_arn} is not valid JSON. "
            "RDS-managed secrets are JSON; bare-string secrets are not."
        ) from exc


def assemble_postgres_dsn(creds: dict[str, str | int]) -> str:
    """Build a `postgresql+asyncpg://...` DSN from an RDS-managed secret.

    AWS RDS auto-creates secrets in the shape::

        {
          "username": "figurematch_app",
          "password": "...",
          "engine": "postgres",
          "host": "...rds.amazonaws.com",
          "port": 5432,
          "dbname": "figurematch",
          "dbInstanceIdentifier": "..."
        }

    `?ssl=require` is appended so asyncpg refuses plaintext fallback
    even if the server happens to allow it. The RDS parameter group
    sets `rds.force_ssl=1` server-side; this is the matching client
    half (belt + suspenders).

    Returns the assembled DSN. Raises `KeyError` if a required field
    is missing — fatal startup failure is the correct response.
    """
    return (
        "postgresql+asyncpg://"
        f"{creds['username']}:{creds['password']}"
        f"@{creds['host']}:{creds['port']}"
        f"/{creds['dbname']}"
        "?ssl=require"
    )


def resolve_database_url_from_rds_secret(secret_arn: str) -> str:
    """End-to-end: fetch the RDS secret + return a usable DATABASE_URL."""
    creds = fetch_secret_json(secret_arn)
    return assemble_postgres_dsn(creds)
