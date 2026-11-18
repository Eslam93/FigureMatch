# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""/content/* endpoints.

Slice 2 widened POST /content/generate to all four content types. Slice 4
adds the dashboard surface: list, detail, soft delete, and a 24-hour
restore window. The service dispatches generation through its registry;
dashboard reads go through `ContentRepository` directly because there's
no business logic above raw queries.
"""

from __future__ import annotations

import uuid
from math import ceil
from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status
from fastapi.responses import PlainTextResponse

from app.api.v1.deps import CurrentUser
from app.core.exceptions import ConflictError, NotFoundError
from app.core.request_context import get_request_id
from app.db.enums import ContentType
from app.db.models import GeneratedImage
from app.db.session import DbSession
from app.providers.factory import get_image_provider, get_llm_provider
from app.repositories.content_repository import ContentRepository
from app.repositories.image_repository import ImageRepository
from app.schemas.content import (
    ContentDetailResponse,
    ContentListItem,
    ContentListResponse,
    GenerateRequest,
    GenerateResponse,
    GenerateUsage,
    ListMeta,
    PaginationMeta,
)
from app.schemas.image import (
    GeneratedImageResponse,
    ImageGenerateRequest,
    ImageGenerateResponse,
    ImageListResponse,
)
from app.services.content_service import ContentService, project_result
from app.services.export_service import build_markdown, filename_for
from app.services.image_service import ImageService
from app.services.image_storage import IImageStorage, build_image_storage

router = APIRouter(prefix="/content", tags=["content"])

# Server-side preview length for the dashboard list. Trimming here keeps
# wire weight bounded and means the FTS hit and the visible preview
# always come from the same string.
_PREVIEW_LEN = 200


def _build_preview(rendered_text: str) -> str:
    """First `_PREVIEW_LEN` chars of `rendered_text`, with a trailing
    ellipsis when truncated. Newlines pass through; the card flattens
    them at render time.
    """
    if len(rendered_text) <= _PREVIEW_LEN:
        return rendered_text
    return rendered_text[:_PREVIEW_LEN].rstrip() + "…"


def _project_image(image: GeneratedImage, storage: IImageStorage) -> GeneratedImageResponse:
    """Project a `generated_images` row to the wire.

    `cdn_url` is computed fresh from the storage layer's
    `public_url_for(key)` so a configuration change to
    `IMAGES_CDN_BASE_URL` (e.g., the eventual S3 cutover) immediately
    rewrites every row's URL — old rows don't need a backfill. The
    persisted `cdn_url` column stays in sync at write time but is
    treated as a cache, not the source of truth.
    """
    return GeneratedImageResponse(
        id=image.id,
        content_piece_id=image.content_piece_id,
        style=image.style,
        provider=image.provider,
        model_id=image.model_id,
        width=image.width,
        height=image.height,
        cdn_url=storage.public_url_for(image.s3_key),
        image_prompt=image.image_prompt,
        negative_prompt=image.negative_prompt,
        cost_usd=image.cost_usd,
        is_current=image.is_current,
        created_at=image.created_at,
    )


@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate content (blog post, LinkedIn post, email, or ad copy).",
)
async def generate(
    request: GenerateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> GenerateResponse:
    """Generate a piece of content for the caller and persist it.

    `request.content_type` must be one of the values the service has a
    registered prompt + renderer for. Pydantic enum validation on the
    request body rejects unknown values with a 422 before this handler
    runs.
    """
    service = ContentService(db, get_llm_provider())
    piece = await service.generate(user=current_user, request=request)
    await db.commit()

    return GenerateResponse(
        content_id=piece.id,
        content_type=piece.content_type,
        result=project_result(piece.content_type, piece.result),
        rendered_text=piece.rendered_text,
        result_parse_status=piece.result_parse_status,
        word_count=piece.word_count or 0,
        usage=GenerateUsage(
            model_id=piece.model_id,
            input_tokens=piece.input_tokens,
            output_tokens=piece.output_tokens,
            cost_usd=piece.cost_usd,
        ),
        created_at=piece.created_at,
    )


@router.get(
    "",
    response_model=ContentListResponse,
    summary="List the caller's content (paginated, with optional filter + search).",
)
async def list_content(
    current_user: CurrentUser,
    db: DbSession,
    content_type: Annotated[ContentType | None, Query(description="Filter by content type")] = None,
    q: Annotated[
        str | None,
        Query(description="Full-text search over rendered_text", max_length=200),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ContentListResponse:
    """Paginated dashboard query — newest first, scoped to the caller,
    soft-deleted rows excluded."""
    repo = ContentRepository(db)
    rows, total = await repo.list_for_user(
        user_id=current_user.id,
        content_type=content_type,
        q=q,
        page=page,
        page_size=page_size,
    )
    total_pages = ceil(total / page_size) if total else 0
    return ContentListResponse(
        data=[
            ContentListItem(
                id=row.id,
                content_type=row.content_type,
                topic=row.topic,
                preview=_build_preview(row.rendered_text),
                word_count=row.word_count or 0,
                model_id=row.model_id,
                result_parse_status=row.result_parse_status,
                created_at=row.created_at,
            )
            for row in rows
        ],
        meta=ListMeta(
            request_id=get_request_id(),
            pagination=PaginationMeta(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        ),
    )


@router.get(
    "/{content_id}",
    response_model=ContentDetailResponse,
    summary="Get one content piece (active rows only).",
)
async def get_content(
    content_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> ContentDetailResponse:
    repo = ContentRepository(db)
    piece = await repo.get_for_user(content_id, current_user.id)
    if piece is None:
        raise NotFoundError("Content not found.", code="CONTENT_NOT_FOUND")
    return ContentDetailResponse(
        id=piece.id,
        content_type=piece.content_type,
        topic=piece.topic,
        tone=piece.tone,
        target_audience=piece.target_audience,
        result=project_result(piece.content_type, piece.result),
        rendered_text=piece.rendered_text,
        result_parse_status=piece.result_parse_status,
        word_count=piece.word_count or 0,
        model_id=piece.model_id,
        created_at=piece.created_at,
        deleted_at=piece.deleted_at,
    )


@router.get(
    "/{content_id}/export",
    response_class=PlainTextResponse,
    summary="Export a content piece as Markdown.",
    responses={
        200: {
            "content": {"text/markdown": {}},
            "description": "Markdown file with `Content-Disposition: attachment`.",
        }
    },
)
async def export_content(
    content_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
    export_format: Annotated[
        str,
        Query(
            alias="format",
            description="Export format. Only `md` is supported today; "
            "`pdf` and `docx` are tracked in issues #73 / #74.",
            pattern="^md$",
        ),
    ] = "md",
) -> Response:
    """Download the content piece as a Markdown file.

    The body is `rendered_text` (already canonical Markdown — the
    renderer ran at write time in Slice 2) wrapped with a small header
    that carries metadata (topic, type, model, generated-at) and an
    optional trailing image embed if the piece has a current image.

    `format` exists for forward-compat with PDF/DOCX exports; today
    only `md` is accepted and a value mismatch returns 422.
    """
    del export_format  # validated by FastAPI; only one supported value today
    repo = ContentRepository(db)
    piece = await repo.get_for_user(content_id, current_user.id)
    if piece is None:
        raise NotFoundError("Content not found.", code="CONTENT_NOT_FOUND")
    image_repo = ImageRepository(db)
    current_image = await image_repo.get_current_for_content(piece.id)
    storage = build_image_storage()
    image_url = storage.public_url_for(current_image.s3_key) if current_image else None
    body = build_markdown(piece, current_image, image_public_url=image_url)
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename_for(piece)}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete(
    "/{content_id}",
    response_model=ContentDetailResponse,
    summary="Soft-delete the content piece. Restorable for 24 hours.",
)
async def delete_content(
    content_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> ContentDetailResponse:
    repo = ContentRepository(db)
    piece = await repo.soft_delete(content_id, current_user.id)
    if piece is None:
        raise NotFoundError("Content not found.", code="CONTENT_NOT_FOUND")
    await db.commit()
    return ContentDetailResponse(
        id=piece.id,
        content_type=piece.content_type,
        topic=piece.topic,
        tone=piece.tone,
        target_audience=piece.target_audience,
        result=project_result(piece.content_type, piece.result),
        rendered_text=piece.rendered_text,
        result_parse_status=piece.result_parse_status,
        word_count=piece.word_count or 0,
        model_id=piece.model_id,
        created_at=piece.created_at,
        deleted_at=piece.deleted_at,
    )


@router.post(
    "/{content_id}/image",
    response_model=ImageGenerateResponse,
    summary="Generate an image for the content piece (becomes the current image).",
)
async def generate_image(
    body: ImageGenerateRequest,
    content_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> ImageGenerateResponse:
    """Build an image prompt from the content, generate the image, and
    record a new `generated_images` row with `is_current=true`. Any
    previously-current image for the piece is flipped to non-current
    inside the same transaction (partial unique index enforces the
    invariant)."""
    storage = build_image_storage()
    service = ImageService(
        db,
        llm_provider=get_llm_provider(),
        image_provider=get_image_provider(),
        storage=storage,
    )
    image = await service.generate_for_content(
        user=current_user,
        content_id=content_id,
        style=body.style,
    )
    await db.commit()
    return ImageGenerateResponse(image=_project_image(image, storage))


@router.get(
    "/{content_id}/images",
    response_model=ImageListResponse,
    summary="List every image ever generated for this content piece.",
)
async def list_images(
    content_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> ImageListResponse:
    repo = ContentRepository(db)
    piece = await repo.get_for_user(content_id, current_user.id)
    if piece is None:
        raise NotFoundError("Content not found.", code="CONTENT_NOT_FOUND")
    image_repo = ImageRepository(db)
    rows = await image_repo.list_for_content(piece.id)
    storage = build_image_storage()
    return ImageListResponse(
        data=[_project_image(row, storage) for row in rows],
    )


@router.post(
    "/{content_id}/restore",
    response_model=ContentDetailResponse,
    summary="Restore a soft-deleted content piece (24-hour window).",
)
async def restore_content(
    content_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> ContentDetailResponse:
    repo = ContentRepository(db)
    # Distinguish "no such row" from "outside restore window" by
    # checking the include-deleted lookup first. Both surface to the
    # client as a structured error so the toast can speak in plain
    # terms. The state-conflict cases return 409 (ConflictError) so a
    # client doesn't mistake them for input-validation problems.
    piece_inc_deleted = await repo.get_for_user_include_deleted(content_id, current_user.id)
    if piece_inc_deleted is None:
        raise NotFoundError("Content not found.", code="CONTENT_NOT_FOUND")
    if piece_inc_deleted.deleted_at is None:
        raise ConflictError(
            "Content is already active.",
            code="CONTENT_NOT_DELETED",
        )

    piece = await repo.restore(content_id, current_user.id)
    if piece is None:
        # The row was deleted but outside the 24-hour window.
        raise ConflictError(
            "Restore window has expired.",
            code="RESTORE_WINDOW_EXPIRED",
        )
    await db.commit()
    return ContentDetailResponse(
        id=piece.id,
        content_type=piece.content_type,
        topic=piece.topic,
        tone=piece.tone,
        target_audience=piece.target_audience,
        result=project_result(piece.content_type, piece.result),
        rendered_text=piece.rendered_text,
        result_parse_status=piece.result_parse_status,
        word_count=piece.word_count or 0,
        model_id=piece.model_id,
        created_at=piece.created_at,
        deleted_at=piece.deleted_at,
    )
