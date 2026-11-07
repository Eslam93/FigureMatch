"""Unit tests for the three-stage parse fallback in ContentService.

The service is exercised end-to-end against a real test session in
`tests/integration/test_content_routes.py`. This file uses fake
providers + in-memory factories to lock the fallback semantics without
spinning up Postgres.

Slice 2 widened the service from blog-only to a registry-based
dispatch; the fallback semantics still apply to every content type, so
the same suite runs once per type via parametrization.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.db.enums import ContentType, ResultParseStatus
from app.prompts import blog_post as blog_post_prompt
from app.providers.errors import ProviderErrorKind, ProviderIncompleteOutput
from app.providers.llm.base import LLMResult
from app.providers.llm.openai_provider import OpenAIChatProvider
from app.schemas.content import GenerateRequest
from app.services.content_service import ContentService
from tests.scripted_openai import SENTINEL, ScriptedUpstream, chat_completion

# ── fakes ──────────────────────────────────────────────────────────────


@dataclass
class _RecordingSession:
    """Bare-minimum async-session stand-in.

    The service commits before each model call and calls `add → flush →
    refresh` on the session via the repo. We capture the added row, no-op
    commit/flush/refresh, and let the test assert on what was persisted.
    Transaction behaviour against a real session is covered by
    `tests/integration/test_model_call_transactions.py`.
    """

    added: list[Any] | None = None

    def __post_init__(self) -> None:
        self.added = []

    async def commit(self) -> None:
        return None

    def add(self, obj: Any) -> None:
        assert self.added is not None
        self.added.append(obj)

    async def flush(self) -> None:
        # Mimic Postgres assigning defaults — fill in word_count etc. is
        # already done by the service; nothing to do here.
        return None

    async def refresh(self, obj: Any) -> None:
        return None


def _billed(raw_text: str, *, finish_reason: str = "stop") -> LLMResult:
    """One call's result, with the usage every fake call reports."""
    return LLMResult(
        raw_text=raw_text,
        model="fake-model-v0",
        input_tokens=5,
        output_tokens=7,
        cost_usd=0.01,
        latency_ms=1,
        finish_reason=finish_reason,
    )


def _fake_provider(raw_texts: list[str]) -> AsyncMock:
    """Build an AsyncMock provider whose `.generate(...)` returns the
    given raw_texts in order.

    Each call records token usage so we can verify the service sums
    them across attempts.
    """
    mock = AsyncMock()
    mock.generate.side_effect = [_billed(raw) for raw in raw_texts]
    return mock


# Valid canned payloads per content type. Shapes mirror the Pydantic
# models in `app.schemas.content`. Used by parametrized fallback tests.
_VALID_PAYLOADS: dict[ContentType, dict[str, Any]] = {
    ContentType.BLOG_POST: {
        "title": "Mocks in CI",
        "meta_description": "A short explanation.",
        "intro": "Why we mock.",
        "sections": [{"heading": "H", "body": "B"}],
        "conclusion": "Done.",
        "suggested_tags": ["mock"],
    },
    ContentType.LINKEDIN_POST: {
        "hook": "Hook line.",
        "body": "Body content.",
        "cta": "Do this.",
        "hashtags": ["ai"],
    },
    ContentType.EMAIL: {
        "subject": "Subject line",
        "preview_text": "Preview text here.",
        "greeting": "Hi,",
        "body": "Body.",
        "cta_text": "Click",
        "sign_off": "— Team",
    },
    ContentType.AD_COPY: {
        "variants": [
            {
                "format": "short",
                "angle": "curiosity",
                "headline": "Short hook",
                "body": "Short body",
                "cta": "Try it",
            },
            {
                "format": "medium",
                "angle": "social_proof",
                "headline": "Medium headline",
                "body": "Medium body.",
                "cta": "See more",
            },
            {
                "format": "long",
                "angle": "transformation",
                "headline": "Long headline",
                "body": "Long body with detail.",
                "cta": "Read more",
            },
        ],
    },
}


_ALL_CONTENT_TYPES = list(_VALID_PAYLOADS.keys())


