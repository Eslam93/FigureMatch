# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Unit tests for the ad-copy renderer."""

from __future__ import annotations

from app.schemas.content import AdCopyResult, AdCopyVariant
from app.services.renderers.ad_copy import render_ad_copy


def _sample(**overrides: object) -> AdCopyResult:
    data: dict[str, object] = {
        "variants": [
            AdCopyVariant.model_validate(
                {
                    "format": "long",
                    "angle": "transformation",
                    "headline": "Long headline that earns the scroll",
                    "body": "A longer body that explains the offer in more detail.",
                    "cta": "Read more",
                }
            ),
            AdCopyVariant.model_validate(
                {
                    "format": "short",
                    "angle": "curiosity",
                    "headline": "Short hook",
                    "body": "Short body",
                    "cta": "Try it",
                }
            ),
            AdCopyVariant.model_validate(
                {
                    "format": "medium",
                    "angle": "social_proof",
                    "headline": "Medium headline",
                    "body": "Medium body with concrete claims.",
                    "cta": "See the setup",
                }
            ),
        ],
    }
    data.update(overrides)
    return AdCopyResult.model_validate(data)


def test_renders_variants_in_short_medium_long_order_regardless_of_input() -> None:
    """Provider may return variants in any order; the renderer normalizes
    to the canonical short → medium → long ladder."""
    md = render_ad_copy(_sample())
    short_idx = md.index("## Short")
    medium_idx = md.index("## Medium")
    long_idx = md.index("## Long")
    assert short_idx < medium_idx < long_idx


def test_each_variant_includes_angle_label_in_heading() -> None:
    md = render_ad_copy(_sample())
    assert "## Short (curiosity)" in md
    assert "## Medium (social_proof)" in md
    assert "## Long (transformation)" in md


def test_headline_is_h3_and_cta_on_its_own_line() -> None:
    md = render_ad_copy(_sample())
    assert "### Short hook" in md
    assert "CTA: Try it" in md
    assert "CTA: See the setup" in md
    assert "CTA: Read more" in md
