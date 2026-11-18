# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""The parity matcher used by the gate: it pairs the prices, percentages,
dates, phone numbers, links and promo codes of an English offer with those
of its Arabic version. It reads no words and calls no model."""

from matcher.compare import Finding, KindResult, compare, same
from matcher.extract import KINDS, Figure, extract

__all__ = ["KINDS", "Figure", "Finding", "KindResult", "compare", "extract", "same"]
