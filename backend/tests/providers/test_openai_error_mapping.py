"""OpenAI SDK errors become typed `ProviderError`s without upstream text.

Both OpenAI providers run against scripted HTTP answers
(`tests/scripted_openai.py`), so each case sees the exception the SDK
really raises. Backoff is zero and every provider gets three attempts.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import openai
import pytest
from structlog.testing import capture_logs

from app.providers.errors import (
    ProviderError,
    ProviderErrorKind,
    ProviderIncompleteOutput,
    ProviderRetryExhausted,
)
from app.providers.image.openai_provider import OpenAIImageProvider
from app.providers.llm.openai_provider import OpenAIChatProvider
from app.providers.openai_errors import classify_openai_error, retry_exhausted_error
from tests.scripted_openai import (
    SENTINEL,
    UPSTREAM_REQUEST_ID,
    Outcome,
    ScriptedUpstream,
    chat_completion,
    connect_error,
    error_response,
    read_timeout,
)

_ATTEMPTS = 3


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    for provider in (OpenAIChatProvider, OpenAIImageProvider):
        monkeypatch.setattr(provider, "_backoff_seconds", staticmethod(lambda _attempt: 0.0))


def _chat(upstream: ScriptedUpstream) -> OpenAIChatProvider:
    return OpenAIChatProvider(
        client=upstream.client(), model="gpt-5.4-mini-2026-03-17", max_retries=_ATTEMPTS
    )


def _image(upstream: ScriptedUpstream) -> OpenAIImageProvider:
    return OpenAIImageProvider(
        client=upstream.client(), model="gpt-image-2.5-flare", max_retries=_ATTEMPTS
    )


# outcome, kind, upstream requests made, retry_after_seconds
_UPSTREAM_FAILURES = [
    pytest.param(
        error_response(401, code="invalid_api_key"), ProviderErrorKind.AUTH, 1, None, id="401"
    ),
    pytest.param(
        error_response(403, code="unsupported_country_region_territory"),
        ProviderErrorKind.AUTH,
        1,
        None,
        id="403",
    ),
    pytest.param(
        error_response(
            429, code="rate_limit_exceeded", error_type="requests", headers={"retry-after": "7"}
        ),
        ProviderErrorKind.RATE_LIMITED,
        _ATTEMPTS,
        7.0,
        id="429-retry-after",
    ),
    # Out of quota: one request, never a retry that bills nothing but failures.
    pytest.param(
        error_response(429, code="insufficient_quota", error_type="insufficient_quota"),
        ProviderErrorKind.QUOTA_EXHAUSTED,
        1,
        None,
        id="429-insufficient-quota",
    ),
    pytest.param(
        error_response(503, error_type="server_error"),
        ProviderErrorKind.UNAVAILABLE,
        _ATTEMPTS,
        None,
        id="503",
    ),
    pytest.param(read_timeout(), ProviderErrorKind.TIMEOUT, _ATTEMPTS, None, id="read-timeout"),
    pytest.param(
        connect_error(), ProviderErrorKind.UNAVAILABLE, _ATTEMPTS, None, id="connect-error"
    ),
    pytest.param(
        error_response(400, code="moderation_blocked", error_type="image_generation_user_error"),
        ProviderErrorKind.CONTENT_REJECTED,
        1,
        None,
        id="400-moderation-blocked",
    ),
    pytest.param(
        error_response(400, code="content_policy_violation"),
        ProviderErrorKind.CONTENT_REJECTED,
        1,
        None,
        id="400-content-policy-violation",
    ),
    pytest.param(
        error_response(400, code="invalid_prompt"),
        ProviderErrorKind.CONTENT_REJECTED,
        1,
        None,
        id="400-invalid-prompt",
    ),
    pytest.param(
        error_response(400, code="unknown_parameter"), ProviderErrorKind.OTHER, 1, None, id="400"
    ),
    # The SDK keeps `code` as sent, so an object must not crash the classifier.
    pytest.param(
        error_response(400, code={"reason": "moderation_blocked"}),
        ProviderErrorKind.OTHER,
        1,
        None,
        id="400-object-code",
    ),
    pytest.param(
        error_response(404, code="model_not_found"), ProviderErrorKind.OTHER, 1, None, id="404"
    ),
]


def _assert_typed_failure(
    error: ProviderError,
    upstream: ScriptedUpstream,
    *,
    kind: ProviderErrorKind,
    requests: int,
    retry_after: float | None,
) -> None:
    assert error.kind is kind
    assert error.retry_after_seconds == retry_after
    assert len(upstream.requests) == requests
    # Retried kinds end as exhausted retries; the rest fail on the spot.
    assert isinstance(error, ProviderRetryExhausted) is (requests == _ATTEMPTS)
    assert SENTINEL not in str(error)


@pytest.mark.parametrize(("outcome", "kind", "requests", "retry_after"), _UPSTREAM_FAILURES)
async def test_chat_upstream_failure_becomes_a_typed_error(
    outcome: Outcome, kind: ProviderErrorKind, requests: int, retry_after: float | None
) -> None:
    upstream = ScriptedUpstream(outcome)

    with pytest.raises(ProviderError) as excinfo:
        await _chat(upstream).generate(system_prompt="s", user_prompt="u", content_type="blog_post")

    _assert_typed_failure(
        excinfo.value, upstream, kind=kind, requests=requests, retry_after=retry_after
    )


@pytest.mark.parametrize(("outcome", "kind", "requests", "retry_after"), _UPSTREAM_FAILURES)
async def test_image_upstream_failure_becomes_a_typed_error(
    outcome: Outcome, kind: ProviderErrorKind, requests: int, retry_after: float | None
) -> None:
    upstream = ScriptedUpstream(outcome)

    with pytest.raises(ProviderError) as excinfo:
        await _image(upstream).generate(prompt="a lighthouse at dusk")

    _assert_typed_failure(
        excinfo.value, upstream, kind=kind, requests=requests, retry_after=retry_after
    )


@pytest.mark.parametrize(
    ("finish_reason", "kind"),
    [
        ("length", ProviderErrorKind.TRUNCATED),
        ("content_filter", ProviderErrorKind.CONTENT_REJECTED),
        ("tool_calls", ProviderErrorKind.OTHER),
    ],
)
async def test_incomplete_strict_schema_output_becomes_a_typed_error(
    finish_reason: str, kind: ProviderErrorKind
) -> None:
    upstream = ScriptedUpstream(
        chat_completion(f'{{"title": "{SENTINEL}', finish_reason=finish_reason)
    )

    with pytest.raises(ProviderError) as excinfo:
        await _chat(upstream).generate(
            system_prompt="s",
            user_prompt="u",
            json_schema={"type": "object"},
            content_type="blog_post",
        )

    assert excinfo.value.kind is kind
    assert len(upstream.requests) == 1
    assert SENTINEL not in str(excinfo.value)
    # The call was billed, so the error carries its result for a caller's fallback.
    assert isinstance(excinfo.value, ProviderIncompleteOutput)
    billed = excinfo.value.result
    assert (billed.input_tokens, billed.output_tokens) == (10, 5)
    assert billed.cost_usd > 0
    assert billed.finish_reason == finish_reason


async def test_transient_failures_are_retried_until_one_succeeds() -> None:
    upstream = ScriptedUpstream(error_response(503), read_timeout(), chat_completion("done"))

    result = await _chat(upstream).generate(
        system_prompt="s", user_prompt="u", content_type="blog_post"
    )

    assert result.raw_text == "done"
    assert len(upstream.requests) == 3


async def test_upstream_details_stay_in_the_server_log() -> None:
    upstream = ScriptedUpstream(error_response(401, code="invalid_api_key"))

    with capture_logs() as logs, pytest.raises(ProviderError):
        await _chat(upstream).generate(system_prompt="s", user_prompt="u", content_type="blog_post")

    [entry] = [e for e in logs if e["event"] == "openai_non_retryable_error"]
    assert entry["kind"] == "auth"
    assert entry["error_type"] == "AuthenticationError"
    assert entry["status_code"] == 401
    assert entry["error_code"] == "invalid_api_key"
    assert entry["upstream_request_id"] == UPSTREAM_REQUEST_ID
    assert SENTINEL in entry["error"]


# ── classification details ─────────────────────────────────────────────


def _rate_limit_error(
    headers: dict[str, str], *, code: str = "rate_limit_exceeded"
) -> openai.RateLimitError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, headers=headers, request=request)
    return openai.RateLimitError("rate limited", response=response, body={"code": code})


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"retry-after": "7"}, 7.0),
        ({"retry-after": "0.5"}, 0.5),
        ({"retry-after-ms": "1500"}, 1.5),
        ({"retry-after-ms": "1500", "retry-after": "9"}, 1.5),
        ({"retry-after-ms": "soon", "retry-after": "9"}, 9.0),
        ({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),
        ({"retry-after": "0"}, None),
        ({"retry-after": "-3"}, None),
        ({"retry-after": "inf"}, None),
        ({"retry-after": "nan"}, None),
        ({}, None),
    ],
)
def test_retry_after_comes_from_the_rate_limit_headers(
    headers: dict[str, str], expected: float | None
) -> None:
    assert classify_openai_error(_rate_limit_error(headers)).retry_after_seconds == expected


def test_out_of_quota_carries_no_retry_after() -> None:
    failure = classify_openai_error(
        _rate_limit_error({"retry-after": "7"}, code="insufficient_quota")
    )

    assert failure.kind is ProviderErrorKind.QUOTA_EXHAUSTED
    assert failure.retryable is False
    assert failure.retry_after_seconds is None


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (
            openai.LengthFinishReasonError(completion=MagicMock(usage=None)),
            ProviderErrorKind.TRUNCATED,
        ),
        (openai.ContentFilterFinishReasonError(), ProviderErrorKind.CONTENT_REJECTED),
    ],
    ids=["length", "content-filter"],
)
def test_sdk_finish_reason_errors_map_like_the_finish_reason_checks(
    exc: openai.OpenAIError, kind: ProviderErrorKind
) -> None:
    failure = classify_openai_error(exc)

    assert failure.kind is kind
    assert failure.retryable is False


def test_no_attempt_at_all_counts_as_unavailable() -> None:
    """A `max_retries` below 1 makes no request, so there's no last failure."""
    error = retry_exhausted_error("OpenAI call", 0, None)

    assert error.kind is ProviderErrorKind.UNAVAILABLE
    assert error.retry_after_seconds is None
