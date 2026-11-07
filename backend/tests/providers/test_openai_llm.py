"""OpenAIChatProvider — retry, cost, structured-output, error mapping.

We never hit the real API in tests. The openai SDK exposes
`AsyncOpenAI(...).chat.completions.create` which we stub by injecting
a fake client into the provider constructor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from app.providers.errors import ProviderError, ProviderRetryExhausted
from app.providers.llm.openai_provider import OpenAIChatProvider, _compute_cost_usd

if TYPE_CHECKING:
    from pytest import MonkeyPatch


_PINNED = "gpt-5.4-mini-2026-03-17"


def _build_fake_response(
    *,
    content: str,
    model: str = _PINNED,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    cached_tokens: int | None = None,
    finish_reason: str = "stop",
) -> MagicMock:
    """Construct an object that quacks like the openai SDK's
    ChatCompletion response — enough fields for our provider to read.
    `cached_tokens=None` models a response without `prompt_tokens_details`."""
    response = MagicMock()
    response.model = model
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = finish_reason
    response.usage = MagicMock()
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.usage.prompt_tokens_details = (
        None if cached_tokens is None else MagicMock(cached_tokens=cached_tokens)
    )
    return response


def _build_fake_client(create_mock: AsyncMock) -> MagicMock:
    """Wire `client.chat.completions.create` to `create_mock`."""
    client = MagicMock()
    client.chat.completions.create = create_mock
    return client


def _cost(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    configured: str = _PINNED,
) -> float:
    return _compute_cost_usd(
        model,
        configured,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
    )


# ── cost calculation ───────────────────────────────────────────────────


def test_one_thousand_input_and_output_tokens_cost_0_00525() -> None:
    """The price-table regression: gpt-5.4-mini is $0.75 in / $4.50 out
    per 1M tokens, so 1,000 + 1,000 tokens cost $0.00075 + $0.0045."""
    assert _cost(_PINNED, input_tokens=1000, output_tokens=1000) == pytest.approx(0.00525)
    assert _cost("gpt-5.4-mini", input_tokens=1000, output_tokens=1000) == pytest.approx(0.00525)


def test_cached_prompt_tokens_bill_at_the_cached_rate() -> None:
    # 600 uncached x $0.75 + 400 cached x $0.075 + 200 output x $4.50, per 1M.
    cost = _cost(_PINNED, input_tokens=1000, cached_input_tokens=400, output_tokens=200)
    assert cost == pytest.approx((600 * 0.75 + 400 * 0.075 + 200 * 4.50) / 1_000_000)


def test_unpriced_response_snapshot_falls_back_to_configured_model(
    monkeypatch: MonkeyPatch,
) -> None:
    """The API may report a snapshot the catalog doesn't list yet. The
    call is already paid for, so price it at the configured model's
    rates and log both ids — never raise, even outside `local`."""
    from app.core.config import Environment, get_settings

    monkeypatch.setattr(get_settings(), "environment", Environment.PROD)
    fake_log = MagicMock()
    monkeypatch.setattr("app.providers.llm.openai_provider.log", fake_log)

    cost = _cost("gpt-5.4-mini-2099-01-01", input_tokens=1000, output_tokens=1000)

    assert cost == pytest.approx(0.00525)
    fake_log.warning.assert_called_once_with(
        "openai_response_model_unpriced",
        response_model="gpt-5.4-mini-2099-01-01",
        configured_model=_PINNED,
    )


def test_priced_response_snapshot_wins_over_configured_model() -> None:
    """`response.model` is looked up first: a priced snapshot is billed at
    its own rates even when the configured id is something else."""
    cost = _cost(_PINNED, input_tokens=1000, output_tokens=1000, configured="not-in-catalog")
    assert cost == pytest.approx(0.00525)


def test_compute_cost_usd_for_unknown_model_returns_zero_in_local(
    monkeypatch: MonkeyPatch,
) -> None:
    # Default test env is `local`, where unknown models log + return 0.0.
    fake_log = MagicMock()
    monkeypatch.setattr("app.providers.llm.openai_provider.log", fake_log)

    cost = _cost("future-model-not-priced", input_tokens=1000, output_tokens=500, configured="x")

    assert cost == 0.0
    fake_log.warning.assert_called_once_with(
        "openai_unknown_model_pricing_local_only",
        model="future-model-not-priced",
        configured_model="x",
    )


def test_compute_cost_usd_for_unknown_model_raises_in_non_local(
    monkeypatch: MonkeyPatch,
) -> None:
    """In production-like environments, an unknown model is a
    misconfiguration: silently losing cost accounting is worse than
    refusing to serve. Force a non-local env and verify."""
    from app.core.config import Environment, get_settings

    monkeypatch.setattr(get_settings(), "environment", Environment.PROD)
    from app.providers.errors import ProviderConfigError

    with pytest.raises(ProviderConfigError, match="No pricing entry"):
        _cost("future-model-not-priced", input_tokens=1000, output_tokens=500, configured="x")


def test_image_model_id_is_not_priced_as_text() -> None:
    """The catalog is kind-aware: an image model in the text slot has no
    text price, so it takes the unknown-model path (zero in `local`)."""
    cost = _cost("gpt-image-2.5-flare", input_tokens=1000, output_tokens=500, configured="x")
    assert cost == 0.0


@pytest.mark.parametrize(
    ("cached_tokens", "expected"),
    [
        (None, 0),  # no prompt_tokens_details block at all
        (0, 0),
        (40, 40),
        (500, 100),  # clamped to prompt_tokens
        (-5, 0),  # clamped to zero
    ],
)
async def test_cached_tokens_are_read_none_safely_and_clamped(
    cached_tokens: int | None, expected: int
) -> None:
    response = _build_fake_response(content="ok", prompt_tokens=100, cached_tokens=cached_tokens)
    provider = OpenAIChatProvider(client=_build_fake_client(AsyncMock(return_value=response)))

    result = await provider.generate(system_prompt="s", user_prompt="u", content_type="blog_post")

    uncached = 100 - expected
    assert result.input_tokens == 100
    assert result.cost_usd == pytest.approx(
        (uncached * 0.75 + expected * 0.075 + 50 * 4.50) / 1_000_000
    )


async def test_cached_tokens_field_set_to_none_counts_as_zero() -> None:
    response = _build_fake_response(content="ok", prompt_tokens=100, cached_tokens=0)
    response.usage.prompt_tokens_details.cached_tokens = None
    provider = OpenAIChatProvider(client=_build_fake_client(AsyncMock(return_value=response)))

    result = await provider.generate(system_prompt="s", user_prompt="u", content_type="blog_post")

    assert result.cost_usd == pytest.approx((100 * 0.75 + 50 * 4.50) / 1_000_000)


async def test_chat_completion_log_carries_cached_input_tokens(
    monkeypatch: MonkeyPatch,
) -> None:
    fake_log = MagicMock()
    monkeypatch.setattr("app.providers.llm.openai_provider.log", fake_log)
    response = _build_fake_response(content="ok", prompt_tokens=100, cached_tokens=30)
    provider = OpenAIChatProvider(client=_build_fake_client(AsyncMock(return_value=response)))

    await provider.generate(system_prompt="s", user_prompt="u", content_type="blog_post")

    event, fields = fake_log.info.call_args.args[0], fake_log.info.call_args.kwargs
    assert event == "openai_chat_completion"
    assert fields["input_tokens"] == 100
    assert fields["cached_input_tokens"] == 30
    assert fields["output_tokens"] == 50


async def test_response_snapshot_fallback_uses_the_providers_configured_model(
    monkeypatch: MonkeyPatch,
) -> None:
    """End to end: the provider passes its own configured model as the
    fallback when the API reports an unpriced snapshot."""
    fake_log = MagicMock()
    monkeypatch.setattr("app.providers.llm.openai_provider.log", fake_log)
    response = _build_fake_response(
        content="ok", model="gpt-5.4-mini-2099-01-01", prompt_tokens=1000, completion_tokens=1000
    )
    provider = OpenAIChatProvider(
        client=_build_fake_client(AsyncMock(return_value=response)), model="gpt-5.4-mini"
    )

    result = await provider.generate(system_prompt="s", user_prompt="u", content_type="blog_post")

    assert result.model == "gpt-5.4-mini-2099-01-01"
    assert result.cost_usd == pytest.approx(0.00525)
    fake_log.warning.assert_called_once_with(
        "openai_response_model_unpriced",
        response_model="gpt-5.4-mini-2099-01-01",
        configured_model="gpt-5.4-mini",
    )


# ── happy path ─────────────────────────────────────────────────────────


async def test_generate_returns_parsed_result(monkeypatch: MonkeyPatch) -> None:
    """A single successful call returns an LLMResult with the response
    body, model, tokens, cost, latency, and finish_reason populated."""
    create_mock = AsyncMock(return_value=_build_fake_response(content='{"x": 1}'))
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client, model=_PINNED)

    result = await provider.generate(
        system_prompt="sys",
        user_prompt="user",
        content_type="blog_post",
    )
    assert result.raw_text == '{"x": 1}'
    assert result.model == _PINNED
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    # 100 input x $0.75 + 50 output x $4.50, per 1M tokens.
    assert result.cost_usd == pytest.approx((100 * 0.75 + 50 * 4.50) / 1_000_000)
    assert result.finish_reason == "stop"


async def test_generate_passes_json_schema_when_supplied() -> None:
    """When `json_schema` is set, the SDK call must include the
    structured-output `response_format`."""
    create_mock = AsyncMock(return_value=_build_fake_response(content="{}"))
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client)

    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    await provider.generate(
        system_prompt="s",
        user_prompt="u",
        json_schema=schema,
        content_type="blog_post",
    )
    kwargs = create_mock.call_args.kwargs
    assert "response_format" in kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert kwargs["response_format"]["json_schema"]["schema"] == schema


async def test_generate_omits_response_format_when_schema_is_none() -> None:
    """Free-form generation must not request structured output —
    response_format would force JSON the caller didn't ask for."""
    create_mock = AsyncMock(return_value=_build_fake_response(content="hello"))
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client)

    await provider.generate(
        system_prompt="s",
        user_prompt="u",
        content_type="blog_post",
    )
    kwargs = create_mock.call_args.kwargs
    assert "response_format" not in kwargs


