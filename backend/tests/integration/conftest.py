"""Integration-test fixtures: live Postgres + per-test transactional rollback.

Pattern (well-documented in the SQLAlchemy 2.0 async docs):
  1. Open a connection.
  2. Begin a transaction on that connection.
  3. Bind sessions to that connection with
     `join_transaction_mode="create_savepoint"`, so every session.commit()
     becomes a SAVEPOINT RELEASE rather than a real commit, and every
     session.rollback() a ROLLBACK TO SAVEPOINT.
  4. On teardown, roll back the outer transaction — every row a test
     created is undone.

Requests made through `integration_client` run the real `get_db_session`
dependency: each request gets its own session that commits on success
and rolls back on error, as in production. `db_session` is a separate
session on the same connection, for test setup and assertions.

Tests that need a live DB import `integration_client` and `db_session`.
The session-scoped engine fixture skips the entire integration suite if
the configured DATABASE_URL is unreachable, unless `REQUIRE_DB=1` (set in
CI), in which case it fails the suite instead.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.main import app

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(scope="session")
async def integration_engine() -> AsyncIterator[AsyncEngine]:
    """Session-scoped engine. Skips integration tests if the DB is unreachable,
    or fails them when `REQUIRE_DB=1` so a missing database can't pass CI."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(
                f"integration DB unreachable and REQUIRE_DB=1: {type(exc).__name__}: {exc}",
                pytrace=False,
            )
        pytest.skip(f"integration DB unreachable: {exc}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_connection(
    integration_engine: AsyncEngine,
) -> AsyncIterator[AsyncConnection]:
    """A connection with an open outer transaction that rolls back on teardown."""
    async with integration_engine.connect() as conn:
        trans = await conn.begin()
        try:
            yield conn
        finally:
            await trans.rollback()


@pytest_asyncio.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    """Per-test session that nests inside the rollback'd transaction."""
    sessionmaker = async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    async with sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
async def integration_client(
    db_connection: AsyncConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """ASGI client whose requests run the real `get_db_session`.

    Only the sessionmaker behind it is swapped, for one bound to the test
    connection. Each request still commits on success and rolls back on
    error, but those only release or roll back a savepoint; the outer
    transaction discards everything at teardown. Don't go back to
    overriding `get_db_session` with a bare `yield`: that skips both, and
    it once let a rollback that undid reuse revocation pass the suite.

    The rate-limit bucket store is module-level state shared across tests
    — without an explicit reset, each test inherits the budget consumed
    by all previous tests on the same path+IP, and the 11th register call
    in a 60s window gets a real 429. Reset before each test so every test
    starts with a fresh budget. Production code never resets at request
    boundaries; only the test seam needs it.
    """
    from app.middleware.rate_limit import reset_rate_limit_state

    reset_rate_limit_state()

    # Same session options as `app.db.session.get_sessionmaker()`, bound to
    # the test connection instead of the engine.
    request_sessions = async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr("app.db.session.get_sessionmaker", lambda: request_sessions)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        yield ac
