"""Golden files pin the first-attempt text prompts, word for word.

Each case renders one prompt from fixed inputs: the four content types, with a
full brief and with only a topic (so the defaults show), and both improver
stages, analyze once per goal and rewrite with and without a plan. The system
and user strings must match `tests/golden/prompts/<case>.txt` exactly, so a
wording change to those prompts, or to the brand-voice block spliced into a
content prompt, fails here with a diff and shows up in review next to its
`PROMPT_VERSION` bump. The corrective-retry instructions and the image prompts
are not pinned here; `tests/test_corrective_retry.py` pins how the retry
prompt is assembled.

To accept an intended change, regenerate the files and commit them with it:

    UPDATE_GOLDENS=1 uv run pytest tests/test_prompt_goldens.py

In PowerShell, set `$env:UPDATE_GOLDENS = "1"` first and remove it afterwards
with `Remove-Item Env:UPDATE_GOLDENS`. Regenerating rewrites only the files
whose render changed, and passes; review `git diff` before committing.

The same renders, plus the image prompts and every corrective-retry
instruction, must also never name FigureMatch: the app's name isn't the user's brand.
"""

from __future__ import annotations

import difflib
import os
from collections.abc import Callable
from functools import partial
from pathlib import Path

import pytest

from app.db.enums import ImprovementGoal
from app.db.models import BrandVoice
from app.prompts import ad_copy, blog_post, email, image_prompt_builder, improver, linkedin_post
from app.services.brand_voice_service import render_brand_voice_block

_GOLDEN_DIR = Path(__file__).parent / "golden" / "prompts"
_UPDATE = os.environ.get("UPDATE_GOLDENS") == "1"

# Fixed inputs. Editing one rewrites goldens with no prompt change behind it.
_TOPIC = "How small teams can cut their cloud bill without slowing down releases"
_TONE = "practical and candid"
_AUDIENCE = "engineering managers at startups with 20 to 100 people"
_ORIGINAL_TEXT = (
    "Our scheduling app helps busy teams plan their week. It has lots of great "
    "features and is really easy to use.\n"
    "\n"
    "Sign up today and see why teams love it."
)
_NEW_AUDIENCE = "clinic managers who plan shifts for nurses"
_PLANNED_CHANGES = [
    "Open with what the app does for a team's week.",
    "Cut the vague 'lots of great features' line.",
    "Make the call to action say what happens after sign-up.",
]

type _Render = Callable[[], tuple[str, str]]

_CONTENT_BUILDERS: dict[str, Callable[..., tuple[str, str]]] = {
    "blog_post": blog_post.build_prompt,
    "linkedin_post": linkedin_post.build_prompt,
    "email": email.build_prompt,
    "ad_copy": ad_copy.build_prompt,
}


def _brand_voice_block() -> str:
    """The block a saved brand voice renders into a content prompt."""
    return render_brand_voice_block(
        BrandVoice(
            name="Acme house style",
            description="Plain words, short sentences, no hype.",
            tone_descriptors=["direct", "specific", "warm"],
            banned_words=["leverage", "synergy"],
            target_audience="technical leads who approve tooling spend",
            sample_text="We timed the build before and after the change. It got faster.",
        )
    )


def _full_brief(build: Callable[..., tuple[str, str]]) -> tuple[str, str]:
    return build(
        topic=_TOPIC,
        tone=_TONE,
        target_audience=_AUDIENCE,
        brand_voice_block=_brand_voice_block(),
    )


def _topic_only(build: Callable[..., tuple[str, str]]) -> tuple[str, str]:
    return build(topic=_TOPIC, tone=None, target_audience=None)


def _analyze(goal: ImprovementGoal) -> tuple[str, str]:
    # The API requires `new_audience` for audience_rewrite and the hint ignores it otherwise.
    new_audience = _NEW_AUDIENCE if goal is ImprovementGoal.AUDIENCE_REWRITE else None
    return improver.build_analyze(
        original_text=_ORIGINAL_TEXT, goal=goal, new_audience=new_audience
    )