def _valid_json(content_type: ContentType) -> str:
    return json.dumps(_VALID_PAYLOADS[content_type])


def _request(content_type: ContentType = ContentType.BLOG_POST) -> GenerateRequest:
    return GenerateRequest(
        content_type=content_type,
        topic="A topic for testing",
        tone="informative",
        target_audience="engineers",
    )


def _user() -> Any:
    return type("U", (), {"id": "00000000-0000-0000-0000-000000000001"})()


# ── tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", _ALL_CONTENT_TYPES, ids=lambda ct: ct.value)
async def test_attempt_1_success_status_ok(content_type: ContentType) -> None:
    session = _RecordingSession()
    provider = _fake_provider([_valid_json(content_type)])
    service = ContentService(session, provider)  # type: ignore[arg-type]

    piece = await service.generate(user=_user(), request=_request(content_type))

    assert piece.result_parse_status == ResultParseStatus.OK
    assert piece.result is not None
    assert piece.content_type == content_type
    assert piece.rendered_text, "rendered_text should be non-empty on OK"
    assert provider.generate.await_count == 1
    assert piece.input_tokens == 5
    assert piece.output_tokens == 7
    assert piece.cost_usd == Decimal("0.01")


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", _ALL_CONTENT_TYPES, ids=lambda ct: ct.value)
async def test_attempt_2_corrective_retry_status_retried(content_type: ContentType) -> None:
    session = _RecordingSession()
    provider = _fake_provider(["not json at all", _valid_json(content_type)])
    service = ContentService(session, provider)  # type: ignore[arg-type]

    piece = await service.generate(user=_user(), request=_request(content_type))

    assert piece.result_parse_status == ResultParseStatus.RETRIED
    assert piece.result is not None
    # Both calls' tokens summed.
    assert piece.input_tokens == 10
    assert piece.output_tokens == 14
    assert piece.cost_usd == Decimal("0.02")
    # The retry keeps the first call's strict json_schema and says what failed.
    (_, first_kwargs), (_, second_kwargs) = provider.generate.call_args_list
    assert second_kwargs["json_schema"] is not None
    assert second_kwargs["json_schema"] == first_kwargs["json_schema"]
    assert "The previous reply was not valid JSON." in second_kwargs["user_prompt"]


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", _ALL_CONTENT_TYPES, ids=lambda ct: ct.value)
async def test_attempt_3_graceful_degrade_status_failed(content_type: ContentType) -> None:
    session = _RecordingSession()
    provider = _fake_provider(["{bad json", "still bad"])
    service = ContentService(session, provider)  # type: ignore[arg-type]

    piece = await service.generate(user=_user(), request=_request(content_type))

    assert piece.result_parse_status == ResultParseStatus.FAILED
    assert piece.result is None
    # Raw model output preserved so the frontend has something to show.
    assert piece.rendered_text == "still bad"
    # Both calls still summed for cost accounting.
    assert piece.input_tokens == 10
    assert piece.output_tokens == 14


@pytest.mark.asyncio
async def test_valid_json_wrong_schema_falls_through_to_retry() -> None:
    """A response that's valid JSON but fails Pydantic validation must
    trigger the retry path — schema-conforming output is non-negotiable.
    """
    session = _RecordingSession()
    wrong_shape = json.dumps({"this_is_not": "a blog post"})
    provider = _fake_provider([wrong_shape, _valid_json(ContentType.BLOG_POST)])
    service = ContentService(session, provider)  # type: ignore[arg-type]

    piece = await service.generate(user=_user(), request=_request())

    assert piece.result_parse_status == ResultParseStatus.RETRIED
    assert piece.result is not None


