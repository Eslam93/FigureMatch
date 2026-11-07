"""Image-prompt builder.

Mirrors §7.5 of PROJECT_BRIEF.md. Runs as a separate LLM call AFTER
content generation: the model reads the rendered content plus a chosen
style and returns a structured `{ prompt, negative_prompt, style_summary }`
payload. The image provider then consumes that prompt.

Two providers; one schema:

- OpenAI's GPT Image models (default `gpt-image-2.5-flare`) take the
  positive `prompt` only, so the service folds the `negative_prompt`
  text into it.
- Bedrock Nova Canvas takes a real negative prompt. Either way the
  payload shape stays the same — the builder is provider-agnostic.

`PROMPT_VERSION` is persisted on `generated_images.image_prompt` so we
can map a stored image back to the exact builder revision.

v2 revision (this file) addresses the "every image looks the same"
failure mode of v1:

  1. Style is no longer a single word — each style maps to concrete
     visual cues (lighting, palette, composition, materials) the model
     can act on. v1's "cinematic" and "photorealistic" produced nearly
     identical outputs because gpt-5.4-mini fell back to the same safe
     defaults when given a one-word direction.

  2. The user prompt now forces a brainstorm-then-pick step. v1 went
     straight to "produce an image prompt" and the model latched onto
     the most obvious visual metaphor for the topic — for any software
     content, that meant "developer at a desk." v2 explicitly tells the
     model to consider three metaphors and reject the cliché one.

  3. Specificity checklist on the output. Subject, environment,
     composition, lighting, palette must all be NAMED. v1's example
     "isometric three-quarter view" was the ONLY composition cue and
     biased every output toward that vantage.

  4. Negative prompt is now half-universal, half-topic-specific. v1's
     boilerplate "text, watermark, logos, faces" was useful but
     identical every time; v2 asks the model to add 2-3 content-aware
     cliché exclusions (e.g. "stock-photo handshake" for hiring posts,
     "anthropomorphic robot" for AI posts) — these matter on OpenAI's
     GPT Image models because the negative folds into the positive as
     an "Avoid:" clause at generation time.
"""

from __future__ import annotations

from typing import Any, Final

PROMPT_VERSION: Final[str] = "image_prompt.v2"

# Each style name maps to a paragraph of concrete visual cues. Without
# this expansion the model treats "photorealistic" / "cinematic" /
# "illustration" as interchangeable abstract labels and produces visually
# similar outputs regardless of pick. The cues here are the named
# vocabulary an art director would use briefing a stock-photographer or
# illustrator — lighting source, palette character, materials, vantage —
# so the prompt-builder LLM has something concrete to attach to.
_STYLE_GUIDE: Final[dict[str, str]] = {
    "photorealistic": (
        "natural light, real-world materials, editorial photography "
        "composition, shallow-depth-of-field on the primary subject, "
        "true colour grading with no posterisation"
    ),
    "illustration": (
        "hand-drawn or vector illustration, bold flat shapes, intentional "
        "negative space, limited 3-4 colour palette with one accent hue, "
        "slight paper or screen-print texture grain"
    ),
    "minimalist": (
        "single subject on an uncluttered background, generous whitespace, "
        "two-tone palette, geometric simplicity, no decorative or "
        "atmospheric elements, calm and focused"
    ),
    "3d_render": (
        "stylised 3D render, soft global illumination, smooth subsurface "
        "materials, isometric or three-quarter vantage, pastel or jewel-tone "
        "palette with rounded forms"
    ),
    "watercolor": (
        "watercolour painting, visible brushwork and pigment bleeds, soft "
        "edges, paper texture showing through, muted earthy palette, "
        "imperfect hand-painted feel"
    ),
    "cinematic": (
        "dramatic chiaroscuro lighting, wide anamorphic framing, desaturated "
        "highlights with one strong accent colour, subtle film-grain texture, "
        "mood-driven composition with strong directional light"
    ),
}

SUPPORTED_STYLES: Final[tuple[str, ...]] = tuple(_STYLE_GUIDE.keys())

