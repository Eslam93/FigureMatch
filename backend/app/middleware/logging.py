# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Per-request access log. Emits one structured line per request.

Pure-ASGI implementation matching the same rationale as `RequestIDMiddleware`:
`BaseHTTPMiddleware` runs `call_next` in a child anyio task, which can
break contextvar visibility. We do the same trick — wrap `send` so we
see the response status, time the request from `__call__` entry, and
emit a single structured line per request.
"""

from __future__ import annotations

import time
from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger

log: Final = get_logger("app.access")


class AccessLogMiddleware:
    """Emit `request_completed` (or `request_failed`) with method, path,
    status, and duration in ms."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_holder: dict[str, int] = {"code": 500}

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            log.exception(
                "request_failed",
                method=scope.get("method"),
                path=scope.get("path"),
                duration_ms=round(duration_ms, 2),
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        log.info(
            "request_completed",
            method=scope.get("method"),
            path=scope.get("path"),
            status=status_holder["code"],
            duration_ms=round(duration_ms, 2),
        )
