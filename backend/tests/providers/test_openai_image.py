"""OpenAIImageProvider — retry, token-based cost, b64 decode, error mapping."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import openai
import pytest
from openai.types.images_response import ImagesResponse, Usage, UsageInputTokensDetails

from app.providers.errors import ProviderError, ProviderRetryExhausted
from app.providers.image.base import ImageQuality
from app.providers.image.openai_provider import OpenAIImageProvider, _compute_cost_usd

if TYPE_CHECKING:
    from pytest import MonkeyPatch


_MODEL = "gpt-image-2.5-flare"

# A 1×1 transparent PNG, the same one MockImageProvider uses.
_FAKE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6"
    "kgAAAABJRU5ErkJggg=="
)


def _sdk_usage(*, text_tokens: int, image_tokens: int, output_tokens: int) -> Usage:
    """A real SDK `Usage` block, so the happy path reads the true shape."""
    return Usage(
        input_tokens=text_tokens + image_tokens,
        input_tokens_details=UsageInputTokensDetails(
            text_tokens=text_tokens, image_tokens=image_tokens
        ),
        output_tokens=output_tokens,
        total_tokens=text_tokens + image_tokens + output_tokens,
    )


# 40 text tokens in, 1,000 image tokens out: (40 x $5 + 1000 x $30) / 1M.
_USAGE = _sdk_usage(text_tokens=40, image_tokens=0, output_tokens=1000)
_USAGE_COST = (40 * 5.00 + 1000 * 30.00) / 1_000_000


def _build_fake_image_response(b64: str = _FAKE_PNG_B64, usage: Any = _USAGE) -> MagicMock:
    response = MagicMock()
    response.data = [MagicMock()]
    response.data[0].b64_json = b64
    response.usage = usage
    return response


def _build_fake_client(generate_mock: AsyncMock) -> MagicMock:
    client = MagicMock()
    client.images.generate = generate_mock
    return client


def _provider_returning(response: MagicMock, **kwargs: Any) -> OpenAIImageProvider:
    client = _build_fake_client(AsyncMock(return_value=response))
    return OpenAIImageProvider(client=client, model=_MODEL, **kwargs)


def _make_rate_limit_error() -> openai.RateLimitError:
    return openai.RateLimitError(
        message="rate limited",
        response=MagicMock(status_code=429, headers={}),
        body={"error": "rate_limit"},
    )


# ── default model + request shape ──────────────────────────────────────


def test_default_image_model_is_gpt_image_2_5_flare() -> None:
    """gpt-image-1 was shut down on 2026-10-23; the shipped default must
    be its named replacement. Read from the field itself, so a developer's
    OPENAI_IMAGE_MODEL can't change the answer."""
    from app.core.config import Settings

    assert Settings.model_fields["openai_image_model"].default == "gpt-image-2.5-flare"


def test_provider_uses_the_configured_image_model_by_default(monkeypatch: MonkeyPatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "openai_image_model", "gpt-image-2.6-flare")

    provider = OpenAIImageProvider(client=_build_fake_client(AsyncMock()))

    assert provider.model == "gpt-image-2.6-flare"


async def test_generate_sends_png_output_format_plus_quality_size_and_n() -> None:
    generate_mock = AsyncMock(return_value=_build_fake_image_response())
    provider = OpenAIImageProvider(client=_build_fake_client(generate_mock), model=_MODEL)

    await provider.generate(prompt="x", quality=ImageQuality.HIGH, size=(1024, 1024))

    kwargs = generate_mock.call_args.kwargs
    assert kwargs == {
        "model": _MODEL,
        "prompt": "x",
        "n": 1,
        "size": "1024x1024",
        "quality": "high",
        # Storage saves every image as `.png`; ask for exactly that.
        "output_format": "png",
    }


# ── cost from usage ────────────────────────────────────────────────────


