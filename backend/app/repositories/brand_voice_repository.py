# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Data access for `brand_voices`.

Thin async repository — same shape pattern as `ContentRepository` /
`ImprovementRepository`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BrandVoice


class BrandVoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        name: str,
        description: str | None,
        tone_descriptors: list[str],
        banned_words: list[str],
        sample_text: str | None,
        target_audience: str | None,
    ) -> BrandVoice:
        voice = BrandVoice(
            user_id=user_id,
            name=name,
            description=description,
            tone_descriptors=tone_descriptors,
            banned_words=banned_words,
            sample_text=sample_text,
            target_audience=target_audience,
        )
        self._session.add(voice)
        await self._session.flush()
        await self._session.refresh(voice)
        return voice

    async def get_for_user(
        self,
        voice_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> BrandVoice | None:
        stmt = select(BrandVoice).where(
            BrandVoice.id == voice_id,
            BrandVoice.user_id == user_id,
            BrandVoice.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[BrandVoice]:
        stmt = (
            select(BrandVoice)
            .where(
                BrandVoice.user_id == user_id,
                BrandVoice.deleted_at.is_(None),
            )
            .order_by(text("created_at DESC"))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        voice: BrandVoice,
        updates: dict[str, Any],
    ) -> BrandVoice:
        """Apply only the present keys; the caller decides what's set
        based on the PATCH body's `model_fields_set`."""
        for key, value in updates.items():
            setattr(voice, key, value)
        await self._session.flush()
        await self._session.refresh(voice)
        return voice

    async def soft_delete(
        self,
        voice_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> BrandVoice | None:
        voice = await self.get_for_user(voice_id, user_id)
        if voice is None:
            return None
        voice.deleted_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(voice)
        return voice
