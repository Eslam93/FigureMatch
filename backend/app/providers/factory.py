# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Provider factory.

Reads `AI_PROVIDER_MODE` from settings and returns the matching
implementation. Result is cached per-mode so the OpenAI HTTP client's
connection pool is reused across requests. Tests can clear the cache
via `reset_provider_cache()`.
"""

from __future__ import annotations

from app.core.config import AIProviderMode, get_settings
from app.providers.errors import ProviderConfigError
from app.providers.image.base import IImageProvider
from app.providers.image.mock import MockImageProvider
from app.providers.image.openai_provider import OpenAIImageProvider
from app.providers.llm.base import ILLMProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.openai_provider import OpenAIChatProvider

# Module-level cache. We want one provider instance per process so the
# OpenAI AsyncOpenAI client (which holds an HTTP connection pool)
# isn't re-created per request. Tests can call `reset_provider_cache()`
# between cases that override env-driven mode selection.
_llm_provider: ILLMProvider | None = None
_image_provider: IImageProvider | None = None


def _build_llm_provider(mode: AIProviderMode) -> ILLMProvider:
    match mode:
        case AIProviderMode.OPENAI:
            return OpenAIChatProvider()
        case AIProviderMode.MOCK:
            return MockLLMProvider()
    raise ProviderConfigError(f"Unknown AI_PROVIDER_MODE: {mode!r}")


def _build_image_provider(mode: AIProviderMode) -> IImageProvider:
    match mode:
        case AIProviderMode.OPENAI:
            return OpenAIImageProvider()
        case AIProviderMode.MOCK:
            return MockImageProvider()
    raise ProviderConfigError(f"Unknown AI_PROVIDER_MODE: {mode!r}")


def get_llm_provider() -> ILLMProvider:
    """Return the process-wide LLM provider. Caches on first call."""
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = _build_llm_provider(get_settings().ai_provider_mode)
    return _llm_provider


def get_image_provider() -> IImageProvider:
    """Return the process-wide image provider. Caches on first call."""
    global _image_provider
    if _image_provider is None:
        _image_provider = _build_image_provider(get_settings().ai_provider_mode)
    return _image_provider


def reset_provider_cache() -> None:
    """Clear the cached providers. Tests call this between cases that
    flip `AI_PROVIDER_MODE`; production code never needs it.
    """
    global _llm_provider, _image_provider
    _llm_provider = None
    _image_provider = None
