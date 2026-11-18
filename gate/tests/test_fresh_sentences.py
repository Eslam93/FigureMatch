# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Sentences that are not in the labelled cases.

Each expected value was written before the matcher was run on its
sentence. They are a check on reading, written by the matcher's author,
so they are weaker than a set labelled by someone else. Their use is to
show where the matcher misreads text it was not designed around.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from matcher import compare, extract
from matcher.text import read_arabic_words, read_english_words


def values(text: str, kind: str) -> list[tuple[object, ...]]:
    return [figure.value for figure in extract(text)[kind]]


# ── prices ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Only $1,299.50 today", [(Decimal("1299.5"), "USD")]),
        ("99 AED/month", [(Decimal(99), "AED")]),
        ("AED50 off your first order", [(Decimal(50), "AED")]),
        ("السعر ٩٩ ريال سعودي فقط", [(Decimal(99), "SAR")]),
        ("د.إ 250 للشخص", [(Decimal(250), "AED")]),
        ("ابتداءً من 5 آلاف جنيه", [(Decimal(5000), "~POUND")]),
        ("Win up to QR 10K", [(Decimal(10000), "QAR")]),
        ("save 2 million dirhams", [(Decimal(2000000), "~DIRHAM")]),
        ("جائزة بقيمة مليون ريال", [(Decimal(1000000), "~RIYAL")]),
        ("بسعر خمسمئة درهم", [(Decimal(500), "~DIRHAM")]),
        ("Galaxy S26 Ultra 512GB", []),
        ("Was SAR 2,000. Now SAR 1,500.", [(Decimal(2000), "SAR"), (Decimal(1500), "SAR")]),
    ],
)
def test_prices(text: str, expected: list[tuple[object, ...]]) -> None:
    assert values(text, "price") == expected


# ── percentages ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Save 10-20% on fares", [10, 20]),
        ("خصم ٢٥ بالمئة", [25]),
        ("خمسون في المئة", [50]),
        ("twenty five percent off", [25]),
        ("0% commission.", [0]),
        ("خصم %15 على الكل", [15]),
        ("Up to 50 % off", [50]),
        ("the percentage of sales", []),
    ],
)
def test_percentages(text: str, expected: list[int]) -> None:
    assert values(text, "percentage") == [(Decimal(rate),) for rate in expected]


# ── dates ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ends on 31/12/2026.", [(2026, 12, 31)]),
        ("Valid 01.02.2027 only", [(2027, 2, 1)]),
        ("Book before 31-Dec-2026", [(2026, 12, 31)]),
        ("December 31st, 2026", [(2026, 12, 31)]),
        ("حتى 5 من يناير 2027", [(2027, 1, 5)]),
        ("until 28 Feb", [(None, 2, 28)]),
        ("from 3 to 7 March 2027", [(2027, 3, 3), (2027, 3, 7)]),
        ("throughout March 2027", [(2027, 3, None)]),
        ("ساري حتى ٢٢ رجب ١٤٤٨", [(2026, 12, 31)]),
        ("you may 15 items per order", []),
        ("version 1.2.3 of the app", []),
    ],
)
def test_dates(text: str, expected: list[tuple[object, ...]]) -> None:
    assert values(text, "date") == expected


# ── phone numbers ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Tel: 04-555-0100", [(None, "45550100")]),
        ("WhatsApp +20 100 555 0100 today", [("20", "1005550100")]),
        ("للاستفسار: ٨٠٠٥٥٥٠١٠٠", [(None, "8005550100")]),
        ("اتصل بنا: 0097144455566", [("971", "44455566")]),
        ("Stay at our hotel for 12345 points", []),
        ("Order number 123456789 is confirmed", []),
        ("Earn 10000 points this year", []),
    ],
)
def test_phones(text: str, expected: list[tuple[object, ...]]) -> None:
    assert values(text, "phone") == expected


# ── links ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Visit www.example.ae/ar/offers.", [("example.ae", ("offers",), (), "ar")]),
        (
            "see https://example.com/uae-en/deals?utm=1",
            [("example.com", ("deals",), (("utm", "1"),), "en")],
        ),
        ("email info@example.com for help", []),
        ("the v2.5 update", []),
    ],
)
def test_links(text: str, expected: list[tuple[object, ...]]) -> None:
    assert values(text, "link") == expected


# ── promo codes ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Enter SAVE10 at checkout", ["save10"]),
        ("use coupon code: winter-2026", ["winter-2026"]),
        ("The code is valid at checkout", []),
        ("كود الخصم: RAMADAN26", ["ramadan26"]),
        ("iPhone 15 Pro 256GB", []),
    ],
)
def test_promo_codes(text: str, expected: list[str]) -> None:
    assert values(text, "promo_code") == [(code,) for code in expected]


# ── pairing ────────────────────────────────────────────────────────────


def test_same_prices_in_another_order_are_a_mismatch() -> None:
    result = compare("AED 100 or AED 200", "٢٠٠ درهم أو ١٠٠ درهم")["price"]
    assert result.verdict == "mismatch"
    assert all(finding.elsewhere for finding in result.findings)


def test_a_country_code_without_its_plus_is_the_same_number() -> None:
    result = compare("Call +971 4 555 0100", "اتصل على 971 4 555 0100")["phone"]
    assert result.verdict == "match"


def test_no_figures_at_all_is_absent_not_match() -> None:
    result = compare("Welcome to our store", "مرحباً بكم في متجرنا")
    assert {r.verdict for r in result.values()} == {"absent"}


# ── number words ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("ألف وخمسمئة", 1500),
        ("خمسة وعشرون", 25),
        ("ثلاثة عشر", 13),
        ("مئتين وخمسين ألف", 250000),
        ("نصف مليون", 500000),
        ("ثلاث مئة", 300),
    ],
)
def test_arabic_number_words(words: str, expected: int) -> None:
    assert read_arabic_words(words) == Decimal(expected)


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("one thousand five hundred", 1500),
        ("a hundred", 100),
        ("one and a half million", 1500000),
        ("twenty-five", 25),
    ],
)
def test_english_number_words(words: str, expected: int) -> None:
    assert read_english_words(words) == Decimal(expected)
