# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""RateLimitMiddleware — enforcement, 429 envelope, isolation, cleanup.

We don't go through the real auth endpoints (those need a DB). Instead
we mount the middleware on a tiny in-process ASGI app and exercise it
directly — fast, no fixtures, deterministic.
"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.middleware.rate_limit import RateLimitMiddleware, reset_rate_limit_state


def _build_test_app(limit: int = 3) -> Starlette:
    """Tiny ASGI app: GET /limited returns 200; the middleware caps it
    at `limit` requests per minute per IP."""

    async def endpoint(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/limited", endpoint)])
    app.add_middleware(RateLimitMiddleware, rules={"/limited": limit})
    return app


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """Each test starts with a clean bucket dict."""
    reset_rate_limit_state()


# ── enforcement ────────────────────────────────────────────────────────


async def test_allows_requests_under_the_limit() -> None:
    app = _build_test_app(limit=3)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        for _ in range(3):
            response = await ac.get("/limited")
            assert response.status_code == 200


async def test_rejects_the_request_that_exceeds_the_limit() -> None:
    app = _build_test_app(limit=3)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        for _ in range(3):
            assert (await ac.get("/limited")).status_code == 200
        over = await ac.get("/limited")
    assert over.status_code == 429
    body = over.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["details"]["retry_after_seconds"] >= 1


async def test_429_includes_retry_after_header() -> None:
    app = _build_test_app(limit=1)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        await ac.get("/limited")
        over = await ac.get("/limited")
    assert over.status_code == 429
    assert "retry-after" in {k.lower() for k in over.headers}
    assert int(over.headers["retry-after"]) >= 1


# ── isolation ──────────────────────────────────────────────────────────


async def test_unlimited_paths_are_not_throttled() -> None:
    """Paths not in the rules dict bypass the middleware entirely."""

    async def endpoint(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/anything", endpoint)])
    app.add_middleware(RateLimitMiddleware, rules={"/something-else": 1})
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        for _ in range(20):
            response = await ac.get("/anything")
            assert response.status_code == 200


async def test_two_paths_have_independent_counters() -> None:
    """Path A hitting its cap doesn't penalize path B."""

    async def a_endpoint(_: Request) -> JSONResponse:
        return JSONResponse({"path": "a"})

    async def b_endpoint(_: Request) -> JSONResponse:
        return JSONResponse({"path": "b"})

    app = Starlette(
        routes=[
            Route("/a", a_endpoint),
            Route("/b", b_endpoint),
        ]
    )
    app.add_middleware(RateLimitMiddleware, rules={"/a": 1, "/b": 1})
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        assert (await ac.get("/a")).status_code == 200
        assert (await ac.get("/a")).status_code == 429
        # /b should still be allowed once.
        assert (await ac.get("/b")).status_code == 200


async def test_envelope_has_request_id_key() -> None:
    """Even when rate-limit middleware runs before RequestID binds the
    contextvar, the envelope shape must still include the meta key —
    callers shouldn't have to special-case 429s."""
    app = _build_test_app(limit=1)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        await ac.get("/limited")
        over = await ac.get("/limited")
    body = json.loads(over.content)
    assert "meta" in body
    assert "request_id" in body["meta"]


async def test_429_on_real_app_carries_security_headers_and_request_id() -> None:
    """Regression for P1.11 #8: when the production middleware stack
    rate-limits a request, the 429 must still carry the security
    headers AND the bound request_id. Previously RateLimit was outside
    SecurityHeaders and RequestID, so 429 responses dropped both."""
    from app.main import app as real_app
    from app.middleware.rate_limit import reset_rate_limit_state

    reset_rate_limit_state()
    incoming_id = "11111111-2222-3333-4444-555555555555"
    async with AsyncClient(
        transport=ASGITransport(app=real_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        # /auth/register is capped at 10/min. Burst past the cap with
        # bodies that all fail validation (no DB needed) so we trip
        # the rate limit deterministically.
        for _ in range(10):
            await ac.post(
                "/api/v1/auth/register",
                json={},
                headers={"X-Request-ID": incoming_id},
            )
        over = await ac.post(
            "/api/v1/auth/register",
            json={},
            headers={"X-Request-ID": incoming_id},
        )
    assert over.status_code == 429
    # Security headers attached even on the rate-limited path.
    assert over.headers["x-content-type-options"] == "nosniff"
    assert over.headers["x-frame-options"] == "DENY"
    # request_id propagated into the envelope.
    body = json.loads(over.content)
    assert body["meta"]["request_id"] == incoming_id
