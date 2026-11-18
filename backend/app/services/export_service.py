# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Content export — Markdown only for now.

The brief's feature #3 lists "view, copy, download, delete" for the
dashboard; this is the download path. `rendered_text` on every
`ContentPiece` is already the canonical Markdown the renderer produced
at write time (Slice 2), so the export is mostly framing: a small
front-matter-style header + the body + a footer with the current
image URL (if any).

DOCX and PDF exports are tracked on the issue board ([#73], [#74]) —
both add a dependency (python-docx / reportlab) and warrant their own
slice. Markdown ships now because the lift is ~30 lines and closes the
dashboard "download" gap from the brief.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.db.models import ContentPiece, GeneratedImage

_SLUG_MAX_LEN = 60


def slugify(topic: str) -> str:
    """Return a filename-safe slug from a free-form topic.

    Lowercase ASCII, hyphens for whitespace, drops anything that isn't
    `[a-z0-9-]`. Falls back to `"content"` for topics that contain
    nothing slug-safe (e.g. emoji-only). Caps at `_SLUG_MAX_LEN` chars
    so downloads work on filesystems that limit path components.
    """
    lowered = topic.lower()
    # Replace runs of non-alphanumeric with single hyphens, then trim.
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not slug:
        return "content"
    return slug[:_SLUG_MAX_LEN].rstrip("-") or "content"


def build_markdown(
    piece: ContentPiece,
    current_image: GeneratedImage | None,
    *,
    image_public_url: str | None = None,
) -> str:
    """Render a single content piece + (optional) image as Markdown.

    The header carries the metadata a downstream reader needs to
    understand the file's provenance: content type, generation
    timestamp, model id. `rendered_text` is already canonical Markdown
    so it's inserted verbatim. If an image is current and the caller
    knows its public URL (computed at projection time, not from the
    persisted `cdn_url` — see PR #143's storage refactor), it's embedded
    as a trailing image link.
    """
    created_iso = (
        piece.created_at.isoformat()
        if isinstance(piece.created_at, datetime)
        else str(piece.created_at)
    )
    lines: list[str] = [
        f"# {piece.topic}",
        "",
        f"> **Type:** {piece.content_type.value}  ",
        f"> **Generated:** {created_iso}  ",
        f"> **Model:** {piece.model_id}",
    ]
    if piece.tone:
        lines.append(f"> **Tone:** {piece.tone}  ")
    if piece.target_audience:
        lines.append(f"> **Audience:** {piece.target_audience}")
    lines.extend(["", "---", "", piece.rendered_text.rstrip()])

    if current_image is not None and image_public_url:
        lines.extend(
            [
                "",
                "---",
                "",
                f"![Generated image (style: {current_image.style})]({image_public_url})",
            ]
        )

    return "\n".join(lines) + "\n"


def filename_for(piece: ContentPiece) -> str:
    """`content-id-prefix-slug.md` — short, unique, slug-readable."""
    return f"{slugify(piece.topic)}-{str(piece.id)[:8]}.md"
