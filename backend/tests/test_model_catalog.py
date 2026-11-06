"""The model catalog — lookup, classification, lifecycle date logic.

Every date-sensitive assertion passes an explicit `on=` date, so these
tests stay true after the real shutdown dates go by.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from app.core import model_catalog
from app.core.model_catalog import (
    MODEL_CATALOG,
    ImagePricing,
    ModelStatus,
    ReferenceImageCost,
    TextPricing,
)

if TYPE_CHECKING:
    from pytest import MonkeyPatch

_VERIFIED = date(2026, 11, 6)


# ── catalog contents ───────────────────────────────────────────────────


def test_gpt_5_4_mini_alias_and_snapshot_share_the_verified_prices() -> None:
    for model_id in ("gpt-5.4-mini", "gpt-5.4-mini-2026-03-17"):
        assert model_catalog.text_pricing(model_id) == TextPricing(
            input_per_million=0.75,
            cached_input_per_million=0.075,
            output_per_million=4.50,
        )


# Fallback estimates. 2.5 uses OpenAI's gpt-image-2 per-image table; 2.6's
# low comes from OpenAI's own GPT Image 2.6 calculator instead.
_GPT_IMAGE_2_TABLE = ReferenceImageCost(low=0.006, medium=0.053, high=0.211)
_GPT_IMAGE_2_6_ESTIMATE = ReferenceImageCost(low=0.02469, medium=0.053, high=0.211)


@pytest.mark.parametrize(
    ("model_id", "reference"),
    [
        ("gpt-image-2.5-flare", _GPT_IMAGE_2_TABLE),
        ("gpt-image-2.5-flare-2026-09-08", _GPT_IMAGE_2_TABLE),
        ("gpt-image-2.5-sunburst", _GPT_IMAGE_2_TABLE),
        ("gpt-image-2.6-flare", _GPT_IMAGE_2_6_ESTIMATE),
        ("gpt-image-2.6-sunburst", _GPT_IMAGE_2_6_ESTIMATE),
    ],
)
def test_current_image_models_carry_the_verified_token_rates(
    model_id: str, reference: ReferenceImageCost
) -> None:
    pricing = model_catalog.image_pricing(model_id)
    assert pricing is not None
    assert pricing.text_input_per_million == 5.00
    assert pricing.image_input_per_million == 8.00
    assert pricing.image_output_per_million == 30.00
    assert pricing.reference_cost_per_image == reference


def test_gpt_image_2_6_low_estimate_is_the_calculators_823_output_tokens() -> None:
    """OpenAI's calculator: 823 output tokens for a low 1024×1024 2.6 image,
    about 4x gpt-image-2's published $0.006, so 2.6 must not reuse that."""
    pricing = model_catalog.image_pricing("gpt-image-2.6-flare")
    assert pricing is not None
    expected = 823 * pricing.image_output_per_million / 1_000_000
    assert pricing.reference_cost_per_image.low == pytest.approx(expected)
    assert pricing.reference_cost_per_image.low > 4 * _GPT_IMAGE_2_TABLE.low


def test_pinned_flare_snapshot_is_priced_like_its_alias() -> None:
    """The 2.5 Flare page lists `gpt-image-2.5-flare-2026-09-08` as its dated
    snapshot, so pinning it (like the text model) must not fail at boot."""
    snapshot = MODEL_CATALOG["gpt-image-2.5-flare-2026-09-08"]
    assert snapshot.pricing == MODEL_CATALOG["gpt-image-2.5-flare"].pricing
    assert snapshot.source_url == (
        "https://developers.openai.com/api/docs/models/gpt-image-2.5-flare"
    )
    assert model_catalog.classify(snapshot.model_id, "image", on=_VERIFIED) is ModelStatus.OK


@pytest.mark.parametrize(
    ("model_id", "shutdown_on", "replacement"),
    [
        ("gpt-image-1", date(2026, 10, 23), "gpt-image-2.5-flare"),
        ("gpt-image-1.5", date(2026, 12, 1), "gpt-image-2.6-flare"),
        ("gpt-image-1.5-2025-12-16", date(2026, 12, 1), "gpt-image-2.6-flare"),
        ("gpt-image-1-mini", date(2026, 12, 1), "gpt-image-2.6-flare"),
        ("chatgpt-image-latest", date(2026, 12, 1), "gpt-image-2.6-flare"),
        ("dall-e-2", date(2026, 5, 12), "gpt-image-2.5-flare"),
        ("dall-e-3", date(2026, 5, 12), "gpt-image-2.5-flare"),
    ],
)
def test_retired_and_retiring_models_have_a_date_and_replacement_but_no_price(
    model_id: str, shutdown_on: date, replacement: str
) -> None:
    entry = model_catalog.lookup(model_id)
    assert entry is not None
    assert entry.kind == "image"
    assert entry.pricing is None
    assert entry.shutdown_on == shutdown_on
    assert entry.replacement == replacement
    assert entry.source_url == "https://developers.openai.com/api/docs/deprecations"


