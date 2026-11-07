"""Integration tests for /auth/register, /auth/login, /auth/refresh, /auth/logout, /auth/me.

Each test runs inside a transaction that rolls back on teardown, so the
database stays clean and tests are order-independent.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_refresh_token, hash_refresh_token
from app.db.models import RefreshToken
from tests.factories import create_refresh_token_in_db, create_user_in_db


async def test_register_creates_user_and_issues_tokens(
    integration_client: AsyncClient,
) -> None:
    response = await integration_client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "Secret123",
            "full_name": "Alice Example",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["full_name"] == "Alice Example"
    assert "id" in body["user"]
    assert body["access_token"]
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] > 0
    # Refresh token rides in a cookie, not the body.
    assert "refresh_token" not in body
    assert response.cookies.get("refresh_token")


async def test_register_rejects_duplicate_email(
    integration_client: AsyncClient,
) -> None:
    body = {
        "email": "dup@example.com",
        "password": "Secret123",
        "full_name": "First",
    }
    first = await integration_client.post("/api/v1/auth/register", json=body)
    assert first.status_code == 201

    body2 = {**body, "password": "Another456", "full_name": "Second"}
    second = await integration_client.post("/api/v1/auth/register", json=body2)
    assert second.status_code == 409
    payload = second.json()
    assert payload["error"]["code"] == "EMAIL_TAKEN"
    assert payload["error"]["details"]["field"] == "email"


async def test_register_rejects_weak_password(
    integration_client: AsyncClient,
) -> None:
    response = await integration_client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "12345678",  # passes Pydantic min_length, fails our checks
            "full_name": "Weak",
        },
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "WEAK_PASSWORD"


async def test_login_with_correct_credentials_succeeds(
    integration_client: AsyncClient,
) -> None:
    await integration_client.post(
        "/api/v1/auth/register",
        json={
            "email": "bob@example.com",
            "password": "Secret123",
            "full_name": "Bob",
        },
    )
    response = await integration_client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "Secret123"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["email"] == "bob@example.com"
    assert body["access_token"]
    assert response.cookies.get("refresh_token")


async def test_login_with_wrong_password_returns_401(
    integration_client: AsyncClient,
) -> None:
    await integration_client.post(
        "/api/v1/auth/register",
        json={
            "email": "carol@example.com",
            "password": "Secret123",
            "full_name": "Carol",
        },
    )
    response = await integration_client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "WrongPassword1"},
    )
    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_with_unknown_email_returns_same_401(
    integration_client: AsyncClient,
) -> None:
    """Unknown email must produce the same error as wrong password — never
    leak which one to the caller."""
    response = await integration_client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "Secret123"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_me_with_valid_token_returns_user(
    integration_client: AsyncClient,
) -> None:
    reg = await integration_client.post(
        "/api/v1/auth/register",
        json={
            "email": "dave@example.com",
            "password": "Secret123",
            "full_name": "Dave",
        },
    )
    token = reg.json()["access_token"]
    response = await integration_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "dave@example.com"


async def test_me_without_token_returns_401(
    integration_client: AsyncClient,
) -> None:
    response = await integration_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MISSING_TOKEN"


async def test_me_with_invalid_token_returns_401(
    integration_client: AsyncClient,
) -> None:
    response = await integration_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


# ── /auth/refresh ──────────────────────────────────────────────────────


async def _register_and_get_refresh(
    client: AsyncClient,
    *,
    email: str,
    password: str = "Secret123",
    full_name: str = "Test User",
) -> str:
    """Register a user and return the raw refresh-cookie value."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert response.status_code == 201, response.text
    cookie = response.cookies.get("refresh_token")
    assert cookie is not None
    return cookie


async def test_refresh_with_valid_cookie_returns_new_pair(
    integration_client: AsyncClient,
) -> None:
    original = await _register_and_get_refresh(integration_client, email="eve@example.com")

    response = await integration_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": original},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["email"] == "eve@example.com"
    assert body["access_token"]
    new_cookie = response.cookies.get("refresh_token")
    assert new_cookie is not None
    assert new_cookie != original  # rotated


async def test_refresh_without_cookie_returns_401(
    integration_client: AsyncClient,
) -> None:
    response = await integration_client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MISSING_REFRESH_TOKEN"


async def test_refresh_with_unknown_token_returns_401(
    integration_client: AsyncClient,
) -> None:
    response = await integration_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": "deadbeef" * 8},  # 64 hex chars, never issued
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


