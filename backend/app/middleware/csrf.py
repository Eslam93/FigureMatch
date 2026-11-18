# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Origin-based CSRF guard for cookie-authenticated state-changing requests.

The refresh cookie is `SameSite=none` in the deployed cross-site posture
(Amplify ↔ App Runner) so the browser sends it on any cross-origin POST
that opts in via `credentials: "include"`. Without this middleware, an
attacker page can fire `fetch("/api/v1/auth/refresh", { credentials:
"include" })` and force a token rotation (DoS-shaped) or, depending on
endpoint, a state change with the victim's identity.

This middleware enforces an Origin / Sec-Fetch-Site allowlist on the
four routes that touch the refresh cookie: `/auth/register` and
`/auth/login` (which ISSUE the cookie — login CSRF is rare but real,
e.g. attacker forces a victim's browser onto the attacker's account),
plus `/auth/refresh` and `/auth/logout` (which AUTHENTICATE via the
cookie). Bearer-authenticated routes are not protected here because the
access token isn't cookie-borne — browsers won't auto-attach it from
an attacker origin. The full path set is `_PROTECTED_PATHS` below.

Allowed shapes for a request to pass:
  - No `Origin` header at all (curl, server-to-server) — accepted.
  - `Sec-Fetch-Site: same-origin` — browser confirmed same-origin.
  - `Origin` in the configured allowlist (`settings.cors_origins`).

Anything else returns 403 with the standard envelope. Returns 403 not
401 so the client doesn't trigger refresh-and-retry loops.
"""

from __future__ import annotations

import json
from typing import Final

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.request_context import get_request_id

# Cookie-borne auth state-change endpoints. Refresh/logout authenticate
# via the cookie; login/register issue the cookie. A cross-site POST
# that lands a victim's browser on the attacker's account (login CSRF)
# is rare but real, so the same Origin policy applies. Everything
# else under /api/v1/* uses Bearer auth from the in-memory access
# token and is safe to leave un-guarded — browsers won't auto-attach
# a Bearer header from an attacker origin.
_PROTECTED_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
    }
)


def _envelope_403(reason: str) -> bytes:
    body = {
        "error": {
            "code": "CSRF_ORIGIN_REJECTED",
            "message": "Cross-origin request rejected.",
            "details": {"reason": reason},
        },
        "meta": {"request_id": get_request_id()},
    }
    return json.dumps(body).encode("utf-8")


class CsrfOriginMiddleware:
    """Reject cross-origin POSTs to cookie-only endpoints.

    Position INSIDE CORS (so CORS preflights still short-circuit) and
    outside the route layer (so the rejection logs as a 403, not a 422).
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        if scope.get("path", "") not in _PROTECTED_PATHS:
            await self._app(scope, receive, send)
            return

        if scope.get("method", "GET").upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
            await self._app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        origin = headers.get("origin")
        sec_fetch_site = headers.get("sec-fetch-site")

        # No Origin header → non-browser client (curl, server-to-server).
        # Cookie-auth is browser-only; if Origin is absent there's no
        # cross-site exposure to guard against here.
        if origin is None:
            await self._app(scope, receive, send)
            return

        # Browsers attach Sec-Fetch-Site on modern Chromium/Firefox/Safari.
        # "same-origin" is unambiguous proof the request didn't come from
        # an attacker page.
        if sec_fetch_site == "same-origin":
            await self._app(scope, receive, send)
            return

        # Fallback: allow if the Origin matches the CORS allowlist.
        allowed = {o.rstrip("/") for o in get_settings().cors_origins}
        if origin.rstrip("/") in allowed:
            await self._app(scope, receive, send)
            return

        body = _envelope_403(reason=f"origin={origin!r} not allowed")
        await self._send_403(send, body=body)

    @staticmethod
    async def _send_403(send: Send, *, body: bytes) -> None:
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})