async def test_strict_schema_with_length_finish_reason_raises() -> None:
    """Strict JSON schema + finish_reason=length means the JSON was
    truncated mid-output. Returning success here would hand downstream
    a malformed JSON string — service-layer fallback can't disambiguate
    that from a model hallucination. Raise instead."""
    create_mock = AsyncMock(
        return_value=_build_fake_response(content='{"partial', finish_reason="length")
    )
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client)

    with pytest.raises(ProviderError, match="finish_reason='length'"):
        await provider.generate(
            system_prompt="s",
            user_prompt="u",
            json_schema={"type": "object"},
            content_type="blog_post",
        )


async def test_strict_schema_with_content_filter_finish_reason_raises() -> None:
    """Content-filter on a strict-schema request means the model
    redacted required fields. Same correctness gap as `length`."""
    create_mock = AsyncMock(
        return_value=_build_fake_response(content="", finish_reason="content_filter")
    )
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client)

    with pytest.raises(ProviderError, match="content_filter"):
        await provider.generate(
            system_prompt="s",
            user_prompt="u",
            json_schema={"type": "object"},
            content_type="blog_post",
        )


async def test_free_form_with_length_finish_reason_does_not_raise() -> None:
    """When the caller didn't request structured output, finish_reason
    other than `stop` is the caller's problem to interpret — don't
    swallow valid partial responses behind a schema-strictness check."""
    create_mock = AsyncMock(
        return_value=_build_fake_response(content="partial", finish_reason="length")
    )
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client)

    result = await provider.generate(
        system_prompt="s",
        user_prompt="u",
        content_type="blog_post",
    )
    assert result.raw_text == "partial"
    assert result.finish_reason == "length"


