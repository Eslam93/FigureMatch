"""Catch-all for unhandled exceptions, inside the middleware stack.

Starlette runs an `Exception` handler in `ServerErrorMiddleware`, which
wraps every user middleware. A 500 rendered there skipped RequestID,
SecurityHeaders and CORS: its envelope had `meta.request_id: null`, and
the response had no X-Request-ID, no CSP, HSTS or nosniff header, and no
CORS header, so the cross-origin frontend couldn't even read it. This
middleware sits inside all of them and sends the same `INTERNAL_ERROR`
envelope, which goes back out through each one like any other response.

The exception stops here, so Sentry's ASGI middleware (outermost) never
sees it. It is reported explicitly instead, a no-op when Sentry isn't
configured.

Once the response has started, a second one can't be sent, so the
exception is re-raised for the outer layers to log.

Pure ASGI, like the other middlewares here: no child task, so the
request-id contextvar bound by RequestID is visible to the log line and
the envelope.
"""

from __future__ import annotations

from typing import Final

import sentry_sdk
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import internal_error_response
from app.core.logging import get_logger

log: Final = get_logger(__name__)


class UnhandledErrorMiddleware:
    """Log an unhandled exception and answer with the INTERNAL_ERROR envelope."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, receive, tracking_send)
        except Exception as exc:
            if response_started:
                raise
            log.exception("unhandled_exception", error=str(exc))
            sentry_sdk.capture_exception(exc)
            await internal_error_response()(scope, receive, send)
