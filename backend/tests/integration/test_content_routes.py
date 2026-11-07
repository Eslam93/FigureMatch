"""Integration tests for POST /api/v1/content/generate.

Uses MockLLMProvider end-to-end so the tests don't reach out to OpenAI.
The real OpenAIChatProvider has unit coverage at
`tests/providers/test_openai_llm.py`; this file proves the route +
service + repository wire together against a real Postgres.

Slice 2 widened the route from blog-only to all four content types. The
happy-path test is parametrized so each content type runs through the
same end-to-end pipeline.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ContentType, ResultParseStatus
from app.db.models import ContentPiece
from app.providers.factory import reset_provider_cache
from app.providers.llm.mock import MockLLMProvider


async def _register_and_login(integration_client) -> str:  # type: ignore[no-untyped-def]
    """Register a user and return a Bearer-ready access token."""
    response = await integration_client.post(
        "/api/v1/auth/register",
        json={
            "email": "writer@example.com",
            "password": "Secret123",
            "full_name": "Writer Example",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


@pytest.mark.parametrize(
    "content_type,result_assertions",
    [
        (
            "blog_post",
            lambda r: (r["title"], r["sections"]),
        ),
        (
            "linkedin_post",
            lambda r: (r["hook"], r["body"], r["cta"], r["hashtags"]),
        ),
        (
            "email",
            lambda r: (r["subject"], r["preview_text"], r["body"], r["sign_off"]),
        ),
        (
            "ad_copy",
            lambda r: (
                r["variants"],
                {v["format"] for v in r["variants"]} == {"short", "medium", "long"},
            ),
        ),
    ],
    ids=["blog_post", "linkedin_post", "email", "ad_copy"],
)
async def test_generate_each_content_type_with_mock_returns_full_response(
    integration_client,  # type: ignore[no-untyped-def]
    db_session: AsyncSession,
    monkeypatch,  # type: ignore[no-untyped-def]
    content_type: str,
    result_assertions,  # type: ignore[no-untyped-def]
) -> None:
    """End-to-end happy path against MockLLMProvider for every content
    type. Mocks `get_llm_provider` so the test forces the mock provider
    regardless of `AI_PROVIDER_MODE` in the test env. Asserts the
    response envelope shape and the persisted row.
    """
    monkeypatch.setattr(
        "app.api.v1.routers.content.get_llm_provider",
        lambda: MockLLMProvider(),
    )
    reset_provider_cache()

    token = await _register_and_login(integration_client)

    response = await integration_client.post(
        "/api/v1/content/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "content_type": content_type,
            "topic": "Mocked content for local development",
            "tone": "informative",
            "target_audience": "engineers",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["content_type"] == content_type
    assert body["result_parse_status"] == "ok"
    assert body["word_count"] > 0
    assert body["rendered_text"]
    assert body["result"] is not None
    # Each content type's result has a distinct key set; the lambda
    # parameter checks the per-type fields are present and truthy.
    asserts = result_assertions(body["result"])
    assert all(asserts), f"per-type assertions failed: {asserts!r}"
    assert body["usage"]["model_id"] == "mock-llm-v1"
    # Mock provider returns zero-cost. Decimal serializes as string.
    assert body["usage"]["cost_usd"] in ("0", "0.000000")

    # DB row exists, owned by the registered user.
    content_id = body["content_id"]
    stmt = select(ContentPiece).where(ContentPiece.id == content_id)
    row = (await db_session.execute(stmt)).scalar_one()
    assert row.content_type == ContentType(content_type)
    assert row.result_parse_status == ResultParseStatus.OK
    # Exact versions are pinned in tests/test_prompts.py; this checks the wiring.
    assert row.prompt_version.startswith(f"{content_type}.v")
    assert row.system_prompt_snapshot
    assert row.user_prompt_snapshot
    assert row.result is not None
    assert row.rendered_text == body["rendered_text"]


async def test_blog_post_rendered_text_is_markdown(
    integration_client,  # type: ignore[no-untyped-def]
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """The blog-post renderer is the only one that produces a heading
    hierarchy with an H1 + H2s; the others use plain text or H2/H3.
    Locking the H1/H2 contract here keeps a regression in the renderer
    from passing silently."""
    monkeypatch.setattr(
        "app.api.v1.routers.content.get_llm_provider",
        lambda: MockLLMProvider(),
    )
    reset_provider_cache()

    token = await _register_and_login(integration_client)
    response = await integration_client.post(
        "/api/v1/content/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": "blog_post", "topic": "Markdown shape"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rendered_text"].startswith("# ")
    assert "## " in body["rendered_text"]


async def test_generate_requires_authentication(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    response = await integration_client.post(
        "/api/v1/content/generate",
        json={
            "content_type": "blog_post",
            "topic": "Anything",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] in {"MISSING_TOKEN", "INVALID_TOKEN"}


async def test_generate_rejects_invalid_content_type_with_422(
    integration_client,  # type: ignore[no-untyped-def]
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """A content_type outside the enum fails Pydantic validation at the
    request boundary — the router never sees it."""
    monkeypatch.setattr(
        "app.api.v1.routers.content.get_llm_provider",
        lambda: MockLLMProvider(),
    )
    reset_provider_cache()

    token = await _register_and_login(integration_client)
    response = await integration_client.post(
        "/api/v1/content/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "content_type": "not_a_real_type",
            "topic": "Hello",
        },
    )
    assert response.status_code == 422


async def test_generate_validates_request_body(
    integration_client,  # type: ignore[no-untyped-def]
) -> None:
    token = await _register_and_login(integration_client)
    response = await integration_client.post(
        "/api/v1/content/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "content_type": "blog_post",
            "topic": "x",  # min_length=3 fails
        },
    )
    assert response.status_code == 422
