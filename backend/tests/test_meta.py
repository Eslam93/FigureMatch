"""GET /api/v1/meta: the public provider mode + app version the frontend reads."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient

from app.core.config import AIProviderMode, get_settings
from app.main import app

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.mark.parametrize("mode", [AIProviderMode.MOCK, AIProviderMode.OPENAI])
async def test_meta_reports_provider_mode_and_app_version(
    client: AsyncClient, monkeypatch: MonkeyPatch, mode: AIProviderMode
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_mode", mode)
    monkeypatch.setattr(settings, "app_version", "9.9.9-test")

    # No Authorization header: the frontend asks before anyone signs in.
    response = await client.get("/api/v1/meta")

    assert response.status_code == 200
    # Exactly these two keys, so no model id, key or other setting leaks.
    assert response.json() == {"provider_mode": mode.value, "app_version": "9.9.9-test"}


def test_meta_response_model_is_in_openapi() -> None:
    spec = app.openapi()

    ok = spec["paths"]["/api/v1/meta"]["get"]["responses"]["200"]
    assert ok["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetaResponse"
    }
    schemas = spec["components"]["schemas"]
    assert set(schemas["MetaResponse"]["properties"]) == {"provider_mode", "app_version"}
    assert set(schemas["MetaResponse"]["required"]) == {"provider_mode", "app_version"}
    assert set(schemas["AIProviderMode"]["enum"]) == {"openai", "mock", "bedrock"}
