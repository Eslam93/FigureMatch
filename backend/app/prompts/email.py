"""Email prompt module.

Mirrors §7.4 of PROJECT_BRIEF.md. Structured around a marketing-style
email: subject line + inbox preview + greeting + body + CTA + sign-off.

Bump `PROMPT_VERSION` whenever a string change here would alter
generation behavior in a way users could notice.
"""

from __future__ import annotations

from typing import Any, Final

PROMPT_VERSION: Final[str] = "email.v1"

SYSTEM_PROMPT: Final[str] = (
    "You are an expert email copywriter. You write short, useful, "
    "human-sounding emails that get opened, read, and replied to — "
    "never marketing-speak, never generic newsletter filler."
)

JSON_SCHEMA: Final[dict[str, Any]] = {
    "name": "email",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "subject",
            "preview_text",
            "greeting",
            "body",
            "cta_text",
            "sign_off",
        ],
        "properties": {
            "subject": {"type": "string"},
            "preview_text": {"type": "string"},
            "greeting": {"type": "string"},
            "body": {"type": "string"},
            "cta_text": {"type": "string"},
            "sign_off": {"type": "string"},
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
    """Render (system, user) for the email template."""
    tone_line = tone or "warm and direct"
    audience_line = target_audience or "an interested professional reader"
    voice_block = f"\n{brand_voice_block.rstrip()}\n" if brand_voice_block else ""

    user_prompt = (
        f"Audience: {audience_line}\n"
        f"Tone: {tone_line}\n"
        f"Topic: {topic}\n"
        f"{voice_block}"
        "\n"
        "Write a marketing email with the following structure:\n"
        "- subject: 4-8 words. Specific enough to earn the open. No "
        "ALL CAPS, no emojis, no clickbait punctuation.\n"
        "- preview_text: 6-15 words. Reinforces the subject and "
        "extends the value. Shown in the inbox preview after the "
        "subject.\n"
        '- greeting: short and human. "Hi there," is fine. Avoid '
        '"Dear valued customer".\n'
        "- body: 60-180 words. Open with the most concrete claim. "
        "Short paragraphs. One specific reason the reader should "
        "care, then the smallest next step.\n"
        "- cta_text: 2-5 words for the button label. Verb-first.\n"
        "- sign_off: a short closer (e.g., '— The Magna team').\n"
        "\n"
        "Quality rules:\n"
        '- Use "you" where natural. Avoid clichés: "in today\'s '
        'fast-paced world", "leverage", "synergy", "game-changer", '
        '"delve into", "navigate the complexities".\n'
        "- No em-dashes unless necessary. No emojis.\n"
        "\n"
        "Return ONLY valid JSON matching the supplied schema, with no "
        "preamble or markdown fencing."
    )
    return SYSTEM_PROMPT, user_prompt


# Follows the note that says what was wrong with the previous reply
# (`app/services/corrective_retry.py`), so it doesn't claim a cause itself.
CORRECTIVE_RETRY_INSTRUCTION: Final[str] = (
    "Return ONLY valid JSON with keys subject, preview_text, "
    "greeting, body, cta_text, sign_off. No preamble, no markdown "
    "fencing, no explanation."
)
