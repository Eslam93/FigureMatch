"""Tests for the `cors_origins` localhost validator.

The deploy default in `compute-stack.ts` is `http://localhost:3000`
which would be intended to be overridden post-deploy with the real
Amplify URL. Without this validator the backend could boot in `dev`
with the stale localhost value, and every cross-origin request from
the real frontend would be blocked at the CORS layer.
"""

from __future__ import annotations

import pytest

from app.core.config import Environment, Settings


def _make_settings(**overrides: object) -> Settings:
    """Build a Settings instance with non-localhost defaults except
    where the test overrides them. Bypasses the .env reader so test
    runs are deterministic."""
    base: dict[str, object] = {
        "environment": Environment.DEV,
        # 64 hex chars from `openssl rand -hex 32`; passes the entropy gate.
        "jwt_secret": "9bf8c4f2e0a1c34d59ab7f3e2b1d8e9c0a7654321fedcba0987654321abcdef0",
        "openai_api_key": "sk-proj-real-looking-value-1234567890",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_localhost_in_cors_rejected_in_dev() -> None:
    with pytest.raises(ValueError) as excinfo:
        _make_settings(cors_origins=["http://localhost:3000"])
    assert "localhost" in str(excinfo.value)
    assert "dev" in str(excinfo.value)


def test_ipv4_loopback_in_cors_rejected_in_dev() -> None:
    with pytest.raises(ValueError) as excinfo:
        _make_settings(cors_origins=["http://127.0.0.1:3000"])
    assert "127.0.0.1" in str(excinfo.value)


def test_real_https_origin_accepted_in_dev() -> None:
    settings = _make_settings(
        cors_origins=["https://app.example.com"],
    )
    assert settings.cors_origins == ["https://app.example.com"]


def test_localhost_allowed_in_local_environment() -> None:
    """The `local` env exists for the developer compose stack —
    placeholder secrets and localhost are intentionally tolerated.
    """
    settings = _make_settings(
        environment=Environment.LOCAL,
        cors_origins=["http://localhost:3000"],
    )
    assert "http://localhost:3000" in settings.cors_origins