def _rewrite(planned_changes: list[str]) -> tuple[str, str]:
    return improver.build_rewrite(
        original_text=_ORIGINAL_TEXT,
        goal=ImprovementGoal.PERSUASIVE,
        planned_changes=planned_changes,
    )


def _cases() -> dict[str, _Render]:
    cases: dict[str, _Render] = {}
    for name, build in _CONTENT_BUILDERS.items():
        cases[f"{name}.full_brief"] = partial(_full_brief, build)
        cases[f"{name}.topic_only"] = partial(_topic_only, build)
    for goal in ImprovementGoal:
        cases[f"improver_analyze.{goal.value}"] = partial(_analyze, goal)
    cases["improver_rewrite.with_plan"] = partial(_rewrite, _PLANNED_CHANGES)
    # What the rewriter gets when the analyze stage degraded to no plan.
    cases["improver_rewrite.no_plan"] = partial(_rewrite, [])
    return cases


_CASES = _cases()


def _golden_text(system: str, user: str) -> str:
    return f"=== system ===\n{system}\n\n=== user ===\n{user}\n"


@pytest.mark.parametrize("case", list(_CASES))
def test_rendered_prompt_matches_its_golden_file(case: str) -> None:
    rendered = _golden_text(*_CASES[case]())
    path = _GOLDEN_DIR / f"{case}.txt"
    # Read with universal newlines, so a CRLF checkout compares equal.
    expected = path.read_text(encoding="utf-8") if path.exists() else None

    if _UPDATE:
        if rendered != expected:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8", newline="\n")
        return

    if expected is None:
        pytest.fail(f"{path.name} is missing; create it with UPDATE_GOLDENS=1.", pytrace=False)
    if rendered != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                rendered.splitlines(keepends=True),
                fromfile=f"golden/prompts/{path.name}",
                tofile="rendered",
            )
        )
        pytest.fail(
            f"{case} no longer matches its golden file. If the change is intended, bump "
            f"PROMPT_VERSION where it applies and rerun with UPDATE_GOLDENS=1.\n\n{diff}",
            pytrace=False,
        )


def test_every_golden_file_belongs_to_a_case() -> None:
    """A renamed or removed case must not leave behind a file nothing checks."""
    expected = {f"{case}.txt" for case in _CASES}
    stale = sorted(path.name for path in _GOLDEN_DIR.glob("*.txt") if path.name not in expected)
    assert not stale, f"no case renders these golden files; delete them: {stale}"


_CORRECTIVE_RETRY_INSTRUCTIONS = {
    "blog_post": blog_post.CORRECTIVE_RETRY_INSTRUCTION,
    "linkedin_post": linkedin_post.CORRECTIVE_RETRY_INSTRUCTION,
    "email": email.CORRECTIVE_RETRY_INSTRUCTION,
    "ad_copy": ad_copy.CORRECTIVE_RETRY_INSTRUCTION,
    "improver_analyze": improver.CORRECTIVE_RETRY_INSTRUCTION_ANALYZE,
    "improver_rewrite": improver.CORRECTIVE_RETRY_INSTRUCTION_REWRITE,
    "image_prompt": image_prompt_builder.CORRECTIVE_RETRY_INSTRUCTION,
}


def test_no_prompt_names_the_app() -> None:
    """A prompt that names the app invites the model to sign the user's copy with it."""
    prompts = {case: "\n".join(render()) for case, render in _CASES.items()}
    for style in image_prompt_builder.SUPPORTED_STYLES:
        rendered = image_prompt_builder.build_prompt(content_summary=_TOPIC, style=style)
        prompts[f"image_prompt.{style}"] = "\n".join(rendered)
    for name, instruction in _CORRECTIVE_RETRY_INSTRUCTIONS.items():
        prompts[f"{name}.corrective_retry"] = instruction

    naming_app = sorted(name for name, text in prompts.items() if "figurematch" in text.casefold())
    assert not naming_app, f"these prompts name FigureMatch: {naming_app}"
