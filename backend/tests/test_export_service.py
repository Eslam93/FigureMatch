# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Unit tests for the Markdown export service.

Covers the pure transform: slug generation, header shape, image embed,
filename. The HTTP route is integration-tested separately in
`tests/integration/test_content_routes.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.db.enums import ContentType, ResultParseStatus
from app.services.export_service import build_markdown, filename_for, slugify


class _Piece:
    """Lightweight stand-in for a ContentPiece row. The export service
    only reads attributes; using a real ORM model would require a DB
    session this test doesn't need."""

    def __init__(
        self,
        *,
        topic: str = "How small teams should evaluate AI tools",
        tone: str | None = "direct, practical",
        target_audience: str | None = "engineering managers",
        content_type: ContentType = ContentType.BLOG_POST,
        model_id: str = "gpt-5.4-mini-2026-03-17",
        rendered_text: str = "# Heading\n\nBody paragraph.",
        created_at: datetime | None = None,
        piece_id: uuid.UUID | None = None,
    ) -> None:
        self.id = piece_id or uuid.UUID("12345678-1234-5678-9abc-def012345678")
        self.topic = topic
        self.tone = tone
        self.target_audience = target_audience
        self.content_type = content_type
        self.model_id = model_id
        self.rendered_text = rendered_text
        self.result_parse_status = ResultParseStatus.OK
        self.created_at = created_at or datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)


class _Image:
    def __init__(self, style: str = "photorealistic") -> None:
        self.style = style


# ── slugify ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("How small teams should evaluate AI tools", "how-small-teams-should-evaluate-ai-tools"),
        ("Spaces  and  punctuation!!", "spaces-and-punctuation"),
        ("UPPER → lower", "upper-lower"),
        ("trailing-hyphens---", "trailing-hyphens"),
        ("non-ascii: café résumé", "non-ascii-caf-r-sum"),
        ("", "content"),
        ("🚀🌟", "content"),
    ],
)
def test_slugify(topic: str, expected: str) -> None:
    assert slugify(topic) == expected


def test_slugify_caps_to_60_chars() -> None:
    # 70-char input, all valid slug chars
    topic = "abcdefghij" * 7
    slug = slugify(topic)
    assert len(slug) <= 60


# ── build_markdown ───────────────────────────────────────────────────────


def test_build_markdown_includes_header_and_body() -> None:
    md = build_markdown(_Piece(), current_image=None)
    assert md.startswith("# How small teams should evaluate AI tools\n")
    assert "**Type:** blog_post" in md
    assert "**Model:** gpt-5.4-mini-2026-03-17" in md
    assert "**Tone:** direct, practical" in md
    assert "**Audience:** engineering managers" in md
    assert "# Heading\n\nBody paragraph." in md
    assert md.endswith("\n")


def test_build_markdown_omits_optional_metadata_when_absent() -> None:
    md = build_markdown(
        _Piece(tone=None, target_audience=None),
        current_image=None,
    )
    assert "**Tone:**" not in md
    assert "**Audience:**" not in md
    # Still has the required header fields.
    assert "**Type:** blog_post" in md


def test_build_markdown_embeds_image_when_present_with_url() -> None:
    md = build_markdown(
        _Piece(),
        current_image=_Image(style="cinematic"),
        image_public_url="https://images.example.com/abc.png",
    )
    assert "![Generated image (style: cinematic)](https://images.example.com/abc.png)" in md


def test_build_markdown_skips_image_when_url_missing() -> None:
    # current_image given but URL is None — service shouldn't emit a broken link.
    md = build_markdown(_Piece(), current_image=_Image(), image_public_url=None)
    assert "![Generated image" not in md


def test_build_markdown_no_image_section_at_all_when_no_current_image() -> None:
    md = build_markdown(_Piece(), current_image=None)
    # The trailing horizontal rule only appears when an image is embedded;
    # ensure the body still ends on the rendered_text content, not a stray rule.
    assert md.count("---") == 1  # only the header/body separator


# ── filename_for ─────────────────────────────────────────────────────────


def test_filename_for_combines_slug_and_id_prefix() -> None:
    piece = _Piece(piece_id=uuid.UUID("deadbeef-1234-5678-9abc-def012345678"))
    name = filename_for(piece)
    assert name.endswith(".md")
    assert "deadbeef" in name
    assert "how-small-teams" in name
