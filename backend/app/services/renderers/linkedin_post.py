# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""LinkedIn-post → plain text renderer.

Layout (per §7.0.1 of PROJECT_BRIEF.md):

  {hook}

  {body}

  {cta}

  #hashtag1 #hashtag2 #hashtag3

Hashtags are stored without the leading `#` in `LinkedInPostResult` so
this renderer is the single place that adds it. Adjacent tags are joined
by single spaces. Empty tags are dropped silently.
"""

from __future__ import annotations

import re

from app.schemas.content import LinkedInPostResult


def _tag(tag: str) -> str:
    """Normalize a tag into `#hyphen-case`. Strip leading `#` and any
    whitespace; collapse internal whitespace runs into single hyphens.
    """
    cleaned = re.sub(r"\s+", "-", tag.strip().lstrip("#"))
    return f"#{cleaned}" if cleaned else ""


def render_linkedin_post(result: LinkedInPostResult) -> str:
    """Render a structured LinkedIn post into plain text.

    Pure: same input always produces the same output. Trailing newline
    omitted so callers can append a banner or footer cleanly.
    """
    parts: list[str] = [
        result.hook.strip(),
        "",
        result.body.strip(),
        "",
        result.cta.strip(),
    ]
    rendered_tags = [t for t in (_tag(tag) for tag in result.hashtags) if t]
    if rendered_tags:
        parts.append("")
        parts.append(" ".join(rendered_tags))
    return "\n".join(parts)
