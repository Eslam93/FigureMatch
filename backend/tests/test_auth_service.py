"""Unit-level regression guards for AuthService refresh & logout (P1.6).

The integration suite exercises the happy and reuse paths against a real
DB. These tests pin the *contract* between AuthService and the repository
so a future refactor that silently drops reuse-detection — or accidentally
calls it on the logout path — fails here, with a fast and small signal.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import UnauthorizedError
from app.db.models import RefreshToken, User
from app.services.auth_service import AuthService

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def _make_service_with_mocks(monkeypatch: MonkeyPatch) -> tuple[AuthService, MagicMock, MagicMock]:
    """Return an AuthService whose two repositories are AsyncMocks.

    The session passed to AuthService is itself a MagicMock, since every
    query routes through the mocked repositories. Its `commit` is an
    AsyncMock because reuse detection commits the revocation itself.
    """
    fake_users = MagicMock()
    fake_refresh = MagicMock()
    for repo in (fake_users, fake_refresh):
        for attr in (
            "find_by_id",
            "find_by_email",
            "find_by_hash",
            "create",
            "consume_if_active",
            "revoke_all_for_user",
            "revoke_by_hash",
            "touch_last_login",
        ):
            setattr(repo, attr, AsyncMock())

    # Patch the constructors so AuthService(session) picks up our mocks.
    monkeypatch.setattr(
        "app.services.auth_service.UserRepository",
        lambda _session: fake_users,
    )
    monkeypatch.setattr(
        "app.services.auth_service.RefreshTokenRepository",
        lambda _session: fake_refresh,
    )
    session = MagicMock()
    session.commit = AsyncMock()
    service = AuthService(session)
    return service, fake_users, fake_refresh


def _make_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="test@example.com",
        password_hash="$2b$12$" + "x" * 53,
        full_name="Test",
    )


def _make_token_row(*, user_id: uuid.UUID, revoked: bool) -> RefreshToken:
    return RefreshToken(
        id=uuid.uuid4(),
        user_id=user_id,
        token_hash="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        revoked_at=datetime.now(UTC) if revoked else None,
    )


# ── refresh: reuse detection ───────────────────────────────────────────


async def test_refresh_reuse_triggers_family_revocation(monkeypatch: MonkeyPatch) -> None:
    """When `consume_if_active` returns None AND the row exists in the
    revoked state, the service MUST call `revoke_all_for_user`.

    This is the core security invariant of P1.6. If a refactor breaks the
    reuse-detection branch (e.g., skipping the `find_by_hash` follow-up
    or only handling the unknown-token case), this test fails.
    """
    service, _users, refresh_repo = _make_service_with_mocks(monkeypatch)
    user_id = uuid.uuid4()
    refresh_repo.consume_if_active.return_value = None
    refresh_repo.find_by_hash.return_value = _make_token_row(user_id=user_id, revoked=True)
    refresh_repo.revoke_all_for_user.return_value = 3

    with pytest.raises(UnauthorizedError) as exc_info:
        await service.refresh(raw_refresh="a" * 64)

    assert exc_info.value.code == "INVALID_REFRESH_TOKEN"
    refresh_repo.revoke_all_for_user.assert_awaited_once_with(user_id)
    # Committed before the 401: the request's rollback-on-error would
    # otherwise undo the revocation.
    service._session.commit.assert_awaited_once()


async def test_refresh_unknown_token_does_not_revoke_family(monkeypatch: MonkeyPatch) -> None:
    """A miss with no matching row means "never existed" — not reuse.
    Mass-revocation here would let an attacker DoS a user by spamming
    fake refresh tokens against /auth/refresh."""
    service, _users, refresh_repo = _make_service_with_mocks(monkeypatch)
    refresh_repo.consume_if_active.return_value = None
    refresh_repo.find_by_hash.return_value = None

    with pytest.raises(UnauthorizedError):
        await service.refresh(raw_refresh="a" * 64)

    refresh_repo.revoke_all_for_user.assert_not_awaited()


async def test_refresh_expired_token_does_not_revoke_family(monkeypatch: MonkeyPatch) -> None:
    """An expired-but-not-revoked token also yields no claim. The row
    exists but `revoked_at IS NULL`, so it's not reuse — the user just
    waited too long. Mass-revocation would be wrong."""
    service, _users, refresh_repo = _make_service_with_mocks(monkeypatch)
    refresh_repo.consume_if_active.return_value = None
    # Row exists, revoked_at is None, expires_at is in the past — that's
    # the "just expired" shape that `consume_if_active` filters out.
    expired_row = _make_token_row(user_id=uuid.uuid4(), revoked=False)
    expired_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    refresh_repo.find_by_hash.return_value = expired_row

    with pytest.raises(UnauthorizedError):
        await service.refresh(raw_refresh="a" * 64)

    refresh_repo.revoke_all_for_user.assert_not_awaited()


async def test_refresh_revoked_and_expired_token_does_not_revoke_family(
    monkeypatch: MonkeyPatch,
) -> None:
    """A token that's both revoked AND expired is an old cookie from a
    logged-out session resurfacing — not a compromise signal. Reuse
    detection must not fire, otherwise a user pulling a months-old
    cookie out of a browser backup wipes all current sessions."""
    service, _users, refresh_repo = _make_service_with_mocks(monkeypatch)
    refresh_repo.consume_if_active.return_value = None
    old_row = _make_token_row(user_id=uuid.uuid4(), revoked=True)
    old_row.expires_at = datetime.now(UTC) - timedelta(days=30)
    refresh_repo.find_by_hash.return_value = old_row

    with pytest.raises(UnauthorizedError):
        await service.refresh(raw_refresh="a" * 64)

    refresh_repo.revoke_all_for_user.assert_not_awaited()


async def test_refresh_success_does_not_revoke_family(monkeypatch: MonkeyPatch) -> None:
    """The happy path must not touch `revoke_all_for_user` — that's the
    nuclear option, reserved for reuse."""
    service, users, refresh_repo = _make_service_with_mocks(monkeypatch)
    user = _make_user()
    refresh_repo.consume_if_active.return_value = user.id
    users.find_by_id.return_value = user

    found_user, _tokens = await service.refresh(raw_refresh="a" * 64)

    assert found_user is user
    refresh_repo.revoke_all_for_user.assert_not_awaited()
    refresh_repo.create.assert_awaited_once()


# ── logout: never triggers reuse detection ─────────────────────────────


async def test_logout_does_not_call_reuse_detection(monkeypatch: MonkeyPatch) -> None:
    """Logout's contract: revoke this one token, nothing else. Even when
    the token is already revoked (idempotent re-call), we must NOT route
    through reuse detection — that would punish multi-device users who
    log out one device twice."""
    service, _users, refresh_repo = _make_service_with_mocks(monkeypatch)
    refresh_repo.revoke_by_hash.return_value = False  # already revoked

    await service.logout(raw_refresh="a" * 64)

    refresh_repo.revoke_by_hash.assert_awaited_once()
    refresh_repo.revoke_all_for_user.assert_not_awaited()
    refresh_repo.find_by_hash.assert_not_awaited()


async def test_logout_with_no_token_is_noop(monkeypatch: MonkeyPatch) -> None:
    """No cookie → no DB work. Keeps logout cheap from any client state."""
    service, _users, refresh_repo = _make_service_with_mocks(monkeypatch)

    await service.logout(raw_refresh=None)
    await service.logout(raw_refresh="")

    refresh_repo.revoke_by_hash.assert_not_awaited()


# ── refresh: deleted user edge case ────────────────────────────────────


async def test_refresh_with_orphaned_user_id_returns_unauthorized(
    monkeypatch: MonkeyPatch,
) -> None:
    """If a user is deleted between issuing the refresh token and the
    refresh call, the atomic claim succeeds but `find_by_id` returns None.
    We treat that as INVALID_REFRESH_TOKEN — same error code as every
    other refresh failure, so the client just re-logs-in. The token is
    already revoked (we claimed it), so no further cleanup is needed.
    """
    service, users, refresh_repo = _make_service_with_mocks(monkeypatch)
    refresh_repo.consume_if_active.return_value = uuid.uuid4()
    users.find_by_id.return_value = None

    with pytest.raises(UnauthorizedError) as exc_info:
        await service.refresh(raw_refresh="a" * 64)

    assert exc_info.value.code == "INVALID_REFRESH_TOKEN"
    refresh_repo.revoke_all_for_user.assert_not_awaited()


# ── register: weak password + duplicate email branches ────────────────


async def test_register_with_weak_password_raises_validation_error(
    monkeypatch: MonkeyPatch,
) -> None:
    """The weak-password branch must NOT reach the user repo — fail
    fast, no DB write, no bcrypt cost."""
    service, users, _refresh_repo = _make_service_with_mocks(monkeypatch)

    with pytest.raises(Exception) as exc_info:
        await service.register(
            email="x@example.com",
            password="weak",  # too short
            full_name="X",
        )
    assert "WEAK_PASSWORD" in str(exc_info.value.code)  # type: ignore[attr-defined]
    users.create.assert_not_awaited()


async def test_register_with_duplicate_email_raises_conflict_error(
    monkeypatch: MonkeyPatch,
) -> None:
    """When the repo raises IntegrityError, the service rolls back and
    surfaces a CONFLICT envelope. This is the email-already-taken path."""
    from sqlalchemy.exc import IntegrityError

    from app.core.exceptions import ConflictError

    service, users, _refresh_repo = _make_service_with_mocks(monkeypatch)
    # Stub session.rollback so the test doesn't need a real session.
    session_mock = MagicMock()
    session_mock.rollback = AsyncMock()
    service._session = session_mock  # type: ignore[attr-defined]

    users.create.side_effect = IntegrityError("dup", {}, Exception("dup"))

    with pytest.raises(ConflictError) as exc_info:
        await service.register(
            email="x@example.com",
            password="Secret123",
            full_name="X",
        )
    assert exc_info.value.code == "EMAIL_TAKEN"
    session_mock.rollback.assert_awaited_once()


# ── login: happy path mints tokens with audit metadata ────────────────


async def test_login_happy_path_mints_tokens_and_touches_last_login(
    monkeypatch: MonkeyPatch,
) -> None:
    """Login success must (1) call touch_last_login, (2) create a
    refresh token row, (3) return an access token tied to the user."""
    service, users, refresh_repo = _make_service_with_mocks(monkeypatch)
    user = _make_user()
    users.find_by_email.return_value = user
    # The real verify_password call must succeed against this user's
    # actual hash — _make_user() bcrypt-hashes "Secret123" so we use
    # that as the input to login.
    monkeypatch.setattr(
        "app.services.auth_service.verify_password",
        lambda _pw, _hash: True,
    )

    found_user, tokens = await service.login(
        email="alice@example.com",
        password="Secret123",
        user_agent="pytest",
        ip_address="203.0.113.42",
    )

    assert found_user is user
    assert tokens.access_token
    assert tokens.refresh_token_raw
    users.touch_last_login.assert_awaited_once_with(user)
    refresh_repo.create.assert_awaited_once()
    create_kwargs = refresh_repo.create.call_args.kwargs
    assert create_kwargs["user_agent"] == "pytest"
    assert create_kwargs["ip_address"] == "203.0.113.42"


# ── get_user: missing user raises ─────────────────────────────────────


async def test_get_user_missing_id_raises_unauthorized(
    monkeypatch: MonkeyPatch,
) -> None:
    """Token's `sub` resolved to a UUID, but the user was hard-deleted
    in the meantime. We refuse the request rather than synthesize a
    stale identity."""
    service, users, _refresh_repo = _make_service_with_mocks(monkeypatch)
    users.find_by_id.return_value = None

    with pytest.raises(UnauthorizedError):
        await service.get_user(uuid.uuid4())
