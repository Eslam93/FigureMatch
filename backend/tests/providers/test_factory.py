# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Provider factory — mode selection, caching, reset hook."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.providers import factory
from app.providers.errors import ProviderConfigError
from app.providers.image.mock import MockImageProvider
from app.providers.image.openai_provider import OpenAIImageProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.openai_provider import OpenAIChatProvider

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.fixture(autouse=True)
def reset_cache() -> None:
    """Every test must start from a cold cache — the factory's
    module-level singletons leak across tests otherwise."""
    factory.reset_provider_cache()


def test_mock_mode_returns_mock_providers(monkeypatch: MonkeyPatch) -> None:
    from app.core.config import AIProviderMode, get_settings

    monkeypatch.setattr(get_settings(), "ai_provider_mode", AIProviderMode.MOCK)
    assert isinstance(factory.get_llm_provider(), MockLLMProvider)
    assert isinstance(factory.get_image_provider(), MockImageProvider)


def test_openai_mode_returns_openai_providers(monkeypatch: MonkeyPatch) -> None:
    """We need a valid-looking API key in settings to construct the
    OpenAI client; the SDK itself isn't called."""
    from pydantic import SecretStr

    from app.core.config import AIProviderMode, get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_mode", AIProviderMode.OPENAI)
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("sk-proj-fake"))
    assert isinstance(factory.get_llm_provider(), OpenAIChatProvider)
    assert isinstance(factory.get_image_provider(), OpenAIImageProvider)


def test_bedrock_mode_raises_config_error(monkeypatch: MonkeyPatch) -> None:
    """Bedrock impls are deliberately stubbed — selecting the mode
    must fail at construction so a misconfigured deploy doesn't
    silently 'work' with `NotImplementedError` at first request time."""
    from app.core.config import AIProviderMode, get_settings

    monkeypatch.setattr(get_settings(), "ai_provider_mode", AIProviderMode.BEDROCK)
    with pytest.raises(ProviderConfigError, match="not implemented"):
        factory.get_llm_provider()
    factory.reset_provider_cache()
    with pytest.raises(ProviderConfigError, match="not implemented"):
        factory.get_image_provider()


def test_cache_returns_same_instance_within_process(
    monkeypatch: MonkeyPatch,
) -> None:
    """The factory caches providers so the OpenAI HTTP client (which
    holds a connection pool) is reused. Verify with the mock mode —
    no client to worry about, but the singleton contract is identical."""
    from app.core.config import AIProviderMode, get_settings

    monkeypatch.setattr(get_settings(), "ai_provider_mode", AIProviderMode.MOCK)
    a = factory.get_llm_provider()
    b = factory.get_llm_provider()
    assert a is b


def test_reset_provider_cache_drops_cached_instances(
    monkeypatch: MonkeyPatch,
) -> None:
    """The test hook — without it, mode changes between tests would
    leak the first-selected provider into every subsequent test."""
    from app.core.config import AIProviderMode, get_settings

    monkeypatch.setattr(get_settings(), "ai_provider_mode", AIProviderMode.MOCK)
    first = factory.get_llm_provider()
    factory.reset_provider_cache()
    second = factory.get_llm_provider()
    assert first is not second
