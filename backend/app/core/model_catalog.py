"""Dated catalog of the OpenAI models this app can be configured with.

The single source of truth for model ids, prices and lifecycle (shutdown
dates and suggested replacements). Every id, price and shutdown date was
copied from OpenAI's own docs on the entry's `verified_on` date, from the
page in `source_url`. Re-verify against that page before changing a number;
never estimate one. The per-image fallback costs are the one labelled
estimate. A replacement is one OpenAI names, unless a comment says why the
catalog suggests another.

Prices are OpenAI's standard tier, in USD per 1M tokens.

Consumers:
  - `app.core.config` refuses shut-down or unpriced models at boot;
  - the OpenAI chat and image providers price every call from here;
  - `app.scripts.check_model_lifecycle` flags a configured model before
    its shutdown date, weekly in CI.

This module must stay free of `app.core.config` and `app.providers`
imports: both of those import it, so anything else would be a cycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Literal

ModelKind = Literal["text", "image"]


@dataclass(frozen=True, slots=True)
class TextPricing:
    """Text-model prices, USD per 1M tokens."""

    input_per_million: float
    cached_input_per_million: float
    output_per_million: float


@dataclass(frozen=True, slots=True)
class ReferenceImageCost:
    """Per-image cost *estimate* in USD for one 1024×1024 image, by quality.

    Not a price: the GPT Image models bill per token. This is only the
    fallback recorded when a response reports no usable token `usage`.
    """

    low: float
    medium: float
    high: float

    def for_quality(self, quality: str) -> float:
        by_quality = {"low": self.low, "medium": self.medium, "high": self.high}
        if quality not in by_quality:
            raise ValueError(f"No reference image cost for quality={quality!r}.")
        return by_quality[quality]


@dataclass(frozen=True, slots=True)
class ImagePricing:
    """Images API prices, USD per 1M tokens, plus the fallback estimate."""

    text_input_per_million: float
    image_input_per_million: float
    image_output_per_million: float
    reference_cost_per_image: ReferenceImageCost


@dataclass(frozen=True, slots=True)
class ModelEntry:
    """One model id. `pricing` is None for models we must not run on.

    Shut-down and shutting-down models carry no price on purpose: their
    entries exist so config validation can name the date and replacement.
    """

    model_id: str
    kind: ModelKind
    pricing: TextPricing | ImagePricing | None
    verified_on: date
    source_url: str
    shutdown_on: date | None = None
    replacement: str | None = None


class ModelStatus(StrEnum):
    """How usable a model id is for a given kind on a given day."""

    OK = "ok"  # catalogued for this kind, priced, not shut down
    UNKNOWN = "unknown"  # not in the catalog at all
    RETIRED = "retired"  # shutdown date is on or before the day asked about
    WRONG_KIND = "wrong_kind"  # catalogued, but as the other kind
    UNPRICED = "unpriced"  # catalogued for this kind, but no verified price


VERIFIED_ON: Final = date(2026, 11, 6)

# OpenAI's canonical docs URLs (platform.openai.com/docs/... redirects here).
_PRICING_URL: Final = "https://developers.openai.com/api/docs/pricing"
_DEPRECATIONS_URL: Final = "https://developers.openai.com/api/docs/deprecations"
_GPT_5_4_MINI_URL: Final = "https://developers.openai.com/api/docs/models/gpt-5.4-mini"
_GPT_IMAGE_2_5_FLARE_URL: Final = (
    "https://developers.openai.com/api/docs/models/gpt-image-2.5-flare"
)

_GPT_5_4_MINI_PRICING: Final = TextPricing(
    input_per_million=0.75,
    cached_input_per_million=0.075,
    output_per_million=4.50,
)


def _gpt_image_pricing(reference_cost_per_image: ReferenceImageCost) -> ImagePricing:
    """The token rates all four current GPT Image models share.

    No cached-input rate: for GPT Image 2 and 2.5 OpenAI bills cached input
    only through the Responses API image tool, never on direct Images API
    calls (all this app makes), and the Images API `usage` block reports no
    cached-token count for any model, so every input token bills in full.
    """
    return ImagePricing(
        text_input_per_million=5.00,
        image_input_per_million=8.00,
        image_output_per_million=30.00,
        reference_cost_per_image=reference_cost_per_image,
    )


# The per-image costs below are ESTIMATES, recorded only when a response
# carries no usable `usage`. OpenAI warns that equal token rates don't mean
# equal cost per image, and it publishes no per-image price for these models.
#
# 2.5: OpenAI's per-image table for gpt-image-2 at 1024×1024, billed at the
# same token rates. The 2.5 model page says the GPT Image 2 calculator does
# not estimate 2.5 token use, so this is only the closest published figure.
_GPT_IMAGE_2_5_PRICING: Final = _gpt_image_pricing(
    ReferenceImageCost(low=0.006, medium=0.053, high=0.211)
)
# 2.6: low is OpenAI's GPT Image 2.6 calculator at 1024×1024 (823 output
# tokens at $30 per 1M = $0.02469), about 4x gpt-image-2's low. Medium and
# high reuse gpt-image-2's figures because no 2.6 value for them was
# verified; as 2.6 bills more than gpt-image-2 at low, they may be low too.
_GPT_IMAGE_2_6_PRICING: Final = _gpt_image_pricing(
    ReferenceImageCost(low=0.02469, medium=0.053, high=0.211)
)

_GPT_IMAGE_1_SHUTDOWN: Final = date(2026, 10, 23)
_GPT_IMAGE_1_5_SHUTDOWN: Final = date(2026, 12, 1)
_DALL_E_SHUTDOWN: Final = date(2026, 5, 12)


def _text(model_id: str, pricing: TextPricing, source_url: str) -> ModelEntry:
    return ModelEntry(
        model_id=model_id,
        kind="text",
        pricing=pricing,
        verified_on=VERIFIED_ON,
        source_url=source_url,
    )


def _image(model_id: str, pricing: ImagePricing, source_url: str = _PRICING_URL) -> ModelEntry:
    return ModelEntry(
        model_id=model_id,
        kind="image",
        pricing=pricing,
        verified_on=VERIFIED_ON,
        source_url=source_url,
    )


def _retired_image(model_id: str, shutdown_on: date, replacement: str) -> ModelEntry:
    return ModelEntry(
        model_id=model_id,
        kind="image",
        pricing=None,
        verified_on=VERIFIED_ON,
        source_url=_DEPRECATIONS_URL,
        shutdown_on=shutdown_on,
        replacement=replacement,
    )


_ENTRIES: Final[tuple[ModelEntry, ...]] = (
    # Text. `gpt-5.4-mini` is the alias; the dated id is its pinned snapshot.
    _text("gpt-5.4-mini", _GPT_5_4_MINI_PRICING, _GPT_5_4_MINI_URL),
    _text("gpt-5.4-mini-2026-03-17", _GPT_5_4_MINI_PRICING, _GPT_5_4_MINI_URL),
    # Images, current. The 2.5 Flare model page lists its dated snapshot at
    # the same prices. The 2.5 Sunburst snapshot is left out because no
    # verified OpenAI page prices it, so pinning it fails at boot instead of
    # billing at a guessed rate.
    _image("gpt-image-2.5-flare", _GPT_IMAGE_2_5_PRICING),
    _image("gpt-image-2.5-flare-2026-09-08", _GPT_IMAGE_2_5_PRICING, _GPT_IMAGE_2_5_FLARE_URL),
    _image("gpt-image-2.5-sunburst", _GPT_IMAGE_2_5_PRICING),
    _image("gpt-image-2.6-flare", _GPT_IMAGE_2_6_PRICING),
    _image("gpt-image-2.6-sunburst", _GPT_IMAGE_2_6_PRICING),
    # Images, shut down or shutting down.
    _retired_image("gpt-image-1", _GPT_IMAGE_1_SHUTDOWN, "gpt-image-2.5-flare"),
    _retired_image("gpt-image-1.5", _GPT_IMAGE_1_5_SHUTDOWN, "gpt-image-2.6-flare"),
    _retired_image("gpt-image-1.5-2025-12-16", _GPT_IMAGE_1_5_SHUTDOWN, "gpt-image-2.6-flare"),
    _retired_image("gpt-image-1-mini", _GPT_IMAGE_1_5_SHUTDOWN, "gpt-image-2.6-flare"),
    _retired_image("chatgpt-image-latest", _GPT_IMAGE_1_5_SHUTDOWN, "gpt-image-2.6-flare"),
    # OpenAI names gpt-image-2, gpt-image-1 or gpt-image-1-mini for DALL·E.
    # gpt-image-1 is shut down, gpt-image-1-mini shuts down on 2026-12-01,
    # and OpenAI's image guide sends new integrations to GPT Image 2.5, so
    # the catalog suggests its 2.5 default instead.
    _retired_image("dall-e-2", _DALL_E_SHUTDOWN, "gpt-image-2.5-flare"),
    _retired_image("dall-e-3", _DALL_E_SHUTDOWN, "gpt-image-2.5-flare"),
)

MODEL_CATALOG: Final[Mapping[str, ModelEntry]] = MappingProxyType(
    {entry.model_id: entry for entry in _ENTRIES}
)


def today() -> date:
    """Today's date in UTC. Callers go through this so tests can pin it."""
    return datetime.now(UTC).date()


