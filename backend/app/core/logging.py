# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""structlog configuration. JSON output to stdout, request-context aware."""

from __future__ import annotations

import logging
import sys
from typing import Any, cast

import structlog
from structlog.stdlib import BoundLogger
from structlog.types import EventDict, Processor

from app.core.request_context import get_request_id, get_user_id


def _add_request_context(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Attach `request_id` and `user_id` from contextvars onto every event."""
    request_id = get_request_id()
    if request_id is not None:
        event_dict.setdefault("request_id", request_id)
    user_id = get_user_id()
    if user_id is not None:
        event_dict.setdefault("user_id", user_id)
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Idempotent structlog configuration.

    The renderer is JSON for production (CloudWatch-friendly). Logs include
    an ISO-8601 timestamp, the log level, the logger name, and any context
    populated via `request_context` (set by `RequestIDMiddleware`).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        _add_request_context,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> BoundLogger:
    """Return a structlog bound logger."""
    return cast(BoundLogger, structlog.get_logger(name))
