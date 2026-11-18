# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""AI provider abstractions.

Two protocols (`ILLMProvider`, `IImageProvider`) with two implementations
each: OpenAI, and Mock (canned output for tests and a demo with no key).
The factory selects an implementation based on `AI_PROVIDER_MODE`.
"""

from app.providers.errors import (
    ProviderConfigError,
    ProviderError,
    ProviderErrorKind,
    ProviderIncompleteOutput,
    ProviderRetryExhausted,
)
from app.providers.factory import get_image_provider, get_llm_provider
from app.providers.image.base import IImageProvider, ImageQuality, ImageResult
from app.providers.llm.base import ILLMProvider, LLMResult

__all__ = [
    "IImageProvider",
    "ILLMProvider",
    "ImageQuality",
    "ImageResult",
    "LLMResult",
    "ProviderConfigError",
    "ProviderError",
    "ProviderErrorKind",
    "ProviderIncompleteOutput",
    "ProviderRetryExhausted",
    "get_image_provider",
    "get_llm_provider",
]
