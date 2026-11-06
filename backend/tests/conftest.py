"""Shared pytest fixtures for the backend test suite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.fixture(autouse=True)
def stub_dependency_probes(monkeypatch: MonkeyPatch) -> None:
    """Default-mock every downstream probe so unit tests don't need live deps.

    Individual tests can opt out by re-patching the probe to return False
    (see `tests/test_health.py::test_health_reports_db_down_when_unreachable`).
    """

    async def _ok() -> bool:
        return True

    monkeypatch.setattr("app.api.v1.routers.health.check_db_health", _ok)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An httpx AsyncClient bound directly to the ASGI app (in-process).

    `raise_app_exceptions=False` makes ASGITransport return a 500 rather
    than re-raise an exception that escapes the app into the test, which
    matches real wire behavior. Route exceptions don't escape:
    `UnhandledErrorMiddleware` turns them into the {error, meta} envelope.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        yield ac