async def test_generate_returns_image_bytes_and_usage_based_cost() -> None:
    provider = _provider_returning(_build_fake_image_response())

    result = await provider.generate(prompt="a cat", quality=ImageQuality.LOW)

    assert result.image_bytes == base64.b64decode(_FAKE_PNG_B64)
    assert result.model == _MODEL
    assert result.quality == ImageQuality.LOW
    assert result.cost_usd == pytest.approx(_USAGE_COST)
    assert result.width == 1024
    assert result.height == 1024
    assert result.prompt_used == "a cat"


async def test_each_token_type_bills_at_its_own_rate() -> None:
    usage = _sdk_usage(text_tokens=100, image_tokens=200, output_tokens=1000)
    provider = _provider_returning(_build_fake_image_response(usage=usage))

    result = await provider.generate(prompt="x")

    # $5 text in, $8 image in, $30 image out — all per 1M tokens.
    assert result.cost_usd == pytest.approx((100 * 5.00 + 200 * 8.00 + 1000 * 30.00) / 1e6)


@pytest.mark.parametrize(
    "usage",
    [
        SimpleNamespace(input_tokens=300, output_tokens=1000),
        SimpleNamespace(input_tokens=300, input_tokens_details=None, output_tokens=1000),
        SimpleNamespace(
            input_tokens=300,
            input_tokens_details=SimpleNamespace(text_tokens=None, image_tokens=None),
            output_tokens=1000,
        ),
    ],
    ids=["details-absent", "details-none", "details-empty"],
)
async def test_without_input_details_all_input_bills_as_text(usage: Any) -> None:
    provider = _provider_returning(_build_fake_image_response(usage=usage))

    result = await provider.generate(prompt="x")

    assert result.cost_usd == pytest.approx((300 * 5.00 + 1000 * 30.00) / 1e6)


async def test_generation_log_carries_token_counts(monkeypatch: MonkeyPatch) -> None:
    fake_log = MagicMock()
    monkeypatch.setattr("app.providers.image.openai_provider.log", fake_log)
    usage = _sdk_usage(text_tokens=100, image_tokens=200, output_tokens=1000)
    provider = _provider_returning(_build_fake_image_response(usage=usage))

    await provider.generate(prompt="x")

    assert fake_log.info.call_args.args == ("openai_image_generation",)
    fields = fake_log.info.call_args.kwargs
    assert fields["text_input_tokens"] == 100
    assert fields["image_input_tokens"] == 200
    assert fields["image_output_tokens"] == 1000
    assert fields["text_output_tokens"] == 0
    fake_log.warning.assert_not_called()


# ── text output tokens are not billed ──────────────────────────────────


def _usage_with_output_details(output_tokens_details: Any) -> Any:
    """`usage` as the SDK's models parse an API payload. SDK 1.109.1's `Usage`
    has no `output_tokens_details` field, so that block stays a plain dict."""
    payload: dict[str, Any] = {
        "created": 1,
        "usage": {
            "input_tokens": 40,
            "input_tokens_details": {"text_tokens": 40, "image_tokens": 0},
            "output_tokens": 1200,
            "output_tokens_details": output_tokens_details,
            "total_tokens": 1240,
        },
    }
    return ImagesResponse.model_validate(payload).usage


async def test_text_output_tokens_are_logged_but_not_billed(monkeypatch: MonkeyPatch) -> None:
    """OpenAI's Images API counts text tokens in `output_tokens`, but
    doesn't bill text output for these models: only the 1,000 image
    tokens bill at $30 per 1M, not all 1,200."""
    fake_log = MagicMock()
    monkeypatch.setattr("app.providers.image.openai_provider.log", fake_log)
    usage = _usage_with_output_details({"image_tokens": 1000, "text_tokens": 200})
    assert isinstance(usage.output_tokens_details, dict)  # the real SDK shape
    provider = _provider_returning(_build_fake_image_response(usage=usage))

    result = await provider.generate(prompt="x")

    assert result.cost_usd == pytest.approx((40 * 5.00 + 1000 * 30.00) / 1e6)
    fields = fake_log.info.call_args.kwargs
    assert fields["image_output_tokens"] == 1000
    assert fields["text_output_tokens"] == 200


