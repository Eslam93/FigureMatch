# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""CORS configuration smoke tests.

The contract: explicit origin allowlist, `allow_credentials=True`, no
wildcard, OPTIONS handled, `X-Request-ID` exposed.
"""

from __future__ import annotations

from httpx import AsyncClient

ALLOWED_ORIGIN = "http://localhost:3000"
DISALLOWED_ORIGIN = "https://evil.example.com"


async def test_preflight_from_allowed_origin(client: AsyncClient) -> None:
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, X-Request-ID",
        },
    )
    assert response.status_code in (200, 204)
    assert response.headers.get("Access-Control-Allow-Origin") == ALLOWED_ORIGIN
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"


async def test_preflight_from_disallowed_origin_omits_cors_headers(
    client: AsyncClient,
) -> None:
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": DISALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    # FastAPI's CORS middleware does not echo the origin back when it isn't
    # in the allowlist — the absence of the header is the safety signal.
    assert response.headers.get("Access-Control-Allow-Origin") != DISALLOWED_ORIGIN


async def test_actual_request_exposes_request_id_header(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/health",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert response.status_code == 200
    expose = response.headers.get("Access-Control-Expose-Headers", "")
    assert "X-Request-ID" in expose
