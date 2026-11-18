# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Test the SELECT ... FOR UPDATE NOWAIT contention path on image regen.

Round 2 swapped the round-1 blocking lock for NOWAIT + 409 — a
contending POST `/content/:id/image` now returns
`IMAGE_GENERATION_IN_PROGRESS` immediately rather than queuing
behind ~10-20s of upstream API calls. This file mocks the
underlying DBAPI error so we don't need a live Postgres race.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import ConflictError
from app.services.image_service import ImageService


class _FakeLockError(Exception):
    """Mimics the asyncpg `LockNotAvailableError` shape. SQLAlchemy
    surfaces it through `DBAPIError.orig` with a `sqlstate` attribute."""

    sqlstate = "55P03"
    pgcode = "55P03"


@pytest.mark.asyncio
async def test_lock_contention_raises_image_generation_in_progress(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """When the repo's SELECT FOR UPDATE NOWAIT loses the race, the
    service must translate Postgres SQLSTATE 55P03 into a 409
    `IMAGE_GENERATION_IN_PROGRESS` instead of letting the raw DBAPI
    error propagate."""
    # Bare-minimum service wiring — we only exercise the lock branch,
    # so providers can be no-op AsyncMocks.
    session = AsyncMock()
    llm = AsyncMock()
    image = AsyncMock()
    storage = AsyncMock()
    service = ImageService(
        session,
        llm_provider=llm,
        image_provider=image,
        storage=storage,
    )

    async def _raise_lock_error(*_a: Any, **_k: Any) -> Any:
        # Construct a DBAPIError carrying our fake SQLSTATE-bearing
        # exception so the service's `_is_lock_not_available` helper
        # finds it on the wrapper's `.orig` attribute.
        raise DBAPIError("SELECT", {}, _FakeLockError())

    monkeypatch.setattr(service._content_repo, "get_for_user", _raise_lock_error)

    user = type("U", (), {"id": uuid.uuid4()})()
    with pytest.raises(ConflictError) as excinfo:
        await service.generate_for_content(
            user=user,
            content_id=uuid.uuid4(),
            style="photorealistic",
        )
    assert excinfo.value.code == "IMAGE_GENERATION_IN_PROGRESS"
    assert excinfo.value.status_code == 409
    # The lock-contention path must NOT have called the upstream LLM
    # — that's the whole point of failing fast at the lock layer.
    llm.generate.assert_not_awaited()
    image.generate.assert_not_awaited()
    storage.store.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_lock_dbapi_error_propagates(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Only SQLSTATE 55P03 is translated to 409. Other DB errors keep
    bubbling so they surface as 500 and the operator notices."""
    session = AsyncMock()
    service = ImageService(
        session,
        llm_provider=AsyncMock(),
        image_provider=AsyncMock(),
        storage=AsyncMock(),
    )

    class _OtherError(Exception):
        sqlstate = "08006"  # connection failure
        pgcode = "08006"

    async def _raise_other(*_a: Any, **_k: Any) -> Any:
        raise DBAPIError("SELECT", {}, _OtherError())

    monkeypatch.setattr(service._content_repo, "get_for_user", _raise_other)

    with pytest.raises(DBAPIError):
        await service.generate_for_content(
            user=type("U", (), {"id": uuid.uuid4()})(),
            content_id=uuid.uuid4(),
            style="photorealistic",
        )