@pytest.mark.asyncio
async def test_prompt_snapshot_persisted_even_on_failure() -> None:
    session = _RecordingSession()
    provider = _fake_provider(["bad", "still bad"])
    service = ContentService(session, provider)  # type: ignore[arg-type]

    piece = await service.generate(user=_user(), request=_request())

    assert piece.system_prompt_snapshot
    assert piece.user_prompt_snapshot
    assert piece.prompt_version == "blog_post.v2"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content_type,expected_version",
    [
        (ContentType.BLOG_POST, "blog_post.v2"),
        (ContentType.LINKEDIN_POST, "linkedin_post.v2"),
        (ContentType.EMAIL, "email.v2"),
        (ContentType.AD_COPY, "ad_copy.v2"),
    ],
    ids=lambda x: x.value if isinstance(x, ContentType) else x,
)
async def test_prompt_version_pinned_per_content_type(
    content_type: ContentType, expected_version: str
) -> None:
    """The registry must wire each content type to its versioned prompt
    module so old rows stay traceable to the template that produced
    them."""
    session = _RecordingSession()
    provider = _fake_provider([_valid_json(content_type)])
    service = ContentService(session, provider)  # type: ignore[arg-type]

    piece = await service.generate(user=_user(), request=_request(content_type))
    assert piece.prompt_version == expected_version


@pytest.mark.asyncio
async def test_attempt_1_sends_strict_json_schema_for_each_type() -> None:
    """First-pass call always carries the per-type strict json_schema
    payload; the corrective retry reuses it."""
    session = _RecordingSession()
    provider = _fake_provider([_valid_json(ContentType.LINKEDIN_POST)])
    service = ContentService(session, provider)  # type: ignore[arg-type]

    await service.generate(user=_user(), request=_request(ContentType.LINKEDIN_POST))

    _, kwargs = provider.generate.call_args_list[0]
    schema = kwargs["json_schema"]
    assert schema is not None
    # LinkedIn schema's required keys are the discriminator we can
    # check without coupling to the exact dict identity.
    assert set(schema["required"]) == {"hook", "body", "cta", "hashtags"}


# ── corrective retry: strict schema, failing field named ───────────────

# One character over `BlogPostResult.meta_description`'s 160-character limit,
# which strict json_schema can't express, so a strict reply can still break it.
_TOO_LONG_META = "m" * 161


def _blog_reply(**overrides: Any) -> str:
    return json.dumps({**_VALID_PAYLOADS[ContentType.BLOG_POST], **overrides})


@pytest.mark.asyncio
async def test_corrective_retry_keeps_strict_schema_and_names_the_failing_field() -> None:
    session = _RecordingSession()
    provider = _fake_provider(
        [_blog_reply(meta_description=_TOO_LONG_META), _valid_json(ContentType.BLOG_POST)]
    )
    service = ContentService(session, provider)  # type: ignore[arg-type]  # duck-typed fakes

    piece = await service.generate(user=_user(), request=_request())

    assert piece.result_parse_status == ResultParseStatus.RETRIED
    assert piece.result == _VALID_PAYLOADS[ContentType.BLOG_POST]
    assert piece.rendered_text.startswith("# Mocks in CI\n")
    _, retry = provider.generate.call_args_list[1]
    assert retry["json_schema"] == blog_post_prompt.JSON_SCHEMA["schema"]
    assert "- meta_description: String should have at most 160 characters" in retry["user_prompt"]
    assert "not valid JSON" not in retry["user_prompt"]
    # The rejected value is in the echoed reply only, never in the note.
    assert retry["user_prompt"].count(_TOO_LONG_META) == 1


@pytest.mark.asyncio
async def test_corrective_retry_that_fails_again_degrades_exactly_as_before() -> None:
    session = _RecordingSession()
    second_reply = _blog_reply(title="Second try", meta_description=_TOO_LONG_META)
    provider = _fake_provider([_blog_reply(meta_description=_TOO_LONG_META), second_reply])
    service = ContentService(session, provider)  # type: ignore[arg-type]  # duck-typed fakes

    piece = await service.generate(user=_user(), request=_request())

    assert piece.result_parse_status == ResultParseStatus.FAILED
    assert piece.result is None
    assert piece.rendered_text == second_reply
    assert piece.input_tokens == 10
    assert piece.output_tokens == 14
    assert piece.cost_usd == Decimal("0.02")
    assert provider.generate.await_count == 2
    _, retry = provider.generate.call_args_list[1]
    assert retry["json_schema"] == blog_post_prompt.JSON_SCHEMA["schema"]


