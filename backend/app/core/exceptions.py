"""Application exception hierarchy and FastAPI handlers.

Every error response follows the same envelope:

    {
      "error":  { "code": "<MACHINE_READABLE>", "message": "<human>", "details": {...} },
      "meta":   { "request_id": "<uuid>" }
    }

This is the contract referenced throughout the API documentation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.core.request_context import get_request_id

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


class ProviderError(AppException):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "PROVIDER_ERROR"
    message = "Upstream provider error."


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


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_exception", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(
            code="INTERNAL_ERROR",
            message="An internal error occurred.",
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire every handler into the FastAPI app."""
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
