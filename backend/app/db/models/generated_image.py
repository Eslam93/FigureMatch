"""AI-generated image bound to a content piece.

`is_current` marks the active image for a piece — at most one row per
content_piece has it set true. Regeneration creates a new row and flips
the previous current row to false in a single transaction.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampedMixin
from app.db.enums import ImageProvider

if TYPE_CHECKING:
    from app.db.models.content_piece import ContentPiece


class GeneratedImage(TimestampedMixin, Base):
    __tablename__ = "generated_images"
    __table_args__ = (
        Index(
            "ix_generated_images_content_piece_id_created_at",
            "content_piece_id",
            text("created_at DESC"),
        ),
        # Fast path for "current image for this content piece".
        Index(
            "ix_generated_images_current_per_piece",
            "content_piece_id",
            unique=True,
            postgresql_where=text("is_current IS TRUE"),
        ),
    )

    content_piece_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_pieces.id", ondelete="CASCADE"),
        nullable=False,
    )

    image_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    style: Mapped[str | None] = mapped_column(String(64), nullable=True)

    provider: Mapped[ImageProvider] = mapped_column(
        SAEnum(
            ImageProvider,
            name="image_provider",
            values_callable=lambda e: [v.value for v in e],
        ),
        nullable=False,
    )
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    # OpenAI's Images API does not expose a seed — column is nullable for that path.
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    cdn_url: Mapped[str] = mapped_column(String(1000), nullable=False)

    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    content_piece: Mapped[ContentPiece] = relationship(back_populates="images")