async def test_refresh_old_token_after_rotation_returns_401(
    integration_client: AsyncClient,
) -> None:
    """Single-use rotation: presenting the now-revoked original after a
    successful refresh must fail. This is the core invariant of P1.6."""
    original = await _register_and_get_refresh(integration_client, email="frank@example.com")

    first = await integration_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": original},
    )
    assert first.status_code == 200

    replay = await integration_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": original},
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


async def test_refresh_reuse_revokes_entire_family(
    integration_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Reuse detection: after a token has been spent, presenting it again
    revokes ALL active refresh tokens for that user. The new token issued
    by the legitimate rotation also stops working."""
    original = await _register_and_get_refresh(integration_client, email="grace@example.com")

    first = await integration_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": original},
    )
    assert first.status_code == 200
    rotated = first.cookies.get("refresh_token")
    assert rotated is not None

    # Replay the spent original — should fire reuse detection.
    replay = await integration_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": original},
    )
    assert replay.status_code == 401

    # The legitimate rotated token must now also be revoked.
    followup = await integration_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": rotated},
    )
    assert followup.status_code == 401
    assert followup.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"

    # Every refresh_token row for this user should be revoked.
    rows = (
        (await db_session.execute(select(RefreshToken).where(RefreshToken.revoked_at.is_(None))))
        .scalars()
        .all()
    )
    assert rows == []


async def test_refresh_reuse_revocation_survives_the_401(
    integration_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """The family revocation must be durable even though the replay gets a 401.

    `get_db_session` rolls back on any exception, so the revocation only
    survives because `AuthService` commits it before raising. The client
    runs that same commit/rollback, so dropping the commit fails here.
    """
    register = await integration_client.post(
        "/api/v1/auth/register",
        json={"email": "reuse@example.com", "password": "Secret123", "full_name": "Reuse"},
    )
    assert register.status_code == 201, register.text
    user_id = uuid.UUID(register.json()["user"]["id"])
    original = register.cookies.get("refresh_token")
    assert original is not None

    rotation = await integration_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": original},
    )
    assert rotation.status_code == 200, rotation.text

    # Drop the rotated cookie the client stored, so only the replayed one is sent.
    integration_client.cookies.clear()
    replay = await integration_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": original},
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"

    # Select columns rather than entities so the values come from the
    # database, never from the test session's identity map.
    tokens = (
        await db_session.execute(
            select(RefreshToken.id, RefreshToken.revoked_at).where(RefreshToken.user_id == user_id)
        )
    ).all()
    assert len(tokens) == 2  # the original and the one the rotation minted
    assert all(token.revoked_at is not None for token in tokens)


async def test_refresh_with_expired_token_returns_401(
    integration_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """An expired refresh token must not refresh, even before it's revoked.

    Uses the factory directly to mint a pre-expired token in one call —
    cleaner than registering via the endpoint and then mutating the row.
    """
    user = await create_user_in_db(db_session, email="harry@example.com")
    _row, raw = await create_refresh_token_in_db(
        db_session,
        user=user,
        expires_in_seconds=-1,
    )

    response = await integration_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": raw},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


# ── /auth/logout ───────────────────────────────────────────────────────


async def test_logout_revokes_token_and_clears_cookie(
    integration_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    raw = await _register_and_get_refresh(integration_client, email="ivan@example.com")

    response = await integration_client.post(
        "/api/v1/auth/logout",
        cookies={"refresh_token": raw},
    )
    assert response.status_code == 204

    # Cookie deletion is signaled by an empty-value Max-Age=0 Set-Cookie.
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "Max-Age=0" in set_cookie or "expires=Thu, 01 Jan 1970" in set_cookie.lower()

    # The row in the DB is now revoked.
    token_hash = hash_refresh_token(raw)
    row = (
        await db_session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    ).scalar_one()
    assert row.revoked_at is not None

    # Using the same token to refresh now fails (rotation rejects revoked).
    replay = await integration_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": raw},
    )
    assert replay.status_code == 401


async def test_logout_without_cookie_returns_204(
    integration_client: AsyncClient,
) -> None:
    """Logout from no-auth state must succeed silently — clients shouldn't
    need to know their cookie state before calling logout."""
    response = await integration_client.post("/api/v1/auth/logout")
    assert response.status_code == 204


async def test_logout_is_idempotent(
    integration_client: AsyncClient,
) -> None:
    raw = await _register_and_get_refresh(integration_client, email="judy@example.com")

    first = await integration_client.post(
        "/api/v1/auth/logout",
        cookies={"refresh_token": raw},
    )
    assert first.status_code == 204

    second = await integration_client.post(
        "/api/v1/auth/logout",
        cookies={"refresh_token": raw},
    )
    assert second.status_code == 204


async def test_logout_does_not_trigger_reuse_detection(
    integration_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Logging out with an already-revoked token must NOT mass-revoke the
    user's other sessions — only `/auth/refresh` is the reuse-detection
    surface. A user can have multiple sessions (laptop + phone); logging
    out the laptop must not kick the phone."""
    raw_a = await _register_and_get_refresh(integration_client, email="kate@example.com")
    # Issue a second session via login.
    login = await integration_client.post(
        "/api/v1/auth/login",
        json={"email": "kate@example.com", "password": "Secret123"},
    )
    assert login.status_code == 200
    raw_b = login.cookies.get("refresh_token")
    assert raw_b is not None

    # Logout session A, then logout session A again with the now-revoked token.
    await integration_client.post(
        "/api/v1/auth/logout",
        cookies={"refresh_token": raw_a},
    )
    await integration_client.post(
        "/api/v1/auth/logout",
        cookies={"refresh_token": raw_a},
    )

    # Session B must still be usable.
    refresh = await integration_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": raw_b},
    )
    assert refresh.status_code == 200, refresh.text


