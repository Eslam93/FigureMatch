# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Integration tests for /improve and /improvements/* endpoints.

Forces the mock LLM provider so the analyze + rewrite chain runs
deterministically against the canned payloads in MockLLMProvider.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.factory import reset_provider_cache
from app.providers.llm.mock import MockLLMProvider

# See test_content_dashboard module docstring for the reasoning. The
# integration fixture wraps every request in one outer transaction;
# Postgres `now()` is constant within a transaction, so the rows this
# test creates all share an identical `created_at`. The tiebreaker
# (`ORDER BY ... , id DESC`) decides the final order. Tests verify
# the contract directly rather than chasing wall-clock distinctness.


@pytest.fixture(autouse=True)
def _force_mock_llm(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "app.api.v1.routers.improve.get_llm_provider",
        lambda: MockLLMProvider(),
    )
    reset_provider_cache()


async def _register(client) -> str:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "improver@example.com",
            "password": "Secret123",
            "full_name": "Improver Test",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


async def _improve(
    client,  # type: ignore[no-untyped-def]
    token: str,
    *,
    goal: str = "persuasive",
    new_audience: str | None = None,
) -> dict:
    body: dict = {
        "original_text": (
            "The product is a tool that can help your team do many things in many ways. "
            "You should try it."
        ),
        "goal": goal,
    }
    if new_audience is not None:
        body["new_audience"] = new_audience
    response = await client.post(
        "/api/v1/improve",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_improve_returns_full_response(
    integration_client,  # type: ignore[no-untyped-def]
    db_session: AsyncSession,
) -> None:
    token = await _register(integration_client)
    body = await _improve(integration_client, token)
    assert body["improved_text"]
    assert len(body["explanation"]) >= 1
    assert body["changes_summary"]["tone_shift"]
    assert body["goal"] == "persuasive"
    assert body["model_id"] == "mock-llm-v1"
    assert body["original_word_count"] > 0
    assert body["improved_word_count"] > 0


async def test_audience_rewrite_requires_new_audience(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register(integration_client)
    response = await integration_client.post(
        "/api/v1/improve",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "original_text": "Some original text long enough to clear validation.",
            "goal": "audience_rewrite",
        },
    )
    assert response.status_code == 422


async def test_list_returns_newest_first_with_previews(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register(integration_client)
    first = await _improve(integration_client, token)
    second = await _improve(integration_client, token, goal="shorter")

    response = await integration_client.get(
        "/api/v1/improvements",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    ids = [item["id"] for item in data]
    expected_ids = {first["id"], second["id"]}
    assert set(ids) == expected_ids
    # Ordering contract: created_at DESC then id DESC. The fixture's
    # shared transaction collapses both rows' timestamps, so id DESC
    # decides — see module docstring.
    assert ids == sorted(expected_ids, reverse=True)

    for item in data:
        assert item["original_preview"]
        assert item["improved_preview"]


async def test_detail_returns_404_for_unknown_id(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register(integration_client)
    response = await integration_client.get(
        "/api/v1/improvements/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "IMPROVEMENT_NOT_FOUND"


async def test_delete_removes_from_list(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register(integration_client)
    created = await _improve(integration_client, token)

    delete_resp = await integration_client.delete(
        f"/api/v1/improvements/{created['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted_at"] is not None

    listing = (
        await integration_client.get(
            "/api/v1/improvements",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()
    assert all(item["id"] != created["id"] for item in listing["data"])


async def test_improvements_scoped_to_caller(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    response = await integration_client.post(
        "/api/v1/auth/register",
        json={"email": "imp1@example.com", "password": "Secret123", "full_name": "I1"},
    )
    token1 = response.json()["access_token"]
    await _improve(integration_client, token1)

    response = await integration_client.post(
        "/api/v1/auth/register",
        json={"email": "imp2@example.com", "password": "Secret123", "full_name": "I2"},
    )
    token2 = response.json()["access_token"]
    own = (
        await integration_client.get(
            "/api/v1/improvements",
            headers={"Authorization": f"Bearer {token1}"},
        )
    ).json()
    other = (
        await integration_client.get(
            "/api/v1/improvements",
            headers={"Authorization": f"Bearer {token2}"},
        )
    ).json()
    assert len(own["data"]) == 1
    assert len(other["data"]) == 0
