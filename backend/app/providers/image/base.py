"""Image provider protocol and result types.

Mirrors the LLM provider surface: a single `generate` method that
returns raw bytes plus enough metadata to log cost, dimensions, and
provider-specific identifiers. The caller (image service) handles S3
upload and CloudFront URL generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ImageQuality(StrEnum):
    """Quality tier requested from the image provider.

    Maps to provider-specific configuration:
    - OpenAI GPT Image models: `quality="low" | "medium" | "high"`
    - Bedrock Nova Canvas: `low → standard`, `medium/high → premium`

    `low` is the dev/CI default. `medium` is the production default for
    most flows. `high` is reserved for hero-image moments where the
    extra latency and cost are justified.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class ImageResult:
    """The outcome of a single image-generation call.

    `image_bytes` are the raw PNG bytes — the caller decides whether to
    upload to S3, serve directly, or hand off to a CDN.
    """

    image_bytes: bytes
    width: int
    height: int
    model: str
    quality: ImageQuality
    cost_usd: float
    latency_ms: int
    prompt_used: str
    """The final prompt as sent to the provider. May include
    constraint folding (e.g., OpenAI's GPT Image models don't accept a
    separate `negative_prompt`, so callers fold constraints into the
    positive prompt). Storing this lets us reproduce the call later."""


class IImageProvider(Protocol):
    """Surface for image-generation providers.

    Same error-handling contract as `ILLMProvider`: retry on transient
    failures within budget, translate provider-specific errors into
    `ProviderError` subclasses.
    """

    async def generate(
        self,
        *,
        prompt: str,
        quality: ImageQuality = ImageQuality.MEDIUM,
        size: tuple[int, int] = (1024, 1024),
    ) -> ImageResult:
        """Generate a single image and return its bytes + metadata.

        `size` defaults to 1024×1024 (square) — the only size all
        providers reliably support. Non-square sizes are provider-
        specific and not part of the protocol.
        """
        ...