async def test_output_details_are_read_as_attributes_too() -> None:
    usage = SimpleNamespace(
        input_tokens=40,
        output_tokens=1200,
        output_tokens_details=SimpleNamespace(image_tokens=1000, text_tokens=200),
    )
    provider = _provider_returning(_build_fake_image_response(usage=usage))

    result = await provider.generate(prompt="x")

    assert result.cost_usd == pytest.approx((40 * 5.00 + 1000 * 30.00) / 1e6)


@pytest.mark.parametrize(
    "output_tokens_details",
    [
        None,
        {},
        {"image_tokens": 0, "text_tokens": 1200},
        {"image_tokens": 5000, "text_tokens": 0},
        {"image_tokens": "1000"},
        {"image_tokens": -1},
    ],
    ids=["none", "empty", "zero-image", "more-than-total", "non-int", "negative"],
)
async def test_untrustworthy_output_details_bill_every_output_token(
    output_tokens_details: Any,
) -> None:
    """Without a usable image count, fall back to billing all 1,200 output
    tokens: over-recording beats silently dropping billed tokens."""
    usage = _usage_with_output_details(output_tokens_details)
    provider = _provider_returning(_build_fake_image_response(usage=usage))

    result = await provider.generate(prompt="x")

    assert result.cost_usd == pytest.approx((40 * 5.00 + 1200 * 30.00) / 1e6)


# ── fallback estimate when usage is missing or unusable ────────────────


@pytest.mark.parametrize(
    ("quality", "estimate"),
    [(ImageQuality.LOW, 0.006), (ImageQuality.MEDIUM, 0.053), (ImageQuality.HIGH, 0.211)],
)
async def test_missing_usage_records_the_reference_estimate_and_warns(
    monkeypatch: MonkeyPatch, quality: ImageQuality, estimate: float
) -> None:
    fake_log = MagicMock()
    monkeypatch.setattr("app.providers.image.openai_provider.log", fake_log)
    provider = _provider_returning(_build_fake_image_response(usage=None))

    result = await provider.generate(prompt="x", quality=quality)

    assert result.cost_usd == estimate
    fake_log.warning.assert_called_once_with(
        "openai_image_usage_missing",
        model=_MODEL,
        quality=quality.value,
        estimated_cost_usd=estimate,
    )
    fields = fake_log.info.call_args.kwargs
    assert fields["image_output_tokens"] is None
    assert fields["text_output_tokens"] is None


@pytest.mark.parametrize(
    ("model", "estimate"),
    [("gpt-image-2.5-flare", 0.006), ("gpt-image-2.6-flare", 0.02469)],
)
def test_missing_usage_estimate_is_per_model(model: str, estimate: float) -> None:
    """2.6 has its own low estimate from OpenAI's 2.6 calculator; reusing
    gpt-image-2's $0.006 would under-record it about 4x."""
    assert _compute_cost_usd(model, ImageQuality.LOW, None) == estimate


@pytest.mark.parametrize(
    "usage",
    [
        SimpleNamespace(input_tokens=None, output_tokens=1000),
        SimpleNamespace(input_tokens=40, output_tokens=None),
        SimpleNamespace(input_tokens=40, output_tokens=0),
        SimpleNamespace(input_tokens=-1, output_tokens=1000),
        SimpleNamespace(input_tokens="40", output_tokens=1000),
        SimpleNamespace(),
    ],
    ids=["no-input", "no-output", "zero-output", "negative", "non-int", "empty"],
)
async def test_unusable_usage_falls_back_to_the_estimate(usage: Any) -> None:
    provider = _provider_returning(_build_fake_image_response(usage=usage))

    result = await provider.generate(prompt="x", quality=ImageQuality.MEDIUM)

    assert result.cost_usd == 0.053


