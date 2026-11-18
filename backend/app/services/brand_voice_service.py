# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Brand-voice services.

Two unrelated responsibilities live here for now:

  1. Convert a `BrandVoice` row into the text block that prompt
     modules splice into the user prompt (`render_brand_voice_block`).
     Pure function; no I/O.
  2. CRUD helpers around the repository — thin wrappers that don't add
     orchestration today but give the router one place to import from.

If Slice 7+ adds business logic (e.g., enforcing one default voice per
user, or denying delete when in use), it lands here rather than in the
router.
"""

from __future__ import annotations

from app.db.models import BrandVoice


def render_brand_voice_block(voice: BrandVoice) -> str:
    """Compose the brand-voice block injected into the user prompt.

    Layout intentionally bounded to the lines the prompt builders
    expect — adding more fields requires both this function and the
    prompt modules to coordinate. Empty / null fields are omitted so
    the block doesn't carry "Tone: " on its own line when nothing was
    supplied.
    """
    lines: list[str] = [f"Brand voice: {voice.name.strip()}"]
    if voice.description and voice.description.strip():
        lines.append(voice.description.strip())
    tones = [t.strip() for t in (voice.tone_descriptors or []) if t and t.strip()]
    if tones:
        lines.append("Tone: " + ", ".join(tones))
    banned = [b.strip() for b in (voice.banned_words or []) if b and b.strip()]
    if banned:
        lines.append("Banned phrases (do not use): " + ", ".join(banned))
    if voice.target_audience and voice.target_audience.strip():
        lines.append(f"Brand audience: {voice.target_audience.strip()}")
    if voice.sample_text and voice.sample_text.strip():
        lines.append("Sample copy to mimic the voice (do not copy verbatim):")
        lines.append(voice.sample_text.strip())
    return "\n".join(lines)
