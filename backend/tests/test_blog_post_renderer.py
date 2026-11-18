# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Unit tests for the blog-post markdown renderer."""

from __future__ import annotations

import pytest

from app.schemas.content import BlogPostResult, BlogPostSection
from app.services.renderers.blog_post import render_blog_post, word_count


def _sample_result(**overrides: object) -> BlogPostResult:
    data: dict[str, object] = {
        "title": "How Mocked Content Helps Local Dev",
        "meta_description": "Why we ship a fully-implemented mock provider.",
        "intro": "Real LLM calls are slow and paid. Mocks aren't.",
        "sections": [
            BlogPostSection(heading="Why mock", body="You want CI to run offline."),
            BlogPostSection(
                heading="What it costs",
                body="Nothing. That's the whole point.",
            ),
        ],
        "conclusion": "Treat mocks as peer implementations.",
        "suggested_tags": ["mock", "developer experience"],
    }
    data.update(overrides)
    return BlogPostResult.model_validate(data)


def test_renders_title_as_h1() -> None:
    md = render_blog_post(_sample_result())
    assert md.splitlines()[0] == "# How Mocked Content Helps Local Dev"


def test_renders_each_section_as_h2_with_body() -> None:
    md = render_blog_post(_sample_result())
    assert "## Why mock" in md
    assert "## What it costs" in md
    # Body content follows its heading.
    assert "You want CI to run offline." in md


def test_renders_tags_with_hash_prefix_and_hyphenated_multiword() -> None:
    md = render_blog_post(_sample_result())
    assert md.rstrip().endswith("Tags: #mock #developer-experience")


def test_word_count_is_whitespace_split() -> None:
    assert word_count("") == 0
    assert word_count("   ") == 0
    assert word_count("one two three") == 3


@pytest.mark.parametrize(
    "tags",
    [
        ["#already-hashed"],
        ["UPPER case"],
        ["    spaced    "],
    ],
)
def test_tag_normalization_handles_edge_cases(tags: list[str]) -> None:
    md = render_blog_post(_sample_result(suggested_tags=tags))
    # Tags line is the last non-empty line.
    tags_line = next(line for line in reversed(md.splitlines()) if line.strip())
    assert tags_line.startswith("Tags: #")
    assert "#" * 2 not in tags_line  # no double-hashing
