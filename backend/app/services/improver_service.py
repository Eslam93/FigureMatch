"""Improver service — analyze + rewrite, two-pass chain.

PROJECT_BRIEF §7.6 asks for a two-call chain: ANALYZE returns issues +
planned changes, REWRITE consumes those changes and returns the final
improved text + explanation + structured summary. This module wires
the chain to the same three-stage parse fallback the content service
uses, applied independently to each stage.

Stage breakdown:

  ANALYZE
    1. strict json_schema → ok, return planned_changes
    2. corrective retry, same strict json_schema, naming what failed
    3. degraded — return an empty planned_changes list (the rewriter
       still runs; the goal hint alone drives it)

  REWRITE
    1. strict json_schema → ok, return ImprovementResult
    2. corrective retry, same strict json_schema, naming what failed
    3. degraded — `improved_text` falls back to the model's raw output;
       `explanation` defaults to a single "Rewrite returned in fallback
       mode" line; `changes_summary` defaults to zero deltas. The
       persisted row is still useful — the user sees something — and
       Sentry logs the drift.

A corrective retry that comes back cut off or filtered
(`ProviderIncompleteOutput`) counts as a failed retry: its usage is still
summed, and stage 3 falls back to attempt 1's raw output.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Improvement, User
from app.db.session import end_read_transaction
from app.prompts import improver as improver_prompt
from app.providers.errors import ProviderIncompleteOutput
from app.providers.llm.base import ILLMProvider
from app.repositories.improvement_repository import ImprovementRepository
from app.schemas.improvement import (
    ImprovementChangesSummary,
    ImprovementResult,
    ImproveRequest,
)
from app.services.corrective_retry import ParseFailure, corrective_user_prompt, parse_reply

log = get_logger(__name__)


# ── intermediate types ─────────────────────────────────────────────────


class _AnalyzeReply(BaseModel):
    """The analyze stage's reply. Lenient: unknown keys are ignored and
    list items of any type are kept, as strings, by the caller."""

    issues: list[Any]
    planned_changes: list[Any]


@dataclass(frozen=True)
class _AnalyzeOutcome:
    planned_changes: list[str]
    issues: list[str]
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


@dataclass(frozen=True)
class _RewriteOutcome:
    result: ImprovementResult
    degraded: bool
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


# ── service ────────────────────────────────────────────────────────────


def _word_count(text_value: str) -> int:
    return len(text_value.split()) if text_value.strip() else 0


class ImproverService:
    """Run the analyze + rewrite chain and persist the result."""

    def __init__(self, session: AsyncSession, provider: ILLMProvider) -> None:
        self._session = session
        self._provider = provider
        self._repo = ImprovementRepository(session)

    async def improve(
        self,
        *,
        user: User,
        request: ImproveRequest,
    ) -> Improvement:
        analyze = await self._run_analyze(request)
        rewrite = await self._run_rewrite(request, analyze.planned_changes)

        improvement = Improvement(
            user_id=user.id,
            original_text=request.original_text,
            improved_text=rewrite.result.improved_text,
            goal=request.goal,
            new_audience=request.new_audience,
            explanation=rewrite.result.explanation,
            changes_summary=rewrite.result.changes_summary.model_dump(),
            original_word_count=_word_count(request.original_text),
            improved_word_count=_word_count(rewrite.result.improved_text),
            model_id=rewrite.model,
            input_tokens=analyze.input_tokens + rewrite.input_tokens,
            output_tokens=analyze.output_tokens + rewrite.output_tokens,
            cost_usd=analyze.cost_usd + rewrite.cost_usd,
        )
        return await self._repo.create(improvement)

    # ── analyze ────────────────────────────────────────────────────────

    async def _run_analyze(self, request: ImproveRequest) -> _AnalyzeOutcome:
        system_prompt, user_prompt = improver_prompt.build_analyze(
            original_text=request.original_text,
            goal=request.goal,
            new_audience=request.new_audience,
        )
        json_schema = improver_prompt.ANALYZE_JSON_SCHEMA["schema"]

        # Don't hold the current-user read's transaction through the call.
        await end_read_transaction(self._session)
        attempt1 = await self._provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=json_schema,
            content_type="improver_analysis",
        )
        parsed = parse_reply(attempt1.raw_text, _AnalyzeReply)
        total_in = attempt1.input_tokens
        total_out = attempt1.output_tokens
        total_cost = Decimal(str(attempt1.cost_usd))

        if isinstance(parsed, ParseFailure):
            log.warning("improver_analyze_parse_failed_attempt_1", model=attempt1.model)
            await end_read_transaction(self._session)
            try:
                attempt2 = await self._provider.generate(
                    system_prompt=system_prompt,
                    user_prompt=corrective_user_prompt(
                        user_prompt=user_prompt,
                        previous_reply=attempt1.raw_text,
                        failure=parsed,
                        instruction=improver_prompt.CORRECTIVE_RETRY_INSTRUCTION_ANALYZE,
                    ),
                    json_schema=json_schema,
                    content_type="improver_analysis",
                )
            except ProviderIncompleteOutput as exc:
                # Billed, but cut off or filtered: degrade as if it hadn't parsed.
                attempt2 = exc.result
            else:
                parsed = parse_reply(attempt2.raw_text, _AnalyzeReply)
            total_in += attempt2.input_tokens
            total_out += attempt2.output_tokens
            total_cost += Decimal(str(attempt2.cost_usd))

            if isinstance(parsed, ParseFailure):
                log.warning("improver_analyze_parse_failed_attempt_2", model=attempt2.model)

        if isinstance(parsed, ParseFailure):
            planned: list[str] = []
            issues: list[str] = []
        else:
            planned = [str(change) for change in parsed.planned_changes]
            issues = [str(issue) for issue in parsed.issues]
        return _AnalyzeOutcome(
            planned_changes=planned,
            issues=issues,
            model=attempt1.model,
            input_tokens=total_in,
            output_tokens=total_out,
            cost_usd=total_cost,
        )

    # ── rewrite ────────────────────────────────────────────────────────

    async def _run_rewrite(
        self,
        request: ImproveRequest,
        planned_changes: list[str],
    ) -> _RewriteOutcome:
        system_prompt, user_prompt = improver_prompt.build_rewrite(
            original_text=request.original_text,
            goal=request.goal,
            planned_changes=planned_changes,
            new_audience=request.new_audience,
        )
        json_schema = improver_prompt.REWRITE_JSON_SCHEMA["schema"]

        await end_read_transaction(self._session)
        attempt1 = await self._provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=json_schema,
            content_type="improver_rewrite",
        )
        parsed = parse_reply(attempt1.raw_text, ImprovementResult)
        total_in = attempt1.input_tokens
        total_out = attempt1.output_tokens
        total_cost = Decimal(str(attempt1.cost_usd))
        raw_for_fallback = attempt1.raw_text

        if isinstance(parsed, ParseFailure):
            log.warning("improver_rewrite_parse_failed_attempt_1", model=attempt1.model)
            await end_read_transaction(self._session)
            try:
                attempt2 = await self._provider.generate(
                    system_prompt=system_prompt,
                    user_prompt=corrective_user_prompt(
                        user_prompt=user_prompt,
                        previous_reply=attempt1.raw_text,
                        failure=parsed,
                        instruction=improver_prompt.CORRECTIVE_RETRY_INSTRUCTION_REWRITE,
                    ),
                    json_schema=json_schema,
                    content_type="improver_rewrite",
                )
            except ProviderIncompleteOutput as exc:
                # Billed, but cut off or filtered: fall back to attempt 1's reply.
                attempt2 = exc.result
            else:
                parsed = parse_reply(attempt2.raw_text, ImprovementResult)
                raw_for_fallback = attempt2.raw_text
            total_in += attempt2.input_tokens
            total_out += attempt2.output_tokens
            total_cost += Decimal(str(attempt2.cost_usd))

            if isinstance(parsed, ParseFailure):
                log.warning("improver_rewrite_parse_failed_attempt_2", model=attempt2.model)
                parsed = ImprovementResult(
                    improved_text=raw_for_fallback or request.original_text,
                    explanation=[
                        "Rewrite returned in fallback mode — formatting may be inconsistent."
                    ],
                    changes_summary=ImprovementChangesSummary(
                        tone_shift="unchanged",
                        length_change_pct=0.0,
                        key_additions=[],
                        key_removals=[],
                    ),
                )
                return _RewriteOutcome(
                    result=parsed,
                    degraded=True,
                    model=attempt1.model,
                    input_tokens=total_in,
                    output_tokens=total_out,
                    cost_usd=total_cost,
                )

        return _RewriteOutcome(
            result=parsed,
            degraded=False,
            model=attempt1.model,
            input_tokens=total_in,
            output_tokens=total_out,
            cost_usd=total_cost,
        )
