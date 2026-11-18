# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""MockLLMProvider + MockImageProvider — full behavioral coverage.

These tests double as the schema-drift detector for the canned mock
responses: every content_type's payload is parsed as JSON, and the
required-field shape is asserted. When Phase 3 lands the real Pydantic
schemas, those schemas become the authoritative validators.
"""

from __future__ import annotations

import json

import pytest

from app.providers.image.base import ImageQuality
from app.providers.image.mock import MockImageProvider
from app.providers.llm.mock import MockLLMProvider

# ── MockLLMProvider ────────────────────────────────────────────────────


_EXPECTED_FIELDS: dict[str, set[str]] = {
    "blog_post": {
        "title",
        "meta_description",
        "intro",
        "sections",
        "conclusion",
        "suggested_tags",
    },
    "linkedin_post": {"hook", "body", "cta", "hashtags"},
    "ad_copy": {"variants"},
    "email": {"subject", "preview_text", "greeting", "body", "cta_text", "sign_off"},
    "image_prompt": {"prompt", "negative_prompt", "style_summary"},
    "improver_analysis": {"issues", "planned_changes"},
    "improver_rewrite": {"improved_text", "explanation", "changes_summary"},
}


@pytest.mark.parametrize("content_type", sorted(_EXPECTED_FIELDS.keys()))
async def test_mock_llm_returns_valid_json_for_each_content_type(
    content_type: str,
) -> None:
    provider = MockLLMProvider()
    result = await provider.generate(
        system_prompt="ignored",
        user_prompt="ignored",
        content_type=content_type,
    )
    payload = json.loads(result.raw_text)
    assert isinstance(payload, dict)
    missing = _EXPECTED_FIELDS[content_type] - payload.keys()
    assert missing == set(), f"missing fields in mock {content_type}: {missing}"


async def test_mock_llm_ad_copy_has_three_variants() -> None:
    """Brief §7.3 requires three ad variants (short/medium/long).
    The mock must produce the same shape so downstream rendering
    doesn't have to special-case the mock path."""
    provider = MockLLMProvider()
    result = await provider.generate(
        system_prompt="x",
        user_prompt="x",
        content_type="ad_copy",
    )
    payload = json.loads(result.raw_text)
    formats = {v["format"] for v in payload["variants"]}
    assert formats == {"short", "medium", "long"}


async def test_mock_llm_unknown_content_type_returns_fallback() -> None:
    """Unknown types get a sentinel payload, never crash. Real callers
    should never reach this branch — but if they do, the fallback is
    visible in logs rather than a 500."""
    provider = MockLLMProvider()
    result = await provider.generate(
        system_prompt="x",
        user_prompt="x",
        content_type="this_content_type_does_not_exist",
    )
    payload = json.loads(result.raw_text)
    assert "_note" in payload


async def test_mock_llm_reports_zero_cost_and_zero_latency() -> None:
    """The mock should NEVER show non-zero cost, so recorded costs tell
    real-money calls apart from offline mocks."""
    provider = MockLLMProvider()
    result = await provider.generate(
        system_prompt="x",
        user_prompt="x",
        content_type="blog_post",
    )
    assert result.cost_usd == 0.0
    assert result.latency_ms == 0
    assert result.model == "mock-llm-v1"


async def test_mock_llm_finish_reason_is_stop() -> None:
    """The mock simulates a clean, complete response — downstream
    parsing should never see a truncated or content-filtered
    finish_reason during testing."""
    provider = MockLLMProvider()
    result = await provider.generate(
        system_prompt="x",
        user_prompt="x",
        content_type="blog_post",
    )
    assert result.finish_reason == "stop"


# ── MockImageProvider ──────────────────────────────────────────────────


async def test_mock_image_returns_valid_png_bytes() -> None:
    """The placeholder must be a real PNG, not arbitrary bytes —
    downstream code (S3 upload, dimension probing) treats it like
    any other image."""
    provider = MockImageProvider()
    result = await provider.generate(prompt="any prompt")
    # PNG signature: 89 50 4E 47 0D 0A 1A 0A
    assert result.image_bytes.startswith(b"\x89PNG\r\n\x1a\n")


async def test_mock_image_reports_actual_1x1_dimensions() -> None:
    """The embedded PNG is 1×1. Reporting fake 1024×1024 would lie to
    downstream code (S3 upload, dimension probing). The mock reports
    what's actually in the bytes."""
    provider = MockImageProvider()
    result = await provider.generate(prompt="x")
    assert result.width == 1
    assert result.height == 1


async def test_mock_image_ignores_requested_size() -> None:
    """The `size` kwarg is kept for interface parity with the OpenAI
    provider but doesn't change the returned dimensions — the bytes
    are fixed."""
    provider = MockImageProvider()
    result = await provider.generate(prompt="x", size=(512, 256))
    assert result.width == 1
    assert result.height == 1


async def test_mock_image_zero_cost_and_zero_latency() -> None:
    provider = MockImageProvider()
    result = await provider.generate(prompt="x", quality=ImageQuality.HIGH)
    assert result.cost_usd == 0.0
    assert result.latency_ms == 0
    assert result.quality == ImageQuality.HIGH


async def test_mock_image_returns_same_bytes_each_call() -> None:
    """Determinism guarantee — tests can assert on byte content."""
    provider = MockImageProvider()
    a = await provider.generate(prompt="anything")
    b = await provider.generate(prompt="something else")
    assert a.image_bytes == b.image_bytes
