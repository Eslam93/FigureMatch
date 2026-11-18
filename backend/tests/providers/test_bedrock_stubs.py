# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Bedrock provider stubs.

The point of these tests: lock down that the stubs **raise at
construction**, not later. A misconfigured deploy must never silently
succeed past startup just to fail at first generation request.
"""

from __future__ import annotations

import pytest

from app.providers.errors import ProviderConfigError
from app.providers.image.bedrock import BedrockNovaCanvasProvider
from app.providers.llm.bedrock import BedrockClaudeProvider


def test_bedrock_claude_construction_raises_config_error() -> None:
    with pytest.raises(ProviderConfigError, match="not implemented"):
        BedrockClaudeProvider()


def test_bedrock_nova_canvas_construction_raises_config_error() -> None:
    with pytest.raises(ProviderConfigError, match="not implemented"):
        BedrockNovaCanvasProvider()
