# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Unit tests for `render_brand_voice_block` — the single function that
turns a `BrandVoice` row into the prompt-friendly text block.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.db.models import BrandVoice
from app.services.brand_voice_service import render_brand_voice_block


def _voice(**overrides: object) -> BrandVoice:
    data: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "name": "Test Brand",
        "description": None,
        "tone_descriptors": [],
        "banned_words": [],
        "sample_text": None,
        "target_audience": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "deleted_at": None,
    }
    data.update(overrides)
    voice = BrandVoice(**data)
    return voice


def test_minimal_voice_renders_just_the_name() -> None:
    block = render_brand_voice_block(_voice())
    assert block == "Brand voice: Test Brand"


def test_full_voice_renders_every_section() -> None:
    voice = _voice(
        description="Direct and honest.",
        tone_descriptors=["direct", "warm", "specific"],
        banned_words=["leverage", "synergy"],
        target_audience="senior engineers",
        sample_text="We tested every claim against production. The numbers held.",
    )
    block = render_brand_voice_block(voice)
    assert "Brand voice: Test Brand" in block
    assert "Direct and honest." in block
    assert "Tone: direct, warm, specific" in block
    assert "Banned phrases (do not use): leverage, synergy" in block
    assert "Brand audience: senior engineers" in block
    assert "Sample copy to mimic the voice" in block
    assert "the numbers held" in block.lower()


def test_blank_optional_fields_dont_emit_empty_lines() -> None:
    """A row with `description=""` (rather than NULL) shouldn't add a
    blank line to the block."""
    voice = _voice(
        description="   ",
        tone_descriptors=["", "  "],
        banned_words=[],
    )
    block = render_brand_voice_block(voice)
    assert block == "Brand voice: Test Brand"


def test_tone_descriptor_whitespace_normalized() -> None:
    voice = _voice(tone_descriptors=["  direct  ", "warm"])
    block = render_brand_voice_block(voice)
    assert "Tone: direct, warm" in block