@pytest.mark.asyncio
async def test_corrective_retry_reaches_openai_as_a_strict_structured_output_request() -> None:
    """The same retry through the real OpenAI provider, on scripted HTTP:
    the second request still asks for strict json_schema output."""
    upstream = ScriptedUpstream(
        chat_completion(_blog_reply(meta_description=_TOO_LONG_META)),
        chat_completion(_valid_json(ContentType.BLOG_POST)),
    )
    provider = OpenAIChatProvider(
        client=upstream.client(), model="gpt-5.4-mini-2026-03-17", max_retries=1
    )
    session = _RecordingSession()
    service = ContentService(session, provider)  # type: ignore[arg-type]  # duck-typed session

    piece = await service.generate(user=_user(), request=_request())

    assert piece.result_parse_status == ResultParseStatus.RETRIED
    assert len(upstream.requests) == 2
    retry_body = json.loads(upstream.requests[1].content)
    assert retry_body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "blog_post",
            "schema": blog_post_prompt.JSON_SCHEMA["schema"],
            "strict": True,
        },
    }
    retry_user_message = retry_body["messages"][1]
    assert retry_user_message["role"] == "user"
    assert (
        "- meta_description: String should have at most 160 characters"
        in retry_user_message["content"]
    )


# ── corrective retry that stops short: still stage 3 ───────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("finish_reason", "kind"),
    [
        ("length", ProviderErrorKind.TRUNCATED),
        ("content_filter", ProviderErrorKind.CONTENT_REJECTED),
    ],
)
async def test_corrective_retry_cut_off_or_filtered_degrades_with_attempt_1(
    finish_reason: str, kind: ProviderErrorKind
) -> None:
    """A strict retry that stops short raises rather than returning a reply.
    Stage 3 still runs, as for a retry that fails to parse: the piece keeps
    attempt 1's raw output and both calls' usage, instead of the request
    failing after two paid calls."""
    first_reply = _blog_reply(meta_description=_TOO_LONG_META)
    cut_off = _billed('{"title": "Cut', finish_reason=finish_reason)
    provider = AsyncMock()
    provider.generate.side_effect = [
        _billed(first_reply),
        ProviderIncompleteOutput("stopped short", kind=kind, result=cut_off),
    ]
    session = _RecordingSession()
    service = ContentService(session, provider)  # type: ignore[arg-type]  # duck-typed fakes

    piece = await service.generate(user=_user(), request=_request())

    assert session.added == [piece]
    assert piece.result_parse_status == ResultParseStatus.FAILED
    assert piece.result is None
    assert piece.rendered_text == first_reply
    assert piece.input_tokens == 10
    assert piece.output_tokens == 14
    assert piece.cost_usd == Decimal("0.02")


@pytest.mark.asyncio
async def test_corrective_retry_cut_off_by_openai_still_saves_the_piece() -> None:
    """The real provider raises `ProviderIncompleteOutput` for a truncated
    strict reply, so the cut-off retry ends in a FAILED piece, not a 502."""
    first_reply = _blog_reply(meta_description=_TOO_LONG_META)
    upstream = ScriptedUpstream(
        chat_completion(first_reply),
        chat_completion(f'{{"title": "{SENTINEL}', finish_reason="length"),
    )
    provider = OpenAIChatProvider(
        client=upstream.client(), model="gpt-5.4-mini-2026-03-17", max_retries=1
    )
    session = _RecordingSession()
    service = ContentService(session, provider)  # type: ignore[arg-type]  # duck-typed session

    piece = await service.generate(user=_user(), request=_request())

    assert len(upstream.requests) == 2
    assert piece.result_parse_status == ResultParseStatus.FAILED
    assert piece.rendered_text == first_reply
    # Each scripted completion bills 10 prompt and 5 completion tokens.
    assert (piece.input_tokens, piece.output_tokens) == (20, 10)
