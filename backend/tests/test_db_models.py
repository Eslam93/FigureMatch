"""Structural tests for the ORM models.

Verifies columns, FK targets, enum membership, and the indexes we depend on.
End-to-end CRUD tests live alongside the services that exercise each model.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, Numeric

from app.db import Base
from app.db.enums import (
    ContentType,
    ImageProvider,
    ImprovementGoal,
    ResultParseStatus,
    UsageEventType,
)
from app.db.models import (
    BrandVoice,
    ContentPiece,
    GeneratedImage,
    Improvement,
    RefreshToken,
    UsageEvent,
    User,
)


def test_all_tables_registered_on_metadata() -> None:
    expected = {
        "users",
        "refresh_tokens",
        "brand_voices",
        "content_pieces",
        "generated_images",
        "improvements",
        "usage_events",
    }
    actual = set(Base.metadata.tables.keys())
    assert expected.issubset(actual), f"missing: {expected - actual}"


def test_user_table_shape() -> None:
    cols = User.__table__.columns
    assert {
        "id",
        "email",
        "password_hash",
        "full_name",
        "email_verified_at",
        "last_login_at",
        "created_at",
        "updated_at",
    }.issubset(cols.keys())
    assert cols["email"].unique is True
    assert cols["email"].nullable is False
    # `deleted_at` MUST NOT exist on users — avoids email-reuse collision.
    assert "deleted_at" not in cols


def test_refresh_token_fk_and_unique_hash() -> None:
    cols = RefreshToken.__table__.columns
    user_fk = next(iter(cols["user_id"].foreign_keys))
    assert user_fk.column.table.name == "users"
    assert user_fk.ondelete == "CASCADE"
    assert cols["token_hash"].unique is True
    assert cols["token_hash"].type.length == 64  # sha256 hex digest


def test_brand_voice_has_soft_delete_and_fk() -> None:
    cols = BrandVoice.__table__.columns
    assert "deleted_at" in cols
    user_fk = next(iter(cols["user_id"].foreign_keys))
    assert user_fk.column.table.name == "users"
    assert user_fk.ondelete == "CASCADE"


def test_content_piece_shape() -> None:
    cols = ContentPiece.__table__.columns
    assert {
        "user_id",
        "content_type",
        "topic",
        "brand_voice_id",
        "prompt_version",
        "system_prompt_snapshot",
        "user_prompt_snapshot",
        "result",
        "rendered_text",
        "result_parse_status",
        "model_id",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "deleted_at",
    }.issubset(cols.keys())
    assert cols["rendered_text"].nullable is False
    assert cols["result"].nullable is True  # FAILED parse → null result
    assert cols["brand_voice_id"].nullable is True
    bv_fk = next(iter(cols["brand_voice_id"].foreign_keys))
    assert bv_fk.column.table.name == "brand_voices"
    assert bv_fk.ondelete == "SET NULL"
    assert isinstance(cols["cost_usd"].type, Numeric)
    assert isinstance(cols["input_tokens"].type, Integer)


def test_content_piece_indexes() -> None:
    index_names = {i.name for i in ContentPiece.__table__.indexes}
    assert "ix_content_pieces_user_id_created_at" in index_names
    assert "ix_content_pieces_user_id_content_type" in index_names
    assert "ix_content_pieces_user_id_active" in index_names
    # GIN full-text expression index — declared on the model so autogenerate
    # sees parity with the live DB.
    assert "ix_content_pieces_rendered_text_fts" in index_names
    fts = next(
        i for i in ContentPiece.__table__.indexes if i.name == "ix_content_pieces_rendered_text_fts"
    )
    assert fts.dialect_kwargs.get("postgresql_using") == "gin"


def test_generated_image_shape() -> None:
    cols = GeneratedImage.__table__.columns
    assert {
        "content_piece_id",
        "image_prompt",
        "provider",
        "model_id",
        "width",
        "height",
        "s3_key",
        "cdn_url",
        "cost_usd",
        "is_current",
    }.issubset(cols.keys())
    cp_fk = next(iter(cols["content_piece_id"].foreign_keys))
    assert cp_fk.column.table.name == "content_pieces"
    assert cp_fk.ondelete == "CASCADE"
    assert isinstance(cols["is_current"].type, Boolean)
    # `seed` is nullable for gpt-image-2.5-flare which doesn't expose one.
    assert cols["seed"].nullable is True


def test_generated_image_has_partial_unique_current_index() -> None:
    index_names = {i.name for i in GeneratedImage.__table__.indexes}
    assert "ix_generated_images_current_per_piece" in index_names


def test_improvement_shape() -> None:
    cols = Improvement.__table__.columns
    assert {
        "original_text",
        "improved_text",
        "goal",
        "new_audience",
        "explanation",
        "changes_summary",
        "deleted_at",
    }.issubset(cols.keys())
    assert cols["new_audience"].nullable is True


def test_usage_event_metadata_aliased() -> None:
    # SQLAlchemy reserves `metadata` on Base; column is mapped to `meta`
    # but stored as `metadata` in Postgres.
    cols = UsageEvent.__table__.columns
    assert "metadata" in cols
    assert "meta" not in cols


def test_enum_values_match_brief_contract() -> None:
    assert {e.value for e in ContentType} == {
        "blog_post",
        "linkedin_post",
        "ad_copy",
        "email",
    }
    assert {e.value for e in ResultParseStatus} == {"ok", "retried", "failed"}
    assert {e.value for e in ImageProvider} == {"openai", "nova_canvas"}
    assert {e.value for e in ImprovementGoal} == {
        "shorter",
        "persuasive",
        "formal",
        "seo",
        "audience_rewrite",
    }
    assert {e.value for e in UsageEventType} == {
        "text_gen",
        "image_gen",
        "improve",
        "image_regen",
        "export",
    }
