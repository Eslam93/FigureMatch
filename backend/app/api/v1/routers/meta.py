"""Public metadata the frontend needs before anyone signs in.

``provider_mode`` lets the UI warn that generations are canned when the
backend runs with ``AI_PROVIDER_MODE=mock``. The route needs no auth, so it
exposes only the mode and the app version: no model ids, keys or other
configuration.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import AIProviderMode, get_settings

router = APIRouter(tags=["system"])


class MetaResponse(BaseModel):
    provider_mode: AIProviderMode = Field(
        description="AI provider serving generations; `mock` returns canned content.",
    )
    app_version: str = Field(description="Backend version (`APP_VERSION`).")


@router.get(
    "/meta",
    response_model=MetaResponse,
    summary="AI provider mode and app version",
)
async def meta() -> MetaResponse:
    settings = get_settings()
    return MetaResponse(
        provider_mode=settings.ai_provider_mode,
        app_version=settings.app_version,
    )
