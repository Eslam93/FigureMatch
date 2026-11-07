"""Unhandled exceptions get the INTERNAL_ERROR envelope inside the middleware stack.

Starlette runs an `Exception` handler in ServerErrorMiddleware, outside
every user middleware, so a 500 rendered there had `meta.request_id: null`
and no X-Request-ID, security or CORS headers. `UnhandledErrorMiddleware`
renders it inside all of those middlewares instead.

Route-level tests build a fresh `create_app()`, so the shared app never
gains the raising route.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import sentry_sdk
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from structlog.testing import capture_logs

from app.core.config import Environment, get_settings
from app.main import create_app
from app.middleware.unhandled_errors import UnhandledErrorMiddleware

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Planted in every raised exception; must never reach a response body.
_SENTINEL = "sentinel-exception-text"
_BOOM_PATH = "/api/v1/__test/boom"


@pytest.fixture
def boom_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """A fresh app with a route that raises `RuntimeError`.

    SecurityHeaders is shown a non-local environment so that HSTS, which
    is skipped on local, is among the headers the 500 must carry.
    """
    non_local = get_settings().model_copy(update={"environment": Environment.PROD})
    monkeypatch.setattr("app.middleware.security_headers.get_settings", lambda: non_local)
    app = create_app()

    @app.get(_BOOM_PATH)
    async def _boom() -> None:
        raise RuntimeError(_SENTINEL)

    return app


def _client(app: FastAPI, *, raise_app_exceptions: bool = True) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions),
        base_url="http://test",
    )


async def test_unhandled_500_carries_request_id_and_security_headers(boom_app: FastAPI) -> None:
    frontend_origin = get_settings().cors_origins[0]
    # raise_app_exceptions stays True: the exception must not escape the app.
    async with _client(boom_app) as client:
        response = await client.get(_BOOM_PATH, headers={"Origin": frontend_origin})

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == {
        "code": "INTERNAL_ERROR",
        "message": "An internal error occurred.",
        "details": {},
    }
    request_id = response.headers.get("x-request-id")
    assert request_id
    assert body["meta"]["request_id"] == request_id
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["strict-transport-security"].startswith("max-age=")
    # CORS too, or the cross-origin frontend couldn't read the envelope.
    assert response.headers["access-control-allow-origin"] == frontend_origin
    assert _SENTINEL not in response.text


async def test_unhandled_500_is_logged_once_with_its_traceback(boom_app: FastAPI) -> None:
    async with _client(boom_app) as client:
        with capture_logs() as logs:
            await client.get(_BOOM_PATH)

    [unhandled] = [entry for entry in logs if entry["event"] == "unhandled_exception"]
    assert unhandled["log_level"] == "error"
    assert unhandled["exc_info"] is True  # format_exc_info renders the traceback
    assert unhandled["error"] == _SENTINEL  # the text stays in the server log
    # AccessLog wraps the catch-all, so it records one completed 500.
    access_events = {"request_completed", "request_failed"}
    [access] = [entry for entry in logs if entry["event"] in access_events]
    assert access["event"] == "request_completed"
    assert access["status"] == 500


async def test_unhandled_500_is_reported_to_sentry(
    boom_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exception no longer reaches Sentry's ASGI middleware, so the
    catch-all reports it itself."""
    reported: list[BaseException] = []
    monkeypatch.setattr(sentry_sdk, "capture_exception", reported.append)

    async with _client(boom_app) as client:
        await client.get(_BOOM_PATH)

    assert len(reported) == 1
    assert isinstance(reported[0], RuntimeError)


async def test_exception_from_an_outer_middleware_still_gets_the_envelope() -> None:
    """The `Exception` handler stays registered as a last resort. It runs
    outside every middleware, so this 500 has no request_id, but it keeps
    the envelope shape."""

    class _BrokenMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            raise RuntimeError(_SENTINEL)

    app = create_app()
    app.add_middleware(_BrokenMiddleware)  # last added, so outside UnhandledErrors

    # ServerErrorMiddleware re-raises after responding.
    async with _client(app, raise_app_exceptions=False) as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert _SENTINEL not in response.text


async def _receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


async def test_exception_after_the_response_started_is_reraised() -> None:
    """Once the status line is out, a second response can't be sent."""
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    async def starts_then_fails(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("stream broke")

    middleware = UnhandledErrorMiddleware(starts_then_fails)
    with pytest.raises(RuntimeError, match="stream broke"):
        await middleware({"type": "http", "method": "GET", "path": "/"}, _receive, send)

    assert [message["type"] for message in sent] == ["http.response.start"]


async def test_non_http_scopes_pass_through() -> None:
    """A lifespan failure must still fail startup, not turn into an HTTP
    response that isn't valid for that scope."""

    async def fails(scope: Scope, receive: Receive, send: Send) -> None:
        raise RuntimeError("startup failed")

    async def send(message: Message) -> None:
        raise AssertionError(f"nothing should be sent, got {message['type']}")

    with pytest.raises(RuntimeError, match="startup failed"):
        await UnhandledErrorMiddleware(fails)({"type": "lifespan"}, _receive, send)