# ── unpriced models ────────────────────────────────────────────────────


def test_cost_for_unknown_model_is_zero_in_local(monkeypatch: MonkeyPatch) -> None:
    # Default test env is `local`; unknown models log + return 0.0.
    fake_log = MagicMock()
    monkeypatch.setattr("app.providers.image.openai_provider.log", fake_log)

    assert _compute_cost_usd("future-image-model", ImageQuality.HIGH, None) == 0.0

    fake_log.warning.assert_called_once_with(
        "openai_image_unknown_pricing_local_only",
        model="future-image-model",
        quality="high",
    )


def test_cost_for_unknown_model_raises_in_non_local(monkeypatch: MonkeyPatch) -> None:
    """Same reasoning as the LLM provider — unknown pricing in
    production silently destroys cost accounting."""
    from app.core.config import Environment, get_settings

    monkeypatch.setattr(get_settings(), "environment", Environment.PROD)
    from app.providers.errors import ProviderConfigError

    with pytest.raises(ProviderConfigError, match="No pricing entry"):
        _compute_cost_usd("future-image-model", ImageQuality.HIGH, None)


def test_shut_down_gpt_image_1_has_no_price() -> None:
    """gpt-image-1 stays in the catalog only to name its shutdown date and
    replacement; it must not be priced as if it still worked."""
    assert _compute_cost_usd("gpt-image-1", ImageQuality.MEDIUM, None) == 0.0


# ── error paths ────────────────────────────────────────────────────────


async def test_response_with_no_data_raises_provider_error() -> None:
    """Defensive coverage — if OpenAI ever returns an empty `data` array,
    we surface a clear ProviderError instead of an IndexError."""
    empty = MagicMock()
    empty.data = []
    generate_mock = AsyncMock(return_value=empty)
    client = _build_fake_client(generate_mock)
    provider = OpenAIImageProvider(client=client, model=_MODEL)

    with pytest.raises(ProviderError, match="no data"):
        await provider.generate(prompt="x")


async def test_response_with_missing_b64_raises_provider_error() -> None:
    fake = MagicMock()
    fake.data = [MagicMock()]
    fake.data[0].b64_json = None
    generate_mock = AsyncMock(return_value=fake)
    client = _build_fake_client(generate_mock)
    provider = OpenAIImageProvider(client=client, model=_MODEL)

    with pytest.raises(ProviderError, match="b64_json"):
        await provider.generate(prompt="x")


# ── retry behavior ─────────────────────────────────────────────────────


async def test_retries_on_rate_limit_and_succeeds(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("app.providers.image.openai_provider.asyncio.sleep", AsyncMock())

    generate_mock = AsyncMock(side_effect=[_make_rate_limit_error(), _build_fake_image_response()])
    client = _build_fake_client(generate_mock)
    provider = OpenAIImageProvider(client=client, model=_MODEL, max_retries=3)

    result = await provider.generate(prompt="x")
    assert generate_mock.call_count == 2
    assert result.image_bytes


async def test_retries_exhausted_raises(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("app.providers.image.openai_provider.asyncio.sleep", AsyncMock())

    generate_mock = AsyncMock(side_effect=[_make_rate_limit_error()] * 3)
    client = _build_fake_client(generate_mock)
    provider = OpenAIImageProvider(client=client, model=_MODEL, max_retries=3)

    with pytest.raises(ProviderRetryExhausted):
        await provider.generate(prompt="x")
    assert generate_mock.call_count == 3


async def test_construction_without_api_key_raises_config_error(
    monkeypatch: MonkeyPatch,
) -> None:
    from app.core.config import get_settings
    from app.providers.errors import ProviderConfigError

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", None)
    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        OpenAIImageProvider()
