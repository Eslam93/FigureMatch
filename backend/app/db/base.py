# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Declarative base and common ORM mixins.

Every aggregate root extends `Base` and typically picks up `TimestampedMixin`
for `id`/`created_at`/`updated_at`. Tables that need soft delete add
`SoftDeleteMixin` on top.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Project-wide declarative base. All ORM models inherit from this."""


class TimestampedMixin:
    """Adds `id` (UUID v4), `created_at`, `updated_at` columns.

    Both timestamps default to `now()` server-side and `updated_at`
    advances on every row update via `onupdate`.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    """Adds a nullable `deleted_at` for soft-deleted rows.

    NULL = active. Repository-layer queries are expected to filter
    `deleted_at IS NULL` unless an explicit "include deleted" flag is set.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
