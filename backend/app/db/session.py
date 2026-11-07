"""Async SQLAlchemy engine, session factory, and FastAPI dependency.

The engine and sessionmaker are lazy singletons — created on first use so
that test environments can override settings before either is materialized.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first call.

    Pool sizing is bounded by RDS `db.t4g.micro`'s `max_connections ≈
    87`. With App Runner pinned to 3 instances by the autoscaling
    config in `infra/lib/compute-stack.ts`, `pool_size=10,
    max_overflow=10` → 20 max concurrent connections per instance, so
    a fully-scaled fleet uses up to 60. That leaves ~25 headroom for
    Alembic migration tasks, psql admin sessions, and the RDS
    Performance Insights collector.

    The image-regen NOWAIT lock (see `image_service` +
    `ContentRepository.get_for_user`) makes the LOSING request release
    its connection immediately, but the WINNER still holds the row
    lock — and therefore the DB connection — across the LLM-prompt
    call, image-provider call, and storage upload. Sizing assumes a
    handful of concurrent image generations per instance, not dozens.
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency.

    Yields one `AsyncSession` per request. Commits on clean exit, rolls back
    on exception. The session is closed by the async context manager either way.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def end_read_transaction(session: AsyncSession) -> None:
    """Commit `session`'s open transaction, returning its connection to the pool.

    Call it right before a slow external call such as a model request. The
    request's reads (the current user, a brand voice) autobegin a
    transaction, and left open it sits idle in transaction on a pooled
    connection for the whole call; about 20 concurrent generations would
    exhaust the pool. It commits whatever the transaction holds, so use it
    only where that is nothing, or is safe to commit early. Loaded objects
    stay usable (`expire_on_commit=False`), and the next query begins a new
    transaction for `get_db_session` to commit.
    """
    await session.commit()


async def check_db_health() -> bool:
    """Cheap reachability probe — `SELECT 1`. Returns False on any failure."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        log.warning("db_health_check_failed", error=str(exc))
        return False
    return True


async def close_db_engine() -> None:
    """Dispose the engine. Call on app shutdown to release pool connections."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
