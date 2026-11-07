"""Blog-post prompt module.

Mirrors §7.1 of PROJECT_BRIEF.md. The system/user strings and the JSON
schema are the contract between the prompt layer and the LLM. Bump
PROMPT_VERSION whenever a string change here would alter generation
behavior in a way users could notice.
"""

from __future__ import annotations

from typing import Any, Final

PROMPT_VERSION: Final[str] = "blog_post.v2"

SYSTEM_PROMPT: Final[str] = (
    "You are an expert content strategist and writer. You produce "
    "publication-ready blog posts that rank on search and read like a "
    "human wrote them — never AI-generic."
)

# OpenAI `response_format: { type: "json_schema", strict: true }` requires
# a closed schema (additionalProperties=false at every object level, and
# every property listed in `required`). Pydantic on the way back enforces
# the same shape — we don't rely on `strict: true` alone.
JSON_SCHEMA: Final[dict[str, Any]] = {
    "name": "blog_post",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "meta_description",
            "intro",
            "sections",
            "conclusion",
            "suggested_tags",
        ],
        "properties": {
            "title": {"type": "string"},
            "meta_description": {"type": "string"},
            "intro": {"type": "string"},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["heading", "body"],
                    "properties": {
                        "heading": {"type": "string"},
                        "body": {"type": "string"},
                    },
                },
            },
            "conclusion": {"type": "string"},
            "suggested_tags": {
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
    """Render (system, user) for the blog-post template.

    `tone` and `target_audience` are nullable on the API to keep the
    form forgiving — when empty, the prompt uses neutral defaults so the
    LLM still has enough signal to produce a coherent post.
    """
    tone_line = tone or "informative and direct"
    audience_line = target_audience or "general business readers"
    voice_block = f"\n{brand_voice_block.rstrip()}\n" if brand_voice_block else ""

    user_prompt = (
        f"Audience: {audience_line}\n"
        f"Tone: {tone_line}\n"
        f"Topic: {topic}\n"
        f"{voice_block}"
        "\n"
        "Write a blog post following these requirements:\n"
        "- H1 title, max 12 words, includes the primary keyword\n"
        "- Meta description under 160 characters\n"
        "- Opening hook (1-2 paragraphs) that creates curiosity\n"
        "- 3-5 H2 sections, each 150-250 words\n"
        "- At least one bulleted list inside a section\n"
        "- Closing paragraph with a clear takeaway and CTA\n"
        "- Total length 800-1200 words\n"
        "- Suggested tags: 3-5 SEO-relevant tags\n"
        "\n"
        "Quality rules:\n"
        '- Short paragraphs. Use "you". Concrete examples over abstractions.\n'
        '- No clichés: avoid "in today\'s fast-paced world", "leverage", '
        '"synergy", "game-changer", "delve into", "navigate the complexities".\n'
        "- No em-dashes unless necessary. No emojis.\n"
        "\n"
        "Return ONLY valid JSON matching the supplied schema, with no "
        "preamble or markdown fencing."
    )
    return SYSTEM_PROMPT, user_prompt


# Follows the note that says what was wrong with the previous reply
# (`app/services/corrective_retry.py`), so it doesn't claim a cause itself.
CORRECTIVE_RETRY_INSTRUCTION: Final[str] = (
    "Return ONLY valid JSON with no preamble, no markdown fencing, and no explanation."
)
