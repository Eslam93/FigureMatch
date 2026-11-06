"""Ad-copy prompt module.

Mirrors §7.3 of PROJECT_BRIEF.md. The prompt asks for three variants
labelled `short`, `medium`, `long` — the mock provider's canned response
locks the same three formats so downstream rendering doesn't have to
special-case the mock path. See `tests/providers/test_mock_providers.py`.

Bump `PROMPT_VERSION` whenever a string change here would alter
generation behavior in a way users could notice.
"""

from __future__ import annotations

from typing import Any, Final

PROMPT_VERSION: Final[str] = "ad_copy.v1"

SYSTEM_PROMPT: Final[str] = (
    "You are an expert performance-marketing copywriter. You produce "
    "ad variants that are specific, benefit-led, and ready to ship — "
    "never generic, never bloated."
)

# Three variants in a fixed format/angle ladder so the renderer can group
# them deterministically. `format` and `angle` are constrained to small
# enums; everything else is free-form short copy.
JSON_SCHEMA: Final[dict[str, Any]] = {
    "name": "ad_copy",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["variants"],
        "properties": {
            "variants": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["format", "angle", "headline", "body", "cta"],
                    "properties": {
                        "format": {
                            "type": "string",
                            "enum": ["short", "medium", "long"],
                        },
                        "angle": {
                            "type": "string",
                            "enum": [
                                "curiosity",
                                "social_proof",
                                "transformation",
                                "urgency",
                                "problem_solution",
                            ],
                        },
                        "headline": {"type": "string"},
                        "body": {"type": "string"},
                        "cta": {"type": "string"},
                    },
                },
            },
        },
    },
}


def build_prompt(
    *,
    topic: str,
    tone: str | None,
    target_audience: str | None,
    brand_voice_block: str | None = None,
) -> tuple[str, str]:
    """Render (system, user) for the ad-copy template."""
    tone_line = tone or "punchy and concrete"
    audience_line = target_audience or "a paid-social audience scrolling on mobile"
    voice_block = f"\n{brand_voice_block.rstrip()}\n" if brand_voice_block else ""

    user_prompt = (
        f"Audience: {audience_line}\n"
        f"Tone: {tone_line}\n"
        f"Topic: {topic}\n"
        f"{voice_block}"
        "\n"
        "Produce exactly three ad variants in a single JSON object "
        "with a `variants` array. The three variants MUST have "
        '`format` values "short", "medium", and "long" — one of each, '
        "no duplicates.\n"
        "- short: headline up to 6 words; body up to 12 words; cta "
        "2-3 words.\n"
        "- medium: headline up to 8 words; body 12-25 words; cta "
        "2-4 words.\n"
        "- long: headline up to 12 words; body 25-60 words; cta "
        "2-5 words.\n"
        '`angle` must be one of: "curiosity", "social_proof", '
        '"transformation", "urgency", "problem_solution". Pick the '
        "best fit per variant.\n"
        "\n"
        "Quality rules:\n"
        "- Specific verbs. Concrete numbers when honest. Avoid "
        'clichés: "leverage", "synergy", "game-changer", '
        '"delve into", "navigate the complexities", "in today\'s '
        'fast-paced world".\n'
        "- No em-dashes unless necessary. No emojis.\n"
        "\n"
        "Return ONLY valid JSON matching the supplied schema, with no "
        "preamble or markdown fencing."
    )
    return SYSTEM_PROMPT, user_prompt


# Follows the note that says what was wrong with the previous reply
# (`app/services/corrective_retry.py`), so it doesn't claim a cause itself.
CORRECTIVE_RETRY_INSTRUCTION: Final[str] = (
    "Return ONLY valid JSON shaped as "
    '{"variants": [{"format": "short"|"medium"|"long", "angle": ..., '
    '"headline": ..., "body": ..., "cta": ...}, ...]} with one of each '
    "format. No preamble, no markdown fencing, no explanation."
)
