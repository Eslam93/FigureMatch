# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""X-Request-ID middleware. Pure-ASGI implementation.

`BaseHTTPMiddleware` runs `call_next` in a child task spawned by anyio.
That has two practical consequences for request-id propagation:

  1. ContextVars set in the dispatch task aren't always visible to FastAPI's
     exception handlers, which run inside the routing layer. The
     unhandled-exception envelope can lose `request_id` as a result.
  2. The `try/finally` that clears the contextvar runs in the parent task,
     so anything reading the contextvar after `call_next` returns sees the
     cleared value.

Pure-ASGI middleware sidesteps both: no child task is spawned, the
contextvar is set once for the duration of the request, and we wrap `send`
to inject the response header.
"""

from __future__ import annotations

import re
import uuid
from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import _request_id_var as _ctx_var

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_HEADER_BYTES = REQUEST_ID_HEADER.lower().encode("latin-1")

# Validate incoming X-Request-ID before binding it. An attacker can
# otherwise inject control chars (log injection), arbitrarily long
# strings (storage / log noise), or non-printable bytes. Accept only
# what an honest client would send: short identifiers in a safe charset.
# UUIDs, ULIDs, and most tracing-system ids fit comfortably.
_MAX_INCOMING_LENGTH: Final[int] = 128
_VALID_ID_RE: Final[re.Pattern[str]] = re.compile(r"\A[A-Za-z0-9_.-]+\Z")


def _is_valid_incoming(value: str) -> bool:
    return 0 < len(value) <= _MAX_INCOMING_LENGTH and bool(_VALID_ID_RE.fullmatch(value))


def _extract_incoming(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == _REQUEST_ID_HEADER_BYTES:
            decoded: str = value.decode("latin-1", errors="replace").strip()
            if decoded and _is_valid_incoming(decoded):
                return decoded
            # Fall through — caller will mint a new UUID.
            return None
    return None


class RequestIDMiddleware:
    """Bind X-Request-ID into the contextvar + expose it on the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _extract_incoming(scope) or str(uuid.uuid4())
        token = _ctx_var.set(request_id)

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                headers.append((_REQUEST_ID_HEADER_BYTES, request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            _ctx_var.reset(token)
