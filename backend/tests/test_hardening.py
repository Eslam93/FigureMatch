"""Hardening tests added in P1.5.1 (and extended in P1.5.2).

Coverage map for the specific failure modes flagged in external review:
  - Login timing: unknown email must pay the same bcrypt cost as wrong password.
  - X-Forwarded-For: junk header values must not crash the request (INET cast).
  - JWT secret: only strong formats (hex>=64 or base64 decoding to >=32 bytes)
    accepted outside the `local` environment.
  - Password length: >72 UTF-8 bytes rejected at registration AND at login
    (bcrypt silently truncates beyond 72 bytes).
  - Middleware order: CORS preflight short-circuits before other middleware
    allocates work (verified via response headers).
  - request_id propagation: echoed on the success path. The unhandled-500
    path is covered in `test_unhandled_errors.py`.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient

from app.core.config import Environment, Settings
from app.core.security import (
    PasswordTooWeakError,
    validate_password_strength,
)

if TYPE_CHECKING:
    from pytest import MonkeyPatch


# ── password length ────────────────────────────────────────────────────


def test_password_just_at_72_bytes_accepted() -> None:
    # 72 ASCII chars = 72 bytes; should be accepted (with a digit included).
    pw = ("a" * 70) + "1A"
    assert len(pw.encode("utf-8")) == 72
    validate_password_strength(pw)


def test_password_over_72_bytes_rejected() -> None:
    pw = ("a" * 71) + "1A"  # 73 bytes
    with pytest.raises(PasswordTooWeakError, match="bytes"):
        validate_password_strength(pw)


def test_password_72_chars_of_multibyte_rejected() -> None:
    # 72 emoji chars = ~288 bytes — must be rejected even though Pydantic's
    # `max_length` would pass at the character level.
    pw = "🔥" * 70 + "1A"
    assert len(pw) <= 72  # char count is fine
    assert len(pw.encode("utf-8")) > 72  # but byte count is not
    with pytest.raises(PasswordTooWeakError, match="bytes"):
        validate_password_strength(pw)


# ── JWT secret strength ────────────────────────────────────────────────


# 64 hex chars (valid `openssl rand -hex 32` output) — used as the default
# strong secret so individual tests can override JWT_SECRET to exercise the
# rejection paths without first having to supply a passing baseline.
_STRONG_HEX_SECRET = "3f9a17ce4d2b48a1c0e7f63bda5912f48e6c0a9d7b2e54f1c8a3d6094e7b1c2f"


def _build_settings(monkeypatch: MonkeyPatch, **overrides: str) -> Settings:
    """Construct a Settings instance from explicit env overrides."""
    base = {
        "ENVIRONMENT": "production",
        "JWT_SECRET": _STRONG_HEX_SECRET,
        "AI_PROVIDER_MODE": "openai",
        "OPENAI_API_KEY": "sk-proj-fake-but-not-placeholder-value-for-test",
        # Real cross-origin URL so the non-local cors-origin validator
        # (which rejects localhost in non-local envs) doesn't fire on
        # the implicit default before the test's actual assertion.
        "CORS_ORIGINS": "https://test-frontend.example.com",
    }
    base.update(overrides)
    for k, v in base.items():
        monkeypatch.setenv(k, v)
    return Settings()


def test_repeating_pattern_jwt_secret_rejected(monkeypatch: MonkeyPatch) -> None:
    """Same-prefix-repeated values decode to highly repetitive bytes — even
    if technically 32+ bytes, the entropy check catches them. `"abcdef" * 10`
    base64-decodes with Shannon entropy ~3.17 bits/byte, well below 4.5."""
    with pytest.raises(ValueError, match=r"Shannon entropy|strong secret format"):
        _build_settings(monkeypatch, JWT_SECRET="abcdef" * 10)  # 60 chars


# Note: pangram passphrases like "the-quick-brown-fox-jumps-over-the-lazy-dog"
# actually base64-decode to high-entropy bytes (~4.88 bits/byte, comparable
# to genuinely random material) because the input uses many distinct chars.
# Mechanical Shannon-entropy checks cannot distinguish a well-distributed
# passphrase from real random output at the 32-byte sample scale; the gate
# catches obvious low-entropy inputs only. The defense against memorable-
# but-public passphrases is the user choosing a real RNG source — the error
# message points them at `openssl rand -hex 32` / `secrets.token_urlsafe(32)`.


def test_all_zero_hex_jwt_secret_rejected(monkeypatch: MonkeyPatch) -> None:
    """64 hex zeros pass format + length but decode to 32 zero bytes
    (entropy = 0). Previously slipped through because the hex path
    skipped entropy entirely — same class of bug as the fox-phrase
    finding on the base64 side."""
    with pytest.raises(ValueError, match=r"low-entropy|trivial pattern"):
        _build_settings(monkeypatch, JWT_SECRET="0" * 64)


def test_alternating_hex_jwt_secret_rejected(monkeypatch: MonkeyPatch) -> None:
    """`"01" * 32` is 64 hex chars decoding to 32 bytes of 0x01 — same
    entropy = 0 problem as all-zeros. Catches the most obvious
    'looks-hex but is trivial' shape."""
    with pytest.raises(ValueError, match=r"low-entropy|trivial pattern"):
        _build_settings(monkeypatch, JWT_SECRET="01" * 32)


def test_short_jwt_secret_rejected(monkeypatch: MonkeyPatch) -> None:
    """Genuinely short value — fails both length AND format gates."""
    with pytest.raises(ValueError, match="not a recognized strong secret format"):
        _build_settings(monkeypatch, JWT_SECRET="abc")


def test_weak_known_value_jwt_secret_rejected(monkeypatch: MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="not a recognized strong secret format"):
        _build_settings(monkeypatch, JWT_SECRET="secret")


def test_strong_hex_jwt_secret_accepted(monkeypatch: MonkeyPatch) -> None:
    settings = _build_settings(
        monkeypatch,
        # 64 hex chars from `openssl rand -hex 32`.
        JWT_SECRET="3f9a17ce4d2b48a1c0e7f63bda5912f48e6c0a9d7b2e54f1c8a3d6094e7b1c2f",
    )
    assert settings.environment == Environment.PROD


def test_strong_standard_base64_jwt_secret_accepted(monkeypatch: MonkeyPatch) -> None:
    """Real `openssl rand -base64 32` output — uses + / = chars rather
    than the URL-safe - _ alphabet. Same decoded bytes as the urlsafe
    case below, just standard-base64-encoded. This is the test that was
    previously passing a HEX value despite the name suggesting base64."""
    settings = _build_settings(
        monkeypatch,
        JWT_SECRET="P4Pp/oQu/xKgFXm7tdH8d+LnGRoT0HzEv3JFwUuq7Aw=",
    )
    assert settings.environment == Environment.PROD


def test_strong_urlsafe_base64_jwt_secret_accepted(monkeypatch: MonkeyPatch) -> None:
    # `secrets.token_urlsafe(32)` output — base64url, no padding, 32 bytes decoded.
    settings = _build_settings(
        monkeypatch,
        JWT_SECRET="P4Pp_oQu_xKgFXm7tdH8d-LnGRoT0HzEv3JFwUuq7Aw",
    )
    assert settings.environment == Environment.PROD


def test_placeholder_jwt_secret_rejected_in_dev_too(monkeypatch: MonkeyPatch) -> None:
    """`dev` is treated as protected (often a shared cloud env)."""
    with pytest.raises(ValueError, match="placeholder"):
        _build_settings(
            monkeypatch,
            ENVIRONMENT="dev",
            JWT_SECRET="REPLACE_ME_pretending_to_be_a_real_secret_value_x",
        )


def test_local_env_still_accepts_placeholders(monkeypatch: MonkeyPatch) -> None:
    """Local docker-compose stays permissive so onboarding is cheap."""
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("JWT_SECRET", "dev-only-REPLACE_ME_with_openssl_rand_hex_32")
    # Should not raise.
    Settings()


# ── provider-mode startup guards ───────────────────────────────────────


def test_mock_provider_rejected_in_production_by_default(monkeypatch: MonkeyPatch) -> None:
    """A production deploy with AI_PROVIDER_MODE=mock would silently
    serve canned marketing JSON to real users. Reject at startup unless
    ALLOW_MOCK_PROVIDER=true is explicitly set."""
    with pytest.raises(ValueError, match="AI_PROVIDER_MODE=mock is not allowed"):
        _build_settings(
            monkeypatch,
            AI_PROVIDER_MODE="mock",
            OPENAI_API_KEY="",  # mock doesn't need a key; clearing avoids confusion
        )


def test_mock_provider_allowed_in_production_with_escape_hatch(
    monkeypatch: MonkeyPatch,
) -> None:
    """The ALLOW_MOCK_PROVIDER escape hatch keeps the demo-on-staging
    flow alive without leaving the door open by default."""
    settings = _build_settings(
        monkeypatch,
        AI_PROVIDER_MODE="mock",
        ALLOW_MOCK_PROVIDER="true",
        OPENAI_API_KEY="",
    )
    assert settings.ai_provider_mode.value == "mock"


def test_bedrock_provider_rejected_at_startup(monkeypatch: MonkeyPatch) -> None:
    """The factory is lazy — without this guard, a misconfigured
    AI_PROVIDER_MODE=bedrock deploy stays healthy at startup and only
    explodes at first generation request. Fail at startup instead."""
    with pytest.raises(ValueError, match="bedrock is documented but not implemented"):
        _build_settings(monkeypatch, AI_PROVIDER_MODE="bedrock")


def test_local_env_allows_mock_without_escape_hatch(monkeypatch: MonkeyPatch) -> None:
    """The whole point of mock-mode is `local` — no escape hatch needed there."""
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("AI_PROVIDER_MODE", "mock")
    Settings()  # should not raise


# ── request_id propagation on success paths ───────────────────────────


async def test_request_id_echoed_on_success_path(client: AsyncClient) -> None:
    """Pure-ASGI RequestID middleware binds the id once at request start;
    the response always carries it back, whether or not the contextvar
    is visible to nested exception handlers."""
    incoming = "44444444-5555-6666-7777-888888888888"
    response = await client.get(
        "/api/v1/health",
        headers={"X-Request-ID": incoming},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == incoming


async def test_request_id_oversized_is_replaced_with_uuid(client: AsyncClient) -> None:
    """A 1000-char incoming X-Request-ID would inflate logs and storage.
    Cap it; on invalid input the middleware mints a fresh UUID."""
    long_id = "a" * 1000
    response = await client.get(
        "/api/v1/health",
        headers={"X-Request-ID": long_id},
    )
    echoed = response.headers.get("X-Request-ID")
    assert echoed is not None
    assert echoed != long_id
    # Default replacement is a UUID4 — 36 chars with dashes.
    assert len(echoed) == 36


async def test_request_id_control_chars_replaced_with_uuid(client: AsyncClient) -> None:
    """Newlines / control chars in X-Request-ID enable log injection
    (a forged 'second log line' from the attacker's perspective).
    Reject and mint a fresh id."""
    response = await client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "valid\n[INJECTED] fake-log-line"},
    )
    echoed = response.headers.get("X-Request-ID")
    assert echoed is not None
    assert "\n" not in echoed
    assert "INJECTED" not in echoed


async def test_request_id_validator_accepts_typical_shapes() -> None:
    """The validator must accept what honest clients actually send:
    UUIDs, ULIDs, generic alphanumeric ids."""
    from app.middleware.request_id import _is_valid_incoming

    assert _is_valid_incoming("44444444-5555-6666-7777-888888888888")  # UUID
    assert _is_valid_incoming("01F7Z9KH8XY3ABCDEF1234567890")  # ULID-like
    assert _is_valid_incoming("trace-abc.123_xyz")  # generic
    assert not _is_valid_incoming("")  # empty
    assert not _is_valid_incoming("has space")  # space rejected
    assert not _is_valid_incoming("has\nnewline")  # control char
    assert not _is_valid_incoming("a" * 200)  # too long


# ── CORS middleware ordering (outermost short-circuits preflights) ─────


async def test_cors_preflight_short_circuits_with_204(client: AsyncClient) -> None:
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Starlette's CORSMiddleware returns 200 OK for preflight; either
    # 2xx variant is acceptable. The key point is the CORS headers are
    # present and we never hit the route.
    assert 200 <= response.status_code < 300
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"


# ── XFF parsing (unit-test the helper) ─────────────────────────────────


def test_valid_ip_accepts_ipv4() -> None:
    from app.api.v1.routers.auth import _valid_ip

    assert _valid_ip("203.0.113.42") == "203.0.113.42"


def test_valid_ip_accepts_ipv6() -> None:
    from app.api.v1.routers.auth import _valid_ip

    assert _valid_ip("2001:db8::1") == "2001:db8::1"


def test_valid_ip_rejects_junk() -> None:
    from app.api.v1.routers.auth import _valid_ip

    assert _valid_ip("not-an-ip") is None
    assert _valid_ip("'; DROP TABLE users; --") is None
    assert _valid_ip("") is None
    assert _valid_ip(None) is None


def test_valid_ip_rejects_scoped_ipv6() -> None:
    """Python's `ipaddress` parses `fe80::1%eth0` since 3.9, but the
    scope id reflects the caller's interface — useless for audit and
    incompatible with some Postgres INET versions. Reject explicitly."""
    from app.api.v1.routers.auth import _valid_ip

    assert _valid_ip("fe80::1%eth0") is None
    assert _valid_ip("fe80::1%0") is None
    # Unscoped IPv6 link-local is still acceptable.
    assert _valid_ip("fe80::1") == "fe80::1"


# ── Login timing parity (smoke — exact parity is impossible, but we ───
#     check the unknown-email path is in the same ballpark as wrong-pw) ─


# ── verify_password rejects >72 bytes on login (parity with register) ──


def test_verify_password_rejects_over_72_byte_input() -> None:
    """bcrypt silently truncates inputs >72 bytes. If we accepted them here,
    a user whose registered password is exactly 72 bytes could authenticate
    with that password + any trailing garbage. verify_password must reject
    such inputs even though the hash check would have "passed"."""
    from app.core.security import hash_password, verify_password

    base_pw = ("a" * 70) + "1A"  # 72 bytes
    hashed = hash_password(base_pw)

    # Correct password -> True (sanity)
    assert verify_password(base_pw, hashed) is True

    # Base + trailing junk would be silently truncated by bcrypt to the
    # same 72 bytes -> would otherwise "match". We reject explicitly.
    truncation_attempt = base_pw + "trailing-garbage-bcrypt-would-ignore"
    assert verify_password(truncation_attempt, hashed) is False


# ── service-level regression: login MUST call verify_password even when ─
#     the email is unknown. Direct unit test of auth_service so a future ─
#     refactor that reintroduces `if user is None: raise` is caught. ─────


class _FakeResult:
    def scalar_one_or_none(self) -> None:
        return None  # always misses — that's the test scenario


class _FakeAsyncSession:
    """Minimal AsyncSession stub for non-DB unit tests of service logic."""

    async def execute(self, _stmt: object) -> _FakeResult:
        return _FakeResult()

    async def flush(self) -> None:  # pragma: no cover - never called here
        return None

    async def commit(self) -> None:  # pragma: no cover
        return None

    async def rollback(self) -> None:  # pragma: no cover
        return None


async def test_login_runs_verify_password_even_when_user_missing(
    monkeypatch: MonkeyPatch,
) -> None:
    """If someone reverts auth_service.login to short-circuit on
    `user is None`, this test fails. The whole point of the dummy-hash
    pattern is that verify_password runs in both branches.
    """
    from app.core.exceptions import UnauthorizedError
    from app.services import auth_service as svc_mod

    calls: list[tuple[str, str]] = []

    def spy(password: str, hashed: str) -> bool:
        calls.append((password, hashed))
        return False  # never authenticates — we just need to know it ran

    monkeypatch.setattr(svc_mod, "verify_password", spy)

    service = svc_mod.AuthService(_FakeAsyncSession())  # type: ignore[arg-type]
    with pytest.raises(UnauthorizedError) as exc_info:
        await service.login(email="nobody@example.com", password="Secret123")

    assert exc_info.value.code == "INVALID_CREDENTIALS"
    assert len(calls) == 1, "verify_password must run exactly once on the missing-user path"
    submitted_password, hashed_arg = calls[0]
    assert submitted_password == "Secret123"
    # The dummy hash must be a real bcrypt hash, not None / placeholder.
    assert hashed_arg.startswith("$2b$"), (
        "login must pass a real bcrypt dummy hash to verify_password on the "
        "unknown-user path — anything else means the timing fix is gone"
    )


# ── Login timing parity (smoke — exact parity is impossible, but we ───
#     check the unknown-email path is in the same ballpark as wrong-pw) ─


def test_login_timing_parity_smoke(monkeypatch: MonkeyPatch) -> None:
    """Both unknown-email and wrong-password branches call verify_password
    against a real bcrypt hash. The cheap branches differ by at most one
    bcrypt verify, which the dummy-hash fix equalizes."""
    from app.core.security import (
        get_dummy_password_hash,
        hash_password,
        verify_password,
    )

    real_hash = hash_password("RealSecret123")
    dummy_hash = get_dummy_password_hash()

    t0 = time.perf_counter()
    verify_password("WrongAttempt1", real_hash)
    wrong_password_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    verify_password("WrongAttempt1", dummy_hash)
    unknown_email_ms = (time.perf_counter() - t0) * 1000

    # Both should be in the same order of magnitude — bcrypt cost 12 is
    # ~250ms; allow generous slack for noisy CI.
    assert wrong_password_ms > 10  # bcrypt actually ran
    assert unknown_email_ms > 10
    ratio = max(wrong_password_ms, unknown_email_ms) / min(wrong_password_ms, unknown_email_ms)
    assert ratio < 3.0, (
        f"timing imbalance — wrong_pw={wrong_password_ms:.1f}ms, "
        f"unknown_email={unknown_email_ms:.1f}ms, ratio={ratio:.2f}"
    )
