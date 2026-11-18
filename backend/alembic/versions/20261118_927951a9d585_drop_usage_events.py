# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""drop usage_events

Revision ID: 927951a9d585
Revises: 68c9768f3798
Create Date: 2026-11-18

The baseline created `usage_events` for a usage page that was never built.
Nothing ever wrote to it or read from it: tokens and cost are recorded on
each content piece, improvement and image. Its model is removed, so the
table and its enum type go too. Downgrade recreates both exactly as the
baseline did, empty.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "927951a9d585"
down_revision: str | Sequence[str] | None = "68c9768f3798"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_usage_events_user_id_created_at", table_name="usage_events")
    op.drop_table("usage_events")
    op.execute("DROP TYPE IF EXISTS usage_event_type")


def downgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "text_gen",
                "image_gen",
                "improve",
                "image_regen",
                "export",
                name="usage_event_type",
            ),
            nullable=False,
        ),
        sa.Column("reference_id", sa.UUID(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=10, scale=6),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_usage_events_user_id_created_at",
        "usage_events",
        ["user_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
