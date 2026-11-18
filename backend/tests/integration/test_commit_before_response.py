# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Auth writes are committed before their response is sent.

The request's session commits in `get_db_session` after the endpoint
returns. With FastAPI's default scope for a dependency with `yield`, that
code ran after the response had been sent, so register, login, refresh
and logout answered before their writes were committed: a client's next
request could find no user, or no refresh token. `DbSession` now uses
`scope="function"`, which runs it before the response.

These tests record the order in which the app commits and sends the last
byte of its response, through the real `get_db_session`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.main import app

pytestmark = pytest.mark.integration

_PASSWORD = "OrderCheck2026"

Events = list[str]


@pytest_asyncio.fixture
async def recorded(
    db_connection: AsyncConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, Events]]:
    """A client whose requests run the real `get_db_session`, as
    `integration_client` does, plus a list of "commit" and "response sent"
    events in the order they happened."""
    from app.middleware.rate_limit import reset_rate_limit_state

    reset_rate_limit_state()
    events: Events = []

    real_commit = AsyncSession.commit

    async def recording_commit(self: AsyncSession) -> None:
        events.append("commit")
        await real_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", recording_commit)
    request_sessions = async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr("app.db.session.get_sessionmaker", lambda: request_sessions)

    async def recording_app(
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        async def recording_send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                events.append("response sent")
            await send(message)

        await app(scope, receive, recording_send)

    async with AsyncClient(
        transport=ASGITransport(app=recording_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client, events


def _committed_before_sending(events: Events) -> bool:
    return "commit" in events and events[-1] == "response sent"


async def test_register_login_refresh_and_logout_commit_before_responding(
    recorded: tuple[AsyncClient, Events],
) -> None:
    client, events = recorded

    events.clear()
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": "order@example.com", "password": _PASSWORD, "full_name": "Order"},
    )
    assert register.status_code == 201
    assert _committed_before_sending(events), f"register: {events}"

    events.clear()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "order@example.com", "password": _PASSWORD},
    )
    assert login.status_code == 200
    assert _committed_before_sending(events), f"login: {events}"

    events.clear()
    refresh = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": login.cookies["refresh_token"]},
    )
    assert refresh.status_code == 200
    assert _committed_before_sending(events), f"refresh: {events}"

    events.clear()
    logout = await client.post(
        "/api/v1/auth/logout",
        cookies={"refresh_token": refresh.cookies["refresh_token"]},
    )
    assert logout.status_code == 204
    assert _committed_before_sending(events), f"logout: {events}"
