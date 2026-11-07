"""The corrective retry's note: what failed, field by field, never the values.

The content and improver services send this note on their second attempt,
so the model learns which rule its reply broke instead of being told, often
wrongly, that its JSON was invalid.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.schemas.content import AdCopyResult, BlogPostResult
from app.services.corrective_retry import ParseFailure, corrective_user_prompt, parse_reply

# Planted in every rejected value; the note must never repeat it.
_SENTINEL = "rejected-value-sentinel"

_VALID_BLOG: dict[str, Any] = {
    "title": "Mocks in CI",
    "meta_description": "A short explanation.",
    "intro": "Why we mock.",
    "sections": [{"heading": "H", "body": "B"}],
    "conclusion": "Done.",
    "suggested_tags": ["mock"],
}


def test_a_valid_reply_parses_into_the_model() -> None:
    parsed = parse_reply(json.dumps(_VALID_BLOG), BlogPostResult)

    assert isinstance(parsed, BlogPostResult)
    assert parsed.model_dump() == _VALID_BLOG


@pytest.mark.parametrize("raw", ["not json at all", "", '{"title": "cut off'])
def test_a_reply_that_is_not_json_is_named_as_such(raw: str) -> None:
    assert parse_reply(raw, BlogPostResult) == ParseFailure(
        "The previous reply was not valid JSON."
    )


def test_each_failing_field_is_listed_with_pydantic_message_and_no_value() -> None:
    reply = {
        **_VALID_BLOG,
        "meta_description": _SENTINEL.ljust(161, "x"),
        "sections": [{"heading": "", "body": _SENTINEL}],
        "suggested_tags": [_SENTINEL] * 11,
        "unexpected": _SENTINEL,
    }

    parsed = parse_reply(json.dumps(reply), BlogPostResult)

    assert isinstance(parsed, ParseFailure)
    assert parsed.note.splitlines() == [
        "The previous reply failed validation. Fix these fields:",
        "- meta_description: String should have at most 160 characters",
        "- sections[0].heading: String should have at least 1 character",
        "- suggested_tags: List should have at most 10 items after validation, not 11",
        "- unexpected: Extra inputs are not permitted",
    ]
    assert _SENTINEL not in parsed.note


def test_errors_about_the_reply_as_a_whole_are_reported_at_the_root() -> None:
    variant = {"format": "short", "angle": "curiosity", "headline": "h", "body": "b", "cta": "c"}

    duplicated = parse_reply(json.dumps({"variants": [variant] * 3}), AdCopyResult)
    not_an_object = parse_reply("[]", BlogPostResult)

    assert isinstance(duplicated, ParseFailure)
    assert (
        "- (root): Value error, ad_copy must contain exactly one variant per format"
        in duplicated.note
    )
    assert isinstance(not_an_object, ParseFailure)
    assert "- (root): Input should be a valid dictionary" in not_an_object.note


def test_the_retry_prompt_shows_the_reply_then_the_note_then_the_instruction() -> None:
    prompt = corrective_user_prompt(
        user_prompt="Write a blog post.",
        previous_reply='{"title": 1}',
        failure=ParseFailure("- title: Input should be a valid string"),
        instruction="Return ONLY valid JSON.",
    )

    assert prompt == (
        "Write a blog post.\n\n"
        'Previous response (invalid):\n{"title": 1}\n\n'
        "- title: Input should be a valid string\n\n"
        "Return ONLY valid JSON."
    )
