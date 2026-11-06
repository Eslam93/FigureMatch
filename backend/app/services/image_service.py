"""Image generation orchestration.

Slice 3 connects three moving parts that have been stubbed for a while:

  1. The LLM provider — used to turn the content piece's rendered text
     plus a chosen style into a structured image prompt (`prompt`,
     `negative_prompt`, `style_summary`). Uses the same OpenAI client
     as text gen; the cost shows up under the same provider config.
  2. The image provider — a GPT Image model (default
     `gpt-image-2.5-flare`) in OpenAI mode, `mock-image-v1` for
     tests/demos, Bedrock Nova Canvas stubbed for later.
  3. `IImageStorage` — local-disk by default in this slice; an S3 path
     will land with the deploy batch.

The service runs end-to-end inside a single DB transaction: flip any
existing `is_current` row for the piece to false, insert the new
`is_current=true` row. The partial unique index in the migration keeps
the invariant of at most one current image per piece. The caller
(router) owns the commit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ProviderError, ValidationError
from app.core.logging import get_logger
from app.db.enums import ImageProvider
from app.db.models import ContentPiece, GeneratedImage, User
from app.prompts import image_prompt_builder
from app.providers.image.base import IImageProvider, ImageQuality
from app.providers.llm.base import ILLMProvider
from app.repositories.content_repository import ContentRepository
from app.repositories.image_repository import ImageRepository
from app.services.image_storage import IImageStorage

# Postgres SQLSTATE for `lock_not_available` — what NOWAIT returns
# when a contending session already holds the row lock.
_PG_LOCK_NOT_AVAILABLE = "55P03"

log = get_logger(__name__)

_CONTENT_SUMMARY_MAX_CHARS = 4000


class ImagePromptResult(BaseModel):
    """Structured shape the image-prompt builder returns."""

    model_config = ConfigDict(extra="forbid")

    prompt: str
    negative_prompt: str
    style_summary: str


@dataclass(frozen=True)
class _PromptOutcome:
    payload: ImagePromptResult
    model_id: str
    cost_usd: Decimal


class ImageService:
    """Generate (or regenerate) the image attached to a content piece."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        llm_provider: ILLMProvider,
        image_provider: IImageProvider,
        storage: IImageStorage,
    ) -> None:
        self._session = session
        self._llm = llm_provider
        self._image = image_provider
        self._storage = storage
        self._content_repo = ContentRepository(session)
        self._image_repo = ImageRepository(session)

    async def generate_for_content(
        self,
        *,
        user: User,
        content_id: Any,
        style: str,
    ) -> GeneratedImage:
        """Run the full pipeline. Raises:

        - `NotFoundError` if the content piece doesn't exist or isn't
          owned by the caller.
        - `ValidationError` if the style is unknown or the upstream
          content failed parsing (no usable rendered text to summarize).
        - `ProviderError` on upstream image-provider failures.
        """
        if style not in image_prompt_builder.SUPPORTED_STYLES:
            raise ValidationError(
                f"Unknown style {style!r}. Pick one of: "
                + ", ".join(image_prompt_builder.SUPPORTED_STYLES),
                code="UNSUPPORTED_IMAGE_STYLE",
            )

        # `for_update=True` uses `SELECT ... FOR UPDATE NOWAIT` so a
        # contending request fails immediately rather than queuing
        # behind ~10-20s of external API calls (which would pin a DB
        # connection from a small asyncpg pool). The contender gets
        # a 409 `IMAGE_GENERATION_IN_PROGRESS` and can retry once the
        # winner's transaction commits.
        try:
            piece = await self._content_repo.get_for_user(
                content_id,
                user.id,
                for_update=True,
            )
        except DBAPIError as exc:
            if _is_lock_not_available(exc):
                log.info(
                    "image_regen_lock_contention",
                    content_id=str(content_id),
                    user_id=str(user.id),
                )
                raise ConflictError(
                    "An image is already being generated for this content piece.",
                    code="IMAGE_GENERATION_IN_PROGRESS",
                ) from exc
            raise
        if piece is None:
            raise NotFoundError("Content not found.", code="CONTENT_NOT_FOUND")
        if not piece.rendered_text or not piece.rendered_text.strip():
            raise ConflictError(
                "Content has no rendered text to base an image on.",
                code="CONTENT_NOT_READY_FOR_IMAGE",
            )

        # --- Step 1: ask the LLM for a structured image prompt ---
        prompt_outcome = await self._build_image_prompt(piece, style)

        # --- Step 2: ask the image provider for bytes ---
        # OpenAI's Images API doesn't accept a separate negative_prompt —
        # fold the negatives into the positive prompt as an "avoid" clause.
        # This is a no-op for providers that accept a real negative
        # field (Bedrock); it's still safe because the wording is
        # natural-language English.
        positive_prompt = prompt_outcome.payload.prompt
        if prompt_outcome.payload.negative_prompt.strip():
            positive_prompt = (
                f"{positive_prompt}\n\nAvoid: {prompt_outcome.payload.negative_prompt.strip()}"
            )
        try:
            image_result = await self._image.generate(
                prompt=positive_prompt,
                quality=default_image_quality(),
            )
        except ProviderError:
            raise
        except Exception as exc:  # pragma: no cover — defensive
            log.error("image_provider_unexpected_error", error=str(exc))
            raise ProviderError(f"Image provider failed: {exc}") from exc

        # --- Step 3: upload bytes; record current ---
        # Storage returns a key only. The URL is derived at projection
        # time via `storage.public_url_for(key)` — `cdn_url` is kept on
        # the row for backwards-compat with old rows but ALSO refreshed
        # on write so a config change to `IMAGES_CDN_BASE_URL` rewrites
        # every new row's URL automatically. Old rows projected through
        # the router use the freshly-computed URL too (see
        # `routers/content.py`).
        s3_key = await self._storage.store(image_bytes=image_result.image_bytes)
        cdn_url = self._storage.public_url_for(s3_key)

        await self._image_repo.mark_others_not_current(piece.id)
        provider_enum = self._image_provider_enum(image_result.model)
        total_cost = prompt_outcome.cost_usd + Decimal(str(image_result.cost_usd))
        new_image = GeneratedImage(
            content_piece_id=piece.id,
            image_prompt=positive_prompt,
            negative_prompt=prompt_outcome.payload.negative_prompt or None,
            style=style,
            provider=provider_enum,
            model_id=image_result.model,
            width=image_result.width,
            height=image_result.height,
            seed=None,
            s3_key=s3_key,
            cdn_url=cdn_url,
            cost_usd=total_cost,
            is_current=True,
        )
        return await self._image_repo.create(new_image)

    # ── helpers ────────────────────────────────────────────────────────

    async def _build_image_prompt(
        self,
        piece: ContentPiece,
        style: str,
    ) -> _PromptOutcome:
        """Single-shot LLM call that returns the structured prompt.

        Unlike the content service, this one does NOT three-stage
        retry: if the model can't return valid JSON on the strict
        schema we fall back to a sensible default prompt rather than
        cost a second call. The downstream image gen will still run.
        """
        content_summary = piece.rendered_text.strip()
        if len(content_summary) > _CONTENT_SUMMARY_MAX_CHARS:
            content_summary = content_summary[:_CONTENT_SUMMARY_MAX_CHARS]

        system_prompt, user_prompt = image_prompt_builder.build_prompt(
            content_summary=content_summary,
            style=style,
        )
        llm_result = await self._llm.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=image_prompt_builder.JSON_SCHEMA["schema"],
            content_type="image_prompt",
        )
        cost = Decimal(str(llm_result.cost_usd))

        try:
            parsed = ImagePromptResult.model_validate(json.loads(llm_result.raw_text))
        except (json.JSONDecodeError, PydanticValidationError):
            log.warning(
                "image_prompt_parse_failed_using_fallback",
                model=llm_result.model,
                content_piece_id=str(piece.id),
            )
            parsed = ImagePromptResult(
                prompt=(f"A {style.replace('_', ' ')} image inspired by: {piece.topic.strip()}."),
                negative_prompt="text, watermark, logos, faces",
                style_summary=style.replace("_", " "),
            )
        return _PromptOutcome(
            payload=parsed,
            model_id=llm_result.model,
            cost_usd=cost,
        )

    @staticmethod
    def _image_provider_enum(model: str) -> ImageProvider:
        """Map a model id to the persisted `ImageProvider` enum.

        Mock and OpenAI map to OPENAI for the persisted column — they
        share a generation surface, and the dashboard distinguishes
        them via `model_id`, not the enum. Bedrock Nova Canvas gets
        its own row when that path is wired.
        """
        if model.startswith("nova-canvas"):
            return ImageProvider.NOVA_CANVAS
        return ImageProvider.OPENAI


def _is_lock_not_available(exc: DBAPIError) -> bool:
    """Detect Postgres SQLSTATE 55P03 raised by SELECT ... FOR UPDATE
    NOWAIT when another session holds the row lock. asyncpg surfaces
    the original error through SQLAlchemy's DBAPIError wrapper; the
    code lives on the wrapped exception's `sqlstate` attribute.
    """
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return sqlstate == _PG_LOCK_NOT_AVAILABLE


def default_image_quality() -> ImageQuality:
    """Translate the configured `openai_image_quality` string to the
    `ImageQuality` enum. Falls back to MEDIUM for unrecognized values
    rather than failing at request time.
    """
    from app.core.config import get_settings  # local import — avoids cycle

    raw = (get_settings().openai_image_quality or "medium").lower()
    try:
        return ImageQuality(raw)
    except ValueError:
        log.warning("openai_image_quality_unrecognized", value=raw)
        return ImageQuality.MEDIUM
