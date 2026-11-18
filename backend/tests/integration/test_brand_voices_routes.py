# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Integration tests for /brand-voices CRUD + injection into /content/generate."""

from __future__ import annotations

import pytest

from app.providers.factory import reset_provider_cache
from app.providers.llm.mock import MockLLMProvider


@pytest.fixture(autouse=True)
def _force_mock_llm(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "app.api.v1.routers.content.get_llm_provider",
        lambda: MockLLMProvider(),
    )
    reset_provider_cache()


async def _register(client, email: str = "voice@example.com") -> str:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Secret123",
            "full_name": "Voice User",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


async def _create_voice(client, token, name: str = "Direct"):  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/brand-voices",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "description": "Direct and honest.",
            "tone_descriptors": ["direct", "warm"],
            "banned_words": ["leverage"],
            "sample_text": "We tested every claim against production.",
            "target_audience": "engineers",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_then_list_returns_the_voice(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register(integration_client)
    created = await _create_voice(integration_client, token)
    assert created["name"] == "Direct"
    assert created["tone_descriptors"] == ["direct", "warm"]

    listing = (
        await integration_client.get(
            "/api/v1/brand-voices",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()
    assert any(item["id"] == created["id"] for item in listing["data"])


async def test_patch_only_updates_present_keys(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register(integration_client)
    created = await _create_voice(integration_client, token)
    response = await integration_client.patch(
        f"/api/v1/brand-voices/{created['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Even more direct"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Even more direct"
    # Other fields unchanged.
    assert body["tone_descriptors"] == ["direct", "warm"]
    assert body["banned_words"] == ["leverage"]


async def test_delete_removes_voice_from_list(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register(integration_client)
    created = await _create_voice(integration_client, token)
    deleted = await integration_client.delete(
        f"/api/v1/brand-voices/{created['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted_at"] is not None
    listing = (
        await integration_client.get(
            "/api/v1/brand-voices",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()
    assert all(item["id"] != created["id"] for item in listing["data"])


async def test_other_users_voice_returns_404(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    owner_token = await _register(integration_client, email="owner-bv@example.com")
    voice = await _create_voice(integration_client, owner_token)
    other_token = await _register(integration_client, email="other-bv@example.com")
    response = await integration_client.get(
        f"/api/v1/brand-voices/{voice['id']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BRAND_VOICE_NOT_FOUND"


async def test_generate_with_brand_voice_persists_block_in_snapshot(
    integration_client,  # type: ignore[no-untyped-def]
    db_session,  # type: ignore[no-untyped-def]
) -> None:
    from sqlalchemy import select

    from app.db.models import ContentPiece

    token = await _register(integration_client)
    voice = await _create_voice(integration_client, token, name="UniqueBrandMarker")

    response = await integration_client.post(
        "/api/v1/content/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "content_type": "blog_post",
            "topic": "Generation pinned to a brand voice",
            "brand_voice_id": voice["id"],
        },
    )
    content_id = response.json()["content_id"]
    stmt = select(ContentPiece).where(ContentPiece.id == content_id)
    row = (await db_session.execute(stmt)).scalar_one()
    assert "UniqueBrandMarker" in row.user_prompt_snapshot
    assert "Tone: direct, warm" in row.user_prompt_snapshot
    assert row.brand_voice_id is not None
    assert str(row.brand_voice_id) == voice["id"]


async def test_generate_with_unknown_brand_voice_returns_404(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register(integration_client)
    response = await integration_client.post(
        "/api/v1/content/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "content_type": "blog_post",
            "topic": "Unknown voice",
            "brand_voice_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BRAND_VOICE_NOT_FOUND"
