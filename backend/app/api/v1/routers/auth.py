# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""/auth/* endpoints — register, login, refresh, logout, current user."""

from __future__ import annotations

import ipaddress

from fastapi import APIRouter, Request, Response, status

from app.api.v1.deps import CurrentUser
from app.core.config import Environment, get_settings
from app.core.exceptions import UnauthorizedError
from app.db.session import DbSession
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.auth_service import AuthService, AuthTokens

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, tokens: AuthTokens) -> None:
    """Set the httpOnly refresh cookie.

    `Secure` is set for every environment except `local`. `SameSite` is
    read from settings — `lax` for same-site setups (local, custom
    domains), `none` for cross-site setups like default
    `*.amplifyapp.com` + `*.awsapprunner.com`. Browsers require
    `Secure` whenever `SameSite=None`, which holds outside local.
    """
    settings = get_settings()
    secure = settings.environment != Environment.LOCAL
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        tokens.refresh_token_raw,
        httponly=True,
        secure=secure,
        samesite=settings.cookie_samesite,
        max_age=settings.jwt_refresh_token_ttl_seconds,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Delete the refresh cookie. Path/secure/samesite must match the
    original `Set-Cookie` for the browser to drop it.
    """
    settings = get_settings()
    secure = settings.environment != Environment.LOCAL
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=secure,
        samesite=settings.cookie_samesite,
        httponly=True,
    )


def _client_user_agent(request: Request) -> str | None:
    ua = request.headers.get("user-agent")
    return ua[:500] if ua else None


def _valid_ip(candidate: str | None) -> str | None:
    """Return `candidate` only if it parses as a real IP, else None.

    Scoped IPv6 addresses (e.g. `fe80::1%eth0`) are rejected explicitly.
    Python's `ipaddress` parses them since 3.9, but the scope id reflects
    the *caller's* local interface, which is meaningless audit signal and
    inconsistent across Postgres `INET` versions. We require unscoped
    addresses only.
    """
    if not candidate:
        return None
    try:
        parsed = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.scope_id is not None:
        return None
    return candidate


def _client_ip(request: Request) -> str | None:
    """Pick the originating client IP for *audit storage only*.

    `X-Forwarded-For` is client-controllable until we sit behind a known proxy
    config, so anything we extract from it gets validated as a real IP before
    we let it into the `INET` column — otherwise junk like
    `X-Forwarded-For: drop-table-users` becomes a 500.

    **WARNING (for P1.9 rate limiting and any future security decision):**
    do NOT reuse this value as a security identity. A client can put any
    syntactically valid IP in the header and we'll trust it — fine for
    audit ("at least one of these IPs touched this row"), unsafe for
    "block this IP after 10 failed logins" (attacker would rotate XFF).
    Rate limiting needs `request.client.host` (the real TCP peer) plus a
    trusted-proxy allowlist before honoring forwarded-for headers.
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        first_hop = fwd.split(",", 1)[0].strip()
        validated = _valid_ip(first_hop)
        if validated is not None:
            return validated
        # Fall through to request.client when the header is junk.

    return _valid_ip(request.client.host) if request.client else None


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account",
)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> AuthResponse:
    user, tokens = await AuthService(db).register(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        user_agent=_client_user_agent(request),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(response, tokens)
    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Authenticate and receive a new token pair",
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> AuthResponse:
    user, tokens = await AuthService(db).login(
        email=body.email,
        password=body.password,
        user_agent=_client_user_agent(request),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(response, tokens)
    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
    )


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Rotate refresh token and issue a new access token",
)
async def refresh(
    request: Request,
    response: Response,
    db: DbSession,
) -> AuthResponse:
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw:
        raise UnauthorizedError(
            "Refresh token cookie is missing.",
            code="MISSING_REFRESH_TOKEN",
        )
    user, tokens = await AuthService(db).refresh(
        raw_refresh=raw,
        user_agent=_client_user_agent(request),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(response, tokens)
    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the refresh token and clear the cookie",
)
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
) -> None:
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    await AuthService(db).logout(raw_refresh=raw)
    _clear_refresh_cookie(response)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Return the authenticated user",
)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
