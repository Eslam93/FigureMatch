# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Security response headers middleware.

Applies a baseline of headers every browser expects from a production
service. The values are conservative — tighter CSP, longer HSTS preload,
and proper Permissions-Policy lockdown land in P11.5 once we have a
real frontend and can measure what breaks.

`Strict-Transport-Security` is only applied outside `local` — telling
a browser to require TLS on `localhost` makes the dev server unusable
on a fresh laptop. `dev` (the shared cloud env) is treated like prod.
"""

from __future__ import annotations

from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Environment, get_settings

# The Swagger-UI flavored CSP. Used in environments where `/docs` is
# exposed (local + dev). Swagger UI's CDN bundle uses inline init
# scripts and inline styles, so `unsafe-inline` and jsdelivr are
# required there.
_SWAGGER_CSP: Final[str] = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# Tight CSP used in staging/production where `/docs` is disabled. Drops
# `unsafe-inline`, the jsdelivr CDN, and `connect-src` to the API's own
# origin. Frontend assets are served from a different origin (Amplify),
# so no `connect-src` widening is needed for the backend.
_TIGHT_CSP: Final[str] = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)

# HSTS: 6 months, no preload, no subdomain inclusion until we own all
# subdomains. Browsers respect this header only over HTTPS responses.
_HSTS_VALUE: Final[str] = "max-age=15552000"

_BASE_STATIC_HEADERS: Final[dict[bytes, bytes]] = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"strict-origin-when-cross-origin",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
}


def _csp_for(env: Environment) -> bytes:
    """Choose the CSP variant. Local + dev expose Swagger UI and so
    need the looser policy; staging + production drop `/docs` entirely
    and get the tight CSP."""
    if env in {Environment.LOCAL, Environment.DEV}:
        return _SWAGGER_CSP.encode("ascii")
    return _TIGHT_CSP.encode("ascii")


class SecurityHeadersMiddleware:
    """Pure-ASGI middleware that attaches a small set of security
    headers to every HTTP response.

    Matches the pure-ASGI shape of `RequestIDMiddleware` rather than
    using BaseHTTPMiddleware — same rationale as P1.5.1's middleware
    rewrite: BaseHTTPMiddleware's task-spawning interferes with
    contextvar visibility for downstream readers, and we don't need
    any of its conveniences here.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        env = get_settings().environment
        self._include_hsts = env != Environment.LOCAL
        self._csp = _csp_for(env)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name for name, _ in headers}
                for name, value in _BASE_STATIC_HEADERS.items():
                    if name not in existing:
                        headers.append((name, value))
                if b"content-security-policy" not in existing:
                    headers.append((b"content-security-policy", self._csp))
                if self._include_hsts and b"strict-transport-security" not in existing:
                    headers.append((b"strict-transport-security", _HSTS_VALUE.encode("ascii")))
                message["headers"] = headers
            await send(message)

        await self._app(scope, receive, send_with_headers)
