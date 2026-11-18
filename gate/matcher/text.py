# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Text preparation and number reading shared by the extractors.

Two views of every text are kept, the same length, so a position in one is
the same position in the other:

  typed   the text as written, minus invisible marks and vowel signs
  plain   `typed` with digits, separators and spaces in one form: Eastern
          Arabic and Persian digits become 0-9, the Arabic decimal and
          thousands separators become `.` and `,`, `٪` becomes `%`

Numbers are read from `plain`. Promo codes are read from `typed`, because
a code is compared as a customer would type it.
"""

from __future__ import annotations

import re
from decimal import Decimal

# Removed outright: bidirectional controls, zero-width characters, the
# byte-order mark, Arabic vowel signs (tashkeel) and the tatweel stretch.
_INVISIBLE = re.compile("[​-‏‪-‮⁦-⁩؜﻿ً-ٰٟـ]")

_PLAIN = str.maketrans(
    {
        **{chr(0x0660 + i): str(i) for i in range(10)},  # ٠-٩
        **{chr(0x06F0 + i): str(i) for i in range(10)},  # ۰-۹
        "٫": ".",  # ٫ Arabic decimal separator
        "٬": ",",  # ٬ Arabic thousands separator
        "٪": "%",  # ٪ Arabic percent sign
        " ": " ",  # no-break space
        " ": " ",  # narrow no-break space
        " ": " ",  # thin space
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",  # en dash
        "—": "-",  # em dash
        "−": "-",  # minus sign
    }
)

MASK = "￼"  # stands in for text an earlier extractor has claimed


def typed(text: str) -> str:
    """`text` without invisible marks and vowel signs."""
    return _INVISIBLE.sub("", text)


def plain(typed_text: str) -> str:
    """`typed_text` with digits, separators and spaces in one form."""
    return typed_text.translate(_PLAIN)


def arabic(word: str) -> str:
    """A regex for an Arabic word that accepts its common spellings: any
    form of alef, ta marbuta written as ha, and alef maqsura for ya."""
    out = []
    for char in word:
        if char in "اأإآٱ":
            out.append("[اأإآٱ]")
        elif char in "ةه":
            out.append("[ةه]")
        elif char in "يى":
            out.append("[يى]")
        elif char == " ":
            out.append(r"\s+")
        else:
            out.append(re.escape(char))
    return "".join(out)


def alternation(words: list[str] | tuple[str, ...], *, arabic_script: bool = False) -> str:
    """A regex group matching any of `words`, longest first so that a short
    word never wins over a longer one it begins."""
    ordered = sorted(set(words), key=len, reverse=True)
    parts = [arabic(w) if arabic_script else re.escape(w) for w in ordered]
    return "(?:" + "|".join(parts) + ")"


# ── digits ─────────────────────────────────────────────────────────────

# 1,299 / 1,299.50 / 4.500 / 99.99 / 12. In `plain`, `.` is always the
# decimal point and `,` always groups thousands, whatever script the text
# was written in.
NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"


def read_number(token: str) -> Decimal:
    return Decimal(token.replace(",", ""))


# ── number words ───────────────────────────────────────────────────────

_AR_UNITS = {
    "واحد": 1, "واحدة": 1, "أحد": 1, "إحدى": 1,
    "اثنان": 2, "اثنين": 2, "اثنتان": 2, "اثنتين": 2, "اثنا": 2, "اثني": 2,
    "ثلاثة": 3, "ثلاث": 3, "أربعة": 4, "أربع": 4, "خمسة": 5, "خمس": 5,
    "ستة": 6, "ست": 6, "سبعة": 7, "سبع": 7, "ثمانية": 8, "ثماني": 8, "ثمان": 8,
    "تسعة": 9, "تسع": 9, "عشرة": 10, "عشر": 10,
}  # fmt: skip
_AR_TENS = {
    "عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30, "أربعون": 40, "أربعين": 40,
    "خمسون": 50, "خمسين": 50, "ستون": 60, "ستين": 60, "سبعون": 70, "سبعين": 70,
    "ثمانون": 80, "ثمانين": 80, "تسعون": 90, "تسعين": 90,
}  # fmt: skip
_AR_HUNDREDS = {
    "مئة": 100, "مائة": 100, "مية": 100,
    "مئتان": 200, "مئتين": 200, "مائتان": 200, "مائتين": 200,
    "ثلاثمئة": 300, "ثلاثمائة": 300, "أربعمئة": 400, "أربعمائة": 400,
    "خمسمئة": 500, "خمسمائة": 500, "ستمئة": 600, "ستمائة": 600,
    "سبعمئة": 700, "سبعمائة": 700, "ثمانمئة": 800, "ثمانمائة": 800,
    "تسعمئة": 900, "تسعمائة": 900,
}  # fmt: skip
_AR_SCALES = {
    "ألف": 1_000, "ألفان": 2_000, "ألفين": 2_000, "آلاف": 1_000,
    "مليون": 1_000_000, "مليونان": 2_000_000, "مليونين": 2_000_000, "ملايين": 1_000_000,
    "مليار": 1_000_000_000, "مليارات": 1_000_000_000,
}  # fmt: skip
_AR_FRACTIONS = {"نصف": Decimal("0.5"), "ربع": Decimal("0.25")}

_EN_UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}  # fmt: skip
_EN_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}  # fmt: skip
_EN_SCALES = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
_EN_FRACTIONS = {"half": Decimal("0.5"), "quarter": Decimal("0.25")}


_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})


def fold(word: str) -> str:
    """One spelling per Arabic word and one case per Latin word, with single
    spaces, for dictionary lookup of text matched by `arabic()`."""
    return " ".join(word.translate(_FOLD).lower().split())


def _folded(table: dict[str, int]) -> dict[str, int]:
    return {fold(word): value for word, value in table.items()}


_AR_UNITS_F = _folded(_AR_UNITS)
_AR_TENS_F = _folded(_AR_TENS)
_AR_HUNDREDS_F = _folded(_AR_HUNDREDS)
_AR_SCALES_F = _folded(_AR_SCALES)
_AR_FRACTIONS_F = {fold(word): value for word, value in _AR_FRACTIONS.items()}
_AR_PLURAL_SCALES = {fold("آلاف"), fold("ملايين"), fold("مليارات")}
_AR_ALL = {**_AR_UNITS_F, **_AR_TENS_F, **_AR_HUNDREDS_F, **_AR_SCALES_F} | dict.fromkeys(
    _AR_FRACTIONS_F, 0
)

# A scale word after digits: "1.5 million", "١٫٥ ألف".
SCALE_WORD = alternation(list(_AR_SCALES), arabic_script=True) + "|" + alternation(list(_EN_SCALES))

_AR_WORD = alternation(
    [*_AR_UNITS, *_AR_TENS, *_AR_HUNDREDS, *_AR_SCALES, *_AR_FRACTIONS], arabic_script=True
)
# One or more Arabic number words, each optionally joined by "و" (and) and
# optionally ending in the accusative alef ("ألفاً" loses its vowel sign in
# `typed` and arrives as "ألفا").
ARABIC_NUMBER_WORDS = rf"(?<![ء-ي])و?{_AR_WORD}ا?(?:\s+و?{_AR_WORD}ا?)*(?![ء-ي])"

_EN_WORD = alternation([*_EN_UNITS, *_EN_TENS, *_EN_SCALES, *_EN_FRACTIONS, "hundred", "a", "an"])
ENGLISH_NUMBER_WORDS = rf"\b{_EN_WORD}(?:(?:\s+and\s+|[\s-]+){_EN_WORD})*\b"


def scale_value(word: str) -> int:
    """1000 for "thousand" or "ألف", and so on."""
    lowered = word.lower()
    if lowered in _EN_SCALES:
        return _EN_SCALES[lowered]
    return _AR_SCALES_F[fold(word)]


def _ar_token(token: str) -> str | None:
    """`token` as a dictionary key, or None if it is not a number word."""
    for candidate in (token, token[1:] if token.startswith("و") else None):
        if not candidate:
            continue
        folded = fold(candidate)
        if folded in _AR_ALL:
            return folded
        if folded.endswith("ا") and folded[:-1] in _AR_ALL:
            return folded[:-1]
    return None


def read_arabic_words(phrase: str) -> Decimal | None:
    """The value of a run of Arabic number words, e.g. "ألف وخمسمئة" = 1500.

    Returns None if any word in the run is not a number word.
    """
    total = Decimal(0)
    current = Decimal(0)
    previous_unit = False
    for raw in phrase.split():
        token = _ar_token(raw)
        if token is None:
            return None
        if token in _AR_FRACTIONS_F:
            current += _AR_FRACTIONS_F[token]
            previous_unit = False
        elif token in _AR_SCALES_F:
            scale = _AR_SCALES_F[token]
            if token in _AR_PLURAL_SCALES or current:
                total += (current or 1) * scale
            else:
                total += scale
            current = Decimal(0)
            previous_unit = False
        elif token in _AR_HUNDREDS_F:
            value = _AR_HUNDREDS_F[token]
            if value == 100 and previous_unit and 3 <= current <= 9:
                current *= 100  # "ثلاث مئة"
            else:
                current += value
            previous_unit = False
        elif token in _AR_TENS_F:
            current += _AR_TENS_F[token]
            previous_unit = False
        else:
            value = _AR_UNITS_F[token]
            if value == 10 and previous_unit and not raw.startswith("و"):
                current += 10  # "ثلاثة عشر"
                previous_unit = False
            else:
                current += value
                previous_unit = value < 10
    return total + current


def read_english_words(phrase: str) -> Decimal | None:
    """The value of a run of English number words, e.g. "one thousand five
    hundred" = 1500. Returns None if the run holds no number."""
    total = Decimal(0)
    current = Decimal(0)
    seen = False
    for token in re.split(r"[\s-]+", phrase.lower()):
        if token in ("and", ""):
            continue
        if token in ("a", "an"):
            if not current:
                current = Decimal(1)
        elif token in _EN_FRACTIONS:
            current += _EN_FRACTIONS[token]
            seen = True
        elif token in _EN_UNITS:
            current += _EN_UNITS[token]
            seen = True
        elif token in _EN_TENS:
            current += _EN_TENS[token]
            seen = True
        elif token == "hundred":
            current = (current or Decimal(1)) * 100
            seen = True
        elif token in _EN_SCALES:
            total += (current or Decimal(1)) * _EN_SCALES[token]
            current = Decimal(0)
            seen = True
        else:
            return None
    return total + current if seen else None
