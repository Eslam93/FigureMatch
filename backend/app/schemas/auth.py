# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Pydantic request / response schemas for the /auth/* endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic_core import PydanticCustomError

from app.core.security import (
    PasswordTooWeakError,
    validate_bcrypt_password_bytes,
    validate_password_strength,
)


class RegisterRequest(BaseModel):
    email: EmailStr
    # `max_length=72` matches bcrypt's silent-truncation boundary. The
    # frontend Zod schema enforces the same UTF-8 byte limit; the
    # `field_validator` below catches multi-byte characters that fit
    # in 72 code points but not 72 bytes, plus the letter/digit rule.
    password: str = Field(
        min_length=8,
        max_length=72,
        description=(
            "8-72 characters and at most 72 UTF-8 bytes. Must contain at "
            "least one letter and one digit."
        ),
    )
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("password")
    @classmethod
    def _enforce_strength(cls, value: str) -> str:
        # Use a distinct PydanticCustomError type so the validation
        # exception handler in `core/exceptions.py` can remap the
        # response envelope's `error.code` to `WEAK_PASSWORD` instead
        # of the generic `VALIDATION_FAILED`. The frontend (and existing
        # integration tests) rely on the specific code to distinguish
        # weak-password failures from other 422s.
        try:
            validate_password_strength(value)
        except PasswordTooWeakError as exc:
            raise PydanticCustomError("weak_password", str(exc)) from exc
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    # Login keeps a lenient max-128 so users who registered before the
    # strength tightening can still authenticate. The 72-byte cap is
    # still enforced via the `field_validator` so bcrypt's silent
    # truncation never lets the wrong password through.
    password: str = Field(min_length=1, max_length=128)

    @field_validator("password")
    @classmethod
    def _enforce_bcrypt_bytes(cls, value: str) -> str:
        try:
            validate_bcrypt_password_bytes(value)
        except PasswordTooWeakError as exc:
            raise ValueError(str(exc)) from exc
        return value


class UserResponse(BaseModel):
    """Public user representation. Never includes password material."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    email_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class AuthResponse(BaseModel):
    """Returned by /auth/register and /auth/login.

    The refresh token rides in an httpOnly cookie on the same response —
    it is intentionally NOT in this body.
    """

    user: UserResponse
    access_token: str
    token_type: str = "Bearer"  # noqa: S105  # OAuth2 token-type literal, not a secret
    expires_in: int  # seconds until access_token expires
