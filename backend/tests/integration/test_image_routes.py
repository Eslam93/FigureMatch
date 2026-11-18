# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Integration tests for the image-generation endpoints.

Covers POST /content/{id}/image (with regenerate) and
GET /content/{id}/images. Both paths force the mock LLM + mock image
provider so the test runs offline and the persisted PNG is the
deterministic 1×1 placeholder.

The mock image provider reports cost_usd=0, so the persisted row's
cost reflects only the LLM prompt-building call.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GeneratedImage
from app.providers.factory import reset_provider_cache
from app.providers.image.mock import MockImageProvider
from app.providers.llm.mock import MockLLMProvider


@pytest.fixture(autouse=True)
def _force_mock_providers_and_isolated_storage(monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    """Force mock providers and redirect local-disk storage to a per-
    test tmp directory so concurrent CI runs don't tread on each
    other's bytes."""

    monkeypatch.setattr(
        "app.api.v1.routers.content.get_llm_provider",
        lambda: MockLLMProvider(),
    )
    monkeypatch.setattr(
        "app.api.v1.routers.content.get_image_provider",
        lambda: MockImageProvider(),
    )
    reset_provider_cache()

    # Reroute the storage directory.
    iso_dir = tmp_path / "local_images"
    monkeypatch.setattr("app.services.image_storage.LOCAL_IMAGES_DIR", iso_dir)


async def _register(client) -> str:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "imageuser@example.com",
            "password": "Secret123",
            "full_name": "Image User",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


async def _generate_blog(client, token) -> str:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/content/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": "blog_post", "topic": "A topic for the image test"},
    )
    assert response.status_code == 200, response.text
    return response.json()["content_id"]


async def test_image_generation_creates_current_row_and_writes_file(
    integration_client,  # type: ignore[no-untyped-def]
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    token = await _register(integration_client)
    content_id = await _generate_blog(integration_client, token)

    response = await integration_client.post(
        f"/api/v1/content/{content_id}/image",
        headers={"Authorization": f"Bearer {token}"},
        json={"style": "photorealistic"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    image = body["image"]
    assert image["is_current"] is True
    assert image["style"] == "photorealistic"
    assert image["model_id"] == "mock-image-v1"
    assert image["cdn_url"]
    # The mock provider returns zero-cost image bytes; the LLM
    # prompt-builder call is also zero-cost on the mock path. Total
    # row cost should be zero.
    assert image["cost_usd"] in ("0", "0.000000")

    # The DB row exists and is current.
    stmt = select(GeneratedImage).where(GeneratedImage.id == image["id"])
    row = (await db_session.execute(stmt)).scalar_one()
    assert row.is_current is True


async def test_regenerate_flips_previous_current_to_false(
    integration_client,  # type: ignore[no-untyped-def]
    db_session: AsyncSession,
) -> None:
    token = await _register(integration_client)
    content_id = await _generate_blog(integration_client, token)

    first = (
        await integration_client.post(
            f"/api/v1/content/{content_id}/image",
            headers={"Authorization": f"Bearer {token}"},
            json={"style": "photorealistic"},
        )
    ).json()["image"]
    second = (
        await integration_client.post(
            f"/api/v1/content/{content_id}/image",
            headers={"Authorization": f"Bearer {token}"},
            json={"style": "minimalist"},
        )
    ).json()["image"]

    # First image flipped to not-current; the second is now current.
    stmt_first = select(GeneratedImage).where(GeneratedImage.id == first["id"])
    first_row = (await db_session.execute(stmt_first)).scalar_one()
    assert first_row.is_current is False

    stmt_second = select(GeneratedImage).where(GeneratedImage.id == second["id"])
    second_row = (await db_session.execute(stmt_second)).scalar_one()
    assert second_row.is_current is True

    # The partial unique index guarantees at most one current per piece.
    listing = await integration_client.get(
        f"/api/v1/content/{content_id}/images",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listing.status_code == 200, listing.text
    items = listing.json()["data"]
    assert len(items) == 2
    current_ids = [item["id"] for item in items if item["is_current"]]
    assert len(current_ids) == 1
    assert current_ids[0] == second["id"]


async def test_unsupported_style_returns_422(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register(integration_client)
    content_id = await _generate_blog(integration_client, token)
    response = await integration_client.post(
        f"/api/v1/content/{content_id}/image",
        headers={"Authorization": f"Bearer {token}"},
        json={"style": "cubism"},
    )
    # Pydantic Literal validation rejects before the service runs.
    assert response.status_code == 422


async def test_image_endpoint_404s_for_unknown_content(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register(integration_client)
    response = await integration_client.post(
        "/api/v1/content/00000000-0000-0000-0000-000000000000/image",
        headers={"Authorization": f"Bearer {token}"},
        json={"style": "photorealistic"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONTENT_NOT_FOUND"


async def test_list_images_returns_404_for_other_users_piece(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    response = await integration_client.post(
        "/api/v1/auth/register",
        json={"email": "owner-img@example.com", "password": "Secret123", "full_name": "O"},
    )
    owner_token = response.json()["access_token"]
    content_id = await _generate_blog(integration_client, owner_token)

    response = await integration_client.post(
        "/api/v1/auth/register",
        json={"email": "other-img@example.com", "password": "Secret123", "full_name": "X"},
    )
    other_token = response.json()["access_token"]
    response = await integration_client.get(
        f"/api/v1/content/{content_id}/images",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


async def test_local_storage_writes_bytes_to_disk(
    integration_client,  # type: ignore[no-untyped-def]
    monkeypatch,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    """Bytes the storage returns must actually be on disk under the
    redirected directory — a smoke test that the StaticFiles mount
    will be able to serve them."""
    iso_dir = tmp_path / "iso_images"
    monkeypatch.setattr("app.services.image_storage.LOCAL_IMAGES_DIR", iso_dir)
    token = await _register(integration_client)
    content_id = await _generate_blog(integration_client, token)
    response = await integration_client.post(
        f"/api/v1/content/{content_id}/image",
        headers={"Authorization": f"Bearer {token}"},
        json={"style": "photorealistic"},
    )
    assert response.status_code == 200, response.text
    cdn_url = response.json()["image"]["cdn_url"]
    filename = cdn_url.rsplit("/", 1)[-1]
    target = iso_dir / filename
    assert target.exists()
    assert target.read_bytes().startswith(b"\x89PNG")
    # Cleanup defensively in case the fixture didn't run for some reason.
    shutil.rmtree(iso_dir, ignore_errors=True)