def lookup(model_id: str) -> ModelEntry | None:
    return MODEL_CATALOG.get(model_id)


def is_retired(entry: ModelEntry, *, on: date) -> bool:
    """True once the shutdown date has arrived (the shutdown day counts)."""
    return entry.shutdown_on is not None and entry.shutdown_on <= on


def days_until_shutdown(entry: ModelEntry, *, on: date) -> int | None:
    """Days from `on` to the shutdown date; negative once it has passed."""
    if entry.shutdown_on is None:
        return None
    return (entry.shutdown_on - on).days


def shuts_down_within(entry: ModelEntry, days: int, *, on: date) -> bool:
    """True if the shutdown date is at most `days` days after `on`.

    Already-passed shutdowns count as within any window.
    """
    remaining = days_until_shutdown(entry, on=on)
    return remaining is not None and remaining <= days


def classify(model_id: str, kind: ModelKind, *, on: date) -> ModelStatus:
    """Classify `model_id` for a `kind` slot. A shut-down model is RETIRED
    whatever slot it was put in, since it cannot work in either."""
    entry = lookup(model_id)
    if entry is None:
        return ModelStatus.UNKNOWN
    if is_retired(entry, on=on):
        return ModelStatus.RETIRED
    if entry.kind != kind:
        return ModelStatus.WRONG_KIND
    if entry.pricing is None:
        return ModelStatus.UNPRICED
    return ModelStatus.OK


def text_pricing(model_id: str) -> TextPricing | None:
    """Prices for a catalogued text model, else None."""
    entry = lookup(model_id)
    if entry is None or not isinstance(entry.pricing, TextPricing):
        return None
    return entry.pricing


def image_pricing(model_id: str) -> ImagePricing | None:
    """Prices for a catalogued image model, else None."""
    entry = lookup(model_id)
    if entry is None or not isinstance(entry.pricing, ImagePricing):
        return None
    return entry.pricing
