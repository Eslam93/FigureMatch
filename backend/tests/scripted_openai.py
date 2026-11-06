"""A real `AsyncOpenAI` client whose HTTP calls get scripted answers.

The SDK runs unchanged on an `httpx.MockTransport`, so a test sees the
exception the SDK really raises for an upstream answer: its class, status,
error code, headers and request id. Nothing leaves the process.

Every scripted error body, timeout and truncated completion carries
`SENTINEL`. It stands for upstream text, which must never reach an API
response body.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from openai import AsyncOpenAI

SENTINEL = "upstream-sentinel-6d1f"
UPSTREAM_REQUEST_ID = "req_scripted_0001"

Outcome = Callable[[httpx.Request], httpx.Response]


def error_response(
    status_code: int,
    *,
    code: object = None,
    error_type: str = "invalid_request_error",
    headers: dict[str, str] | None = None,
) -> Outcome:
    """An OpenAI-shaped error body whose message carries the sentinel.

    `code` is a string or None from OpenAI; any other JSON value stands in
    for a non-conforming upstream, such as a proxy."""
    body = {
        "error": {
            "message": f"Upstream detail that must stay server-side: {SENTINEL}",
            "type": error_type,
            "param": None,
            "code": code,
        }
    }
    response_headers = {"x-request-id": UPSTREAM_REQUEST_ID, **(headers or {})}

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=body, headers=response_headers)

    return respond


def read_timeout() -> Outcome:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"read timed out: {SENTINEL}", request=request)

    return respond


def connect_error() -> Outcome:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connection refused: {SENTINEL}", request=request)

    return respond


def chat_completion(
    content: str,
    *,
    finish_reason: str = "stop",
    model: str = "gpt-5.4-mini-2026-03-17",
) -> Outcome:
    """A successful chat completion, e.g. with `finish_reason="length"`."""
    body: dict[str, Any] = {
        "id": "chatcmpl-scripted",
        "object": "chat.completion",
        "created": 1_700_000_000,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return respond


class ScriptedUpstream:
    """Answers the n-th request with the n-th outcome; the last outcome
    repeats once the script runs out. Records every request."""

    def __init__(self, *outcomes: Outcome) -> None:
        if not outcomes:
            raise ValueError("script at least one outcome")
        self._outcomes = outcomes
        self.requests: list[httpx.Request] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        outcome = self._outcomes[min(len(self.requests), len(self._outcomes)) - 1]
        return outcome(request)

    def client(self) -> AsyncOpenAI:
        # The SDK's own retries are off: only the provider's retry loop runs.
        return AsyncOpenAI(
            api_key="test",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self._handle)),
            max_retries=0,
        )
