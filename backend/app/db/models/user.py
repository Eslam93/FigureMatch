# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""User account.

Email uses Postgres `citext` so uniqueness is case-insensitive without forcing
the rest of the system to lowercase at every boundary. Passwords are stored
as bcrypt hashes only — the plain value never touches the database.

Users are NOT soft-deleted; if a user is removed the cascade wipes their
content along with them (the brief intentionally omits soft-delete on this
table to avoid email-reuse collisions against soft-deleted rows).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampedMixin

if TYPE_CHECKING:
    from app.db.models.brand_voice import BrandVoice
    from app.db.models.content_piece import ContentPiece
    from app.db.models.improvement import Improvement
    from app.db.models.refresh_token import RefreshToken


class User(TimestampedMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        CITEXT(),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships — strings are forward refs, resolved via the declarative registry.
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    brand_voices: Mapped[list[BrandVoice]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    content_pieces: Mapped[list[ContentPiece]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    improvements: Mapped[list[Improvement]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
