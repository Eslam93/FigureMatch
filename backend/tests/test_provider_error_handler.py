"""Each kind of provider failure gets a fixed status, code and message.

The codes are a contract with the frontend, which maps them to friendly
messages: `_CONTRACT` pins them. Probe routes on a fresh `create_app()`
raise the errors, so the shared app never gains them. Every raised error
carries a sentinel that must stay out of the response.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from structlog.testing import capture_logs

from app.core.exceptions import provider_exception_handler
from app.main import create_app
from app.providers.errors import (
    ProviderConfigError,
    ProviderError,
    ProviderErrorKind,
    ProviderRetryExhausted,
)

_SENTINEL = "sentinel-provider-error-text"
_PROBE = "/api/v1/__test/provider-error"

# kind, status, code: what the frontend relies on.
_CONTRACT = [
    (ProviderErrorKind.AUTH, 502, "AI_PROVIDER_AUTH_FAILED"),
    (ProviderErrorKind.RATE_LIMITED, 429, "AI_RATE_LIMITED"),
    (ProviderErrorKind.QUOTA_EXHAUSTED, 503, "AI_UNAVAILABLE"),
    (ProviderErrorKind.UNAVAILABLE, 503, "AI_UNAVAILABLE"),
    (ProviderErrorKind.TIMEOUT, 504, "AI_TIMEOUT"),
    (ProviderErrorKind.TRUNCATED, 502, "AI_OUTPUT_TRUNCATED"),
    (ProviderErrorKind.CONTENT_REJECTED, 422, "AI_CONTENT_REJECTED"),
    (ProviderErrorKind.MISCONFIGURED, 503, "AI_PROVIDER_MISCONFIGURED"),
    (ProviderErrorKind.OTHER, 502, "PROVIDER_ERROR"),
]


@pytest.fixture
def probe_app() -> FastAPI:
    app = create_app()

    @app.get(_PROBE)
    async def _raise(kind: ProviderErrorKind, retry_after: float | None = None) -> None:
        raise ProviderError(
            f"upstream said: {_SENTINEL}", kind=kind, retry_after_seconds=retry_after
        )

    @app.get(f"{_PROBE}/config")
    async def _raise_config() -> None:
        raise ProviderConfigError(f"OPENAI_API_KEY is required: {_SENTINEL}")

    @app.get(f"{_PROBE}/exhausted")
    async def _raise_exhausted() -> None:
        raise ProviderRetryExhausted(f"exhausted 3 retries: {_SENTINEL}")

    return app


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def test_every_kind_is_in_the_contract() -> None:
    assert {kind for kind, _, _ in _CONTRACT} == set(ProviderErrorKind)


@pytest.mark.parametrize(("kind", "status", "code"), _CONTRACT, ids=[k for k, _, _ in _CONTRACT])
async def test_each_kind_gets_its_status_code_and_a_fixed_message(
    probe_app: FastAPI, kind: ProviderErrorKind, status: int, code: str
) -> None:
    async with _client(probe_app) as client:
        response = await client.get(_PROBE, params={"kind": kind.value})

    assert response.status_code == status
    body = response.json()
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert body["error"]["details"] == {}
    assert body["meta"]["request_id"] == response.headers["x-request-id"]
    assert "retry-after" not in response.headers
    assert _SENTINEL not in response.text


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        (f"{_PROBE}/config", 503, "AI_PROVIDER_MISCONFIGURED"),
        (f"{_PROBE}/exhausted", 503, "AI_UNAVAILABLE"),
    ],
    ids=["config-error", "retry-exhausted"],
)
async def test_subclasses_default_to_their_own_kind(
    probe_app: FastAPI, path: str, status: int, code: str
) -> None:
    async with _client(probe_app) as client:
        response = await client.get(path)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert _SENTINEL not in response.text
    assert "OPENAI_API_KEY" not in response.text


@pytest.mark.parametrize(("retry_after", "header"), [("7", "7"), ("1.2", "2"), (None, None)])
async def test_a_rate_limit_sends_retry_after_when_known(
    probe_app: FastAPI, retry_after: str | None, header: str | None
) -> None:
    params = {"kind": "rate_limited"}
    if retry_after is not None:
        params["retry_after"] = retry_after

    async with _client(probe_app) as client:
        response = await client.get(_PROBE, params=params)

    assert response.status_code == 429
    assert response.headers.get("retry-after") == header
    # The cross-origin frontend can't read Retry-After, so the body says it too.
    expected = {} if header is None else {"retry_after_seconds": int(header)}
    assert response.json()["error"]["details"] == expected


async def test_only_a_rate_limit_sends_retry_after(probe_app: FastAPI) -> None:
    async with _client(probe_app) as client:
        response = await client.get(_PROBE, params={"kind": "unavailable", "retry_after": "7"})

    assert response.status_code == 503
    assert "retry-after" not in response.headers
    assert response.json()["error"]["details"] == {}


@pytest.mark.parametrize("seconds", [0.0, -1.0, float("inf"), float("nan")])
async def test_an_unusable_retry_after_is_left_out(seconds: float) -> None:
    error = ProviderError("x", kind=ProviderErrorKind.RATE_LIMITED, retry_after_seconds=seconds)

    response = await provider_exception_handler(Request({"type": "http"}), error)

    assert response.status_code == 429
    assert "retry-after" not in response.headers


@pytest.mark.parametrize(
    ("kind", "code", "level"),
    [
        (ProviderErrorKind.AUTH, "AI_PROVIDER_AUTH_FAILED", "warning"),
        # It breaks every request until fixed, and nothing else logs it.
        (ProviderErrorKind.MISCONFIGURED, "AI_PROVIDER_MISCONFIGURED", "error"),
    ],
)
async def test_the_exception_text_goes_to_the_log_only(
    probe_app: FastAPI, kind: ProviderErrorKind, code: str, level: str
) -> None:
    async with _client(probe_app) as client:
        with capture_logs() as logs:
            await client.get(_PROBE, params={"kind": kind.value})

    [entry] = [e for e in logs if e["event"] == "provider_error"]
    assert entry["log_level"] == level
    assert entry["kind"] == kind.value
    assert entry["code"] == code
    assert _SENTINEL in entry["error"]
