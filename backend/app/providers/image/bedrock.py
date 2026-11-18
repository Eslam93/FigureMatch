# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""BedrockNovaCanvasProvider — documented stub.

Same status as `BedrockClaudeProvider`: documented path,
unimplemented until needed. Activation requires resolving Nova Canvas's
LEGACY status (EOL 2026-09-30) — likely by migrating to whatever
Bedrock ships as the successor image model when that lands.
"""

from __future__ import annotations

from app.providers.errors import ProviderConfigError
from app.providers.image.base import ImageQuality, ImageResult


class BedrockNovaCanvasProvider:
    """Stub for the Bedrock Nova Canvas implementation."""

    def __init__(self) -> None:
        raise ProviderConfigError(
            "AI_PROVIDER_MODE=bedrock is documented but not implemented. "
            "BedrockNovaCanvasProvider has no working implementation yet. "
            "Nova Canvas is also LEGACY (EOL 2026-09-30); migrate to its "
            "successor before activating this path."
        )

    async def generate(  # pragma: no cover - unreachable until impl lands
        self,
        *,
        prompt: str,
        quality: ImageQuality = ImageQuality.MEDIUM,
        size: tuple[int, int] = (1024, 1024),
    ) -> ImageResult:
        raise NotImplementedError("BedrockNovaCanvasProvider.generate")
