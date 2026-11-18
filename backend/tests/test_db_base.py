# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Smoke tests for the ORM base + mixins.

Verifies the public surface — real schema tests arrive with the models in P1.3.
"""

from __future__ import annotations

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db import Base, SoftDeleteMixin, TimestampedMixin


def test_base_is_declarative() -> None:
    assert hasattr(Base, "metadata")
    assert hasattr(Base, "registry")


def test_timestamped_mixin_attaches_id_and_timestamp_columns() -> None:
    class _TS(TimestampedMixin, Base):
        __tablename__ = "_ts_probe"

    cols = _TS.__table__.columns
    assert {"id", "created_at", "updated_at"}.issubset(cols.keys())

    # id is a UUID primary key.
    id_col = cols["id"]
    assert id_col.primary_key is True
    assert isinstance(id_col.type, PG_UUID)

    # created_at / updated_at are TIMESTAMP WITH TIME ZONE.
    for name in ("created_at", "updated_at"):
        col = cols[name]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True
        assert col.nullable is False


def test_soft_delete_mixin_attaches_nullable_deleted_at() -> None:
    class _SD(SoftDeleteMixin, TimestampedMixin, Base):
        __tablename__ = "_sd_probe"

    cols = _SD.__table__.columns
    assert "deleted_at" in cols
    assert cols["deleted_at"].nullable is True
    assert isinstance(cols["deleted_at"].type, DateTime)
    assert cols["deleted_at"].type.timezone is True