# ── retry behavior ─────────────────────────────────────────────────────


def _make_retryable_error() -> openai.RateLimitError:
    """Construct a RateLimitError with the minimum args the SDK requires."""
    return openai.RateLimitError(
        message="rate limited",
        response=MagicMock(status_code=429, headers={}),
        body={"error": "rate_limit"},
    )


async def test_retries_on_rate_limit_and_succeeds(
    monkeypatch: MonkeyPatch,
) -> None:
    """First call returns 429, second succeeds — provider must retry."""
    # No real sleeping in tests.
    monkeypatch.setattr("app.providers.llm.openai_provider.asyncio.sleep", AsyncMock())

    create_mock = AsyncMock(
        side_effect=[
            _make_retryable_error(),
            _build_fake_response(content="ok"),
        ]
    )
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client, max_retries=3)

    result = await provider.generate(
        system_prompt="s",
        user_prompt="u",
        content_type="blog_post",
    )
    assert result.raw_text == "ok"
    assert create_mock.call_count == 2


async def test_retries_exhausted_raises_retry_exhausted(
    monkeypatch: MonkeyPatch,
) -> None:
    """When every attempt raises a retryable error, the provider gives
    up with `ProviderRetryExhausted`."""
    monkeypatch.setattr("app.providers.llm.openai_provider.asyncio.sleep", AsyncMock())

    create_mock = AsyncMock(side_effect=[_make_retryable_error()] * 3)
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client, max_retries=3)

    with pytest.raises(ProviderRetryExhausted):
        await provider.generate(
            system_prompt="s",
            user_prompt="u",
            content_type="blog_post",
        )
    assert create_mock.call_count == 3


