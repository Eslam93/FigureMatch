# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Pydantic request / response schemas for /improve endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.enums import ImprovementGoal


class ImproveRequest(BaseModel):
    """Body for POST /improve."""

    original_text: Annotated[str, Field(min_length=10, max_length=20000)]
    goal: ImprovementGoal
    new_audience: Annotated[str | None, Field(default=None, max_length=500)] = None

    @model_validator(mode="after")
    def _audience_required_for_audience_rewrite(self) -> ImproveRequest:
        if self.goal is ImprovementGoal.AUDIENCE_REWRITE and not (
            self.new_audience and self.new_audience.strip()
        ):
            raise ValueError("`new_audience` is required when goal=audience_rewrite")
        return self


class ImprovementChangesSummary(BaseModel):
    """Structured rollup the rewriter returns alongside the new text."""

    model_config = ConfigDict(extra="forbid")

    tone_shift: str
    length_change_pct: float
    key_additions: list[str]
    key_removals: list[str]


class ImprovementResult(BaseModel):
    """Final shape the rewrite stage returns."""

    model_config = ConfigDict(extra="forbid")

    improved_text: Annotated[str, Field(min_length=1)]
    explanation: list[str]
    changes_summary: ImprovementChangesSummary


class ImprovementResponse(BaseModel):
    """Wire shape for both POST /improve and GET /improvements/:id."""

    id: uuid.UUID
    original_text: str
    improved_text: str
    goal: ImprovementGoal
    new_audience: str | None
    explanation: list[str]
    changes_summary: ImprovementChangesSummary
    original_word_count: int
    improved_word_count: int
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    created_at: datetime
    deleted_at: datetime | None


class ImprovementListItem(BaseModel):
    """Lightweight row for the list view (no full original/improved text
    — those come back via the detail endpoint when the user expands a
    row)."""

    id: uuid.UUID
    goal: ImprovementGoal
    original_preview: str
    improved_preview: str
    original_word_count: int
    improved_word_count: int
    created_at: datetime


class ImprovementListResponse(BaseModel):
    data: list[ImprovementListItem]


__all__ = [
    "ImproveRequest",
    "ImprovementChangesSummary",
    "ImprovementGoal",
    "ImprovementListItem",
    "ImprovementListResponse",
    "ImprovementResponse",
    "ImprovementResult",
]
