# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Improvement record — original text + improved text + explanation.

Each row captures one /improve invocation. Soft-deletable so users can
restore from the dashboard. JSONB fields hold structured explanation and
changes-summary returned by the two-call improver chain.
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
from app.db.enums import ImprovementGoal

if TYPE_CHECKING:
    from app.db.models.user import User


class Improvement(SoftDeleteMixin, TimestampedMixin, Base):
    __tablename__ = "improvements"
    __table_args__ = (
        Index(
            "ix_improvements_user_id_created_at",
            "user_id",
            text("created_at DESC"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    improved_text: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[ImprovementGoal] = mapped_column(
        SAEnum(
            ImprovementGoal,
            name="improvement_goal",
            values_callable=lambda e: [v.value for v in e],
        ),
        nullable=False,
    )
    new_audience: Mapped[str | None] = mapped_column(String(500), nullable=True)

    explanation: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    changes_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    original_word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    improved_word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    user: Mapped[User] = relationship(back_populates="improvements")
