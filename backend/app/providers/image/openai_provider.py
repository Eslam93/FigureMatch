"""OpenAI GPT Image provider (Images API, default `gpt-image-2.5-flare`).

Same retry/logging contract as the chat provider. Quality maps directly
to OpenAI's `quality` parameter; size defaults to 1024×1024 (the only
size the protocol guarantees). PNG output is requested explicitly
because the storage layer saves every image with a `.png` extension.

GPT Image models bill per token, so cost comes from the response's
`usage` block at the rates in `app.core.model_catalog`. Output bills only
its image tokens: OpenAI doesn't bill these models' text output. A
response without usable `usage` is logged and recorded at the catalog's
per-image reference cost for the quality, which is an estimate. An
unpriced model logs and records zero in `local` and raises
`ProviderConfigError` everywhere else, like the chat provider.
"""

from __future__ import annotations

import asyncio
import base64
import random
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

import openai
from openai import AsyncOpenAI

from app.core import model_catalog
from app.core.config import Environment, get_settings
from app.core.logging import get_logger
from app.providers.errors import ProviderConfigError, ProviderError, ProviderRetryExhausted
from app.providers.image.base import ImageQuality, ImageResult

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _ImageUsage:
    """Token counts from one Images API response. All but
    `text_output_tokens` are billed: OpenAI doesn't bill text output for
    these models, which output images."""

    text_input_tokens: int
    image_input_tokens: int
    image_output_tokens: int
    text_output_tokens: int


