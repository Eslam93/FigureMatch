# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Data access for `content_pieces`.

Thin async repository — no business logic, no validation. The service
layer owns parse-fallback orchestration and the user-scoping rules; this
file just shuttles rows between the ORM and the caller.

Slice 4 adds the dashboard queries: paginated list with optional
content-type filter and full-text search, plus soft-delete and restore
(24-hour window). Active rows are the default — `get_for_user`
intentionally excludes soft-deleted records.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ContentType
from app.db.models import ContentPiece

RESTORE_WINDOW = timedelta(hours=24)


class ContentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, piece: ContentPiece) -> ContentPiece:
        """Insert + flush so the caller gets `id`, `created_at`, and any
        server-side defaults before commit. The caller owns the commit.
        """
        self._session.add(piece)
        await self._session.flush()
        await self._session.refresh(piece)
        return piece

    async def get_for_user(
        self,
        content_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> ContentPiece | None:
        """Look up a content piece scoped to its owner. Soft-deleted rows
        are excluded — restoring lives on its own endpoint and reads will
        resurface them then.

        `for_update=True` takes a row-level lock with `NOWAIT`. Used
        by the image-regen pipeline to detect "a regeneration is
        already in flight for this piece" — without it, two parallel
        POSTs would both fire the upstream image call (~$0.04 each
        at medium quality) before the partial unique index rejected
        the loser, AND each waiter would pin a DB connection for
        ~10-20s while the winner ran external API calls.

        With NOWAIT, a contending request fails immediately with
        Postgres error 55P03 (`lock_not_available`); the service
        catches that and surfaces it as a 409
        `IMAGE_GENERATION_IN_PROGRESS` so the user sees a friendly
        "already running" message and the connection is released at
        once. A proper job-table dedupe lands in Phase 11.
        """
        stmt = select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.user_id == user_id,
            ContentPiece.deleted_at.is_(None),
        )
        if for_update:
            stmt = stmt.with_for_update(nowait=True)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_user_include_deleted(
        self,
        content_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ContentPiece | None:
        """Same lookup as `get_for_user` but includes soft-deleted rows.

        Used by the restore endpoint to see the deleted record before
        flipping `deleted_at` back to NULL.
        """
        stmt = select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        content_type: ContentType | None = None,
        q: str | None = None,
        page: int,
        page_size: int,
    ) -> tuple[list[ContentPiece], int]:
        """Paginated list of the caller's active (non-deleted) content.

        Sorted newest-first. `q` runs against the GIN full-text index on
        `rendered_text` (see migration `0001_baseline.py` — index
        `ix_content_pieces_rendered_text_fts`). Returns `(rows, total)`
        where total is the count after filters but before pagination.
        """
        base_filters = [
            ContentPiece.user_id == user_id,
            ContentPiece.deleted_at.is_(None),
        ]
        if content_type is not None:
            base_filters.append(ContentPiece.content_type == content_type)
        if q is not None and q.strip():
            # `plainto_tsquery` is forgiving of free-form input — strips
            # operators and quotes that would otherwise raise on raw
            # `to_tsquery`. Matches the GIN index expression so the
            # planner picks the index, not a sequential scan.
            ts_query = func.plainto_tsquery("english", q.strip())
            base_filters.append(
                func.to_tsvector("english", ContentPiece.rendered_text).op("@@")(ts_query),
            )

        count_stmt = select(func.count()).select_from(ContentPiece).where(*base_filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())

        offset = max(0, (page - 1) * page_size)
        list_stmt = (
            select(ContentPiece)
            # `id DESC` tiebreaker keeps ordering deterministic when
            # multiple rows share a `created_at` value (rapid inserts
            # in tests, or any same-microsecond write under real load).
            # Without it, Postgres returns ties in physical-disk order
            # — usually insert order — so a `LIMIT` clause can cut the
            # newest rows and return the oldest instead.
            .where(*base_filters)
            .order_by(ContentPiece.created_at.desc(), ContentPiece.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = list((await self._session.execute(list_stmt)).scalars().all())
        return rows, total

    async def soft_delete(
        self,
        content_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ContentPiece | None:
        """Set `deleted_at = now()` if the row is active and owned.

        Returns the soft-deleted record (with `deleted_at` populated)
        so the caller can hand it to the frontend's undo affordance.
        Returns None if the row doesn't exist, isn't owned, or was
        already soft-deleted.
        """
        piece = await self.get_for_user(content_id, user_id)
        if piece is None:
            return None
        piece.deleted_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(piece)
        return piece

    async def restore(
        self,
        content_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ContentPiece | None:
        """Clear `deleted_at` if the row is owned, deleted, and still
        inside the 24-hour restore window.

        Returns the restored record on success, or None when the row
        doesn't exist, isn't owned, isn't deleted, or fell outside the
        window. The router translates None into a 404/410-style error
        depending on the underlying cause it cares to surface.
        """
        piece = await self.get_for_user_include_deleted(content_id, user_id)
        if piece is None or piece.deleted_at is None:
            return None
        if datetime.now(UTC) - piece.deleted_at > RESTORE_WINDOW:
            return None
        # Re-issue via UPDATE so we don't fight `onupdate=now()` for
        # `updated_at`. Refresh picks up the new state.
        stmt = (
            update(ContentPiece)
            .where(ContentPiece.id == content_id, ContentPiece.user_id == user_id)
            .values(deleted_at=None)
        )
        await self._session.execute(stmt)
        await self._session.refresh(piece)
        return piece
