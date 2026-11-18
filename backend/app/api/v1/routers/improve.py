# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""/improve and /improvements/* endpoints.

Slice 5 ships POST /improve (non-streaming — the brief explicitly
allows it) plus a thin CRUD surface on /improvements so the dashboard
side of the improver matches /content.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.api.v1.deps import CurrentUser
from app.core.exceptions import NotFoundError
from app.db.session import DbSession
from app.providers.factory import get_llm_provider
from app.repositories.improvement_repository import ImprovementRepository
from app.schemas.improvement import (
    ImprovementChangesSummary,
    ImprovementListItem,
    ImprovementListResponse,
    ImprovementResponse,
    ImproveRequest,
)
from app.services.improver_service import ImproverService

router = APIRouter(tags=["improver"])

_PREVIEW_LEN = 200


def _preview(value: str) -> str:
    if len(value) <= _PREVIEW_LEN:
        return value
    return value[:_PREVIEW_LEN].rstrip() + "…"


def _project(record) -> ImprovementResponse:  # type: ignore[no-untyped-def]
    return ImprovementResponse(
        id=record.id,
        original_text=record.original_text,
        improved_text=record.improved_text,
        goal=record.goal,
        new_audience=record.new_audience,
        explanation=list(record.explanation or []),
        changes_summary=ImprovementChangesSummary.model_validate(
            record.changes_summary or {},
        ),
        original_word_count=record.original_word_count or 0,
        improved_word_count=record.improved_word_count or 0,
        model_id=record.model_id,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        cost_usd=record.cost_usd,
        created_at=record.created_at,
        deleted_at=record.deleted_at,
    )


@router.post(
    "/improve",
    response_model=ImprovementResponse,
    status_code=status.HTTP_200_OK,
    summary="Improve a piece of text (analyze → rewrite chain).",
)
async def improve(
    body: ImproveRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ImprovementResponse:
    """Run the two-call chain end to end and persist the result."""
    service = ImproverService(db, get_llm_provider())
    record = await service.improve(user=current_user, request=body)
    await db.commit()
    return _project(record)


@router.get(
    "/improvements",
    response_model=ImprovementListResponse,
    summary="List the caller's improvements, newest first.",
)
async def list_improvements(
    current_user: CurrentUser,
    db: DbSession,
) -> ImprovementListResponse:
    repo = ImprovementRepository(db)
    rows = await repo.list_for_user(current_user.id)
    return ImprovementListResponse(
        data=[
            ImprovementListItem(
                id=row.id,
                goal=row.goal,
                original_preview=_preview(row.original_text),
                improved_preview=_preview(row.improved_text),
                original_word_count=row.original_word_count or 0,
                improved_word_count=row.improved_word_count or 0,
                created_at=row.created_at,
            )
            for row in rows
        ],
    )


@router.get(
    "/improvements/{improvement_id}",
    response_model=ImprovementResponse,
    summary="Get one improvement (active rows only).",
)
async def get_improvement(
    improvement_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> ImprovementResponse:
    repo = ImprovementRepository(db)
    record = await repo.get_for_user(improvement_id, current_user.id)
    if record is None:
        raise NotFoundError("Improvement not found.", code="IMPROVEMENT_NOT_FOUND")
    return _project(record)


@router.delete(
    "/improvements/{improvement_id}",
    response_model=ImprovementResponse,
    summary="Soft-delete an improvement. No restore window (yet).",
)
async def delete_improvement(
    improvement_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> ImprovementResponse:
    repo = ImprovementRepository(db)
    record = await repo.soft_delete(improvement_id, current_user.id)
    if record is None:
        raise NotFoundError("Improvement not found.", code="IMPROVEMENT_NOT_FOUND")
    await db.commit()
    return _project(record)
