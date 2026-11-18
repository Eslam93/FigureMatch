# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""SecurityHeadersMiddleware — every response carries the baseline set.

Tests run against the live ASGI app so we exercise the actual middleware
stack ordering (the headers must survive being wrapped by AccessLog +
RequestID, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from httpx import AsyncClient

if TYPE_CHECKING:
    from pytest import MonkeyPatch


async def test_health_response_has_baseline_security_headers(client: AsyncClient) -> None:
    """A trivial 200 response from /health must carry every baseline
    header — these aren't tied to specific routes."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


async def test_local_env_does_not_emit_hsts(client: AsyncClient) -> None:
    """HSTS on `localhost` blocks the dev server on a fresh browser
    profile — we deliberately skip it when env=local. The default test
    config inherits ENVIRONMENT=local."""
    response = await client.get("/api/v1/health")
    assert "strict-transport-security" not in {k.lower() for k in response.headers}


async def test_non_local_env_emits_hsts(monkeypatch: MonkeyPatch) -> None:
    """In any non-local env, HSTS is on. The middleware reads `environment`
    at __init__ time, so we patch `get_settings` at the middleware module
    level (where `from app.core.config import get_settings` bound the
    reference) and build a fresh app whose middleware __init__ then sees
    the patched function.
    """
    from httpx import ASGITransport
    from pydantic import SecretStr

    from app.core.config import AIProviderMode, Environment, Settings
    from app.main import create_app

    settings = Settings(
        environment=Environment.PROD,
        ai_provider_mode=AIProviderMode.MOCK,
        # Mock-in-prod now requires the explicit escape hatch (P1.10).
        # We're testing HSTS, not provider validation, so flip it on.
        allow_mock_provider=True,
        jwt_secret=SecretStr("3f9a17ce4d2b48a1c0e7f63bda5912f48e6c0a9d7b2e54f1c8a3d6094e7b1c2f"),
        # The non-local cors-origin validator rejects the default
        # `localhost:3000` in production. Provide a real-shaped origin
        # so this HSTS-focused test doesn't trip the validator instead.
        cors_origins=["https://test-frontend.example.com"],  # type: ignore[arg-type]
    )
    # Patch at the use sites — security_headers imports the symbol, so
    # patching `app.core.config.get_settings` alone wouldn't reach it.
    monkeypatch.setattr("app.middleware.security_headers.get_settings", lambda: settings)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        response = await ac.get("/api/v1/health")
    assert response.headers["strict-transport-security"].startswith("max-age=")


async def test_error_response_also_has_security_headers(client: AsyncClient) -> None:
    """A non-2xx response must still carry the headers — clients render
    error pages too, and CSP/X-Frame-Options have to apply uniformly."""
    response = await client.get("/api/v1/this-path-does-not-exist")
    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
