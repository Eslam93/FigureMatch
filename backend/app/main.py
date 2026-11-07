"""FastAPI application factory + ASGI entry point.

Starlette stacks middleware in REVERSE order of `add_middleware()` calls:
the last one added is the outermost. So a request flows from the outermost
(last added) wrapper inward, then back outward on the response. The wiring
below reads outer-to-inner along the request path:

  1. CORS (last added, outermost) — preflights short-circuit before any
     other middleware allocates work.
  2. SecurityHeaders              — adds nosniff / DENY / CSP / HSTS to
                                    every response on its way out,
                                    INCLUDING 429s emitted by RateLimit.
  3. RequestID                    — binds `X-Request-ID` into the contextvar
                                    before RateLimit (or CSRF) reads it
                                    for an early-return envelope, and
                                    wraps `send` to inject the response
                                    header on every response — including
                                    those short-circuited by CSRF/RateLimit.
  4. CSRF (Origin guard)          — runs INSIDE RequestID so its 403
                                    envelope carries `request_id` and
                                    its response gains the X-Request-ID
                                    header. Protects cookie-borne auth
                                    state-change endpoints only.
  5. RateLimit                    — rejects 429 before the request reaches
                                    auth code; bound IP is the real TCP
                                    peer (forwarded-for is unsafe as
                                    rate-limit identity until P11.x).
                                    Position INSIDE SecurityHeaders +
                                    RequestID so 429 responses carry both.
  6. AccessLog                    — reads the bound request_id from the
                                    contextvar so every log line carries
                                    it. OUTSIDE UnhandledErrors, so an
                                    unhandled 500 is logged once, as a
                                    completed request with status 500.
  7. UnhandledErrors (first added, innermost) — turns an exception the app
     raises into the INTERNAL_ERROR envelope while still INSIDE RequestID
     + SecurityHeaders, so the 500 carries `request_id`, X-Request-ID and
     the security headers. Logs it as `unhandled_exception`.
  8. Exception handlers           — AppException, ProviderError,
                                    HTTPException and validation errors
                                    get the {error, meta} envelope here,
                                    inside every middleware.
                                    The `Exception` handler is the odd one
                                    out: Starlette runs it in its own
                                    ServerErrorMiddleware, OUTSIDE all of
                                    the above, so it is only a last resort
                                    for an exception a middleware raises.
  9. v1 router                    — mounted at /api/v1.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.api.v1.router import v1_router
from app.core.config import Environment, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import close_db_engine
from app.middleware.csrf import CsrfOriginMiddleware
from app.middleware.logging import AccessLogMiddleware
from app.middleware.rate_limit import RateLimitMiddleware, RateLimitRule
from app.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.unhandled_errors import UnhandledErrorMiddleware
from app.services.image_storage import LOCAL_IMAGES_DIR

# Per-path requests-per-minute caps. /auth/login + /auth/register are
# the brief's explicit targets; /auth/refresh is added because the
# security-review pass on P1.6 flagged the unauthenticated endpoint as
# a token-space probing surface. /content/generate gets a per-minute
# cap that's the closest analog to the brief's 20/hour budget — the
# real 20/hour sliding window arrives with Redis (P11.3). P11.3 will
# also swap this whole dict for per-account dimensions.
_AUTH_RATE_LIMITS: Final[dict[str, int]] = {
    "/api/v1/auth/login": 10,
    "/api/v1/auth/register": 10,
    "/api/v1/auth/refresh": 10,
    "/api/v1/content/generate": 20,
}

# Pattern rules cover dynamic paths the exact-path dict can't. Each
# pattern carries a stable `key` so two endpoints never share a counter.
# Image generation is the expensive one (~$0.04/image at medium quality)
# — cap it tighter than text-gen. Improver runs two LLM calls per
# invocation, so its cap is also conservative.
_RATE_LIMIT_PATTERNS: Final[list[RateLimitRule]] = [
    RateLimitRule(
        pattern=re.compile(r"^/api/v1/content/[0-9a-fA-F-]{36}/image$"),
        limit=6,
        key="pattern:content_image_generate",
    ),
    RateLimitRule(
        pattern=re.compile(r"^/api/v1/improve$"),
        limit=10,
        key="pattern:improve",
    ),
]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("app.startup")
    log.info(
        "application_starting",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        ai_provider_mode=settings.ai_provider_mode.value,
    )
    yield
    log.info("application_stopping")
    await close_db_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    # Sentry: initialized at create_app time so it captures startup
    # errors too. Silently no-ops when SENTRY_DSN is empty (the
    # default), so dev environments never need Sentry credentials.
    # P11.5 will polish PII scrubbing + source maps.
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment.value,
            release=settings.app_version,
            traces_sample_rate=0.1,
            send_default_pii=False,
            integrations=[
                FastApiIntegration(),
                StarletteIntegration(),
                AsyncioIntegration(),
            ],
        )

    # Swagger/ReDoc/openapi.json are convenient in dev and the demo
    # environment but introduce a Swagger-UI script surface that
    # forces `unsafe-inline` in CSP. Hide them in staging/production —
    # external API consumers should get a bundled spec via release
    # artifacts, not a public live-docs page.
    docs_enabled = settings.environment in {Environment.LOCAL, Environment.DEV}
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI Content Marketing Suite — backend API.",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # Add middleware INNER-MOST first so the LAST-added one wraps outside
    # everything else (Starlette's documented ordering).
    app.add_middleware(UnhandledErrorMiddleware)  # innermost — 500s pass back through the rest
    app.add_middleware(AccessLogMiddleware)  # outside UnhandledErrors — logs the 500's status
    app.add_middleware(
        RateLimitMiddleware,
        rules=_AUTH_RATE_LIMITS,
        patterns=_RATE_LIMIT_PATTERNS,
    )
    # CSRF guard added BEFORE RequestID so it ends up inside RequestID
    # in Starlette's outer-to-inner stack: RequestID sees the request
    # first, binds the contextvar + wraps `send`, then delegates to
    # CSRF. When CSRF short-circuits with a 403, the envelope picks up
    # the bound `request_id` and the response gains X-Request-ID on
    # the way back out through RequestID's send-wrapper.
    app.add_middleware(CsrfOriginMiddleware)
    app.add_middleware(
        RequestIDMiddleware
    )  # binds contextvar + adds X-Request-ID header to every response
    app.add_middleware(SecurityHeadersMiddleware)  # wraps RateLimit so 429 carries security headers
    app.add_middleware(
        CORSMiddleware,  # outermost — preflights short-circuit before anything else
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            REQUEST_ID_HEADER,
            "Idempotency-Key",
        ],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )

    register_exception_handlers(app)

    app.include_router(v1_router, prefix="/api/v1")

    # Local-disk image serving for dev. When `IMAGES_CDN_BASE_URL`
    # points elsewhere (e.g. CloudFront in prod), this mount is still
    # harmless — the directory is created lazily by the storage layer
    # on first write.
    LOCAL_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/local-images",
        StaticFiles(directory=str(LOCAL_IMAGES_DIR)),
        name="local-images",
    )

    return app


app = create_app()
