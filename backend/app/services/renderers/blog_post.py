# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Blog-post → markdown renderer.

Maps the structured `BlogPostResult` into clean GitHub-flavored markdown:

  - title  → `# {title}`
  - intro  → first paragraph block
  - sections[].heading / .body → `## {heading}` then the body verbatim
  - conclusion → final paragraph block
  - suggested_tags → trailing `Tags: #foo #bar` line

The renderer is intentionally lossy on `meta_description` (SEO metadata,
not body copy) — it lives in the JSONB `result` for export use.
"""

from __future__ import annotations

import re

from app.schemas.content import BlogPostResult


def word_count(text: str) -> int:
    """Whitespace-separated word count. Markdown punctuation passes
    through — close enough for dashboard previews and not worth a
    tokenizer dependency.
    """
    return len(text.split()) if text.strip() else 0


def _tag(tag: str) -> str:
    """Normalize a tag into `#hyphen-case`. Strip leading `#` and any
    whitespace; collapse internal whitespace runs into single hyphens.
    """
    cleaned = re.sub(r"\s+", "-", tag.strip().lstrip("#"))
    return f"#{cleaned}" if cleaned else ""


def render_blog_post(result: BlogPostResult) -> str:
    """Render a structured blog post into markdown.

    Pure: same input always produces the same output. Trailing newline
    omitted so callers can append a banner or footer cleanly.
    """
    parts: list[str] = [f"# {result.title.strip()}", "", result.intro.strip()]
    for section in result.sections:
        parts.append("")
        parts.append(f"## {section.heading.strip()}")
        parts.append("")
        parts.append(section.body.strip())
    parts.append("")
    parts.append(result.conclusion.strip())

    rendered_tags = [t for t in (_tag(tag) for tag in result.suggested_tags) if t]
    if rendered_tags:
        parts.append("")
        parts.append("Tags: " + " ".join(rendered_tags))

    return "\n".join(parts)