def test_every_entry_is_internally_consistent() -> None:
    for model_id, entry in MODEL_CATALOG.items():
        assert entry.model_id == model_id
        assert entry.verified_on == _VERIFIED
        # OpenAI's canonical docs host, not the platform.openai.com redirect.
        assert entry.source_url.startswith("https://developers.openai.com/api/docs/")
        if entry.pricing is not None:
            expected = TextPricing if entry.kind == "text" else ImagePricing
            assert isinstance(entry.pricing, expected), model_id
        if entry.shutdown_on is not None:
            # A replacement must itself be a priced model of the same kind,
            # or the error message would send people somewhere dead.
            assert entry.replacement is not None, model_id
            replacement = model_catalog.lookup(entry.replacement)
            assert replacement is not None, model_id
            assert replacement.kind == entry.kind
            assert replacement.pricing is not None
            assert replacement.shutdown_on is None


# ── lookup + pricing helpers ───────────────────────────────────────────


def test_lookup_unknown_model_returns_none() -> None:
    assert model_catalog.lookup("gpt-9-imaginary") is None


def test_pricing_helpers_are_kind_aware() -> None:
    assert model_catalog.text_pricing("gpt-image-2.5-flare") is None
    assert model_catalog.image_pricing("gpt-5.4-mini") is None
    assert model_catalog.text_pricing("gpt-9-imaginary") is None
    assert model_catalog.image_pricing("gpt-9-imaginary") is None
    # Retired entries carry no price at all.
    assert model_catalog.image_pricing("gpt-image-1") is None


def test_reference_cost_by_quality() -> None:
    ref = ReferenceImageCost(low=0.006, medium=0.053, high=0.211)
    assert ref.for_quality("low") == 0.006
    assert ref.for_quality("medium") == 0.053
    assert ref.for_quality("high") == 0.211
    with pytest.raises(ValueError, match="xhigh"):
        ref.for_quality("xhigh")


# ── classification ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("model_id", "kind", "on", "expected"),
    [
        ("gpt-5.4-mini-2026-03-17", "text", _VERIFIED, ModelStatus.OK),
        ("gpt-image-2.5-flare", "image", _VERIFIED, ModelStatus.OK),
        ("gpt-9-imaginary", "text", _VERIFIED, ModelStatus.UNKNOWN),
        ("gpt-image-1", "image", _VERIFIED, ModelStatus.RETIRED),
        ("dall-e-3", "image", _VERIFIED, ModelStatus.RETIRED),
        ("gpt-image-2.5-flare", "text", _VERIFIED, ModelStatus.WRONG_KIND),
        ("gpt-5.4-mini", "image", _VERIFIED, ModelStatus.WRONG_KIND),
        # Shutting down 2026-12-01: unpriced before, retired from that day.
        ("gpt-image-1.5", "image", date(2026, 11, 30), ModelStatus.UNPRICED),
        ("gpt-image-1.5", "image", date(2026, 12, 1), ModelStatus.RETIRED),
        # Retired wins over wrong kind: a dead model works in no slot.
        ("gpt-image-1", "text", _VERIFIED, ModelStatus.RETIRED),
    ],
)
def test_classify(
    model_id: str, kind: model_catalog.ModelKind, on: date, expected: ModelStatus
) -> None:
    assert model_catalog.classify(model_id, kind, on=on) is expected


def test_gpt_image_1_was_already_live_the_day_before_shutdown() -> None:
    """Retired means the shutdown day has arrived — not before."""
    entry = MODEL_CATALOG["gpt-image-1"]
    assert not model_catalog.is_retired(entry, on=date(2026, 10, 22))
    assert model_catalog.is_retired(entry, on=date(2026, 10, 23))


# ── shutdown windows ───────────────────────────────────────────────────


def test_days_until_shutdown() -> None:
    entry = MODEL_CATALOG["gpt-image-1.5"]
    assert model_catalog.days_until_shutdown(entry, on=_VERIFIED) == 25
    assert model_catalog.days_until_shutdown(entry, on=date(2026, 12, 3)) == -2
    assert model_catalog.days_until_shutdown(MODEL_CATALOG["gpt-5.4-mini"], on=_VERIFIED) is None


def test_shuts_down_within_window_boundaries() -> None:
    entry = MODEL_CATALOG["gpt-image-1.5"]  # 25 days after _VERIFIED
    assert model_catalog.shuts_down_within(entry, 30, on=_VERIFIED)
    assert model_catalog.shuts_down_within(entry, 25, on=_VERIFIED)
    assert not model_catalog.shuts_down_within(entry, 24, on=_VERIFIED)
    # A shutdown that already happened is inside every window.
    assert model_catalog.shuts_down_within(MODEL_CATALOG["gpt-image-1"], 0, on=_VERIFIED)


def test_models_without_a_shutdown_never_fall_inside_a_window() -> None:
    entry = MODEL_CATALOG["gpt-image-2.5-flare"]
    assert not model_catalog.shuts_down_within(entry, 100_000, on=_VERIFIED)


def test_today_is_the_utc_date_not_the_local_one(monkeypatch: MonkeyPatch) -> None:
    """23:30 on Jan 31 at UTC-5 is already Feb 1 in UTC. The clock is pinned
    to a past day, so a regression to the machine's local date (naive
    `datetime.now()` or the real `date.today()`) can never match."""
    instant = datetime(2026, 1, 31, 23, 30, tzinfo=timezone(timedelta(hours=-5)))

    def _now(tz: tzinfo | None = None) -> datetime:
        return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)

    monkeypatch.setattr(model_catalog, "datetime", SimpleNamespace(now=_now))

    assert model_catalog.today() == date(2026, 2, 1)
