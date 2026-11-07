"""Model calls run with no database transaction open on the request session.

The current-user and brand-voice reads autobegin a transaction on the
request's session. Left open through a 5-30 s model call, it holds a pooled
connection idle in transaction, and about 20 concurrent generations exhaust
the 10 + 10 pool. A probe provider records, at every call (corrective
retries included), whether a request session has a transaction open.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session as session_module
from app.db.models import ContentPiece, Improvement
from app.providers.llm.base import LLMResult
from app.providers.llm.mock import MockLLMProvider


class _TransactionProbe:
    """Notes whether any request session is in a transaction, then answers
    like the mock provider. The first call for each content type gets a
    reply that isn't JSON, so every corrective retry runs too."""

    def __init__(self, request_sessions: list[AsyncSession]) -> None:
        self._request_sessions = request_sessions
        self._mock = MockLLMProvider()
        self.calls: list[tuple[str, bool]] = []

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
        content_type: str,
    ) -> LLMResult:
        first_call = all(seen != content_type for seen, _ in self.calls)
        in_transaction = any(session.in_transaction() for session in self._request_sessions)
        self.calls.append((content_type, in_transaction))
        result = await self._mock.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=json_schema,
            content_type=content_type,
        )
        return replace(result, raw_text="not json") if first_call else result


@pytest.fixture
def request_sessions(
    integration_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> list[AsyncSession]:
    """Every session `get_db_session` opens for a request, in order."""
    open_test_session = session_module.get_sessionmaker()
    opened: list[AsyncSession] = []

    def tracking_sessionmaker() -> Callable[[], AsyncSession]:
        def open_session() -> AsyncSession:
            session = open_test_session()
            opened.append(session)
            return session

        return open_session

    monkeypatch.setattr(session_module, "get_sessionmaker", tracking_sessionmaker)
    return opened


async def _register(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "transactions@example.com",
            "password": "Secret123",
            "full_name": "Transaction Probe",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_content_generation_calls_the_model_outside_a_transaction(
    integration_client: AsyncClient,
    request_sessions: list[AsyncSession],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _TransactionProbe(request_sessions)
    monkeypatch.setattr("app.api.v1.routers.content.get_llm_provider", lambda: probe)
    auth = await _register(integration_client)
    voice = await integration_client.post(
        "/api/v1/brand-voices",
        headers=auth,
        json={
            "name": "Direct",
            "description": "Direct and honest.",
            "tone_descriptors": ["direct"],
            "banned_words": [],
            "sample_text": "We tested every claim against production.",
            "target_audience": "engineers",
        },
    )
    assert voice.status_code == 201, voice.text

    response = await integration_client.post(
        "/api/v1/content/generate",
        headers=auth,
        json={
            "content_type": "blog_post",
            "topic": "Connections idle in transaction",
            "brand_voice_id": voice.json()["id"],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["result_parse_status"] == "retried"
    assert probe.calls == [("blog_post", False), ("blog_post", False)]
    # The write after the calls opens a new transaction, and it still commits.
    stored = await db_session.execute(
        select(ContentPiece).where(ContentPiece.id == uuid.UUID(response.json()["content_id"]))
    )
    assert str(stored.scalar_one().brand_voice_id) == voice.json()["id"]


async def test_both_improver_stages_call_the_model_outside_a_transaction(
    integration_client: AsyncClient,
    request_sessions: list[AsyncSession],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _TransactionProbe(request_sessions)
    monkeypatch.setattr("app.api.v1.routers.improve.get_llm_provider", lambda: probe)
    auth = await _register(integration_client)

    response = await integration_client.post(
        "/api/v1/improve",
        headers=auth,
        json={"original_text": "A draft paragraph that needs work.", "goal": "persuasive"},
    )

    assert response.status_code == 200, response.text
    assert probe.calls == [
        ("improver_analysis", False),
        ("improver_analysis", False),
        ("improver_rewrite", False),
        ("improver_rewrite", False),
    ]
    stored = await db_session.get(Improvement, uuid.UUID(response.json()["id"]))
    assert stored is not None
    assert stored.improved_text == response.json()["improved_text"]
