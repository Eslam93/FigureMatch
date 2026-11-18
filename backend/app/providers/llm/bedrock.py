# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""BedrockClaudeProvider — documented stub.

The brief calls for Bedrock + Claude Sonnet 4.5 + Nova Canvas as an
alternative provider path, gated behind `AI_PROVIDER_MODE=bedrock`.
Real implementation is deliberately deferred until there is a reason
to switch — Bedrock requires per-account Anthropic enablement and
Nova Canvas is LEGACY with a 2026-09-30 EOL.

When activated, this class becomes the place to wire the
`bedrock-runtime:InvokeModel` call. Until then it raises so a
misconfigured deploy (`AI_PROVIDER_MODE=bedrock` without the impl
ready) fails fast at construction.
"""

from __future__ import annotations

from typing import Any

from app.providers.errors import ProviderConfigError
from app.providers.llm.base import LLMResult


class BedrockClaudeProvider:
    """Stub for the Bedrock + Claude Sonnet 4.5 implementation."""

    def __init__(self) -> None:
        raise ProviderConfigError(
            "AI_PROVIDER_MODE=bedrock is documented but not implemented. "
            "Either switch to AI_PROVIDER_MODE=openai (recommended) or "
            "AI_PROVIDER_MODE=mock, or implement BedrockClaudeProvider "
            "before deploying with this mode."
        )

    async def generate(  # pragma: no cover - unreachable until impl lands
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
        content_type: str,
    ) -> LLMResult:
        raise NotImplementedError("BedrockClaudeProvider.generate")
