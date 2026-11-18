# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Per-user activity record.

Inline usage on content_pieces / improvements is the canonical source in the
MVP. This table arrives properly in Phase 9; the model exists from P1.3 so
the schema is settled and the migration baseline doesn't churn later.
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampedMixin
from app.db.enums import UsageEventType

if TYPE_CHECKING:
    from app.db.models.user import User


class UsageEvent(TimestampedMixin, Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        Index(
            "ix_usage_events_user_id_created_at",
            "user_id",
            text("created_at DESC"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[UsageEventType] = mapped_column(
        SAEnum(
            UsageEventType,
            name="usage_event_type",
            values_callable=lambda e: [v.value for v in e],
        ),
        nullable=False,
    )
    # UUID pointer to a content_piece / generated_image / improvement / etc.
    # Not a hard FK because the referenced table varies per event_type.
    reference_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata",  # column name; `metadata` is reserved on Base so we alias.
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    user: Mapped[User] = relationship(back_populates="usage_events")
