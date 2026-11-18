# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Tests for the Origin-based CSRF guard.

The middleware protects cookie-borne auth state-change endpoints
(login, register, refresh, logout) from cross-origin POSTs when the
refresh cookie is `SameSite=none`. Bearer-authed endpoints
(everything else under /api/v1/*) are intentionally skipped.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.middleware.request_id import REQUEST_ID_HEADER


@pytest.mark.asyncio
async def test_refresh_with_disallowed_origin_returns_403() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={
                "origin": "https://evil.example.com",
                "sec-fetch-site": "cross-site",
            },
        )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "CSRF_ORIGIN_REJECTED"
    assert "evil.example.com" in body["error"]["details"]["reason"]


@pytest.mark.asyncio
async def test_refresh_with_no_origin_passes_through() -> None:
    """Server-to-server callers (curl, k8s probes) never send Origin.
    The guard must let them through — the refresh endpoint's own
    auth check (missing-cookie 401) is the next gate.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/auth/refresh")
    # No Origin → middleware passes; route handler then 401s because
    # there's no refresh cookie. The point is we don't 403.
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_refresh_with_same_origin_sec_fetch_passes() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={
                "origin": "https://anywhere.example.com",
                "sec-fetch-site": "same-origin",
            },
        )
    # Sec-Fetch-Site: same-origin overrides the unknown Origin.
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_refresh_with_allowlisted_origin_passes() -> None:
    # The default cors_origins includes http://localhost:3000 in local
    # env, which is where the test suite runs.
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={
                "origin": "http://localhost:3000",
                "sec-fetch-site": "cross-site",
            },
        )
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_unprotected_endpoint_with_disallowed_origin_passes() -> None:
    """Only the cookie-only routes are guarded. Bearer-authed endpoints
    don't expose this CSRF surface — their access token isn't auto-
    attached from an attacker origin."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/health",
            headers={"origin": "https://evil.example.com"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
    ],
)
async def test_every_protected_path_rejects_cross_origin(path: str) -> None:
    """Login + register were added in round 2 — they issue the refresh
    cookie, so the same Origin policy must apply to them as to refresh/
    logout. A cross-origin POST should never be able to land a victim
    on the attacker's account (login CSRF)."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            path,
            headers={
                "origin": "https://evil.example.com",
                "sec-fetch-site": "cross-site",
            },
            # Provide a valid-looking body so 422 schema-validation
            # doesn't beat us to the 403 — though CSRF should fire
            # first regardless.
            json={"email": "anyone@example.com", "password": "Hunter2x"},
        )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "CSRF_ORIGIN_REJECTED"


@pytest.mark.asyncio
async def test_csrf_403_carries_request_id_header_and_envelope_field() -> None:
    """The CSRF middleware was moved INSIDE RequestID so 403 responses
    pick up the bound contextvar in `meta.request_id` AND the
    `X-Request-ID` response header. Before the reorder these were
    null/absent and observability suffered."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={
                "origin": "https://evil.example.com",
                "sec-fetch-site": "cross-site",
            },
        )
    assert response.status_code == 403
    # Header is present and non-empty.
    rid_header = response.headers.get(REQUEST_ID_HEADER)
    assert rid_header
    # Envelope `meta.request_id` matches the header.
    body = response.json()
    assert body["meta"]["request_id"] == rid_header
