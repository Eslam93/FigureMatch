"""Improver prompt module — analyze + rewrite, two distinct calls.

Mirrors §7.6 of PROJECT_BRIEF.md. The brief asks for a two-pass chain:

  1. ANALYZE — given the original text plus a goal, return the issues
     the rewriter should fix and the planned changes that will fix
     them. Output: `{ issues, planned_changes }` (both string lists).
  2. REWRITE — given the original text, the goal, AND the planned
     changes from step 1, return the final improved text plus
     explanation bullets and a changes-summary block.

The two-step structure forces the model to *commit* to a plan before
writing, which empirically produces cleaner rewrites than a single
"please improve this" pass. The downside is two paid LLM calls per
invocation; the cost is summed onto the persisted `improvements` row.

Goal-specific guidance lives in `_goal_hint` so `build_analyze` and
`build_rewrite` stay close to the brief shape.
"""

from __future__ import annotations

from typing import Any, Final

from app.db.enums import ImprovementGoal

PROMPT_VERSION: Final[str] = "improver.v2"


# ── shared ──────────────────────────────────────────────────────────────


def _goal_hint(goal: ImprovementGoal, new_audience: str | None) -> str:
    match goal:
        case ImprovementGoal.SHORTER:
            return "Cut at least 25% of the original length while preserving every key claim."
        case ImprovementGoal.PERSUASIVE:
            return (
                "Make it more persuasive: lead with the strongest claim, back it with proof "
                "already in the original text (never invent numbers, results, or quotes), "
                "and convert generic statements into specific verbs."
            )
        case ImprovementGoal.FORMAL:
            return (
                "Shift the register to formal business prose without becoming stiff: "
                "no slang, no exclamation marks, no contractions."
            )
        case ImprovementGoal.SEO:
            return (
                "Optimize for organic search: ensure the primary keyword appears in the "
                "first sentence and at least twice in the body, strengthen scannability "
                "with short paragraphs, and surface a clear semantic structure."
            )
        case ImprovementGoal.AUDIENCE_REWRITE:
            audience = (new_audience or "the new audience the caller will provide").strip()
            return (
                f"Rewrite the same substance for this new audience: {audience}. "
                "Replace jargon and assumed context appropriate to the original audience "
                "with language and concrete examples that fit the new one."
            )


# ── analyze ─────────────────────────────────────────────────────────────

ANALYZE_SYSTEM_PROMPT: Final[str] = (
    "You are an expert editor. You read marketing copy and produce a "
    "tight, honest list of issues and a parallel list of planned changes "
    "the rewriter will execute. You never rewrite the text yourself in "
    "this step — the rewriter runs separately."
)

ANALYZE_JSON_SCHEMA: Final[dict[str, Any]] = {
    "name": "improver_analysis",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["issues", "planned_changes"],
        "properties": {
            "issues": {
                "type": "array",
                "items": {"type": "string"},
            },
            "planned_changes": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
}


def build_analyze(
    *,
    original_text: str,
    goal: ImprovementGoal,
    new_audience: str | None = None,
) -> tuple[str, str]:
    """Render (system, user) for the analyze stage."""
    hint = _goal_hint(goal, new_audience)
    user_prompt = (
        f"Goal: {goal.value}\n"
        f"{hint}\n"
        "\n"
        "Original text:\n"
        "---\n"
        f"{original_text.strip()}\n"
        "---\n"
        "\n"
        'Return JSON shaped as { "issues": [...], "planned_changes": [...] }:\n'
        "- `issues`: 2-6 short bullets. Concrete. Things a reader could verify against "
        "the original — no generic 'could be tighter' filler.\n"
        "- `planned_changes`: 2-6 short bullets. One-to-one with the issues where "
        "natural; each one names a specific edit the rewriter should make.\n"
        "\n"
        "Return ONLY valid JSON. No preamble, no markdown fencing."
    )
    return ANALYZE_SYSTEM_PROMPT, user_prompt


# ── rewrite ─────────────────────────────────────────────────────────────

REWRITE_SYSTEM_PROMPT: Final[str] = (
    "You are an expert rewriter. You execute the supplied plan against "
    "the original text and produce the improved version, plus a short "
    "explanation of what you changed and a structured changes_summary."
)

REWRITE_JSON_SCHEMA: Final[dict[str, Any]] = {
    "name": "improver_rewrite",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["improved_text", "explanation", "changes_summary"],
        "properties": {
            "improved_text": {"type": "string"},
            "explanation": {
                "type": "array",
                "items": {"type": "string"},
            },
            "changes_summary": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "tone_shift",
                    "length_change_pct",
                    "key_additions",
                    "key_removals",
                ],
                "properties": {
                    "tone_shift": {"type": "string"},
                    "length_change_pct": {"type": "number"},
                    "key_additions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "key_removals": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}


def build_rewrite(
    *,
    original_text: str,
    goal: ImprovementGoal,
    planned_changes: list[str],
    new_audience: str | None = None,
) -> tuple[str, str]:
    """Render (system, user) for the rewrite stage.

    Accepts the `planned_changes` list from the analyze stage so the
    rewriter knows exactly which edits to make. When the analyze stage
    returned no plan (parse failure), pass an empty list and rely on
    the goal hint alone.
    """
    hint = _goal_hint(goal, new_audience)
    plan_block = "\n".join(f"- {change.strip()}" for change in planned_changes if change.strip())
    if not plan_block:
        plan_block = "- (no explicit plan provided; rewrite to match the goal)"

    user_prompt = (
        f"Goal: {goal.value}\n"
        f"{hint}\n"
        "\n"
        "Planned changes:\n"
        f"{plan_block}\n"
        "\n"
        "Original text:\n"
        "---\n"
        f"{original_text.strip()}\n"
        "---\n"
        "\n"
        "Return JSON shaped as:\n"
        "{\n"
        '  "improved_text": "...",\n'
        '  "explanation": ["...", ...],\n'
        '  "changes_summary": {\n'
        '    "tone_shift": "...",\n'
        '    "length_change_pct": <number>,\n'
        '    "key_additions": ["..."],\n'
        '    "key_removals": ["..."]\n'
        "  }\n"
        "}\n"
        "\n"
        "Quality rules:\n"
        "- `improved_text`: full rewritten copy. Markdown formatting OK if the original used it.\n"
        "- `explanation`: 2-5 bullets a user could read to understand what you did.\n"
        "- `length_change_pct`: word-count change vs. the original, signed (-32 = 32% shorter).\n"
        '- No clichés: avoid "leverage", "synergy", "game-changer", '
        '"delve into", "navigate the complexities", "in today\'s fast-paced world".\n'
        "- No em-dashes unless necessary. No emojis.\n"
        "\n"
        "Return ONLY valid JSON. No preamble, no markdown fencing."
    )
    return REWRITE_SYSTEM_PROMPT, user_prompt


# Both follow the note that says what was wrong with the previous reply
# (`app/services/corrective_retry.py`), so they don't claim a cause themselves.
CORRECTIVE_RETRY_INSTRUCTION_ANALYZE: Final[str] = (
    "Return ONLY valid JSON with keys issues, planned_changes. "
    "No preamble, no markdown fencing, no explanation."
)

CORRECTIVE_RETRY_INSTRUCTION_REWRITE: Final[str] = (
    "Return ONLY valid JSON with keys improved_text, "
    "explanation, changes_summary. No preamble, no markdown fencing, "
    "no explanation."
)
