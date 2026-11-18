# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Ad-copy → markdown renderer.

Layout (per §7.0.1 of PROJECT_BRIEF.md): each variant is grouped under
its format label, with the angle in parentheses, the headline as an H3,
the body as a paragraph, and the CTA on its own line:

  ## Short (curiosity)
  ### {headline}

  {body}

  CTA: {cta}

  ## Medium (social_proof)
  ...

Output ordering follows the canonical short → medium → long ladder
regardless of input order, so a provider that returns variants in a
different sequence still produces deterministic copy.
"""

from __future__ import annotations

from app.schemas.content import AdCopyResult, AdCopyVariant

_FORMAT_ORDER: tuple[str, ...] = ("short", "medium", "long")
_FORMAT_LABELS: dict[str, str] = {
    "short": "Short",
    "medium": "Medium",
    "long": "Long",
}


def _render_variant(variant: AdCopyVariant) -> list[str]:
    label = _FORMAT_LABELS.get(variant.format, variant.format.title())
    return [
        f"## {label} ({variant.angle})",
        f"### {variant.headline.strip()}",
        "",
        variant.body.strip(),
        "",
        f"CTA: {variant.cta.strip()}",
    ]


def render_ad_copy(result: AdCopyResult) -> str:
    """Render the three ad variants into markdown.

    Pure: same input always produces the same output. Trailing newline
    omitted so callers can append a banner or footer cleanly.
    """
    by_format: dict[str, AdCopyVariant] = {v.format: v for v in result.variants}
    parts: list[str] = []
    for fmt in _FORMAT_ORDER:
        variant = by_format.get(fmt)
        if variant is None:
            # Pydantic guarantees three variants but does not enforce
            # one-of-each at the type level. Skip the missing slot
            # rather than emit a half-rendered block.
            continue
        if parts:
            parts.append("")
        parts.extend(_render_variant(variant))
    return "\n".join(parts)
