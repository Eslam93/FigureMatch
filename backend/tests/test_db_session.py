"""Tests for the async DB engine/session singletons.

Real query tests live alongside the models that introduce schema (P1.3+).
Here we cover the lazy-init + dispose plumbing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import get_settings
from app.db import session as session_mod

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.fixture(autouse=True)
def _reset_db_singletons() -> None:
    """Wipe the module-level engine/sessionmaker before and after each test
    so tests are order-independent.

    Each test also caches `get_settings()` with a DATABASE_URL that points
    nowhere. Monkeypatch restores the env var but not that cache, so the
    teardown clears it too; otherwise a later integration engine would use
    the dead URL and, with REQUIRE_DB=1, fail the whole integration suite."""
    session_mod._engine = None
    session_mod._sessionmaker = None
    yield
    session_mod._engine = None
    session_mod._sessionmaker = None
    get_settings.cache_clear()


def test_get_engine_returns_async_engine(monkeypatch: MonkeyPatch) -> None:
    # Force a URL that won't try to actually connect at construction time.
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@nowhere.invalid:5432/app")
    engine = session_mod.get_engine()
    assert isinstance(engine, AsyncEngine)
    # Subsequent calls return the same instance.
    assert session_mod.get_engine() is engine


def test_get_sessionmaker_returns_async_sessionmaker(monkeypatch: MonkeyPatch) -> None:
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@nowhere.invalid:5432/app")
    factory = session_mod.get_sessionmaker()
    assert isinstance(factory, async_sessionmaker)
    assert session_mod.get_sessionmaker() is factory


async def test_check_db_health_returns_false_on_unreachable_host(
    monkeypatch: MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    get_settings.cache_clear()
    # Point at an unresolvable host. The probe must catch the exception and
    # return False rather than propagating.
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app:app@unreachable.invalid.example:5432/app",
    )
    result = await session_mod.check_db_health()
    assert result is False


async def test_close_db_engine_resets_singletons(monkeypatch: MonkeyPatch) -> None:
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@nowhere.invalid:5432/app")
    _ = session_mod.get_engine()
    _ = session_mod.get_sessionmaker()
    assert session_mod._engine is not None
    assert session_mod._sessionmaker is not None
    await session_mod.close_db_engine()
    assert session_mod._engine is None
    assert session_mod._sessionmaker is None