# ── concurrency: the atomic claim primitive under real parallel sessions ───
#
# Every other integration test in this file runs inside one outer
# transaction that rolls back on teardown (a request's commit only
# releases a savepoint) — fast and isolated, but unable to model separate
# transactions racing. The atomic UPDATE in
# `RefreshTokenRepository.consume_if_active` is exactly the place where
# the single-transaction model is misleading: it relies on row-level locking
# across SEPARATE transactions. So this test deliberately bypasses the
# `integration_client` + `db_session` fixtures and goes straight to the
# engine, with explicit COMMITs and explicit cleanup. Slow by design;
# it's the only test where that cost buys real signal.


async def test_concurrent_refresh_only_one_session_wins(
    integration_engine: object,  # AsyncEngine — typed loosely so pytest finds it
) -> None:
    """Two parallel `consume_if_active` calls on the same hash: the
    atomic `UPDATE ... WHERE revoked_at IS NULL AND expires_at > now()
    RETURNING user_id` must let exactly ONE caller claim the row.

    Under Postgres `READ COMMITTED` (the default isolation level), the
    second updater blocks on the row-level lock the first acquired,
    then re-reads the row post-commit and sees its predicate is no
    longer satisfied — so 0 rows match, RETURNING is empty, and the
    second caller gets None. That's the linearization the primitive
    is supposed to give us.
    """
    import asyncio
    import uuid as _uuid
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from app.repositories.refresh_token_repository import RefreshTokenRepository

    engine: AsyncEngine = integration_engine  # type: ignore[assignment]
    _raw_token, hashed_token = generate_refresh_token()

    # Setup: create a user + a single active refresh token, committed
    # so both concurrent sessions can see it. `expire_on_commit=False`
    # because we re-read attributes post-commit; the default would
    # trigger a greenlet-bridged reload that fails outside the session.
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        user = await create_user_in_db(setup, email=f"race-{_uuid.uuid4().hex[:8]}@example.test")
        target = RefreshToken(
            user_id=user.id,
            token_hash=hashed_token,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        setup.add(target)
        await setup.commit()
        user_id = user.id

    try:
        # Two independent sessions race for the same hash.
        async def claim() -> _uuid.UUID | None:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                repo = RefreshTokenRepository(session)
                claimed = await repo.consume_if_active(hashed_token)
                await session.commit()
                return claimed

        results = await asyncio.gather(claim(), claim())
        winners = [r for r in results if r is not None]
        losers = [r for r in results if r is None]
        assert len(winners) == 1, f"expected exactly one winner, got {results}"
        assert len(losers) == 1, f"expected exactly one loser, got {results}"
        assert winners[0] == user_id

        # The target row is now revoked. A third sequential attempt to
        # claim it must also miss — re-running the same hash never
        # succeeds twice.
        third = await claim()
        assert third is None
    finally:
        async with AsyncSession(engine, expire_on_commit=False) as cleanup:
            from app.db.models import User as UserModel

            await cleanup.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
            await cleanup.execute(delete(UserModel).where(UserModel.id == user_id))
            await cleanup.commit()
