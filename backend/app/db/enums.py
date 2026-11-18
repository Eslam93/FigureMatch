# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Enumerated types used in the database schema.

Each `StrEnum` corresponds to a Postgres `CREATE TYPE ... AS ENUM` produced by
Alembic. Values are stable (used in migrations and external API contracts) —
add new variants at the end of each enum; never re-order or rename.
"""

from __future__ import annotations

from enum import StrEnum


class ContentType(StrEnum):
    """The four content types the generator supports."""

    BLOG_POST = "blog_post"
    LINKEDIN_POST = "linkedin_post"
    AD_COPY = "ad_copy"
    EMAIL = "email"


class ResultParseStatus(StrEnum):
    """Outcome of the three-stage JSON-parse fallback for a generation."""

    OK = "ok"  # parsed on the first attempt
    RETRIED = "retried"  # parsed on the corrective second attempt
    FAILED = "failed"  # never produced valid JSON; raw output stored in rendered_text


class ImageProvider(StrEnum):
    """Which image-generation backend produced a given image."""

    OPENAI = "openai"  # GPT Image models, and the mock provider
    # In the database's `image_provider` type since the baseline migration.
    # Nothing produces it: the Bedrock stub it was for has been removed.
    NOVA_CANVAS = "nova_canvas"


class ImprovementGoal(StrEnum):
    """Goal selected for an /improve invocation."""

    SHORTER = "shorter"
    PERSUASIVE = "persuasive"
    FORMAL = "formal"
    SEO = "seo"
    AUDIENCE_REWRITE = "audience_rewrite"
