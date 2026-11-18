# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Pydantic-layer password validation tests.

Round 2 moved the strength + bcrypt-bytes checks from the service
layer into Pydantic `field_validator`s on `RegisterRequest` and
`LoginRequest`. That makes the OpenAPI spec honest about the real
constraints AND fails fast at the request boundary (no DB round-trip
just to learn the password was 8000 characters long).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest


def _register(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "email": "a@b.co",
        "password": "Hunter2x",
        "full_name": "Person",
    }
    base.update(overrides)
    return base


# ── RegisterRequest: full strength check ───────────────────────────────


def test_register_accepts_min_length_password_with_letter_and_digit() -> None:
    RegisterRequest.model_validate(_register(password="Aa345678"))


def test_register_rejects_too_short_password() -> None:
    with pytest.raises(ValidationError) as excinfo:
        RegisterRequest.model_validate(_register(password="A1abc"))
    # Pydantic's String length check fires before our custom validator.
    # Either message is fine; just make sure the user gets feedback.
    assert "8" in str(excinfo.value)


def test_register_rejects_password_with_no_letter() -> None:
    with pytest.raises(ValidationError, match="letter"):
        RegisterRequest.model_validate(_register(password="12345678"))


def test_register_rejects_password_with_no_digit() -> None:
    with pytest.raises(ValidationError, match="digit"):
        RegisterRequest.model_validate(_register(password="abcdefgh"))


def test_register_rejects_password_over_72_bytes() -> None:
    # 74 ASCII chars = 74 UTF-8 bytes. Pydantic's `max_length=72` fires
    # first on the ASCII path with a length-mismatch message rather
    # than our custom "72 bytes" wording; that's fine — either gate
    # rejects, which is what the user needs.
    pw = ("a" * 70) + "1A" + "b" * 2  # 74 chars/bytes
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(_register(password=pw))


def test_register_rejects_password_over_72_bytes_via_multibyte_chars() -> None:
    """50 characters that each encode to 2 UTF-8 bytes = 100 bytes — well
    over the 72-byte cap even though it's a "short" string in code points.
    Catches the gap the frontend's Zod `TextEncoder` check already
    enforces; the round-2 Pydantic validator brings the backend to
    parity."""
    pw = "é1" * 36  # 72 chars; each "é" is 2 bytes → 108 bytes total
    with pytest.raises(ValidationError, match="72 bytes"):
        RegisterRequest.model_validate(_register(password=pw))


# ── LoginRequest: byte-length guard only ───────────────────────────────


def test_login_accepts_short_password_for_legacy_accounts() -> None:
    """Login keeps a lenient `min_length=1` so users who registered
    before the strength rules tightened can still authenticate. The
    bcrypt-bytes check still fires so a 2000-byte input never reaches
    bcrypt."""
    LoginRequest.model_validate({"email": "a@b.co", "password": "short"})


def test_login_rejects_password_over_72_bytes() -> None:
    with pytest.raises(ValidationError, match="72 bytes"):
        LoginRequest.model_validate(
            {"email": "a@b.co", "password": "é1" * 36},
        )


def test_login_accepts_password_with_no_letter_or_digit() -> None:
    """A login attempt with a "weak" password (e.g., a stored legacy
    password that's all letters) must NOT be rejected at the schema
    layer — that would give an enumeration signal of "this account
    pre-dates the strength rules." The full strength check stays
    register-only."""
    LoginRequest.model_validate({"email": "a@b.co", "password": "abcdefgh"})
