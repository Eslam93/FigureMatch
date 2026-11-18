# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Shared FastAPI dependencies for the v1 API."""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Header

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import DbSession
from app.services.auth_service import AuthService


async def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve the caller's User from the `Authorization: Bearer <jwt>` header.

    Raises `UnauthorizedError` (envelope-mapped to 401) on any failure.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError(
            "Missing or invalid Authorization header.",
            code="MISSING_TOKEN",
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token has expired.", code="TOKEN_EXPIRED") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid access token.", code="INVALID_TOKEN") from exc

    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise UnauthorizedError("Invalid token subject.", code="INVALID_TOKEN")
    try:
        user_id = uuid.UUID(sub)
    except ValueError as exc:
        raise UnauthorizedError("Invalid token subject.", code="INVALID_TOKEN") from exc

    return await AuthService(db).get_user(user_id)


CurrentUser = Annotated[User, Depends(get_current_user)]
