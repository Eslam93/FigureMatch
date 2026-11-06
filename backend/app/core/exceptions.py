"""Application exception hierarchy and FastAPI handlers.

Every error response follows the same envelope:

    {
      "error":  { "code": "<MACHINE_READABLE>", "message": "<human>", "details": {...} },
      "meta":   { "request_id": "<uuid>" }
    }

This is the contract referenced throughout the API documentation.

Provider failures (`app.providers.errors.ProviderError`) aren't
`AppException`s: their handler maps each kind to a fixed status, code and
message, so no exception text, and with it no upstream error text, ever
reaches a response.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.core.request_context import get_request_id
from app.providers.errors import ProviderError, ProviderErrorKind

log = get_logger(__name__)


class AppException(Exception):
    """Base class for all application-defined exceptions.

    Subclasses set their own `status_code`, `code`, and default `message`.
    Instances may override the message or attach `details` per occurrence.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or self.message)
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        self.details = details or {}


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    message = "Resource not found."


class UnauthorizedError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"
    message = "Authentication required."


class ForbiddenError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    message = "You don't have permission to perform this action."


class ValidationError(AppException):
    status_code = 422
    code = "VALIDATION_FAILED"
    message = "Request validation failed."


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    message = "Resource conflict."


class RateLimitError(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    message = "Too many requests."


@dataclass(frozen=True, slots=True)
class _ProviderErrorResponse:
    status_code: int
    code: str
    message: str


_AI_UNAVAILABLE: Final = _ProviderErrorResponse(
    status.HTTP_503_SERVICE_UNAVAILABLE,
    "AI_UNAVAILABLE",
    "The AI provider is unavailable right now. Try again later.",
)

# What the client gets for each kind of provider failure. Every message is
# fixed: an exception's own text may describe the upstream failure, so it
# goes to the log only. The frontend maps these codes; keep them stable.
_PROVIDER_ERROR_RESPONSES: Final[dict[ProviderErrorKind, _ProviderErrorResponse]] = {
    ProviderErrorKind.AUTH: _ProviderErrorResponse(
        status.HTTP_502_BAD_GATEWAY,
        "AI_PROVIDER_AUTH_FAILED",
        "The AI provider rejected the server's credentials.",
    ),
    ProviderErrorKind.RATE_LIMITED: _ProviderErrorResponse(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "AI_RATE_LIMITED",
        "The AI provider is rate limiting requests. Try again shortly.",
    ),
    # Out of quota is an operator problem, not a reason to retry soon.
    ProviderErrorKind.QUOTA_EXHAUSTED: _AI_UNAVAILABLE,
    ProviderErrorKind.UNAVAILABLE: _AI_UNAVAILABLE,
    ProviderErrorKind.TIMEOUT: _ProviderErrorResponse(
        status.HTTP_504_GATEWAY_TIMEOUT,
        "AI_TIMEOUT",
        "The AI provider took too long to respond. Try again.",
    ),
    ProviderErrorKind.TRUNCATED: _ProviderErrorResponse(
        status.HTTP_502_BAD_GATEWAY,
        "AI_OUTPUT_TRUNCATED",
        "The AI response was cut off before it was complete. Try again.",
    ),
    ProviderErrorKind.CONTENT_REJECTED: _ProviderErrorResponse(
        422,
        "AI_CONTENT_REJECTED",
        "The AI provider declined this request under its content policy.",
    ),
    ProviderErrorKind.MISCONFIGURED: _ProviderErrorResponse(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "AI_PROVIDER_MISCONFIGURED",
        "The AI provider is not configured correctly on the server.",
    ),
    ProviderErrorKind.OTHER: _ProviderErrorResponse(
        status.HTTP_502_BAD_GATEWAY,
        "PROVIDER_ERROR",
        "Upstream provider error.",
    ),
}


def _envelope(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "meta": {
            "request_id": get_request_id(),
        },
    }


_HTTP_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_FAILED",
    429: "RATE_LIMITED",
}


