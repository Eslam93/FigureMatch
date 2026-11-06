"""Unit tests for ImproverService — the analyze + rewrite chain.

Locks the per-stage fallback semantics and the cost summation across
both calls.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.db.enums import ImprovementGoal
from app.prompts import improver as improver_prompt
from app.providers.llm.base import LLMResult
from app.schemas.improvement import ImproveRequest
from app.services.improver_service import ImproverService


@dataclass
class _RecordingSession:
    added: list[Any] | None = None

    def __post_init__(self) -> None:
        self.added = []

    async def commit(self) -> None:
        # The service ends the read transaction before each model call; see
        # tests/integration/test_model_call_transactions.py for a real session.
        return None

    def add(self, obj: Any) -> None:
        assert self.added is not None
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: Any) -> None:
        return None


def _llm_with(raw_texts: list[str]) -> AsyncMock:
    results = [
        LLMResult(
            raw_text=raw,
            model="fake-llm",
            input_tokens=10,
            output_tokens=20,
            cost_usd=0.005,
            latency_ms=1,
            finish_reason="stop",
        )
        for raw in raw_texts
    ]
    mock = AsyncMock()
    mock.generate.side_effect = results
    return mock


_VALID_ANALYZE = json.dumps(
    {
        "issues": ["Buries the lede.", "Generic CTA."],
        "planned_changes": ["Move the strongest claim first.", "Make the CTA verb-first."],
    }
)

_VALID_REWRITE = json.dumps(
    {
        "improved_text": "An improved piece of marketing copy with a strong opening.",
        "explanation": ["Led with the concrete claim.", "Rewrote the CTA as an imperative."],
        "changes_summary": {
            "tone_shift": "softened_to_direct",
            "length_change_pct": -10.0,
            "key_additions": ["concrete claim"],
            "key_removals": ["passive CTA"],
        },
    }
)


def _request(goal: ImprovementGoal = ImprovementGoal.PERSUASIVE) -> ImproveRequest:
    return ImproveRequest(
        original_text=(
            "The product is a tool that can help your team do many things "
            "in many ways and you should try it."
        ),
        goal=goal,
        new_audience="senior engineers" if goal is ImprovementGoal.AUDIENCE_REWRITE else None,
    )


def _user() -> Any:
    return type("U", (), {"id": uuid.uuid4()})()


@pytest.mark.asyncio
async def test_happy_path_persists_improvement_with_summed_costs() -> None:
    session = _RecordingSession()
    provider = _llm_with([_VALID_ANALYZE, _VALID_REWRITE])
    service = ImproverService(session, provider)  # type: ignore[arg-type]

    record = await service.improve(user=_user(), request=_request())
    assert "An improved piece" in record.improved_text
    assert record.goal == ImprovementGoal.PERSUASIVE
    assert len(record.explanation) == 2
    # Costs from both calls sum onto the row.
    assert record.input_tokens == 20  # 10 + 10
    assert record.output_tokens == 40  # 20 + 20
    assert record.cost_usd == Decimal("0.010")
    assert provider.generate.await_count == 2
    # Word counts populated.
    assert record.original_word_count and record.original_word_count > 0
    assert record.improved_word_count and record.improved_word_count > 0


@pytest.mark.asyncio
async def test_analyze_parse_failure_still_runs_rewrite_with_empty_plan() -> None:
    """If the analyzer returns junk on both attempts, the rewriter
    still fires — with an empty `planned_changes` it falls back to
    the goal hint alone."""
    session = _RecordingSession()
    provider = _llm_with(["bad json", "still bad", _VALID_REWRITE])
    service = ImproverService(session, provider)  # type: ignore[arg-type]

    record = await service.improve(user=_user(), request=_request())
    # Three calls total: analyze-attempt-1, analyze-attempt-2, rewrite-attempt-1.
    assert provider.generate.await_count == 3
    assert "An improved piece" in record.improved_text


@pytest.mark.asyncio
async def test_rewrite_retry_path_status_retried() -> None:
    """First rewrite attempt fails; second succeeds. Tokens from both
    sum onto the row."""
    session = _RecordingSession()
    provider = _llm_with([_VALID_ANALYZE, "junk", _VALID_REWRITE])
    service = ImproverService(session, provider)  # type: ignore[arg-type]

    record = await service.improve(user=_user(), request=_request())
    assert record.improved_text.startswith("An improved piece")
    assert provider.generate.await_count == 3
    # tokens: analyze (10+20) + rewrite_attempt1 (10+20) + rewrite_attempt2 (10+20)
    assert record.input_tokens == 30
    assert record.output_tokens == 60
    assert record.cost_usd == Decimal("0.015")


@pytest.mark.asyncio
async def test_rewrite_total_failure_degrades_with_fallback_summary() -> None:
    """When neither rewrite attempt parses, the persisted row uses the
    raw final attempt as `improved_text` and notes the degrade in
    `explanation`."""
    session = _RecordingSession()
    provider = _llm_with([_VALID_ANALYZE, "bad json", "still bad"])
    service = ImproverService(session, provider)  # type: ignore[arg-type]

    record = await service.improve(user=_user(), request=_request())
    assert record.improved_text == "still bad"
    assert any("fallback mode" in line for line in record.explanation)
    assert record.changes_summary["length_change_pct"] == 0.0


@pytest.mark.asyncio
async def test_analyze_retry_keeps_strict_schema_and_names_the_failing_field() -> None:
    not_a_list = json.dumps({"issues": "Buries the lede.", "planned_changes": ["Lead with it."]})
    session = _RecordingSession()
    provider = _llm_with([not_a_list, _VALID_ANALYZE, _VALID_REWRITE])
    service = ImproverService(session, provider)  # type: ignore[arg-type]  # duck-typed fakes

    await service.improve(user=_user(), request=_request())

    _, retry = provider.generate.call_args_list[1]
    assert retry["content_type"] == "improver_analysis"
    assert retry["json_schema"] == improver_prompt.ANALYZE_JSON_SCHEMA["schema"]
    assert "- issues: Input should be a valid list" in retry["user_prompt"]
    assert "not valid JSON" not in retry["user_prompt"]
    # The retried plan is the one the rewriter executes.
    _, rewrite = provider.generate.call_args_list[2]
    assert "- Move the strongest claim first." in rewrite["user_prompt"]


@pytest.mark.asyncio
async def test_rewrite_retry_keeps_strict_schema_and_names_the_failing_field() -> None:
    empty_text = json.dumps({**json.loads(_VALID_REWRITE), "improved_text": ""})
    session = _RecordingSession()
    provider = _llm_with([_VALID_ANALYZE, empty_text, _VALID_REWRITE])
    service = ImproverService(session, provider)  # type: ignore[arg-type]  # duck-typed fakes

    record = await service.improve(user=_user(), request=_request())

    assert record.improved_text.startswith("An improved piece")
    _, retry = provider.generate.call_args_list[2]
    assert retry["content_type"] == "improver_rewrite"
    assert retry["json_schema"] == improver_prompt.REWRITE_JSON_SCHEMA["schema"]
    assert "- improved_text: String should have at least 1 character" in retry["user_prompt"]
    assert "not valid JSON" not in retry["user_prompt"]


@pytest.mark.asyncio
async def test_analyze_reply_stays_lenient_about_extra_keys_and_item_types() -> None:
    """Behaviour the hand-written analyze parser had: unknown keys are
    ignored and non-string items are kept as strings, with no retry."""
    loose = json.dumps({"issues": ["Too long."], "planned_changes": [42], "notes": "extra"})
    session = _RecordingSession()
    provider = _llm_with([loose, _VALID_REWRITE])
    service = ImproverService(session, provider)  # type: ignore[arg-type]  # duck-typed fakes

    await service.improve(user=_user(), request=_request())

    assert provider.generate.await_count == 2
    _, rewrite = provider.generate.call_args_list[1]
    assert "- 42" in rewrite["user_prompt"]


@pytest.mark.asyncio
async def test_audience_rewrite_requires_new_audience_at_schema_level() -> None:
    with pytest.raises(ValueError):
        ImproveRequest(
            original_text=(
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit "
                "but really at least 10 chars."
            ),
            goal=ImprovementGoal.AUDIENCE_REWRITE,
        )
