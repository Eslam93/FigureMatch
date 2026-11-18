# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Pydantic request / response schemas for /brand-voices endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

_MAX_LIST_ITEMS = 25


class BrandVoiceCreate(BaseModel):
    """Body for POST /brand-voices."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str | None, Field(default=None, max_length=2000)] = None
    tone_descriptors: Annotated[
        list[str],
        Field(default_factory=list, max_length=_MAX_LIST_ITEMS),
    ]
    banned_words: Annotated[
        list[str],
        Field(default_factory=list, max_length=_MAX_LIST_ITEMS),
    ]
    sample_text: Annotated[str | None, Field(default=None, max_length=5000)] = None
    target_audience: Annotated[str | None, Field(default=None, max_length=500)] = None


class BrandVoiceUpdate(BaseModel):
    """Body for PATCH /brand-voices/:id.

    Every field is optional — **only the keys present on the wire are
    applied**. The router uses Pydantic's `model_fields_set` to filter
    out unsent keys, so:

      - Sending `{"name": "New name"}` updates only `name`.
      - Omitting a key leaves its current value untouched.

    To **clear** a nullable string column (`description`,
    `sample_text`, `target_audience`), send an empty string `""`
    rather than `null` — `null` is not used as a "clear me" signal.
    The list-typed fields (`tone_descriptors`, `banned_words`) accept
    an empty array `[]` to clear them.
    """

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=120)] = None
    description: Annotated[str | None, Field(default=None, max_length=2000)] = None
    tone_descriptors: Annotated[
        list[str] | None,
        Field(default=None, max_length=_MAX_LIST_ITEMS),
    ] = None
    banned_words: Annotated[
        list[str] | None,
        Field(default=None, max_length=_MAX_LIST_ITEMS),
    ] = None
    sample_text: Annotated[str | None, Field(default=None, max_length=5000)] = None
    target_audience: Annotated[str | None, Field(default=None, max_length=500)] = None


class BrandVoiceResponse(BaseModel):
    """Wire shape for list + detail endpoints."""

    id: uuid.UUID
    name: str
    description: str | None
    tone_descriptors: list[str]
    banned_words: list[str]
    sample_text: str | None
    target_audience: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class BrandVoiceListResponse(BaseModel):
    data: list[BrandVoiceResponse]


__all__ = [
    "BrandVoiceCreate",
    "BrandVoiceListResponse",
    "BrandVoiceResponse",
    "BrandVoiceUpdate",
]
