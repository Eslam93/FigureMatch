"""Unit tests for `app.core.aws_secrets`.

The module is only exercised when running against AWS; locally `boto3` is
mocked or unused. These tests cover the pure helpers — DSN assembly and
JSON parsing — without touching the network.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from app.core.aws_secrets import (
    assemble_postgres_dsn,
    fetch_secret_json,
    resolve_database_url_from_rds_secret,
)


class TestAssemblePostgresDsn:
    def test_includes_ssl_require(self) -> None:
        """`?ssl=require` is the client-side half of forced TLS — it
        keeps asyncpg from falling back to plaintext even if the server
        somehow allows it. Belt + suspenders to the RDS parameter
        group's `rds.force_ssl=1`.
        """
        dsn = assemble_postgres_dsn(
            {
                "username": "figurematch_app",
                "password": "p@ss",
                "host": "db.example.rds.amazonaws.com",
                "port": 5432,
                "dbname": "figurematch",
            }
        )
        assert dsn.endswith("?ssl=require")
        assert dsn.startswith("postgresql+asyncpg://")

    def test_full_shape(self) -> None:
        dsn = assemble_postgres_dsn(
            {
                "username": "u",
                "password": "p",
                "host": "h",
                "port": 1,
                "dbname": "d",
            }
        )
        assert dsn == "postgresql+asyncpg://u:p@h:1/d?ssl=require"

    def test_missing_field_raises(self) -> None:
        with pytest.raises(KeyError):
            assemble_postgres_dsn({"username": "u"})


class TestFetchSecretJson:
    def test_returns_parsed_dict(self) -> None:
        fake_client: Any = type(
            "FakeClient",
            (),
            {
                "get_secret_value": lambda self, SecretId: {  # noqa: N803
                    "SecretString": json.dumps({"username": "u", "password": "p"}),
                },
            },
        )()
        with patch("app.core.aws_secrets._client", return_value=fake_client):
            out = fetch_secret_json("arn:aws:secretsmanager:...")
        assert out == {"username": "u", "password": "p"}

    def test_empty_payload_raises(self) -> None:
        fake_client: Any = type(
            "FakeClient",
            (),
            {
                "get_secret_value": lambda self, SecretId: {  # noqa: N803
                    "SecretString": "",
                },
            },
        )()
        with (
            patch("app.core.aws_secrets._client", return_value=fake_client),
            pytest.raises(ValueError, match="no SecretString payload"),
        ):
            fetch_secret_json("arn:aws:secretsmanager:...")

    def test_non_json_payload_raises(self) -> None:
        fake_client: Any = type(
            "FakeClient",
            (),
            {
                "get_secret_value": lambda self, SecretId: {  # noqa: N803
                    "SecretString": "not json",
                },
            },
        )()
        with (
            patch("app.core.aws_secrets._client", return_value=fake_client),
            pytest.raises(ValueError, match="not valid JSON"),
        ):
            fetch_secret_json("arn:aws:secretsmanager:...")


def test_resolve_database_url_from_rds_secret_end_to_end() -> None:
    fake_client: Any = type(
        "FakeClient",
        (),
        {
            "get_secret_value": lambda self, SecretId: {  # noqa: N803
                "SecretString": json.dumps(
                    {
                        "username": "u",
                        "password": "p",
                        "host": "h",
                        "port": 5432,
                        "dbname": "d",
                    }
                ),
            },
        },
    )()
    with patch("app.core.aws_secrets._client", return_value=fake_client):
        dsn = resolve_database_url_from_rds_secret("arn:aws:secretsmanager:...")
    assert dsn == "postgresql+asyncpg://u:p@h:5432/d?ssl=require"
