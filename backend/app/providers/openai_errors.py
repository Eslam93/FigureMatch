"""Classify OpenAI SDK exceptions into `ProviderError` kinds.

Shared by the chat and image providers, so both map a failure the same
way and both retry loops ask the same question: is another attempt worth
it?

  401 / 403                          AUTH
  429 with `insufficient_quota`      QUOTA_EXHAUSTED  (never retried)
  any other 429                      RATE_LIMITED     (retried; keeps Retry-After)
  5xx, connection error              UNAVAILABLE      (retried)
  timeout                            TIMEOUT          (retried)
  400 from the safety system         CONTENT_REJECTED
  anything else                      OTHER

Upstream error text only goes into `log_fields`, for the server log. The
`ProviderError` a provider raises is worded from `summary` alone: the
error type and HTTP status.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

import openai

from app.providers.errors import ProviderError, ProviderErrorKind, ProviderRetryExhausted

# 400 `code`s that mean OpenAI's safety system blocked the request:
# GPT Image prompts get `moderation_blocked`, DALL·E prompts
# `content_policy_violation`, reasoning-model prompts `invalid_prompt`.
_CONTENT_REJECTED_CODES: Final[frozenset[str]] = frozenset(
    {"content_policy_violation", "invalid_prompt", "moderation_blocked"}
)

# A 429 with this code (and type) is an out-of-quota account, not a
# transient limit: retrying only bills more failed requests.
_INSUFFICIENT_QUOTA: Final = "insufficient_quota"

# `retry-after-ms` is OpenAI's more precise variant; the SDK prefers it too.
_RETRY_AFTER_HEADERS: Final[tuple[tuple[str, float], ...]] = (
    ("retry-after-ms", 1000.0),
    ("retry-after", 1.0),
)


@dataclass(frozen=True, slots=True)
class OpenAIFailure:
    """What one SDK exception means to a provider's retry loop."""

    kind: ProviderErrorKind
    retryable: bool
    retry_after_seconds: float | None
    summary: str
    """Error type and HTTP status, e.g. `RateLimitError, HTTP 429`."""
    log_fields: dict[str, Any]
    """Diagnostics for the server log, upstream message included."""

    def error(self, operation: str) -> ProviderError:
        """The error to raise for this failure, e.g. `OpenAI call failed
        (AuthenticationError, HTTP 401).`"""
        return ProviderError(
            f"{operation} failed ({self.summary}).",
            kind=self.kind,
            retry_after_seconds=self.retry_after_seconds,
        )


def retry_exhausted_error(
    operation: str, attempts: int, last_failure: OpenAIFailure | None
) -> ProviderRetryExhausted:
    """The error to raise once every attempt failed transiently. It takes
    the last failure's kind and Retry-After. With no failure at all (a
    `max_retries` below 1 means no attempt was made) it keeps the class
    default, UNAVAILABLE."""
    if last_failure is None:
        return ProviderRetryExhausted(f"{operation} exhausted {attempts} retries.")
    return ProviderRetryExhausted(
        f"{operation} exhausted {attempts} retries ({last_failure.summary}).",
        kind=last_failure.kind,
        retry_after_seconds=last_failure.retry_after_seconds,
    )


def classify_openai_error(exc: openai.OpenAIError) -> OpenAIFailure:
    """What `exc` means: its kind, whether to retry, and what to log."""
    kind, retryable = _kind_of(exc)
    # Only errors with an HTTP response have a status, headers and request id.
    status_error = exc if isinstance(exc, openai.APIStatusError) else None
    status_code = status_error.status_code if status_error else None
    error_type = type(exc).__name__
    return OpenAIFailure(
        kind=kind,
        retryable=retryable,
        retry_after_seconds=(
            _retry_after_seconds(status_error.response.headers)
            if status_error and kind is ProviderErrorKind.RATE_LIMITED
            else None
        ),
        summary=error_type if status_code is None else f"{error_type}, HTTP {status_code}",
        log_fields={
            "kind": kind.value,
            "error_type": error_type,
            "status_code": status_code,
            "error_code": exc.code if isinstance(exc, openai.APIError) else None,
            "upstream_request_id": status_error.request_id if status_error else None,
            "error": str(exc),
        },
    )


def _kind_of(exc: openai.OpenAIError) -> tuple[ProviderErrorKind, bool]:
    """The failure's kind, and whether it is worth retrying."""
    # APITimeoutError subclasses APIConnectionError, so it goes first.
    if isinstance(exc, openai.APITimeoutError):
        return ProviderErrorKind.TIMEOUT, True
    if isinstance(exc, openai.APIConnectionError | openai.InternalServerError):
        return ProviderErrorKind.UNAVAILABLE, True
    if isinstance(exc, openai.RateLimitError):
        if _INSUFFICIENT_QUOTA in (exc.code, exc.type):
            return ProviderErrorKind.QUOTA_EXHAUSTED, False
        return ProviderErrorKind.RATE_LIMITED, True
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return ProviderErrorKind.AUTH, False
    # The SDK keeps `code` as the body sent it, so a non-conforming upstream
    # (a proxy behind OPENAI_BASE_URL) can make it an object, which a set
    # lookup can't hash.
    if (
        isinstance(exc, openai.BadRequestError)
        and isinstance(exc.code, str)
        and exc.code in _CONTENT_REJECTED_CODES
    ):
        return ProviderErrorKind.CONTENT_REJECTED, False
    # Raised by the SDK's parse helpers rather than `create`, but they
    # mean exactly what the finish-reason checks in the providers mean.
    if isinstance(exc, openai.LengthFinishReasonError):
        return ProviderErrorKind.TRUNCATED, False
    if isinstance(exc, openai.ContentFilterFinishReasonError):
        return ProviderErrorKind.CONTENT_REJECTED, False
    return ProviderErrorKind.OTHER, False


def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """How long the provider asked us to wait, from `retry-after-ms` or
    `retry-after` in seconds. An HTTP-date or unusable value counts as
    unknown."""
    for header, per_second in _RETRY_AFTER_HEADERS:
        raw = headers.get(header)
        if raw is None:
            continue
        try:
            seconds = float(raw) / per_second
        except ValueError:
            continue
        if math.isfinite(seconds) and seconds > 0:
            return seconds
    return None
