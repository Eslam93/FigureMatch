"""Provider-layer exceptions: the one `ProviderError` family.

Every provider failure is a `ProviderError` whose `kind` says why it
failed. `app.core.exceptions` registers the single handler that maps a
kind to a fixed HTTP status, error code and message, so a response never
carries an exception's text. Providers still keep upstream error text out
of these messages: they log it where they catch the SDK's exception, and
chain that exception as the cause.

These live alongside the provider protocols rather than under
`app/core/exceptions.py` because they describe infrastructure failures,
not request-shaped errors.
"""

from __future__ import annotations

from enum import StrEnum


class ProviderErrorKind(StrEnum):
    """Why a provider call failed."""

    AUTH = "auth"  # the provider rejected our credentials or permissions
    RATE_LIMITED = "rate_limited"  # too many requests; worth retrying later
    QUOTA_EXHAUSTED = "quota_exhausted"  # the account is out of quota; retrying won't help
    UNAVAILABLE = "unavailable"  # 5xx or a connection failure
    TIMEOUT = "timeout"  # the provider didn't answer in time
    TRUNCATED = "truncated"  # the output hit the length limit
    CONTENT_REJECTED = "content_rejected"  # the provider's safety system blocked it
    MISCONFIGURED = "misconfigured"  # our configuration is wrong: missing key, unpriced model
    OTHER = "other"  # any other provider failure


class ProviderError(Exception):
    """A provider call failed in a way the caller can't handle.

    `kind` defaults per class and can be set per instance.
    `retry_after_seconds` is set only when the provider said how long to
    wait before trying again.
    """

    kind: ProviderErrorKind = ProviderErrorKind.OTHER

    def __init__(
        self,
        message: str,
        *,
        kind: ProviderErrorKind | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        if kind is not None:
            self.kind = kind
        self.retry_after_seconds = retry_after_seconds


class ProviderRetryExhausted(ProviderError):
    """Raised after the provider exhausted its retry budget on transient
    failures (5xx, 429, timeouts). `kind` is the last failure's; the
    wrapped cause carries the last underlying error for diagnostics.
    """

    kind = ProviderErrorKind.UNAVAILABLE


class ProviderConfigError(ProviderError):
    """Raised when a provider can't run because its configuration is
    invalid (missing API key, unpriced model, Bedrock without an
    implementation, etc.). Distinct from runtime failures because the
    cause is structural, not transient.
    """

    kind = ProviderErrorKind.MISCONFIGURED
