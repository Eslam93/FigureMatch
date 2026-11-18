# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Unit tests for password hashing, JWT, and refresh-token generation."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import jwt
import pytest

from app.core.security import (
    PasswordTooWeakError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    validate_password_strength,
    verify_password,
)

if TYPE_CHECKING:
    from pytest import MonkeyPatch


# ── password strength ──────────────────────────────────────────────────


def test_validate_password_strength_accepts_good_password() -> None:
    validate_password_strength("Secret123")


def test_validate_password_strength_rejects_too_short() -> None:
    with pytest.raises(PasswordTooWeakError, match="at least"):
        validate_password_strength("Short1")


def test_validate_password_strength_rejects_no_digits() -> None:
    with pytest.raises(PasswordTooWeakError, match="digit"):
        validate_password_strength("OnlyLetters")


def test_validate_password_strength_rejects_no_letters() -> None:
    with pytest.raises(PasswordTooWeakError, match="letter"):
        validate_password_strength("12345678")


# ── password hashing ───────────────────────────────────────────────────


def test_hash_password_produces_distinct_hashes_for_same_input() -> None:
    h1 = hash_password("Secret123")
    h2 = hash_password("Secret123")
    assert h1 != h2  # salt differs


def test_verify_password_accepts_correct_password() -> None:
    hashed = hash_password("Secret123")
    assert verify_password("Secret123", hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("Secret123")
    assert verify_password("WrongPassword1", hashed) is False


def test_verify_password_returns_false_on_garbage_hash() -> None:
    assert verify_password("anything", "not-a-bcrypt-hash") is False


# ── JWT ────────────────────────────────────────────────────────────────


def test_create_and_decode_access_token_roundtrip() -> None:
    token = create_access_token(subject="user-123")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"
    assert payload["exp"] > payload["iat"]


def test_decode_access_token_rejects_expired_token(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.config.Settings.__call__",
        lambda *a, **kw: None,
        raising=False,
    )
    token = create_access_token(subject="user-123", ttl_seconds=1)
    time.sleep(1.2)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_decode_access_token_rejects_refresh_typed_token() -> None:
    # Manually craft a token with type != "access" to confirm rejection.
    from datetime import UTC, datetime, timedelta

    from app.core.config import get_settings

    payload = {
        "sub": "user-123",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "type": "refresh",
    }
    forged = jwt.encode(
        payload,
        get_settings().jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(forged)


# ── refresh tokens ─────────────────────────────────────────────────────


def test_generate_refresh_token_returns_raw_and_hash() -> None:
    raw, hashed = generate_refresh_token()
    assert len(raw) == 64  # 32 bytes hex
    assert len(hashed) == 64  # sha256 hex
    assert raw != hashed
    # Hashing the raw deterministically reproduces the stored hash.
    assert hash_refresh_token(raw) == hashed


def test_generate_refresh_token_is_unpredictable() -> None:
    seen = {generate_refresh_token()[0] for _ in range(100)}
    assert len(seen) == 100  # no collisions
