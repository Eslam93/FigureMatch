"""MockLLMProvider — zero-cost, zero-key, fully working LLM stand-in.

Used by:
  - the test suite when no real provider is wanted
  - `AI_PROVIDER_MODE=mock` for demos and offline development

Returns canned JSON keyed by `content_type`. The shapes match the
schemas the brief defines for each prompt module (see §7 of
PROJECT_BRIEF.md). When real schemas land in Phase 3, these cannds
must keep matching — there is a test in `tests/providers/` that
parses each canned blob as JSON to catch drift early.
"""

from __future__ import annotations

import json
from typing import Any, Final

from app.providers.llm.base import LLMResult

# Canned JSON payloads keyed by content_type. Each value matches the
# brief §7 schema for that content type. Stored as dict so tests can
# walk the shape; `generate()` serializes via `json.dumps`.
_CANNED_RESPONSES: Final[dict[str, dict[str, Any]]] = {
    "blog_post": {
        "title": "How mocked content makes development cheap and predictable",
        "meta_description": (
            "A worked example of using a mock LLM during local development — "
            "deterministic, free, fast, and offline."
        ),
        "intro": (
            "Real LLM calls are slow, paid, and non-deterministic. "
            "A mock provider gives you the same surface with none of those "
            "downsides — the app behaves the same, just without the bill."
        ),
        "sections": [
            {
                "heading": "Why mock at all",
                "body": (
                    "You want CI to run without network. You want tests to be "
                    "stable. You want your offline demo to keep working when "
                    "the conference Wi-Fi is gone. A mock provider buys all of "
                    "that with no behavioral compromise."
                ),
            },
            {
                "heading": "What 'fully implemented' means here",
                "body": (
                    "The mock doesn't just no-op. It returns valid JSON in the "
                    "exact shape the real provider would, so downstream parsing "
                    "and rendering run the same code path. The seam stays honest."
                ),
            },
            {
                "heading": "When to flip to the real provider",
                "body": (
                    "Set AI_PROVIDER_MODE=openai once you have a funded key and "
                    "want real-quality output. Nothing about the app code changes."
                ),
            },
        ],
        "conclusion": (
            "Mocks aren't a fallback — they're a peer implementation. Treat "
            "them as such and your local development loop stays tight."
        ),
        "suggested_tags": ["mock", "developer-experience", "ai"],
    },
    "linkedin_post": {
        "hook": "The cheapest LLM call is the one you don't make.",
        "body": (
            "Three reasons we ship a fully-functional mock provider alongside "
            "the real one:\n\n"
            "1. Tests run offline.\n"
            "2. CI bills nothing.\n"
            "3. Demos survive bad Wi-Fi.\n\n"
            "Same interface. Same JSON shapes. No real model calls. The "
            "feature parity is the point."
        ),
        "cta": (
            "What's the cheapest provider in your stack — and is it really "
            "a mock, or a half-implementation?"
        ),
        "hashtags": ["#engineering", "#ai", "#developerexperience"],
    },
    "ad_copy": {
        "variants": [
            {
                "format": "short",
                "angle": "curiosity",
                "headline": "What if it worked offline?",
                "body": "Mock-mode AI for every demo.",
                "cta": "Try it",
            },
            {
                "format": "medium",
                "angle": "social_proof",
                "headline": "Tested on every commit, billed on none",
                "body": (
                    "CI runs every test against a fully-implemented mock "
                    "provider — same JSON shapes as production."
                ),
                "cta": "See the setup",
            },
            {
                "format": "long",
                "angle": "transformation",
                "headline": "Stop paying for tests to pass — wire a real mock",
                "body": (
                    "Replace flaky integration tests against live LLMs with a deterministic "
                    "in-process provider. Same surface as OpenAI, returning valid JSON per "
                    "content type. Your CI gets faster and your bill drops."
                ),
                "cta": "Read the implementation",
            },
        ],
    },
    "email": {
        "subject": "Quick note about your local-dev loop",
        "preview_text": "Three changes that make AI features cheap to iterate on.",
        "greeting": "Hi there,",
        "body": (
            "If you're building anything on top of an LLM, your local-dev loop "
            "is doing more work than it needs to.\n\n"
            "We've been running with a mock provider in CI and on demo machines "
            "for a while. It returns the same JSON shapes as the real model, "
            "just deterministically. Tests are faster, demos are reliable, and "
            "the bill is zero.\n\n"
            "Worth trying if you haven't already."
        ),
        "cta_text": "Show me the pattern",
        "sign_off": "— The FigureMatch team",
    },
    "image_prompt": {
        "prompt": (
            "A clean, slightly isometric illustration of a developer workstation. "
            "Two monitors, one showing a JSON response, the other a green test "
            "suite. Soft daylight from the left, cool blue-grey palette with "
            "warm orange accents on coffee mug and desk lamp. No identifiable "
            "person, no logos, no on-screen text."
        ),
        "negative_prompt": "",
        "style_summary": "isometric illustration, soft daylight",
    },
    "improver_analysis": {
        "issues": [
            "Buries the hook past the second sentence.",
            "Uses banned phrases the brand voice forbids.",
            "Passive voice in the call to action weakens the ask.",
        ],
        "planned_changes": [
            "Move the strongest concrete claim to the opening line.",
            "Replace banned phrases with concrete brand-voice substitutes.",
            "Rewrite the CTA in active voice with a verb-first imperative.",
        ],
    },
    "improver_rewrite": {
        "improved_text": (
            "Three engineers shipped a feature this week using the mocked "
            "provider end-to-end. No real LLM call, no flaky tests, no surprise "
            "bill. The seam survives contact with production. Pull the branch "
            "and run the suite — you'll see."
        ),
        "explanation": [
            (
                "Led with the concrete outcome (three engineers, this week) "
                "instead of generic claims."
            ),
            "Cut the banned phrase and replaced with a specific verb.",
            (
                "Reworked the CTA into an imperative — 'Pull the branch' — "
                "rather than a passive invitation."
            ),
        ],
        "changes_summary": {
            "tone_shift": "softened_to_direct",
            "length_change_pct": -32.0,
            "key_additions": ["concrete numbers", "imperative CTA"],
            "key_removals": ["banned phrase 'in today's fast-paced world'"],
        },
    },
}

# A neutral fallback for content types not in the canned set. Real
# parsing will reject this shape — that's deliberate, callers should
# never see it unless they're asking for an unknown content_type.
_UNKNOWN_FALLBACK: Final[dict[str, str]] = {
    "_note": "MockLLMProvider received an unknown content_type. Add a canned response.",
}


class MockLLMProvider:
    """In-process LLM substitute. Deterministic, free, offline-friendly.

    Honors the same interface as `OpenAIChatProvider` so swapping
    providers is a config change, not a code change.
    """

    model: Final[str] = "mock-llm-v1"

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
        content_type: str,
    ) -> LLMResult:
        payload = _CANNED_RESPONSES.get(content_type, _UNKNOWN_FALLBACK)
        raw_text = json.dumps(payload, ensure_ascii=False)
        # Stable token estimate so downstream cost rollups stay
        # deterministic in tests.
        return LLMResult(
            raw_text=raw_text,
            model=self.model,
            input_tokens=10,
            output_tokens=len(raw_text) // 4,  # rough char-to-token ratio
            cost_usd=0.0,
            latency_ms=0,
            finish_reason="stop",
        )
