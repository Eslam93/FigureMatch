"""LLM provider protocol and result types.

`ILLMProvider` is the surface every chat-model implementation conforms
to. The result type is intentionally schema-agnostic — providers return
*raw text* (typically JSON when `json_schema` was supplied), and the
calling service layer is responsible for parsing/validating against the
content-type-specific Pydantic schema. This keeps the provider layer
oblivious to the content-type catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMResult:
    """The outcome of a single chat-completion call.

    Cost and latency are populated by the provider so the service layer
    can log/persist them uniformly across implementations. Mock and stub
    providers return zeroes — callers should not treat zero as "unknown".
    """

    raw_text: str
    """The model's response. Usually a JSON string when `json_schema` was
    supplied. Parsing/validating against the content-type schema is the
    caller's job."""

    model: str
    """The exact model identifier used (e.g., "gpt-5.4-mini-2026-03-17").
    Pinned model IDs make generations reproducible across deploys."""

    input_tokens: int
    output_tokens: int
    """Token counts as reported by the provider. Used for cost
    accounting in `usage_events`."""

    cost_usd: float
    """Computed cost for this call in USD. Provider-specific pricing
    tables; see each implementation."""

    latency_ms: int
    """Wall-clock time the provider call took. Includes retries."""

    finish_reason: str | None = None
    """Provider-reported reason the model stopped (e.g., "stop",
    "length", "content_filter"). May be None for stubs."""


class ILLMProvider(Protocol):
    """Surface for chat-completion-style LLM providers.

    Implementations are responsible for: (a) issuing the call, (b)
    retrying on transient failures within their configured budget, (c)
    computing cost from the response metadata, and (d) translating
    provider-specific errors into `ProviderError`s of the right `kind`,
    without upstream error text in their messages.

    The `content_type` parameter is for logging/cost-attribution only —
    it doesn't change the request shape. Schema validation belongs in
    the service layer that owns the content-type's Pydantic model.
    """

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
        content_type: str,
    ) -> LLMResult:
        """Run one chat completion and return the structured result.

        When `json_schema` is provided, the implementation should ask
        the model for strict-schema JSON output (e.g., OpenAI's
        `response_format: json_schema` with `strict: true`). The
        returned `raw_text` will then be a JSON-parseable string. When
        `json_schema` is None, the model is free to return any text.

        Raises `ProviderRetryExhausted` when transient failures
        exhausted the retry budget, `ProviderConfigError` on
        construction-time misconfiguration, and `ProviderError` for
        all other infrastructure failures.
        """
        ...
