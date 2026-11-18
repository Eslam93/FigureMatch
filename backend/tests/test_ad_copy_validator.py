# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Tests for the AdCopyResult one-of-each-format validator.

The Pydantic schema enforces the 3-variant count and per-variant
`format` Literal, but a model that returns three "short" variants
would silently render only the short block (the renderer keys on
format). The after-validator catches that at parse time and forces
the corrective retry through `ResultParseStatus.FAILED`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.content import AdCopyResult


def _variant(fmt: str, *, angle: str = "curiosity") -> dict[str, str]:
    return {
        "format": fmt,
        "angle": angle,
        "headline": f"{fmt} headline",
        "body": f"{fmt} body",
        "cta": "click",
    }


def test_accepts_one_of_each_format() -> None:
    payload = {
        "variants": [_variant("short"), _variant("medium"), _variant("long")],
    }
    parsed = AdCopyResult.model_validate(payload)
    assert {v.format for v in parsed.variants} == {"short", "medium", "long"}


def test_rejects_duplicate_formats() -> None:
    payload = {
        "variants": [_variant("short"), _variant("short"), _variant("short")],
    }
    with pytest.raises(ValidationError) as excinfo:
        AdCopyResult.model_validate(payload)
    msg = str(excinfo.value)
    assert "one variant per format" in msg
    # The error should name the missing formats so a corrective retry
    # gives the model concrete feedback.
    assert "medium" in msg
    assert "long" in msg


def test_accepts_any_order_of_formats() -> None:
    """The renderer normalizes order; the validator must not care."""
    payload = {
        "variants": [_variant("long"), _variant("short"), _variant("medium")],
    }
    parsed = AdCopyResult.model_validate(payload)
    assert len(parsed.variants) == 3
