# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Password hashing, JWT encoding/decoding, refresh-token generation.

All inputs and outputs are deliberately strict: typed, narrow, and easy to
mock at test time. The runtime secret is read lazily from settings so test
overrides via env vars take effect without import-order surprises.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import bcrypt
import jwt

from app.core.config import get_settings

# bcrypt cost factor. 12 is the brief default; 14 in protected environments
# can be a future enhancement once we have benchmarking.
BCRYPT_ROUNDS: Final[int] = 12

# JWT signing algorithm. HS256 is sufficient for first-party clients; RS256
# would let us hand out public keys to third parties later.
JWT_ALGORITHM: Final[str] = "HS256"

# Min password length + at-least-one-letter + at-least-one-digit. Light by
# design — strong passwords are the user's responsibility; we just forbid
# the trivially weak ones.
_PASSWORD_MIN_LENGTH = 8
# bcrypt silently truncates inputs after 72 bytes — we reject longer
# passwords explicitly so two passwords that differ only after byte 72 are
# not treated as equal. UTF-8 bytes, not chars.
_PASSWORD_MAX_BYTES = 72
_PASSWORD_LETTER_RE = re.compile(r"[A-Za-z]")
_PASSWORD_DIGIT_RE = re.compile(r"\d")


class PasswordTooWeakError(ValueError):
    """Raised when a candidate password fails the strength check."""


def validate_bcrypt_password_bytes(password: str) -> None:
    """Reject passwords whose UTF-8 encoding exceeds bcrypt's 72-byte limit.

    bcrypt silently truncates inputs beyond 72 bytes, so two passwords
    that differ only after byte 72 would otherwise compare equal. We
    reject explicitly. Used by BOTH register (via the full strength
    check below) AND login (byte guard only — old accounts created
    before the strength rules tightened must still authenticate).
    """
    if len(password.encode("utf-8")) > _PASSWORD_MAX_BYTES:
        raise PasswordTooWeakError(
            f"Password must be at most {_PASSWORD_MAX_BYTES} bytes when UTF-8 encoded "
            "(bcrypt silently truncates inputs longer than this)."
        )


def validate_password_strength(password: str) -> None:
    """Raise PasswordTooWeakError if the password is unacceptable.

    Full check applied to registration. Login uses
    `validate_bcrypt_password_bytes` only so the response stays
    "invalid credentials" regardless of which legacy rule the stored
    password violates.
    """
    if len(password) < _PASSWORD_MIN_LENGTH:
        raise PasswordTooWeakError(f"Password must be at least {_PASSWORD_MIN_LENGTH} characters.")
    validate_bcrypt_password_bytes(password)
    if not _PASSWORD_LETTER_RE.search(password):
        raise PasswordTooWeakError("Password must contain at least one letter.")
    if not _PASSWORD_DIGIT_RE.search(password):
        raise PasswordTooWeakError("Password must contain at least one digit.")


def hash_password(password: str) -> str:
    """bcrypt-hash a plaintext password. Returns a UTF-8 string suitable for DB."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
    ).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time compare via bcrypt. Returns False on any error.

    Inputs longer than `_PASSWORD_MAX_BYTES` (72) bytes are rejected
    explicitly. bcrypt silently truncates beyond that limit, which would
    let a user authenticate with "their first 72 bytes + arbitrary trailing
    garbage" — a footgun, not a vulnerability, but worth closing. Timing
    parity (unknown-email vs wrong-password) is preserved: this early-exit
    only fires for inputs that could never have been registered, so it
    doesn't leak account existence.
    """
    if len(password.encode("utf-8")) > _PASSWORD_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# Cached dummy hash used to equalize the bcrypt cost between the
# "user not found" and "wrong password" branches of login. Computed on
# first use; ~250ms at cost-12 is paid once per process.
_DUMMY_HASH: str | None = None


def get_dummy_password_hash() -> str:
    """Return a stable bcrypt hash of a non-secret string.

    Login calls `verify_password(submitted, this_hash)` when the email
    lookup misses, so the unknown-email path pays the same CPU cost as
    the wrong-password path. Without this, an attacker can distinguish
    registered emails by response latency alone.
    """
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")
    return _DUMMY_HASH


def _jwt_secret() -> str:
    return get_settings().jwt_secret.get_secret_value()


def create_access_token(*, subject: str, ttl_seconds: int | None = None) -> str:
    """Sign an access token. `subject` is typically the user id as a string."""
    settings = get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else settings.jwt_access_token_ttl_seconds
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
        "type": "access",
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify and decode an access token. Raises `jwt.PyJWTError` on failure."""
    payload: dict[str, Any] = jwt.decode(
        token,
        _jwt_secret(),
        algorithms=[JWT_ALGORITHM],
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Token is not an access token.")
    return payload


def generate_refresh_token() -> tuple[str, str]:
    """Mint a refresh token. Returns (raw, sha256_hash).

    The raw value goes into the httpOnly cookie. The hash is what gets
    persisted to `refresh_tokens.token_hash`; the raw value is unrecoverable
    if the database is leaked.
    """
    raw = secrets.token_hex(32)  # 64 hex chars
    hashed = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, hashed


def hash_refresh_token(raw: str) -> str:
    """Reproduce the SHA-256 hash of a raw refresh token for lookup."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