def _token_count(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _detail(details: Any, name: str) -> int | None:
    """One count from a `*_tokens_details` block. The SDK types the input
    block, but delivers blocks it doesn't model yet (`output_tokens_details`)
    as plain dicts, so both shapes are read."""
    if isinstance(details, Mapping):
        return _token_count(details.get(name))
    return _token_count(getattr(details, name, None))


def _read_usage(usage: Any) -> _ImageUsage | None:
    """Token counts from an `ImagesResponse.usage` block, read None-safely.

    Returns None when the block is missing or unusable: absent or
    non-integer counts, or zero output tokens (a returned image always
    bills output tokens, so zero means the block can't be trusted).
    Without `input_tokens_details`, every input token counts as text.

    `output_tokens` counts every output token, text included. When
    `output_tokens_details` breaks out a positive image count no larger
    than that total, only those image tokens bill at the output rate;
    otherwise the whole total does.
    """
    if usage is None:
        return None
    input_tokens = _token_count(getattr(usage, "input_tokens", None))
    output_tokens = _token_count(getattr(usage, "output_tokens", None))
    if input_tokens is None or not output_tokens:
        return None
    input_details = getattr(usage, "input_tokens_details", None)
    text_tokens = _detail(input_details, "text_tokens")
    image_tokens = _detail(input_details, "image_tokens")
    if text_tokens is None or image_tokens is None:
        text_tokens, image_tokens = input_tokens, 0
    image_output_tokens = _detail(getattr(usage, "output_tokens_details", None), "image_tokens")
    if not image_output_tokens or image_output_tokens > output_tokens:
        image_output_tokens = output_tokens
    return _ImageUsage(
        text_input_tokens=text_tokens,
        image_input_tokens=image_tokens,
        image_output_tokens=image_output_tokens,
        text_output_tokens=output_tokens - image_output_tokens,
    )


def _compute_cost_usd(model: str, quality: ImageQuality, usage: _ImageUsage | None) -> float:
    pricing = model_catalog.image_pricing(model)
    if pricing is None:
        if get_settings().environment != Environment.LOCAL:
            raise ProviderConfigError(
                f"No pricing entry for image model={model!r}. Add it to "
                "app/core/model_catalog.py with verified prices before "
                "deploying with this configuration."
            )
        log.warning(
            "openai_image_unknown_pricing_local_only",
            model=model,
            quality=quality.value,
        )
        return 0.0
    if usage is None:
        estimate = pricing.reference_cost_per_image.for_quality(quality.value)
        log.warning(
            "openai_image_usage_missing",
            model=model,
            quality=quality.value,
            estimated_cost_usd=estimate,
        )
        return estimate
    return (
        usage.text_input_tokens * pricing.text_input_per_million
        + usage.image_input_tokens * pricing.image_input_per_million
        + usage.image_output_tokens * pricing.image_output_per_million
    ) / 1_000_000


_RETRYABLE_EXCEPTIONS: Final[tuple[type[BaseException], ...]] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


class OpenAIImageProvider:
    """Production image provider against OpenAI's GPT Image models."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        settings = get_settings()
        if client is None:
            if settings.openai_api_key is None:
                raise ProviderConfigError(
                    "OPENAI_API_KEY is required when AI_PROVIDER_MODE=openai."
                )
            client = AsyncOpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout=timeout_seconds or settings.openai_timeout_seconds,
                max_retries=0,
            )
        self._client = client
        self._model = model or settings.openai_image_model
        self._max_retries = max_retries or settings.openai_max_retries

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        *,
        prompt: str,
        quality: ImageQuality = ImageQuality.MEDIUM,
        size: tuple[int, int] = (1024, 1024),
    ) -> ImageResult:
        width, height = size
        request_kwargs: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "n": 1,
            "size": f"{width}x{height}",
            "quality": quality.value,
            "output_format": "png",
        }
        return await self._call_with_retry(
            request_kwargs,
            prompt=prompt,
            quality=quality,
            width=width,
            height=height,
        )

    async def _call_with_retry(
        self,
        request_kwargs: dict[str, Any],
        *,
        prompt: str,
        quality: ImageQuality,
        width: int,
        height: int,
    ) -> ImageResult:
        started = time.perf_counter()
        last_exc: BaseException | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.images.generate(**request_kwargs)
            except _RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                log.warning(
                    "openai_image_retryable_error",
                    attempt=attempt,
                    max_attempts=self._max_retries,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._backoff_seconds(attempt))
                    continue
                break
            except openai.OpenAIError as exc:
                log.error(
                    "openai_image_non_retryable_error",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                raise ProviderError(f"OpenAI image call failed: {exc}") from exc
            else:
                return self._build_result(
                    response,
                    prompt=prompt,
                    quality=quality,
                    width=width,
                    height=height,
                    started=started,
                )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log.error(
            "openai_image_retry_exhausted",
            attempts=self._max_retries,
            elapsed_ms=elapsed_ms,
            last_error=str(last_exc),
        )
        raise ProviderRetryExhausted(
            f"OpenAI image call exhausted {self._max_retries} retries: {last_exc}"
        ) from last_exc

    def _build_result(
        self,
        response: Any,
        *,
        prompt: str,
        quality: ImageQuality,
        width: int,
        height: int,
        started: float,
    ) -> ImageResult:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if not response.data:
            raise ProviderError("OpenAI image response contained no data.")
        b64 = response.data[0].b64_json
        if not b64:
            raise ProviderError("OpenAI image response missing b64_json payload.")
        image_bytes = base64.b64decode(b64)
        usage = _read_usage(getattr(response, "usage", None))
        cost_usd = _compute_cost_usd(self._model, quality, usage)

        log.info(
            "openai_image_generation",
            model=self._model,
            quality=quality.value,
            size=f"{width}x{height}",
            bytes=len(image_bytes),
            text_input_tokens=usage.text_input_tokens if usage else None,
            image_input_tokens=usage.image_input_tokens if usage else None,
            image_output_tokens=usage.image_output_tokens if usage else None,
            text_output_tokens=usage.text_output_tokens if usage else None,
            cost_usd=round(cost_usd, 4),
            latency_ms=elapsed_ms,
        )
        return ImageResult(
            image_bytes=image_bytes,
            width=width,
            height=height,
            model=self._model,
            quality=quality,
            cost_usd=cost_usd,
            latency_ms=elapsed_ms,
            prompt_used=prompt,
        )

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        base = float(2 ** (attempt - 1))
        jitter = random.uniform(0, 0.25 * base)  # noqa: S311 — jitter, not crypto
        return base + jitter
