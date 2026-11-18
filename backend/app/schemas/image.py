# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Pydantic request / response schemas for /content/{id}/image(s)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.db.enums import ImageProvider
from app.prompts.image_prompt_builder import SUPPORTED_STYLES

ImageStyle = Literal[
    "photorealistic",
    "illustration",
    "minimalist",
    "3d_render",
    "watercolor",
    "cinematic",
]


class ImageGenerateRequest(BaseModel):
    """Body for POST /content/{id}/image.

    `style` defaults to photorealistic so the route works with no body.
    `provider` is reserved for future-flexibility (Bedrock vs OpenAI);
    Slice 3 honours whatever `AI_PROVIDER_MODE` is configured and
    ignores explicit overrides.
    """

    style: ImageStyle = "photorealistic"


class GeneratedImageResponse(BaseModel):
    """The persisted `generated_images` row, projected for the API."""

    id: uuid.UUID
    content_piece_id: uuid.UUID
    style: str | None
    provider: ImageProvider
    model_id: str
    width: int
    height: int
    cdn_url: str
    image_prompt: str
    negative_prompt: str | None
    cost_usd: Decimal
    is_current: bool
    created_at: datetime


class ImageGenerateResponse(BaseModel):
    """Body for POST /content/{id}/image — single new image."""

    image: GeneratedImageResponse


class ImageListResponse(BaseModel):
    """Body for GET /content/{id}/images — every version, newest first."""

    data: list[GeneratedImageResponse]


# Re-export `SUPPORTED_STYLES` for callers that want to render the
# enum without re-importing the prompt module.
SUPPORTED_IMAGE_STYLES: Annotated[tuple[str, ...], Field()] = SUPPORTED_STYLES


__all__ = [
    "SUPPORTED_IMAGE_STYLES",
    "GeneratedImageResponse",
    "ImageGenerateRequest",
    "ImageGenerateResponse",
    "ImageListResponse",
    "ImageStyle",
]
