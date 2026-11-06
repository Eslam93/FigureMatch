"""Upstream AI failures reach the client as typed errors without upstream text.

The real OpenAI providers serve the real routes against scripted HTTP
answers (`tests/scripted_openai.py`). Every scripted failure carries a
sentinel that must not appear in any response. Backoff is zero and the
providers get three attempts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient, Response

from app.providers.image.openai_provider import OpenAIImageProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.openai_provider import OpenAIChatProvider
from tests.scripted_openai import (
    SENTINEL,
    Outcome,
    ScriptedUpstream,
    chat_completion,
    error_response,
    read_timeout,
)

_ATTEMPTS = 3


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    for provider in (OpenAIChatProvider, OpenAIImageProvider):
        monkeypatch.setattr(provider, "_backoff_seconds", staticmethod(lambda _attempt: 0.0))


def _chat_provider(upstream: ScriptedUpstream) -> OpenAIChatProvider:
    return OpenAIChatProvider(
        client=upstream.client(), model="gpt-5.4-mini-2026-03-17", max_retries=_ATTEMPTS
    )


async def _register(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "upstream-errors@example.com",
            "password": "Secret123",
            "full_name": "Upstream Errors",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _assert_safe_error(response: Response, *, status: int, code: str) -> None:
    assert SENTINEL not in response.text
    assert SENTINEL not in str(response.headers)
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"]["code"] == code
    assert body["meta"]["request_id"] == response.headers["x-request-id"]


# outcome, status, code, Retry-After, upstream requests made
_GENERATE_CASES = [
    pytest.param(
        error_response(401, code="invalid_api_key"),
        502,
        "AI_PROVIDER_AUTH_FAILED",
        None,
        1,
        id="401",
    ),
    pytest.param(
        error_response(
            429, code="rate_limit_exceeded", error_type="requests", headers={"retry-after": "7"}
        ),
        429,
        "AI_RATE_LIMITED",
        "7",
        _ATTEMPTS,
        id="429-retry-after",
    ),
    pytest.param(
        error_response(429, code="insufficient_quota", error_type="insufficient_quota"),
        503,
        "AI_UNAVAILABLE",
        None,
        1,
        id="429-insufficient-quota",
    ),
    pytest.param(
        error_response(503, error_type="server_error"),
        503,
        "AI_UNAVAILABLE",
        None,
        _ATTEMPTS,
        id="503",
    ),
    pytest.param(read_timeout(), 504, "AI_TIMEOUT", None, _ATTEMPTS, id="read-timeout"),
    pytest.param(
        chat_completion(f'{{"title": "{SENTINEL}', finish_reason="length"),
        502,
        "AI_OUTPUT_TRUNCATED",
        None,
        1,
        id="finish-reason-length",
    ),
]


@pytest.mark.parametrize(("outcome", "status", "code", "retry_after", "requests"), _GENERATE_CASES)
async def test_generate_reports_upstream_failures_safely(
    integration_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    outcome: Outcome,
    status: int,
    code: str,
    retry_after: str | None,
    requests: int,
) -> None:
    upstream = ScriptedUpstream(outcome)
    monkeypatch.setattr(
        "app.api.v1.routers.content.get_llm_provider", lambda: _chat_provider(upstream)
    )
    auth = await _register(integration_client)

    response = await integration_client.post(
        "/api/v1/content/generate",
        headers=auth,
        json={"content_type": "blog_post", "topic": "Scripted upstream failures"},
    )

    _assert_safe_error(response, status=status, code=code)
    assert response.headers.get("retry-after") == retry_after
    assert len(upstream.requests) == requests


async def test_improve_reports_a_content_policy_block_safely(
    integration_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    upstream = ScriptedUpstream(error_response(400, code="invalid_prompt"))
    monkeypatch.setattr(
        "app.api.v1.routers.improve.get_llm_provider", lambda: _chat_provider(upstream)
    )
    auth = await _register(integration_client)

    response = await integration_client.post(
        "/api/v1/improve",
        headers=auth,
        json={"original_text": "A draft paragraph that needs work.", "goal": "persuasive"},
    )

    _assert_safe_error(response, status=422, code="AI_CONTENT_REJECTED")
    assert len(upstream.requests) == 1


@pytest.mark.parametrize(
    ("outcome", "status", "code"),
    [
        pytest.param(
            error_response(
                400, code="moderation_blocked", error_type="image_generation_user_error"
            ),
            422,
            "AI_CONTENT_REJECTED",
            id="moderation-blocked",
        ),
        pytest.param(
            error_response(401, code="invalid_api_key"),
            502,
            "AI_PROVIDER_AUTH_FAILED",
            id="401",
        ),
    ],
)
async def test_image_generation_reports_upstream_failures_safely(
    integration_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    outcome: Outcome,
    status: int,
    code: str,
) -> None:
    """The image path used to wrap these as `Image provider failed: {exc}`,
    which put OpenAI's own error text in the response."""
    upstream = ScriptedUpstream(outcome)
    monkeypatch.setattr("app.services.image_storage.LOCAL_IMAGES_DIR", tmp_path / "images")
    monkeypatch.setattr("app.api.v1.routers.content.get_llm_provider", lambda: MockLLMProvider())
    monkeypatch.setattr(
        "app.api.v1.routers.content.get_image_provider",
        lambda: OpenAIImageProvider(
            client=upstream.client(), model="gpt-image-2.5-flare", max_retries=_ATTEMPTS
        ),
    )
    auth = await _register(integration_client)
    created = await integration_client.post(
        "/api/v1/content/generate",
        headers=auth,
        json={"content_type": "blog_post", "topic": "A topic to illustrate"},
    )
    assert created.status_code == 200, created.text

    response = await integration_client.post(
        f"/api/v1/content/{created.json()['content_id']}/image",
        headers=auth,
        json={"style": "photorealistic"},
    )

    _assert_safe_error(response, status=status, code=code)
    assert len(upstream.requests) == 1
