# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""MockImageProvider — returns a deterministic placeholder PNG.

Real-world image generation is slow (8–15s) and paid. The mock returns
the same shape (`ImageResult`) so the downstream S3-upload + URL-signing
code paths run unchanged. The PNG itself is a hardcoded 1×1 transparent
pixel — small, valid, and trivially identifiable in storage as
"not a real generated image."
"""

from __future__ import annotations

import base64
from typing import Final

from app.providers.image.base import ImageQuality, ImageResult

# A 1×1 transparent PNG, hex-encoded for human-readability of the byte
# stream. Small enough to embed inline, valid enough that Pillow / any
# image decoder accepts it. We use this as the fixed mock output —
# downstream code never needs to know it's a stub.
_PLACEHOLDER_PNG_B64: Final[str] = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
_PLACEHOLDER_PNG: Final[bytes] = base64.b64decode(_PLACEHOLDER_PNG_B64)


class MockImageProvider:
    """In-process image-generation substitute. Returns the same bytes
    every call so tests and demos stay byte-stable.

    Dimensions in the result reflect the ACTUAL bytes (1×1) rather than
    the requested `size`. Reporting fake 1024×1024 would lie to
    downstream code (S3 upload, dimension probing, CDN); a caller that
    really needs a 1024×1024 placeholder should generate one rather
    than have the provider pretend.
    """

    model: Final[str] = "mock-image-v1"

    # Dimensions of the embedded 1×1 PNG.
    _ACTUAL_WIDTH: Final[int] = 1
    _ACTUAL_HEIGHT: Final[int] = 1

    async def generate(
        self,
        *,
        prompt: str,
        quality: ImageQuality = ImageQuality.MEDIUM,
        size: tuple[int, int] = (1024, 1024),  # kept for interface parity; ignored
    ) -> ImageResult:
        return ImageResult(
            image_bytes=_PLACEHOLDER_PNG,
            width=self._ACTUAL_WIDTH,
            height=self._ACTUAL_HEIGHT,
            model=self.model,
            quality=quality,
            cost_usd=0.0,
            latency_ms=0,
            prompt_used=prompt,
        )
