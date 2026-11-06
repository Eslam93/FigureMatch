"""LinkedIn-post prompt module.

Mirrors §7.2 of PROJECT_BRIEF.md. The structured shape mirrors the mock
provider's canned response so swapping providers stays a config change.

Bump `PROMPT_VERSION` whenever a string change here would alter
generation behavior in a way users could notice.
"""

from __future__ import annotations

from typing import Any, Final

PROMPT_VERSION: Final[str] = "linkedin_post.v2"

SYSTEM_PROMPT: Final[str] = (
    "You are an expert LinkedIn content writer. You produce posts that "
    "stop the scroll: punchy hook, scannable body, one specific call to "
    "action, and a small set of relevant hashtags. You never sound like "
    "a press release."
)

# Closed schema for OpenAI `response_format: json_schema, strict: true`.
# Every property listed in `required`, additionalProperties=false. Pydantic
# validates the same shape coming back; strict mode is a defense in depth,
# not the only line.
JSON_SCHEMA: Final[dict[str, Any]] = {
    "name": "linkedin_post",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["hook", "body", "cta", "hashtags"],
        "properties": {
            "hook": {"type": "string"},
            "body": {"type": "string"},
            "cta": {"type": "string"},
            "hashtags": {
                "type": "array",
                "items": {"type": "string"},
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
    """Render (system, user) for the LinkedIn-post template."""
    tone_line = tone or "direct and conversational"
    audience_line = target_audience or "professionals on LinkedIn"
    voice_block = f"\n{brand_voice_block.rstrip()}\n" if brand_voice_block else ""

    user_prompt = (
        f"Audience: {audience_line}\n"
        f"Tone: {tone_line}\n"
        f"Topic: {topic}\n"
        f"{voice_block}"
        "\n"
        "Write a LinkedIn post with the following structure:\n"
        "- hook: 1-2 sentences. A claim, contrarian take, or specific fact "
        "from the topic — something that earns the next sentence.\n"
        "- body: 60-180 words. Short paragraphs and/or a numbered list. "
        "Concrete examples over abstractions. No fluff.\n"
        "- cta: one direct call to action OR an open question that "
        "invites a comment. Verb-first if it's a CTA.\n"
        "- hashtags: 3-5 lowercase tags, no spaces, no `#` prefix (the "
        "client adds it on render).\n"
        "\n"
        "Quality rules:\n"
        "- Use only facts stated above. Never invent statistics, results, "
        "names, or quotes.\n"
        '- Write in second person ("you") when natural. Avoid clichés: '
        '"in today\'s fast-paced world", "leverage", "synergy", '
        '"game-changer", "delve into", "navigate the complexities".\n'
        "- No em-dashes unless necessary. No emojis.\n"
        "\n"
        "Return ONLY valid JSON matching the supplied schema, with no "
        "preamble or markdown fencing."
    )
    return SYSTEM_PROMPT, user_prompt


# Follows the note that says what was wrong with the previous reply
# (`app/services/corrective_retry.py`), so it doesn't claim a cause itself.
CORRECTIVE_RETRY_INSTRUCTION: Final[str] = (
    "Return ONLY valid JSON with keys hook, body, cta, hashtags. "
    "No preamble, no markdown fencing, no explanation."
)