SYSTEM_PROMPT: Final[str] = (
    "You are an expert visual art director who turns marketing copy into "
    "concrete, production-ready image prompts. You output strict JSON: a "
    "positive `prompt`, a `negative_prompt` of things to avoid, and a short "
    "`style_summary` for the dashboard.\n"
    "\n"
    "Reject the obvious visual metaphor. For any software topic the cliché "
    "image is 'a developer at a desk with monitors'; for any AI topic it is "
    "'a glowing brain or anthropomorphic robot'; for any hiring topic it is "
    "'a corporate handshake'. Your job is to find the SECOND-best metaphor — "
    "the one that captures the substance of the piece without the visual "
    "trope. The reader should look at the image and feel something specific "
    "about the content, not generically 'tech.'\n"
    "\n"
    "Never include on-image text, logos, or identifiable people unless the "
    "caller explicitly asks."
)

JSON_SCHEMA: Final[dict[str, Any]] = {
    "name": "image_prompt",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["prompt", "negative_prompt", "style_summary"],
        "properties": {
            "prompt": {"type": "string"},
            "negative_prompt": {"type": "string"},
            "style_summary": {"type": "string"},
        },
    },
}


def build_prompt(
    *,
    content_summary: str,
    style: str,
) -> tuple[str, str]:
    """Render (system, user) for the image-prompt builder.

    `content_summary` is the rendered_text of the related content piece
    (or a truncated version of it). `style` must be one of
    `SUPPORTED_STYLES`. The caller is expected to enforce that gate;
    this function trusts its inputs and falls back to `photorealistic`
    cues if an unknown style slips through.
    """
    style_key = style if style in _STYLE_GUIDE else "photorealistic"
    style_cues = _STYLE_GUIDE[style_key]
    user_prompt = (
        f"Style direction: **{style_key}** — {style_cues}.\n"
        "\n"
        "Content to visualise:\n"
        "---\n"
        f"{content_summary.strip()}\n"
        "---\n"
        "\n"
        "Process (do this internally — do NOT include in output):\n"
        "  1. Brainstorm three different visual metaphors that could "
        "communicate the substance of this content. Note the most "
        "obvious / cliché one explicitly so you can REJECT it.\n"
        "  2. Pick the strongest of the remaining two. Strongest means: "
        "a concrete subject doing a concrete thing in a concrete place "
        "at a concrete moment, not an abstract concept.\n"
        "  3. Map the style cues above to the picked metaphor.\n"
        "\n"
        "Output JSON requirements:\n"
        "\n"
        "  `prompt`: 40-90 words, single paragraph. Must NAME each of:\n"
        "    • Subject — specific, not generic (e.g. 'a third-shift "
        "on-call engineer mid-yawn', not 'a developer')\n"
        "    • Environment — specific (e.g. 'a server room at 3am, lit "
        "by amber status LEDs and one overhead emergency light', not "
        "'an office')\n"
        "    • Composition / vantage (close-up portrait, wide environmental "
        "shot, overhead flat-lay, low-angle hero, profile, etc.)\n"
        "    • Lighting (named source — 'a single warm desk lamp', "
        "'overcast skylight through dusty windows', 'cyan monitor "
        "glow', not just 'soft light')\n"
        "    • Palette (named — 'muted teals with a single amber accent', "
        "'paper-white with sepia tones', not just 'warm colours')\n"
        "\n"
        "  `negative_prompt`: 4-8 comma-separated items. Include the "
        "universal exclusions (text, watermark, logos, identifiable "
        "faces, signatures) PLUS 2-3 cliché exclusions specific to the "
        "topic. Examples by topic: hiring → 'stock handshake, generic "
        "corporate arrows'; AI → 'glowing blue brain, anthropomorphic "
        "robot, circuit-board overlay'; software → 'developer at desk, "
        "code on a giant monitor, hooded silhouette typing'.\n"
        "\n"
        "  `style_summary`: 4-10 words for the dashboard label "
        "(e.g. 'cinematic chiaroscuro, single amber light').\n"
        "\n"
        "Return ONLY valid JSON matching the supplied schema."
    )
    return SYSTEM_PROMPT, user_prompt


CORRECTIVE_RETRY_INSTRUCTION: Final[str] = (
    "Your previous response was not valid JSON matching the required "
    "schema. Return ONLY valid JSON with keys prompt, negative_prompt, "
    "style_summary. No preamble, no markdown fencing, no explanation."
)