async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
    log.warning(
        "app_exception",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        status_code=exc.status_code,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code=exc.code, message=exc.message, details=exc.details),
    )


def _retry_after_whole_seconds(seconds: float | None) -> int | None:
    """Whole seconds for a `Retry-After` header, rounded up; None when
    the provider didn't say or said something unusable."""
    if seconds is None or not math.isfinite(seconds) or seconds <= 0:
        return None
    return math.ceil(seconds)


async def provider_exception_handler(_: Request, exc: ProviderError) -> JSONResponse:
    """Answer a provider failure with its kind's fixed status, code and message.

    A rate limit with a known wait also gets `Retry-After` and, like the
    RateLimit middleware's 429, `details.retry_after_seconds`: the
    cross-origin frontend can read the body but not that header.
    """
    response = _PROVIDER_ERROR_RESPONSES[exc.kind]
    retry_after = (
        _retry_after_whole_seconds(exc.retry_after_seconds)
        if exc.kind is ProviderErrorKind.RATE_LIMITED
        else None
    )
    # A misconfiguration fails every request until someone fixes it, and
    # nothing logs it before this point.
    emit = log.error if exc.kind is ProviderErrorKind.MISCONFIGURED else log.warning
    emit(
        "provider_error",
        kind=exc.kind.value,
        code=response.code,
        status_code=response.status_code,
        error_type=type(exc).__name__,
        error=str(exc),
        retry_after_seconds=retry_after,
    )
    details: dict[str, Any] = {}
    headers: dict[str, str] | None = None
    if retry_after is not None:
        details["retry_after_seconds"] = retry_after
        headers = {"Retry-After": str(retry_after)}
    return JSONResponse(
        status_code=response.status_code,
        content=_envelope(code=response.code, message=response.message, details=details),
        headers=headers,
    )


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
    message = str(exc.detail) if exc.detail else "HTTP error."
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code=code, message=message),
    )


def _public_validation_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """Keep only `loc`, `msg` and `type` of each validation error.

    Pydantic also returns `input`, the submitted value, so a rejected
    password would come straight back in the response body. `ctx` and
    `url` only describe Pydantic internals. The frontend reads `loc` and
    `msg`.
    """
    return [
        {"loc": err.get("loc"), "msg": err.get("msg"), "type": err.get("type")} for err in errors
    ]


async def validation_exception_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = exc.errors()
    # If a Pydantic `PydanticCustomError` flagged a weak-password
    # validation failure on /auth/register, surface the specific
    # WEAK_PASSWORD code (frontend + integration tests depend on it).
    # `field_validator`s in `schemas/auth.py` raise the distinct error
    # type; everything else maps to the generic VALIDATION_FAILED.
    code = "VALIDATION_FAILED"
    message = "Request validation failed."
    if any(err.get("type") == "weak_password" for err in errors):
        code = "WEAK_PASSWORD"
        message = next(
            (err.get("msg", message) for err in errors if err.get("type") == "weak_password"),
            message,
        )
    return JSONResponse(
        status_code=422,
        content=_envelope(
            code=code,
            message=message,
            details={"errors": _public_validation_errors(errors)},
        ),
    )


def internal_error_response() -> JSONResponse:
    """The generic 500 envelope. Never carries the exception's text."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(
            code="INTERNAL_ERROR",
            message="An internal error occurred.",
        ),
    )


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Last resort for what `UnhandledErrorMiddleware` can't render.

    Starlette runs this in `ServerErrorMiddleware`, outside every user
    middleware, so its envelope has no `request_id` and its response none
    of their headers. App exceptions don't get here: the middleware
    renders them inside the stack. What's left is an exception raised by
    a middleware outside it, or one re-raised because the response had
    already started (then nothing more is sent and only the log remains).
    """
    log.exception("unhandled_exception", error=str(exc))
    return internal_error_response()


def register_exception_handlers(app: FastAPI) -> None:
    """Wire every handler into the FastAPI app."""
    # The ignores: Starlette types every handler as taking a bare
    # `Exception`, but each one takes the class it is registered for.
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ProviderError, provider_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
