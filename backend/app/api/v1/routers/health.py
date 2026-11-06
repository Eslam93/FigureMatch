"""Health endpoint. Reports service version and downstream-dep status.

Probes attach as the components they depend on land:
  - ``db``     — real ``SELECT 1`` probe (wired in P1.2)
  - ``openai`` — real probe (wired in P1.7)
Unwired probes report ``unknown``.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.db.session import check_db_health

router = APIRouter(tags=["system"])


DependencyState = Literal["ok", "unknown", "down"]


class DependencyStatus(BaseModel):
    db: DependencyState = "unknown"
    openai: DependencyState = "unknown"


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    environment: str
    dependencies: DependencyStatus = Field(default_factory=DependencyStatus)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health and dependency status",
)
async def health() -> HealthResponse:
    settings = get_settings()
    db_state: DependencyState = "ok" if await check_db_health() else "down"
    return HealthResponse(
        version=settings.app_version,
        environment=settings.environment.value,
        dependencies=DependencyStatus(db=db_state),
    )
