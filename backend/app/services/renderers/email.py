# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Email → plain text renderer.

Layout (per §7.0.1 of PROJECT_BRIEF.md):

  Subject: {subject}
  Preview: {preview_text}

  {greeting}

  {body}

  {cta_text}

  {sign_off}

The first two lines are inbox metadata, separated from the email body by
a blank line. They live in `rendered_text` so dashboard preview, copy,
and full-text search all see them.
"""

from __future__ import annotations

from app.schemas.content import EmailResult


def render_email(result: EmailResult) -> str:
    """Render a structured email into plain text.

    Pure: same input always produces the same output. Trailing newline
    omitted so callers can append a banner or footer cleanly.
    """
    parts: list[str] = [
        f"Subject: {result.subject.strip()}",
        f"Preview: {result.preview_text.strip()}",
        "",
        result.greeting.strip(),
        "",
        result.body.strip(),
        "",
        result.cta_text.strip(),
        "",
        result.sign_off.strip(),
    ]
    return "\n".join(parts)
