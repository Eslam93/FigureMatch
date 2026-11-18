# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Per-request context variables. Populated by middleware, consumed by logging."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Final

_request_id_var: Final[ContextVar[str | None]] = ContextVar("request_id", default=None)
_user_id_var: Final[ContextVar[str | None]] = ContextVar("user_id", default=None)


def get_request_id() -> str | None:
    return _request_id_var.get()


def set_request_id(value: str | None) -> None:
    _request_id_var.set(value)


def get_user_id() -> str | None:
    return _user_id_var.get()


def set_user_id(value: str | None) -> None:
    _user_id_var.set(value)