async def test_non_retryable_error_raises_provider_error() -> None:
    """Auth errors, bad requests, content_filter — none of these should
    be retried. The provider raises `ProviderError` immediately."""

    class _AuthError(openai.AuthenticationError):
        def __init__(self) -> None:
            super().__init__(
                message="bad key",
                response=MagicMock(status_code=401, headers={}),
                body={"error": "invalid_api_key"},
            )

    create_mock = AsyncMock(side_effect=_AuthError())
    client = _build_fake_client(create_mock)
    provider = OpenAIChatProvider(client=client, max_retries=3)

    with pytest.raises(ProviderError):
        await provider.generate(
            system_prompt="s",
            user_prompt="u",
            content_type="blog_post",
        )
    # No retries on non-retryable errors.
    assert create_mock.call_count == 1


# ── backoff math ───────────────────────────────────────────────────────


def test_backoff_grows_exponentially() -> None:
    """Successive attempts should sleep ~1, ~2, ~4 seconds plus jitter."""
    s1 = OpenAIChatProvider._backoff_seconds(1)
    s2 = OpenAIChatProvider._backoff_seconds(2)
    s3 = OpenAIChatProvider._backoff_seconds(3)
    # Bases are 1, 2, 4. Jitter adds up to +25% of base.
    assert 1.0 <= s1 < 1.25
    assert 2.0 <= s2 < 2.50
    assert 4.0 <= s3 < 5.00


# ── config error path ─────────────────────────────────────────────────


def test_construction_without_api_key_raises_config_error(monkeypatch: MonkeyPatch) -> None:
    """Provider construction must fail fast when no API key is configured."""
    from app.core.config import get_settings

    settings = get_settings()
    # Force the cached settings to look as if no key is set.
    monkeypatch.setattr(settings, "openai_api_key", None)
    from app.providers.errors import ProviderConfigError

    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        OpenAIChatProvider()


# Silence unused-import lint when imports above are only used for types.
_ = Any
