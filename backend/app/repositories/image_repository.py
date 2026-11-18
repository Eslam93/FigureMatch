# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Data access for `generated_images`.

Same shape as `ContentRepository`: thin async wrapper around the ORM,
no business logic. The image service handles the multi-step
generate → upload → record-current dance; this file just talks to
SQLAlchemy.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GeneratedImage


class ImageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, image: GeneratedImage) -> GeneratedImage:
        """Insert + flush so the caller gets `id`/`created_at` before
        commit. The caller owns the commit."""
        self._session.add(image)
        await self._session.flush()
        await self._session.refresh(image)
        return image

    async def mark_others_not_current(self, content_piece_id: uuid.UUID) -> None:
        """Flip every existing `is_current=true` row for the piece to
        false. Pair with inserting a new `is_current=true` row in the
        same transaction — the partial unique index
        (`ix_generated_images_current_per_piece`) keeps the invariant
        of at most one current image per piece."""
        stmt = (
            update(GeneratedImage)
            .where(
                GeneratedImage.content_piece_id == content_piece_id,
                GeneratedImage.is_current.is_(True),
            )
            .values(is_current=False)
        )
        await self._session.execute(stmt)

    async def list_for_content(
        self,
        content_piece_id: uuid.UUID,
    ) -> list[GeneratedImage]:
        """Every image ever generated for the piece, newest first.

        Includes superseded ones — the dashboard uses this to render
        the thumbnail strip of previous versions next to the current.
        """
        stmt = (
            select(GeneratedImage)
            .where(GeneratedImage.content_piece_id == content_piece_id)
            .order_by(text("created_at DESC"))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_current_for_content(
        self,
        content_piece_id: uuid.UUID,
    ) -> GeneratedImage | None:
        stmt = select(GeneratedImage).where(
            GeneratedImage.content_piece_id == content_piece_id,
            GeneratedImage.is_current.is_(True),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
