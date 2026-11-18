# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Unit tests for the LinkedIn-post renderer."""

from __future__ import annotations

import pytest

from app.schemas.content import LinkedInPostResult
from app.services.renderers.linkedin_post import render_linkedin_post


def _sample(**overrides: object) -> LinkedInPostResult:
    data: dict[str, object] = {
        "hook": "The cheapest LLM call is the one you don't make.",
        "body": (
            "Three reasons we ship a mock provider:\n1. Tests run offline.\n2. CI bills nothing."
        ),
        "cta": "What's the cheapest provider in your stack?",
        "hashtags": ["engineering", "ai"],
    }
    data.update(overrides)
    return LinkedInPostResult.model_validate(data)


def test_renders_hook_body_cta_in_order() -> None:
    md = render_linkedin_post(_sample())
    lines = md.splitlines()
    assert lines[0] == "The cheapest LLM call is the one you don't make."
    # Body is preserved as-is (with its internal newlines).
    assert "Three reasons we ship a mock provider:" in md
    assert "What's the cheapest provider in your stack?" in md


def test_hashtags_rendered_with_hash_prefix_and_space_joined() -> None:
    md = render_linkedin_post(_sample())
    assert md.rstrip().endswith("#engineering #ai")


@pytest.mark.parametrize(
    "tags,expected",
    [
        (["#alreadyhashed"], "#alreadyhashed"),
        (["UPPER case"], "#UPPER-case"),
        (["    spaced    "], "#spaced"),
    ],
)
def test_tag_normalization(tags: list[str], expected: str) -> None:
    md = render_linkedin_post(_sample(hashtags=tags))
    last = md.rstrip().splitlines()[-1]
    assert last == expected


def test_blank_hashtags_drop_silently() -> None:
    """An accidentally-empty tag string shouldn't leave a stray `#`."""
    md = render_linkedin_post(_sample(hashtags=["#valid", "   "]))
    last = md.rstrip().splitlines()[-1]
    assert last == "#valid"
