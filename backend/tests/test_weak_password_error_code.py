# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Pin the wire contract: /auth/register with a weak password returns
422 with `error.code = "WEAK_PASSWORD"`, not the generic
`VALIDATION_FAILED`.

The Pydantic `field_validator` raises `PydanticCustomError("weak_password",
...)` and `validation_exception_handler` in `app/core/exceptions.py`
remaps it to the application-level code. The integration test in
`tests/integration/test_auth_routes.py::test_register_rejects_weak_password`
covers the same contract via the postgres-backed integration suite, but
that path is skipped locally when Postgres is unreachable; this unit
test runs without a database because the schema validator rejects the
request before any route logic executes.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_weak_password_returns_weak_password_code(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "12345678",  # passes Pydantic min_length, fails strength
            "full_name": "Weak",
        },
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "WEAK_PASSWORD"
    # Message should be useful — the strength-check error text, not the
    # generic "Request validation failed."
    assert (
        "letter" in payload["error"]["message"].lower()
        or "digit" in payload["error"]["message"].lower()
    )


@pytest.mark.asyncio
async def test_register_missing_email_still_returns_validation_failed(
    client: AsyncClient,
) -> None:
    """Sanity: non-weak-password validation errors keep the generic code."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"password": "Secret123", "full_name": "No Email"},
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_FAILED"
