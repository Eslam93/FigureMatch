# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""What the replay takes as true about OpenAI, with where each fact comes from.

The replay never contacts OpenAI. Two of the four defects are about the
outside world (a published price, a model's shutdown), so the stand-in
server in `fake_openai.py` and the cost probe both read their facts from
here. Check them against the pages named below: if a figure here is wrong,
the replay's verdict on those two probes is wrong with it.

Every figure was read from OpenAI's documentation on 2026-11-06, when the
defects were fixed, and is the same figure `backend/app/core/model_catalog.py`
records with that date. They were not read again when this file was written
(2026-11-18): the machine that wrote it could not reach OpenAI's site.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

READ_ON = date(2026, 11, 6)

PRICING_URL = "https://developers.openai.com/api/docs/pricing"
DEPRECATIONS_URL = "https://developers.openai.com/api/docs/deprecations"

# USD per 1,000,000 tokens, standard tier. Source: PRICING_URL.
_GPT_5_4_MINI = {
    "input": Decimal("0.75"),
    "cached_input": Decimal("0.075"),
    "output": Decimal("4.50"),
}
TEXT_PRICES_PER_MILLION: dict[str, dict[str, Decimal]] = {
    "gpt-5.4-mini": _GPT_5_4_MINI,
    "gpt-5.4-mini-2026-03-17": _GPT_5_4_MINI,
}

# Models OpenAI has shut down, with the shutdown date. Source: DEPRECATIONS_URL.
# A request naming one of these gets the API's 404 `model_not_found`.
SHUT_DOWN: dict[str, date] = {
    "gpt-image-1": date(2026, 10, 23),
}

# The models the stand-in serves. Any other id gets a 404, as an unknown
# model does at OpenAI. Source: PRICING_URL, which prices each of them.
LIVE_TEXT_MODELS: frozenset[str] = frozenset(TEXT_PRICES_PER_MILLION)
LIVE_IMAGE_MODELS: frozenset[str] = frozenset(
    {"gpt-image-2.5-flare", "gpt-image-2.5-flare-2026-09-08"}
)


def is_shut_down(model: str, *, on: date) -> bool:
    """True from the shutdown day onwards."""
    shutdown = SHUT_DOWN.get(model)
    return shutdown is not None and shutdown <= on


def text_cost_usd(
    model: str, *, input_tokens: int, cached_input_tokens: int, output_tokens: int
) -> Decimal:
    """What OpenAI charges for one completion, from the published prices."""
    price = TEXT_PRICES_PER_MILLION[model]
    uncached = input_tokens - cached_input_tokens
    total = (
        uncached * price["input"]
        + cached_input_tokens * price["cached_input"]
        + output_tokens * price["output"]
    )
    return total / Decimal(1_000_000)
