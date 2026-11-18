# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Content piece — a single generated output.

Stores both the structured result (`result` jsonb) and a server-rendered plain
representation (`rendered_text`). The renderer runs at write time so dashboard
preview, full-text search, copy-to-clipboard, and export all consume the same
canonical text. `result_parse_status` captures the JSON-parse fallback outcome.

Indexes (per §5):
  - (user_id, created_at DESC) — paginated dashboard.
  - (user_id, content_type)    — type filter.
  - (user_id) WHERE deleted_at IS NULL — active counts / "still mine, still live".
  - GIN to_tsvector('english', rendered_text) — added in the P1.4 migration.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampedMixin
from app.db.enums import ContentType, ResultParseStatus

if TYPE_CHECKING:
    from app.db.models.brand_voice import BrandVoice
    from app.db.models.generated_image import GeneratedImage
    from app.db.models.user import User


class ContentPiece(SoftDeleteMixin, TimestampedMixin, Base):
    __tablename__ = "content_pieces"
    __table_args__ = (
        Index(
            "ix_content_pieces_user_id_created_at",
            "user_id",
            text("created_at DESC"),
        ),
        Index("ix_content_pieces_user_id_content_type", "user_id", "content_type"),
        Index(
            "ix_content_pieces_user_id_active",
            "user_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # GIN full-text expression index — drives `?q=` dashboard search.
        Index(
            "ix_content_pieces_rendered_text_fts",
            text("to_tsvector('english', rendered_text)"),
            postgresql_using="gin",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_type: Mapped[ContentType] = mapped_column(
        SAEnum(ContentType, name="content_type", values_callable=lambda e: [v.value for v in e]),
        nullable=False,
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(500), nullable=True)

    brand_voice_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("brand_voices.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Prompt snapshot — frozen at generation time for reproducibility.
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    system_prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False)

    # The structured LLM output (None when result_parse_status == FAILED).
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Server-rendered plain/markdown — non-null so search/preview always work,
    # even in the FAILED case where it holds the raw model output.
    rendered_text: Mapped[str] = mapped_column(Text, nullable=False)
    result_parse_status: Mapped[ResultParseStatus] = mapped_column(
        SAEnum(
            ResultParseStatus,
            name="result_parse_status",
            values_callable=lambda e: [v.value for v in e],
        ),
        nullable=False,
        default=ResultParseStatus.OK,
    )
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Usage: the model, tokens and cost of the calls that produced this piece.
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    user: Mapped[User] = relationship(back_populates="content_pieces")
    brand_voice: Mapped[BrandVoice | None] = relationship(back_populates="content_pieces")
    images: Mapped[list[GeneratedImage]] = relationship(
        back_populates="content_piece",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
