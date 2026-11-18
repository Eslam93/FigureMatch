# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Data access for `improvements`.

Thin async repository. Same shape pattern as `ContentRepository` —
service-layer code owns the multi-call orchestration; this file just
shuttles rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Improvement


class ImprovementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, improvement: Improvement) -> Improvement:
        """Insert + flush so the caller gets `id`/`created_at` before
        commit. The caller owns the commit."""
        self._session.add(improvement)
        await self._session.flush()
        await self._session.refresh(improvement)
        return improvement

    async def get_for_user(
        self,
        improvement_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Improvement | None:
        """Scoped lookup. Soft-deleted rows are excluded."""
        stmt = select(Improvement).where(
            Improvement.id == improvement_id,
            Improvement.user_id == user_id,
            Improvement.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
    ) -> list[Improvement]:
        """Every active improvement, newest first.

        Slice 5 doesn't paginate this — the average user creates a
        handful per session. If volume grows the list gets pagination
        identical to /content.
        """
        stmt = (
            select(Improvement)
            .where(
                Improvement.user_id == user_id,
                Improvement.deleted_at.is_(None),
            )
            # `id DESC` tiebreaker — see content_repository.list_for_user
            # for the rationale. Same-microsecond `created_at` ties
            # would otherwise be ordered by physical disk position.
            .order_by(Improvement.created_at.desc(), Improvement.id.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete(
        self,
        improvement_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Improvement | None:
        """Set `deleted_at = now()` if the row is active and owned.
        Returns the soft-deleted record (with `deleted_at` populated)
        or None if there's nothing to delete."""
        improvement = await self.get_for_user(improvement_id, user_id)
        if improvement is None:
            return None
        improvement.deleted_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(improvement)
        return improvement
