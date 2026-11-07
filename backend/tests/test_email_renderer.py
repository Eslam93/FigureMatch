"""Unit tests for the email renderer."""

from __future__ import annotations

from app.schemas.content import EmailResult
from app.services.renderers.email import render_email


def _sample(**overrides: object) -> EmailResult:
    data: dict[str, object] = {
        "subject": "Quick note about your local-dev loop",
        "preview_text": "Three changes that make AI features cheap to iterate on.",
        "greeting": "Hi there,",
        "body": (
            "If you're building anything on top of an LLM, your local-dev loop "
            "is doing more work than it needs to."
        ),
        "cta_text": "Show me the pattern",
        "sign_off": "— The FigureMatch team",
    }
    data.update(overrides)
    return EmailResult.model_validate(data)


def test_renders_subject_then_preview_on_their_own_lines() -> None:
    md = render_email(_sample())
    lines = md.splitlines()
    assert lines[0] == "Subject: Quick note about your local-dev loop"
    assert lines[1] == "Preview: Three changes that make AI features cheap to iterate on."


def test_blank_line_separates_metadata_from_greeting() -> None:
    md = render_email(_sample())
    lines = md.splitlines()
    # Subject (0), Preview (1), blank (2), greeting (3).
    assert lines[2] == ""
    assert lines[3] == "Hi there,"


def test_body_cta_and_sign_off_appear_in_order() -> None:
    md = render_email(_sample())
    body_idx = md.index("If you're building")
    cta_idx = md.index("Show me the pattern")
    sign_idx = md.index("The FigureMatch team")
    assert body_idx < cta_idx < sign_idx
