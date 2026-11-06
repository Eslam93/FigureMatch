"""OpenAI chat-completion provider.

Wraps the async `openai` SDK with:
  - structured-output mode via `response_format: json_schema, strict=True`
    when the caller supplies a schema
  - exponential-backoff retry on 429 + 5xx + network timeout
  - per-call cost computation from `app.core.model_catalog`, with cached
    prompt tokens billed at the cached-input rate
  - structured logging of model, tokens, cost, latency, finish_reason

Pricing looks up the snapshot the API reports (`response.model`) first,
then the configured model, so a new snapshot id never fails a call that
has already been paid for. If neither is priced, `local` logs a warning
and records zero cost (a dev experimenting with a new model id isn't
blocked); every other environment raises `ProviderConfigError`, because
silently losing cost accounting is worse than refusing to serve.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Final

import openai
from openai import AsyncOpenAI

from app.core import model_catalog
from app.core.config import Environment, get_settings
from app.core.logging import get_logger
from app.providers.errors import ProviderConfigError, ProviderError, ProviderRetryExhausted
from app.providers.llm.base import LLMResult

log = get_logger(__name__)


def _cached_prompt_tokens(usage: Any, prompt_tokens: int) -> int:
    """Prompt tokens served from OpenAI's prompt cache, clamped to
    `[0, prompt_tokens]`. Both `usage.prompt_tokens_details` and its
    `cached_tokens` field are optional; anything missing counts as zero."""
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", None)
    if not isinstance(cached, int):
        return 0
    return max(0, min(cached, prompt_tokens))


def _resolve_pricing(
    response_model: str, configured_model: str
) -> model_catalog.TextPricing | None:
    pricing = model_catalog.text_pricing(response_model)
    if pricing is not None:
        return pricing
    fallback = model_catalog.text_pricing(configured_model)
    if fallback is not None:
        log.warning(
            "openai_response_model_unpriced",
            response_model=response_model,
            configured_model=configured_model,
        )
    return fallback


def _compute_cost_usd(
    response_model: str,
    configured_model: str,
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> float:
    """USD cost of one completion.

    `input_tokens` is the whole prompt; `cached_input_tokens` is the part
    of it billed at the cached rate (0 <= cached <= input).
    """
    pricing = _resolve_pricing(response_model, configured_model)
    if pricing is None:
        if get_settings().environment != Environment.LOCAL:
            raise ProviderConfigError(
                f"No pricing entry for model={response_model!r} (configured "
                f"{configured_model!r}). Add it to app/core/model_catalog.py "
                "with verified prices before deploying with this model — "
                "silently losing cost accounting in non-local environments "
                "is worse than refusing to serve."
            )
        log.warning(
            "openai_unknown_model_pricing_local_only",
            model=response_model,
            configured_model=configured_model,
        )
        return 0.0
    uncached_input_tokens = input_tokens - cached_input_tokens
    return (
        uncached_input_tokens * pricing.input_per_million
        + cached_input_tokens * pricing.cached_input_per_million
        + output_tokens * pricing.output_per_million
    ) / 1_000_000


# Retry policy. The brief specifies max 3 attempts on 5xx/429; we
# add timeout + APIConnectionError for the same reason.
_RETRYABLE_EXCEPTIONS: Final[tuple[type[BaseException], ...]] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


class OpenAIChatProvider:
    """Production LLM provider against OpenAI's chat-completions API."""

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
            # Production path: build a real client from settings. The key
            # requirement only matters here — an injected client (test
            # seam) has already provided whatever credentials it needs.
            if settings.openai_api_key is None:
                raise ProviderConfigError(
                    "OPENAI_API_KEY is required when AI_PROVIDER_MODE=openai."
                )
            client = AsyncOpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout=timeout_seconds or settings.openai_timeout_seconds,
                # We do our own retries — disabling the SDK's so retry
                # counts don't double up.
                max_retries=0,
            )
        self._client = client
        self._model = model or settings.openai_text_model
        self._max_retries = max_retries or settings.openai_max_retries

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
        content_type: str,
    ) -> LLMResult:
        request_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_schema is not None:
            request_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": content_type,
                    "schema": json_schema,
                    "strict": True,
                },
            }

        return await self._call_with_retry(
            request_kwargs,
            content_type=content_type,
            json_schema_supplied=json_schema is not None,
        )

    async def _call_with_retry(
        self,
        request_kwargs: dict[str, Any],
        *,
        content_type: str,
        json_schema_supplied: bool,
    ) -> LLMResult:
        started = time.perf_counter()
        last_exc: BaseException | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.chat.completions.create(**request_kwargs)
            except _RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                log.warning(
                    "openai_retryable_error",
                    attempt=attempt,
                    max_attempts=self._max_retries,
                    error_type=type(exc).__name__,
                    error=str(exc),
                    content_type=content_type,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._backoff_seconds(attempt))
                    continue
                break
            except openai.OpenAIError as exc:
                # Non-retryable (auth, bad request, content_filter, etc.)
                log.error(
                    "openai_non_retryable_error",
                    error_type=type(exc).__name__,
                    error=str(exc),
                    content_type=content_type,
                )
                raise ProviderError(f"OpenAI call failed: {exc}") from exc
            else:
                return self._build_result(
                    response,
                    content_type=content_type,
                    started=started,
                    json_schema_supplied=json_schema_supplied,
                )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log.error(
            "openai_retry_exhausted",
            attempts=self._max_retries,
            elapsed_ms=elapsed_ms,
            content_type=content_type,
            last_error=str(last_exc),
        )
        raise ProviderRetryExhausted(
            f"OpenAI call exhausted {self._max_retries} retries: {last_exc}"
        ) from last_exc

    def _build_result(
        self,
        response: Any,
        *,
        content_type: str,
        started: float,
        json_schema_supplied: bool,
    ) -> LLMResult:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        choice = response.choices[0]
        raw_text = choice.message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage is not None else 0
        output_tokens = usage.completion_tokens if usage is not None else 0
        cached_input_tokens = _cached_prompt_tokens(usage, input_tokens)
        cost_usd = _compute_cost_usd(
            response.model,
            self._model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
        )

        log.info(
            "openai_chat_completion",
            model=response.model,
            content_type=content_type,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost_usd, 6),
            latency_ms=elapsed_ms,
            finish_reason=choice.finish_reason,
        )

        # When the caller asked for strict JSON schema output, any
        # finish_reason other than "stop" means the response can't
        # actually satisfy the schema — `length` truncates the JSON
        # mid-output, `content_filter` redacts content the schema
        # required. Treat these as provider failures so the service-
        # layer fallback (P3.4 three-stage parser) can react cleanly
        # rather than handing downstream a malformed JSON string.
        if json_schema_supplied and choice.finish_reason not in (None, "stop"):
            log.warning(
                "openai_finish_reason_incomplete",
                finish_reason=choice.finish_reason,
                content_type=content_type,
            )
            raise ProviderError(
                f"OpenAI returned finish_reason={choice.finish_reason!r} on a "
                f"strict-JSON-schema request for content_type={content_type!r}. "
                "The response cannot satisfy the schema."
            )

        return LLMResult(
            raw_text=raw_text,
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=elapsed_ms,
            finish_reason=choice.finish_reason,
        )

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        """Exponential backoff with jitter.

        Sleeps roughly 1, 2, 4 seconds on attempts 1, 2, 3 with up to
        +25% jitter to avoid thundering-herd against a recovering API.
        """
        base = float(2 ** (attempt - 1))
        jitter = random.uniform(0, 0.25 * base)  # noqa: S311 — jitter, not crypto
        return base + jitter
