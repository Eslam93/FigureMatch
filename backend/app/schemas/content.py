# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Pydantic request / response schemas for /content/* endpoints.

Slice 2 widens the response result to a union across all four content
types — blog post, LinkedIn post, email, ad copy. Each per-type model
forbids extras so a provider response with the right keys plus garbage
triggers the corrective-retry path rather than silently passing through.
The content service runs the LLM output through the right model
according to `request.content_type`; that registry lives in
`services/content_service.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.enums import ContentType, ResultParseStatus

# ── Request ────────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    """Body for POST /content/generate.

    `content_type` is open to every value in the enum from day one.
    Slice 1 rejected non-blog types in the router with 422; Slice 2 now
    accepts all four. Brand-voice injection arrives in Slice 6.
    """

    content_type: ContentType
    topic: Annotated[str, Field(min_length=3, max_length=500)]
    tone: Annotated[str | None, Field(default=None, max_length=120)] = None
    target_audience: Annotated[str | None, Field(default=None, max_length=500)] = None
    brand_voice_id: uuid.UUID | None = None


# ── Per-type result models ─────────────────────────────────────────────


class BlogPostSection(BaseModel):
    heading: Annotated[str, Field(min_length=1)]
    body: Annotated[str, Field(min_length=1)]


class BlogPostResult(BaseModel):
    """Structured shape the blog-post prompt asks the model to return.

    Mirrors §7.1 of PROJECT_BRIEF.md. `model_config` forbids extras so
    a model that returns the right keys plus garbage triggers the retry
    path rather than silently passing through.
    """

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=200)]
    meta_description: Annotated[str, Field(min_length=1, max_length=160)]
    intro: Annotated[str, Field(min_length=1)]
    sections: Annotated[list[BlogPostSection], Field(min_length=1)]
    conclusion: Annotated[str, Field(min_length=1)]
    suggested_tags: Annotated[list[str], Field(min_length=1, max_length=10)]


class LinkedInPostResult(BaseModel):
    """Structured shape the LinkedIn-post prompt returns.

    Mirrors §7.2 of PROJECT_BRIEF.md. Hashtags are stored without the
    leading `#` so the renderer is the single place that adds it.
    """

    model_config = ConfigDict(extra="forbid")

    hook: Annotated[str, Field(min_length=1, max_length=500)]
    body: Annotated[str, Field(min_length=1)]
    cta: Annotated[str, Field(min_length=1, max_length=500)]
    hashtags: Annotated[list[str], Field(min_length=1, max_length=10)]


class EmailResult(BaseModel):
    """Structured shape the email prompt returns.

    Mirrors §7.4 of PROJECT_BRIEF.md. The subject + preview pair is what
    inboxes show before open; the body is the read content.
    """

    model_config = ConfigDict(extra="forbid")

    subject: Annotated[str, Field(min_length=1, max_length=140)]
    preview_text: Annotated[str, Field(min_length=1, max_length=200)]
    greeting: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1)]
    cta_text: Annotated[str, Field(min_length=1, max_length=80)]
    sign_off: Annotated[str, Field(min_length=1, max_length=200)]


AdCopyFormat = Literal["short", "medium", "long"]
AdCopyAngle = Literal[
    "curiosity",
    "social_proof",
    "transformation",
    "urgency",
    "problem_solution",
]


class AdCopyVariant(BaseModel):
    """A single ad variant inside an `AdCopyResult.variants` list."""

    model_config = ConfigDict(extra="forbid")

    format: AdCopyFormat
    angle: AdCopyAngle
    headline: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1, max_length=1000)]
    cta: Annotated[str, Field(min_length=1, max_length=80)]


class AdCopyResult(BaseModel):
    """Structured shape the ad-copy prompt returns.

    Mirrors §7.3 of PROJECT_BRIEF.md. Three variants, one per format
    (short / medium / long). The service-layer corrective retry catches
    the case where the model returned two or four — `min_length` /
    `max_length` enforces the count, and the after-validator enforces
    "one of each format" so a model that returns `[short, short, short]`
    doesn't silently render only the short block (the renderer keys on
    format and would drop two duplicates).
    """

    model_config = ConfigDict(extra="forbid")

    variants: Annotated[list[AdCopyVariant], Field(min_length=3, max_length=3)]

    @model_validator(mode="after")
    def _variants_cover_every_format(self) -> AdCopyResult:
        formats = {variant.format for variant in self.variants}
        if formats != {"short", "medium", "long"}:
            missing = {"short", "medium", "long"} - formats
            extra = formats - {"short", "medium", "long"}
            details = []
            if missing:
                details.append(f"missing={sorted(missing)}")
            if extra:
                details.append(f"unexpected={sorted(extra)}")
            raise ValueError(
                "ad_copy must contain exactly one variant per format "
                "(short, medium, long); " + ", ".join(details)
            )
        return self


# Union of every per-type result. Order matters in some Pydantic versions
# for discriminator-less unions, but `extra="forbid"` on each model means
# the wrong-typed payload will always fail validation rather than be
# accepted into the wrong slot.
ContentResult = BlogPostResult | LinkedInPostResult | EmailResult | AdCopyResult


# ── Response ───────────────────────────────────────────────────────────


class GenerateUsage(BaseModel):
    """Per-call usage block. Same shape across content types."""

    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class GenerateResponse(BaseModel):
    """Body for POST /content/generate.

    `result` is None when `result_parse_status == FAILED` — the frontend
    falls back to `rendered_text`, which always carries something
    usable (model output verbatim in the failed case).
    """

    content_id: uuid.UUID
    content_type: ContentType
    result: ContentResult | None
    rendered_text: str
    result_parse_status: ResultParseStatus
    word_count: int
    usage: GenerateUsage
    created_at: datetime


# ── Dashboard list / detail ────────────────────────────────────────────


class ContentListItem(BaseModel):
    """Preview-grade row for the dashboard list.

    Carries everything the card needs without round-tripping the full
    `result` JSON or full `rendered_text` — the preview is server-side
    so the search-matched text stays in one place. The detail endpoint
    returns the full payload when the card is opened.
    """

    id: uuid.UUID
    content_type: ContentType
    topic: str
    preview: str
    word_count: int
    model_id: str
    result_parse_status: ResultParseStatus
    created_at: datetime


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class ListMeta(BaseModel):
    request_id: str | None = None
    pagination: PaginationMeta


class ContentListResponse(BaseModel):
    """Body for GET /content. Envelope mirrors the brief's standard
    `{ data, meta }` shape with a `pagination` block under `meta`."""

    data: list[ContentListItem]
    meta: ListMeta


class ContentDetailResponse(BaseModel):
    """Body for GET /content/:id.

    Same shape as `GenerateResponse` minus the `usage` block — the
    dashboard doesn't surface per-call cost in the detail view (that
    rolls up via `/usage/summary` later). Keep `id`/`content_type` so
    the client doesn't have to merge with the list item.
    """

    id: uuid.UUID
    content_type: ContentType
    topic: str
    tone: str | None
    target_audience: str | None
    result: ContentResult | None
    rendered_text: str
    result_parse_status: ResultParseStatus
    word_count: int
    model_id: str
    created_at: datetime
    deleted_at: datetime | None


__all__ = [
    "AdCopyAngle",
    "AdCopyFormat",
    "AdCopyResult",
    "AdCopyVariant",
    "BlogPostResult",
    "BlogPostSection",
    "ContentDetailResponse",
    "ContentListItem",
    "ContentListResponse",
    "ContentResult",
    "ContentType",
    "EmailResult",
    "GenerateRequest",
    "GenerateResponse",
    "GenerateUsage",
    "LinkedInPostResult",
    "ListMeta",
    "PaginationMeta",
    "ResultParseStatus",
]
