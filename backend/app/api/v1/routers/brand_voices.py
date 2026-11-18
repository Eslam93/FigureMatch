# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""/brand-voices CRUD endpoints.

Standard list / create / detail / update / delete. The PATCH endpoint
uses `model_fields_set` to apply only the keys the caller actually
sent — `None` is treated as "unset", not "set to null". For the few
nullable string columns where the caller really does want to clear
the value, send an empty string.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.api.v1.deps import CurrentUser
from app.core.exceptions import NotFoundError
from app.db.session import DbSession
from app.repositories.brand_voice_repository import BrandVoiceRepository
from app.schemas.brand_voice import (
    BrandVoiceCreate,
    BrandVoiceListResponse,
    BrandVoiceResponse,
    BrandVoiceUpdate,
)

router = APIRouter(prefix="/brand-voices", tags=["brand-voices"])


def _project(voice) -> BrandVoiceResponse:  # type: ignore[no-untyped-def]
    return BrandVoiceResponse(
        id=voice.id,
        name=voice.name,
        description=voice.description,
        tone_descriptors=list(voice.tone_descriptors or []),
        banned_words=list(voice.banned_words or []),
        sample_text=voice.sample_text,
        target_audience=voice.target_audience,
        created_at=voice.created_at,
        updated_at=voice.updated_at,
        deleted_at=voice.deleted_at,
    )


@router.get("", response_model=BrandVoiceListResponse, summary="List the caller's brand voices.")
async def list_voices(
    current_user: CurrentUser,
    db: DbSession,
) -> BrandVoiceListResponse:
    repo = BrandVoiceRepository(db)
    rows = await repo.list_for_user(current_user.id)
    return BrandVoiceListResponse(data=[_project(row) for row in rows])


@router.post(
    "",
    response_model=BrandVoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a brand voice.",
)
async def create_voice(
    body: BrandVoiceCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> BrandVoiceResponse:
    repo = BrandVoiceRepository(db)
    voice = await repo.create(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        tone_descriptors=body.tone_descriptors,
        banned_words=body.banned_words,
        sample_text=body.sample_text,
        target_audience=body.target_audience,
    )
    await db.commit()
    return _project(voice)


@router.get(
    "/{voice_id}",
    response_model=BrandVoiceResponse,
    summary="Get one brand voice.",
)
async def get_voice(
    voice_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> BrandVoiceResponse:
    repo = BrandVoiceRepository(db)
    voice = await repo.get_for_user(voice_id, current_user.id)
    if voice is None:
        raise NotFoundError("Brand voice not found.", code="BRAND_VOICE_NOT_FOUND")
    return _project(voice)


@router.patch(
    "/{voice_id}",
    response_model=BrandVoiceResponse,
    summary="Update one or more brand-voice fields.",
)
async def update_voice(
    voice_id: Annotated[uuid.UUID, Path()],
    body: BrandVoiceUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> BrandVoiceResponse:
    repo = BrandVoiceRepository(db)
    voice = await repo.get_for_user(voice_id, current_user.id)
    if voice is None:
        raise NotFoundError("Brand voice not found.", code="BRAND_VOICE_NOT_FOUND")
    updates = {key: getattr(body, key) for key in body.model_fields_set}
    voice = await repo.update(voice, updates)
    await db.commit()
    return _project(voice)


@router.delete(
    "/{voice_id}",
    response_model=BrandVoiceResponse,
    summary="Soft-delete a brand voice.",
)
async def delete_voice(
    voice_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> BrandVoiceResponse:
    repo = BrandVoiceRepository(db)
    voice = await repo.soft_delete(voice_id, current_user.id)
    if voice is None:
        raise NotFoundError("Brand voice not found.", code="BRAND_VOICE_NOT_FOUND")
    await db.commit()
    return _project(voice)
