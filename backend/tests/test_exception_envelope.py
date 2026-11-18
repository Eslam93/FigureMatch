# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Tests for the consistent error envelope across exception types."""

from __future__ import annotations

from fastapi import APIRouter
from httpx import AsyncClient

from app.core.exceptions import (
    AppException,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
)
from app.main import app


async def test_404_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/nonexistent")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "message" in body["error"]
    assert "request_id" in body["meta"]


def _attach_probe_routes() -> APIRouter:
    """Build a small router that raises each of our exception types."""
    r = APIRouter()

    @r.get("/__probe/not-found")
    async def _not_found() -> None:
        raise NotFoundError()

    @r.get("/__probe/unauthorized")
    async def _unauthorized() -> None:
        raise UnauthorizedError()

    @r.get("/__probe/conflict")
    async def _conflict() -> None:
        raise ConflictError("Email already registered.", details={"field": "email"})

    @r.get("/__probe/custom")
    async def _custom() -> None:
        raise AppException("Custom message.", code="CUSTOM_CODE")

    return r


# Attach the probe router once at import time so the fixture-driven client
# can exercise it.
app.include_router(_attach_probe_routes(), prefix="/api/v1")


async def test_app_exception_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/__probe/not-found")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Resource not found."
    assert body["error"]["details"] == {}
    assert "request_id" in body["meta"]


async def test_app_exception_with_details(client: AsyncClient) -> None:
    response = await client.get("/api/v1/__probe/conflict")
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["message"] == "Email already registered."
    assert body["error"]["details"] == {"field": "email"}


async def test_app_exception_with_custom_code(client: AsyncClient) -> None:
    response = await client.get("/api/v1/__probe/custom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "CUSTOM_CODE"
    assert body["error"]["message"] == "Custom message."


async def test_unauthorized_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/__probe/unauthorized")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
