"""Seed the database with demo content.

Idempotent — re-running won't create duplicate users, voices, or pieces.
Designed for the demo: one user, one brand voice, three content pieces
(one per text content type the demo cares about), one image per piece,
one improvement. Uses the mock providers throughout so the script
runs offline and the bill stays at zero.

Usage:

    python -m app.scripts.seed

Env vars honoured: `DATABASE_URL`, `AI_PROVIDER_MODE` (forced to `mock`
inside the script regardless of env), `IMAGES_CDN_BASE_URL`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import configure_logging, get_logger
from app.db.enums import ContentType, ImprovementGoal
from app.db.models import BrandVoice, ContentPiece, GeneratedImage, Improvement, User
from app.db.session import close_db_engine, get_sessionmaker
from app.providers.image.mock import MockImageProvider
from app.providers.llm.mock import MockLLMProvider
from app.schemas.content import GenerateRequest
from app.schemas.improvement import ImproveRequest
from app.services.content_service import ContentService
from app.services.image_service import ImageService
from app.services.image_storage import build_image_storage
from app.services.improver_service import ImproverService

log = get_logger(__name__)

DEMO_EMAIL = "demo@figurematch.dev"
DEMO_PASSWORD = "DemoPass123"  # noqa: S105 — public demo credential, printed on success
DEMO_NAME = "FigureMatch Demo"

DEMO_VOICE: dict[str, Any] = {
    "name": "In-house voice",
    "description": "Direct, specific, no clichés.",
    "tone_descriptors": ["direct", "specific", "warm"],
    "banned_words": ["leverage", "synergy", "game-changer", "in today's fast-paced world"],
    "sample_text": (
        "We ran every claim against production. The numbers held. "
        "If a sentence doesn't survive that test it doesn't ship."
    ),
    "target_audience": "engineering managers and senior individual contributors",
}


async def _ensure_user(session: AsyncSession) -> User:
    """Create the demo user if they don't exist, return the row."""
    stmt = select(User).where(User.email == DEMO_EMAIL)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is not None:
        log.info("seed_user_exists", user_id=str(user.id))
        return user

    from app.core.security import hash_password
    from app.repositories.user_repository import UserRepository

    repo = UserRepository(session)
    new_user = await repo.create(
        email=DEMO_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        full_name=DEMO_NAME,
    )
    log.info("seed_user_created", user_id=str(new_user.id), email=DEMO_EMAIL)
    return new_user


async def _ensure_brand_voice(session: AsyncSession, user: User) -> BrandVoice:
    stmt = select(BrandVoice).where(
        BrandVoice.user_id == user.id,
        BrandVoice.name == DEMO_VOICE["name"],
        BrandVoice.deleted_at.is_(None),
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        log.info("seed_voice_exists", voice_id=str(existing.id))
        return existing
    voice = BrandVoice(
        user_id=user.id,
        name=DEMO_VOICE["name"],
        description=DEMO_VOICE["description"],
        tone_descriptors=DEMO_VOICE["tone_descriptors"],
        banned_words=DEMO_VOICE["banned_words"],
        sample_text=DEMO_VOICE["sample_text"],
        target_audience=DEMO_VOICE["target_audience"],
    )
    session.add(voice)
    await session.flush()
    await session.refresh(voice)
    log.info("seed_voice_created", voice_id=str(voice.id))
    return voice


async def _ensure_content_pieces(
    session: AsyncSession,
    user: User,
    voice: BrandVoice,
) -> list[ContentPiece]:
    """Generate three pieces (blog / linkedin / email) if absent."""
    targets = [
        (ContentType.BLOG_POST, "How small teams should evaluate AI tools"),
        (ContentType.LINKEDIN_POST, "Three reasons mocks beat magic in CI"),
        (ContentType.EMAIL, "Sneak peek of the new improver chain"),
    ]
    existing_stmt = select(ContentPiece).where(
        ContentPiece.user_id == user.id,
        ContentPiece.deleted_at.is_(None),
    )
    existing = (await session.execute(existing_stmt)).scalars().all()
    existing_topics = {row.topic for row in existing}

    service = ContentService(session, MockLLMProvider())
    created: list[ContentPiece] = list(existing)
    for content_type, topic in targets:
        if topic in existing_topics:
            log.info("seed_piece_exists", content_type=content_type.value, topic=topic)
            continue
        request = GenerateRequest(
            content_type=content_type,
            topic=topic,
            tone=None,
            target_audience=None,
            brand_voice_id=voice.id,
        )
        piece = await service.generate(user=user, request=request)
        log.info(
            "seed_piece_created",
            content_type=content_type.value,
            topic=topic,
            piece_id=str(piece.id),
        )
        created.append(piece)
    return created


async def _ensure_one_image_per_piece(
    session: AsyncSession,
    user: User,
    pieces: list[ContentPiece],
) -> None:
    storage = build_image_storage()
    image_service = ImageService(
        session,
        llm_provider=MockLLMProvider(),
        image_provider=MockImageProvider(),
        storage=storage,
    )
    for piece in pieces:
        # Skip if this piece already has any image attached.
        stmt = select(GeneratedImage).where(GeneratedImage.content_piece_id == piece.id)
        if (await session.execute(stmt)).scalar_one_or_none() is not None:
            log.info("seed_image_exists", piece_id=str(piece.id))
            continue
        image = await image_service.generate_for_content(
            user=user,
            content_id=piece.id,
            style="photorealistic",
        )
        log.info("seed_image_created", image_id=str(image.id), piece_id=str(piece.id))


async def _ensure_one_improvement(session: AsyncSession, user: User) -> Improvement:
    stmt = select(Improvement).where(
        Improvement.user_id == user.id,
        Improvement.deleted_at.is_(None),
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        log.info("seed_improvement_exists", improvement_id=str(existing.id))
        return existing
    service = ImproverService(session, MockLLMProvider())
    record = await service.improve(
        user=user,
        request=ImproveRequest(
            original_text=(
                "The product is a tool that can help your team do many things "
                "in many ways. You should try it."
            ),
            goal=ImprovementGoal.PERSUASIVE,
        ),
    )
    log.info("seed_improvement_created", improvement_id=str(record.id))
    return record


async def seed() -> None:
    configure_logging("INFO")
    sessionmaker = get_sessionmaker()
    try:
        async with sessionmaker() as session:
            user = await _ensure_user(session)
            voice = await _ensure_brand_voice(session, user)
            pieces = await _ensure_content_pieces(session, user, voice)
            await _ensure_one_image_per_piece(session, user, pieces)
            await _ensure_one_improvement(session, user)
            await session.commit()
            log.info(
                "seed_complete",
                email=DEMO_EMAIL,
                password=DEMO_PASSWORD,
                pieces=len(pieces),
            )
    finally:
        await close_db_engine()


def main() -> None:
    """`python -m app.scripts.seed` entrypoint."""
    asyncio.run(seed())


if __name__ == "__main__":  # pragma: no cover
    main()
