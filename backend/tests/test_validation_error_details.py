"""422 responses must never echo what the client submitted.

Pydantic's error dicts carry `input`, the rejected value itself, so the
validation handler used to send a rejected password straight back in the
response body (alongside Pydantic's `ctx` and `url`). Each entry of
`error.details.errors` now keeps only `loc`, `msg` and `type`.

Both requests fail schema validation before any route logic runs, so no
database is needed.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.middleware.rate_limit import reset_rate_limit_state

_ERROR_KEYS = {"loc", "msg", "type"}


@pytest.fixture(autouse=True)
def _fresh_rate_limit_budget() -> None:
    """/auth/register and /auth/login are rate limited, and the bucket
    store is module-level state that earlier tests may have filled."""
    reset_rate_limit_state()


async def test_register_weak_password_is_not_echoed(client: AsyncClient) -> None:
    sentinel = "SentinelWeakPasswordNoDigit"  # no digit, so it fails the strength rule
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "sentinel@example.com", "password": sentinel, "full_name": "Sentinel"},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    # The WEAK_PASSWORD remap and its message survive the trimming.
    assert error["code"] == "WEAK_PASSWORD"
    assert error["message"] == "Password must contain at least one digit."
    errors = error["details"]["errors"]
    assert len(errors) == 1
    assert set(errors[0]) == _ERROR_KEYS
    assert errors[0]["loc"] == ["body", "password"]
    assert errors[0]["type"] == "weak_password"
    assert sentinel not in response.text


async def test_login_over_long_password_is_not_echoed(client: AsyncClient) -> None:
    sentinel = "SentinelOverLong"
    password = sentinel * 10  # 160 characters; login caps passwords at 128
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "sentinel@example.com", "password": password},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    errors = error["details"]["errors"]
    assert len(errors) == 1
    # `string_too_long` is one of the errors that also carried `ctx`.
    assert set(errors[0]) == _ERROR_KEYS
    assert errors[0]["loc"] == ["body", "password"]
    assert errors[0]["type"] == "string_too_long"
    assert errors[0]["msg"]
    assert sentinel not in response.text
