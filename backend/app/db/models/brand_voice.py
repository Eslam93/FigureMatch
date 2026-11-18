# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Brand voice profile.

A user-owned style preset that is injected into generation prompts via the
brand-voice block (§7.7 of the design). Soft-deletable so users can recover
recent deletions; repository queries filter `deleted_at IS NULL` by default.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampedMixin

if TYPE_CHECKING:
    from app.db.models.content_piece import ContentPiece
    from app.db.models.user import User


class BrandVoice(SoftDeleteMixin, TimestampedMixin, Base):
    __tablename__ = "brand_voices"
    __table_args__ = (Index("ix_brand_voices_user_id", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSONB arrays of strings — Pydantic schema layer enforces shape.
    tone_descriptors: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    banned_words: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    sample_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user: Mapped[User] = relationship(back_populates="brand_voices")
    content_pieces: Mapped[list[ContentPiece]] = relationship(
        back_populates="brand_voice",
    )
