# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Object factories for tests.

Two flavors:

- **Pure** (`make_*`) — construct ORM objects without touching the DB.
  Useful in unit tests that mock repositories.

- **Persisted** (`create_*_in_db`) — flush the object into the test
  session so subsequent SELECTs see it. Used by integration tests that
  want a pre-existing user before exercising an endpoint.

Defaults are deliberately permissive: random unique emails, a
strong-enough canned password, plausible names. Override any field
that the test cares about.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_refresh_token, hash_password
from app.db.models import RefreshToken, User


def _unique_email() -> str:
    """Generate a non-colliding email so concurrent test runs don't trip
    the CITEXT unique constraint."""
    return f"user-{uuid.uuid4().hex[:12]}@example.test"


# Precomputed bcrypt hash so tests that don't care about password
# verification can skip the ~250ms bcrypt cost per `make_user` call.
# Computed once at import time, cached for the suite. Tests that DO
# exercise login pass `password=` explicitly to force a fresh real hash.
_PRECOMPUTED_PASSWORD_HASH: str | None = None


def _default_password_hash() -> str:
    global _PRECOMPUTED_PASSWORD_HASH
    if _PRECOMPUTED_PASSWORD_HASH is None:
        _PRECOMPUTED_PASSWORD_HASH = hash_password("Secret123")
    return _PRECOMPUTED_PASSWORD_HASH


def make_user(
    *,
    email: str | None = None,
    password: str | None = None,
    full_name: str = "Test User",
    email_verified: bool = False,
) -> User:
    """Build an unsaved User.

    When `password` is None (default), the user gets a precomputed
    bcrypt hash — fast, but can't authenticate against any specific
    plaintext other than "Secret123". Use for tests that just need a
    User row to exist.

    When `password` is provided, bcrypt-hash it fresh (~250ms). Required
    for tests that hit `/auth/login` and expect verification.
    """
    password_hash = _default_password_hash() if password is None else hash_password(password)
    user = User(
        id=uuid.uuid4(),
        email=email or _unique_email(),
        password_hash=password_hash,
        full_name=full_name,
    )
    if email_verified:
        user.email_verified_at = datetime.now(UTC)
    return user


async def create_user_in_db(
    session: AsyncSession,
    *,
    email: str | None = None,
    password: str | None = None,
    full_name: str = "Test User",
    email_verified: bool = False,
) -> User:
    """Build and flush a User into the test session. Returns the
    flushed object with its server-assigned columns populated.

    Inherits `make_user`'s precomputed-hash-by-default behavior.
    Pass `password=` only if the test verifies that specific password.
    """
    user = make_user(
        email=email,
        password=password,
        full_name=full_name,
        email_verified=email_verified,
    )
    session.add(user)
    await session.flush()
    return user


async def create_refresh_token_in_db(
    session: AsyncSession,
    *,
    user: User,
    expires_in_seconds: int = 60 * 60 * 24,
    revoked: bool = False,
) -> tuple[RefreshToken, str]:
    """Mint a refresh token, flush it, and return the row + raw token.

    The raw value is what the cookie would hold; the row's
    `token_hash` matches it. Tests that want to exercise the refresh
    endpoint pass the raw value as a cookie, and assertions on the
    row's state run against the returned model.
    """
    raw, hashed = generate_refresh_token()
    now = datetime.now(UTC)
    row = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hashed,
        expires_at=now + timedelta(seconds=expires_in_seconds),
        revoked_at=now if revoked else None,
    )
    session.add(row)
    await session.flush()
    return row, raw
