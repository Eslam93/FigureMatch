"""Tests for the /api/v1/health endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from httpx import AsyncClient

if TYPE_CHECKING:
    from pytest import MonkeyPatch


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"status", "version", "environment", "dependencies"}
    assert body["status"] == "ok"
    # No `redis` key: the backend has no Redis dependency to report.
    assert set(body["dependencies"].keys()) == {"db", "openai"}


async def test_health_reports_db_ok_when_reachable(client: AsyncClient) -> None:
    # The conftest autouse fixture stubs the probe to True.
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["dependencies"]["db"] == "ok"


async def test_health_reports_db_down_when_unreachable(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    async def _down() -> bool:
        return False

    monkeypatch.setattr("app.api.v1.routers.health.check_db_health", _down)
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["dependencies"]["db"] == "down"


async def test_health_echoes_incoming_request_id(client: AsyncClient) -> None:
    incoming = "11111111-2222-3333-4444-555555555555"
    response = await client.get(
        "/api/v1/health",
        headers={"X-Request-ID": incoming},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == incoming


async def test_health_generates_request_id_when_absent(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    # uuid4 stringified is 36 chars (32 hex + 4 dashes)
    assert len(request_id) == 36
