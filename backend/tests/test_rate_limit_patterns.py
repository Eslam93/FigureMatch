# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Tests for the pattern-rule branch of the rate-limit middleware.

The exact-path dict is already covered by `test_rate_limit.py`; this
file pins the regex-rule path used for dynamic endpoints like
`/api/v1/content/<uuid>/image` and `/api/v1/improve`.
"""

from __future__ import annotations

import re

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.middleware.rate_limit import (
    RateLimitMiddleware,
    RateLimitRule,
    reset_rate_limit_state,
)


def _make_app(rules=None, patterns=None) -> Starlette:  # type: ignore[no-untyped-def]
    async def _ok(_request):  # type: ignore[no-untyped-def]
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/{path:path}", _ok, methods=["GET", "POST"])])
    app.add_middleware(RateLimitMiddleware, rules=rules or {}, patterns=patterns or [])
    return app


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_rate_limit_state()


@pytest.mark.asyncio
async def test_pattern_rule_limits_dynamic_path() -> None:
    pattern = RateLimitRule(
        pattern=re.compile(r"^/api/v1/content/[0-9a-fA-F-]{36}/image$"),
        limit=2,
        key="pattern:image",
    )
    app = _make_app(patterns=[pattern])
    url = "/api/v1/content/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/image"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r1 = await client.post(url)
        r2 = await client.post(url)
        r3 = await client.post(url)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r3.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_pattern_rule_buckets_distinct_uuids_separately() -> None:
    """Two different content-ids must share the SAME rule key (not
    separate counters per uuid) so a user can't dodge the limit by
    rotating the dynamic segment. The bucket key is `(rule.key, ip)`
    not `(path, ip)`.
    """
    pattern = RateLimitRule(
        pattern=re.compile(r"^/api/v1/content/[0-9a-fA-F-]{36}/image$"),
        limit=2,
        key="pattern:image",
    )
    app = _make_app(patterns=[pattern])
    uuid_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    uuid_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r1 = await client.post(f"/api/v1/content/{uuid_a}/image")
        r2 = await client.post(f"/api/v1/content/{uuid_b}/image")
        r3 = await client.post(f"/api/v1/content/{uuid_a}/image")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429


@pytest.mark.asyncio
async def test_exact_path_wins_over_pattern() -> None:
    exact_rules = {"/api/v1/improve": 1}
    catch_all = RateLimitRule(
        pattern=re.compile(r"^/api/v1/improve$"),
        limit=100,
        key="pattern:improve",
    )
    app = _make_app(rules=exact_rules, patterns=[catch_all])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r1 = await client.post("/api/v1/improve")
        r2 = await client.post("/api/v1/improve")

    assert r1.status_code == 200
    # Exact-path rule (limit=1) hits before the pattern's larger cap
    # would have. Confirms exact wins.
    assert r2.status_code == 429


@pytest.mark.asyncio
async def test_unmatched_path_is_unlimited() -> None:
    pattern = RateLimitRule(
        pattern=re.compile(r"^/api/v1/improve$"),
        limit=1,
        key="pattern:improve",
    )
    app = _make_app(patterns=[pattern])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        for _ in range(10):
            r = await client.get("/api/v1/health")
            assert r.status_code == 200
