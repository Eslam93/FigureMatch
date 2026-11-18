# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Finds the six kinds of figure in one text, English or Arabic.

Each figure is read into a value that does not depend on how it was
written, so `١٬٢٩٩ ر.س` and `SAR 1,299` read the same. What counts as the
same figure is decided in `compare.py`; this module only reads.

The kinds are found in a fixed order: links, dates, prices, percentages,
promo codes, phone numbers. Text one kind has claimed is hidden from the
kinds after it, so the `42` in a link is not also read as a price.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from hijridate import Hijri

from matcher import text as t

KINDS = ("price", "percentage", "date", "phone", "link", "promo_code")

_AR_LETTER = "ء-ي"


@dataclass(frozen=True)
class Figure:
    kind: str
    start: int
    end: int
    text: str  # as written
    value: tuple[Any, ...]  # as read; compared by compare.same()


class _Text:
    """One text in its two views, with a record of what has been claimed."""

    def __init__(self, raw: str) -> None:
        self.typed = t.typed(raw)
        self.plain = t.plain(self.typed)

    def claim(self, start: int, end: int) -> None:
        self.plain = self.plain[:start] + t.MASK * (end - start) + self.plain[end:]

    def figure(self, kind: str, start: int, end: int, value: tuple[Any, ...]) -> Figure:
        return Figure(kind=kind, start=start, end=end, text=self.typed[start:end], value=value)


# ── links ──────────────────────────────────────────────────────────────

_TLDS = (
    "com|net|org|io|co|me|info|gov|edu|app|shop|store|online|site|biz|tv|travel|bank|ai|dev|"
    "ae|sa|eg|qa|kw|bh|om|jo|lb|ma|tn|dz|iq|ly|sd|ye|ps|sy|uk|us"
)
_URL_BODY = r"""[^\s<>"'،؛]"""
_LINK = re.compile(
    rf"""(?ix)
    (?<![\w@./-])
    (?: https?://{_URL_BODY}+
      | www\.{_URL_BODY}+
      | (?:[a-z0-9-]+\.)+(?:{_TLDS})\b(?:/{_URL_BODY}*)?
    )"""
)
_LINK_TRAILING = ".,;:!?)]}»\"'؟"
_LANGUAGE_PARAMS = {"lang", "language", "locale", "lng", "hl", "culture"}
_LANGUAGE_WORDS = {"en": "en", "english": "en", "ar": "ar", "arabic": "ar"}
_LANGUAGE_SEGMENT = re.compile(r"(?i)^(?:(en|ar)(?:[-_][a-z]{2,3})?|[a-z]{2,3}[-_](en|ar))$")


def _language_of(token: str) -> str | None:
    lowered = token.lower()
    if lowered in _LANGUAGE_WORDS:
        return _LANGUAGE_WORDS[lowered]
    match = _LANGUAGE_SEGMENT.match(lowered)
    return (match.group(1) or match.group(2)) if match else None


def read_link(url: str) -> tuple[str, tuple[str, ...], tuple[tuple[str, str], ...], str | None]:
    """(host, path, query, language) with the language marker taken out of
    the first three. `language` is "en", "ar", None for no marker, or
    "mixed" if the link carries markers that disagree."""
    parts = urlsplit(url if re.match(r"(?i)https?://", url) else f"http://{url}")
    languages: set[str] = set()
    labels = (parts.hostname or "").lower().split(".")
    if labels and labels[0] == "www":
        labels = labels[1:]
    if len(labels) > 2 and labels[0] in _LANGUAGE_WORDS:
        languages.add(_LANGUAGE_WORDS[labels[0]])
        labels = labels[1:]
    path = []
    for segment in parts.path.split("/"):
        language = _language_of(segment) if segment else None
        if language:
            languages.add(language)
        elif segment:
            path.append(segment)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        language = _language_of(value) if key.lower() in _LANGUAGE_PARAMS else None
        if language:
            languages.add(language)
        else:
            query.append((key, value))
    marker = None if not languages else languages.pop() if len(languages) == 1 else "mixed"
    return ".".join(labels), tuple(path), tuple(sorted(query)), marker


def _links(doc: _Text) -> list[Figure]:
    found = []
    for match in _LINK.finditer(doc.plain):
        url = match.group(0).rstrip(_LINK_TRAILING)
        end = match.start() + len(url)
        found.append(doc.figure("link", match.start(), end, read_link(url)))
    for figure in found:
        doc.claim(figure.start, figure.end)
    return found


# ── dates ──────────────────────────────────────────────────────────────

_EN_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4,
    "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10, "november": 11,
    "nov": 11, "december": 12, "dec": 12,
}  # fmt: skip
_AR_MONTHS = {
    # The names used in Egypt and the Gulf.
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "مايو": 5, "يونيو": 6, "يونيه": 6,
    "يوليو": 7, "يوليه": 7, "أغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "نوفمبر": 11,
    "ديسمبر": 12,
    # The Levantine names.
    "كانون الثاني": 1, "شباط": 2, "آذار": 3, "نيسان": 4, "أيار": 5, "حزيران": 6,
    "تموز": 7, "آب": 8, "أيلول": 9, "تشرين الأول": 10, "تشرين الثاني": 11,
    "كانون الأول": 12,
    # The Maghrebi names.
    "جانفي": 1, "فيفري": 2, "أفريل": 4, "ماي": 5, "جوان": 6, "جويلية": 7, "أوت": 8,
    "يوليوز": 7, "غشت": 8, "شتنبر": 9, "نونبر": 11, "دجنبر": 12,
}  # fmt: skip
_HIJRI_MONTHS = {
    "محرم": 1, "صفر": 2, "ربيع الأول": 3, "ربيع الآخر": 4, "ربيع الثاني": 4,
    "جمادى الأولى": 5, "جمادى الآخرة": 6, "جمادى الثانية": 6, "رجب": 7, "شعبان": 8,
    "رمضان": 9, "شوال": 10, "ذو القعدة": 11, "ذي القعدة": 11, "ذو الحجة": 12,
    "ذي الحجة": 12,
    "muharram": 1, "safar": 2, "rajab": 7, "shaban": 8, "sha'ban": 8, "ramadan": 9,
    "ramadhan": 9, "shawwal": 10,
}  # fmt: skip

_MONTH_NUMBER = {t.fold(name): number for name, number in {**_EN_MONTHS, **_AR_MONTHS}.items()}
_HIJRI_NUMBER = {t.fold(name): number for name, number in _HIJRI_MONTHS.items()}

_LATIN_MONTH_NAMES = [*_EN_MONTHS, *(n for n in _HIJRI_MONTHS if n.isascii())]
_ARABIC_MONTH_NAMES = [*_AR_MONTHS, *(n for n in _HIJRI_MONTHS if not n.isascii())]
_MONTH = (
    rf"(?:(?<![A-Za-z]){t.alternation(_LATIN_MONTH_NAMES)}\.?(?![A-Za-z])"
    rf"|(?<![{_AR_LETTER}]){t.alternation(_ARABIC_MONTH_NAMES, arabic_script=True)}"
    rf"(?![{_AR_LETTER}]))"
)
_ORDINAL = r"(?:st|nd|rd|th)?"
_YEAR = r"(?:\s*,?\s*(?P<year>\d{4})(?!\d))?"

# 31 December 2026 / ٣١ ديسمبر ٢٠٢٦ / 22 Rajab 1448
_DAY_MONTH = re.compile(
    rf"(?i)(?<![\d/.-])(?P<day>\d{{1,2}}){_ORDINAL}\s*(?:of\s+|من\s+)?(?P<month>{_MONTH}){_YEAR}"
)
# December 31, 2026 / December 1-15, 2026
_MONTH_DAY = re.compile(
    rf"(?i)(?P<month>{_MONTH})\s+(?P<day>\d{{1,2}}){_ORDINAL}"
    rf"(?:\s*(?:-|to)\s*(?P<day2>\d{{1,2}}){_ORDINAL})?(?!\d){_YEAR}"
)
# March 2027: a month with no day
_MONTH_YEAR = re.compile(rf"(?i)(?P<month>{_MONTH})\s*,?\s*(?P<year>\d{{4}})(?!\d)")
# "1 to", "١ إلى", "1-" directly before a day-and-month date: the first day
# of a range that shares the month and year.
_RANGE_START = re.compile(
    rf"(?i)(?<![\d/.-])(?P<day>\d{{1,2}}){_ORDINAL}\s*"
    rf"(?:-|to|till|until|through|and|&|{t.arabic('إلى')}|حتى|لغاية|و)\s*$"
)
# 30/11/2026, 2027/04/03, 30-11-26
_NUMERIC_DATE = re.compile(r"(?<![\d/.-])(\d{1,4})([/.-])(\d{1,2})\2(\d{1,4})(?![\d/.-])")


def _month_of(name: str) -> tuple[int, bool] | None:
    """(month number, is it a Hijri month). None for a lowercase "may",
    which is the verb far more often than the month."""
    if name == "may":
        return None
    key = t.fold(name.rstrip("."))
    if key in _HIJRI_NUMBER:
        return _HIJRI_NUMBER[key], True
    return _MONTH_NUMBER[key], False


def _date_value(year: int | None, month: int, day: int | None, *, hijri: bool) -> tuple[Any, ...]:
    """(year, month, day) in the Gregorian calendar. A Hijri date with its
    year is converted by the Umm al-Qura calendar; one without a year
    cannot be, and is kept apart so it never equals a Gregorian date."""
    if not hijri:
        return (year, month, day)
    if year is None or day is None:
        return ("hijri", year, month, day)
    try:
        converted = Hijri(year, month, day).to_gregorian()
    except (ValueError, OverflowError):
        return ("hijri", year, month, day)
    return (converted.year, converted.month, converted.day)


def _numeric_date(first: str, second: str, third: str) -> tuple[Any, ...] | None:
    if len(first) == 4:
        year, month, day = int(first), int(second), int(third)
    elif len(third) in (2, 4):
        day, month, year = int(first), int(second), int(third)
        if len(third) == 2:
            year += 2000
        if month > 12 >= day:  # written month first
            day, month = month, day
    else:
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    if 1300 <= year <= 1500:
        return _date_value(year, month, day, hijri=True)
    if not 1900 <= year <= 2100:
        return None
    try:
        date(year, month, day)
    except ValueError:
        return None
    return (year, month, day)


def _dates(doc: _Text) -> list[Figure]:
    found: list[Figure] = []

    def taken(start: int, end: int) -> bool:
        return any(start < f.end and f.start < end for f in found)

    for match in _NUMERIC_DATE.finditer(doc.plain):
        value = _numeric_date(match.group(1), match.group(3), match.group(4))
        if value is not None:
            found.append(doc.figure("date", match.start(), match.end(), value))

    for match in _DAY_MONTH.finditer(doc.plain):
        named = _month_of(match.group("month"))
        if named is None or taken(match.start(), match.end()):
            continue
        month, hijri = named
        year = int(match.group("year")) if match.group("year") else None
        day = int(match.group("day"))
        if not 1 <= day <= 31:
            continue
        lead = _RANGE_START.search(doc.plain[: match.start()])
        if lead and 1 <= int(lead.group("day")) <= 31 and not taken(lead.start(), lead.end()):
            first = _date_value(year, month, int(lead.group("day")), hijri=hijri)
            found.append(doc.figure("date", lead.start(), lead.end("day"), first))
        found.append(
            doc.figure(
                "date", match.start(), match.end(), _date_value(year, month, day, hijri=hijri)
            )
        )

    for match in _MONTH_DAY.finditer(doc.plain):
        named = _month_of(match.group("month"))
        if named is None or taken(match.start(), match.end()):
            continue
        month, hijri = named
        year = int(match.group("year")) if match.group("year") else None
        days = [int(match.group("day"))]
        if match.group("day2"):
            days.append(int(match.group("day2")))
        if not all(1 <= day <= 31 for day in days):
            continue
        for day in days:
            found.append(
                doc.figure(
                    "date",
                    match.start(),
                    match.end(),
                    _date_value(year, month, day, hijri=hijri),
                )
            )

    for match in _MONTH_YEAR.finditer(doc.plain):
        named = _month_of(match.group("month"))
        if named is None or taken(match.start(), match.end()):
            continue
        month, hijri = named
        value = _date_value(int(match.group("year")), month, None, hijri=hijri)
        found.append(doc.figure("date", match.start(), match.end(), value))

    found.sort(key=lambda f: (f.start, f.end))
    for figure in found:
        doc.claim(figure.start, figure.end)
    return found


# ── amounts: digits or number words, used by prices and percentages ────


@dataclass(frozen=True)
class _Amount:
    start: int
    end: int
    value: Decimal


_DIGITS_AMOUNT = re.compile(
    rf"(?<![\d.,])(?P<number>{t.NUMBER})(?![\d])"
    rf"(?:\s*(?P<scale>{t.SCALE_WORD})(?![A-Za-z{_AR_LETTER}])|(?P<suffix>[kK]|M|mn|bn)(?![A-Za-z]))?"
)
_SUFFIX_SCALE = {"k": 1_000, "K": 1_000, "M": 1_000_000, "mn": 1_000_000, "bn": 1_000_000_000}
_ARABIC_WORDS_AMOUNT = re.compile(t.ARABIC_NUMBER_WORDS)
_ENGLISH_WORDS_AMOUNT = re.compile(rf"(?i){t.ENGLISH_NUMBER_WORDS}")


def _amounts(doc: _Text) -> list[_Amount]:
    found = []
    for match in _DIGITS_AMOUNT.finditer(doc.plain):
        value = t.read_number(match.group("number"))
        if match.group("scale"):
            value *= t.scale_value(match.group("scale"))
        elif match.group("suffix"):
            value *= _SUFFIX_SCALE[match.group("suffix")]
        found.append(_Amount(match.start(), match.end(), value))

    def free(start: int, end: int) -> bool:
        return not any(start < a.end and a.start < end for a in found)

    for pattern, read in (
        (_ARABIC_WORDS_AMOUNT, t.read_arabic_words),
        (_ENGLISH_WORDS_AMOUNT, t.read_english_words),
    ):
        for match in pattern.finditer(doc.plain):
            words = read(match.group(0))
            if words and free(match.start(), match.end()):
                found.append(_Amount(match.start(), match.end(), words))
    return sorted(found, key=lambda a: a.start)


def _adjacent(doc: _Text, left_end: int, right_start: int) -> bool:
    """True if nothing but up to two spaces lies between two positions."""
    gap = doc.plain[left_end:right_start]
    return len(gap) <= 2 and not gap.strip()


# ── prices ─────────────────────────────────────────────────────────────

# A currency word that could be one of several currencies reads as a
# family, written with a leading "~". compare.same() treats a family as
# compatible with each of its members.
CURRENCY_FAMILIES = {
    "~RIYAL": {"SAR", "QAR", "OMR", "YER"},
    "~DINAR": {"KWD", "BHD", "JOD", "IQD", "TND", "DZD", "LYD"},
    "~POUND": {"EGP", "GBP", "SDG", "LBP", "SYP"},
    "~DIRHAM": {"AED", "MAD"},
}

_LATIN_CODES = {
    "AED": "AED", "Dhs": "AED", "DHS": "AED", "Dh": "AED", "DH": "AED",
    "SAR": "SAR", "SR": "SAR", "QAR": "QAR", "QR": "QAR", "OMR": "OMR",
    "KWD": "KWD", "KD": "KWD", "BHD": "BHD", "BD": "BHD", "JOD": "JOD", "JD": "JOD",
    "EGP": "EGP", "LE": "EGP", "USD": "USD", "EUR": "EUR", "GBP": "GBP",
}  # fmt: skip
_SYMBOLS = {"US$": "USD", "$": "USD", "€": "EUR", "£": "GBP"}
_ENGLISH_CURRENCY_WORDS = {
    "uae dirham": "AED", "emirati dirham": "AED", "dirham": "~DIRHAM",
    "saudi riyal": "SAR", "qatari riyal": "QAR", "omani rial": "OMR", "omani riyal": "OMR",
    "riyal": "~RIYAL", "rial": "~RIYAL",
    "kuwaiti dinar": "KWD", "bahraini dinar": "BHD", "jordanian dinar": "JOD",
    "dinar": "~DINAR",
    "egyptian pound": "EGP", "british pound": "GBP", "pound sterling": "GBP",
    "pound": "~POUND",
    "us dollar": "USD", "dollar": "USD", "euro": "EUR",
}  # fmt: skip
_ARABIC_ABBREVIATIONS = {
    "د.إ": "AED", "ر.س": "SAR", "ر.ق": "QAR", "ر.ع": "OMR", "د.ك": "KWD",
    "د.ب": "BHD", "د.أ": "JOD", "ج.م": "EGP",
}  # fmt: skip
# Singular, accusative and plural of each Arabic currency noun.
_ARABIC_NOUNS = {
    "درهم": "~DIRHAM", "درهما": "~DIRHAM", "دراهم": "~DIRHAM",
    "ريال": "~RIYAL", "ريالا": "~RIYAL", "ريالات": "~RIYAL",
    "دينار": "~DINAR", "دينارا": "~DINAR", "دنانير": "~DINAR",
    "جنيه": "~POUND", "جنيها": "~POUND", "جنيهات": "~POUND",
    "دولار": "USD", "دولارا": "USD", "دولارات": "USD",
    "يورو": "EUR",
}  # fmt: skip
# The adjective that settles which riyal, dinar, pound or dirham is meant.
_ARABIC_NATIONALITIES = {
    ("~DIRHAM", "إماراتي"): "AED", ("~DIRHAM", "مغربي"): "MAD",
    ("~RIYAL", "سعودي"): "SAR", ("~RIYAL", "قطري"): "QAR", ("~RIYAL", "عماني"): "OMR",
    ("~RIYAL", "يمني"): "YER",
    ("~DINAR", "كويتي"): "KWD", ("~DINAR", "بحريني"): "BHD", ("~DINAR", "أردني"): "JOD",
    ("~DINAR", "عراقي"): "IQD",
    ("~POUND", "مصري"): "EGP", ("~POUND", "إسترليني"): "GBP", ("~POUND", "استرليني"): "GBP",
    ("USD", "أمريكي"): "USD",
}  # fmt: skip
_NATIONALITY_BY_KEY = {
    (family, t.fold(adjective)): code for (family, adjective), code in _ARABIC_NATIONALITIES.items()
}
_NOUN_BY_KEY = {t.fold(noun): code for noun, code in _ARABIC_NOUNS.items()}
_ADJECTIVES = sorted({adjective for _, adjective in _ARABIC_NATIONALITIES})

_CURRENCY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(rf"(?<![A-Za-z]){t.alternation(list(_LATIN_CODES))}\.?(?![A-Za-z])"), "code"),
    (re.compile(t.alternation(list(_SYMBOLS))), "symbol"),
    (
        re.compile(
            rf"(?i)(?<![A-Za-z]){t.alternation(list(_ENGLISH_CURRENCY_WORDS))}s?(?![A-Za-z])"
        ),
        "english",
    ),
    (
        re.compile(
            "(?:"
            + "|".join(
                rf"{re.escape(a.split('.')[0])}\.\s?{re.escape(a.split('.')[1])}\.?"
                for a in _ARABIC_ABBREVIATIONS
            )
            + ")"
        ),
        "abbreviation",
    ),
    (
        re.compile(
            rf"(?<![{_AR_LETTER}])"
            rf"(?P<noun>{t.alternation(list(_ARABIC_NOUNS), arabic_script=True)})"
            rf"(?:\s+(?P<adjective>{t.alternation(_ADJECTIVES, arabic_script=True)})[اةه]?)?"
            rf"(?![{_AR_LETTER}])"
        ),
        "arabic",
    ),
)


@dataclass(frozen=True)
class _Currency:
    start: int
    end: int
    code: str
    number_first: bool  # the amount is usually written before it


def _read_currency(match: re.Match[str], style: str) -> str:
    found = match.group(0)
    if style == "code":
        return _LATIN_CODES[found.rstrip(".")]
    if style == "symbol":
        return _SYMBOLS[found]
    if style == "english":
        lowered = " ".join(found.lower().split())
        return _ENGLISH_CURRENCY_WORDS.get(lowered) or _ENGLISH_CURRENCY_WORDS[lowered[:-1]]
    if style == "abbreviation":
        letters = [c for c in found if c not in ". "]
        return _ARABIC_ABBREVIATIONS[f"{letters[0]}.{letters[1]}"]
    family = _NOUN_BY_KEY[t.fold(match.group("noun"))]
    if match.group("adjective"):
        return _NATIONALITY_BY_KEY.get((family, t.fold(match.group("adjective"))), family)
    return family


def _currencies(doc: _Text) -> list[_Currency]:
    found: list[_Currency] = []
    for pattern, style in _CURRENCY_PATTERNS:
        for match in pattern.finditer(doc.plain):
            if any(match.start() < c.end and c.start < match.end() for c in found):
                continue
            found.append(
                _Currency(
                    start=match.start(),
                    end=match.end(),
                    code=_read_currency(match, style),
                    number_first=style in ("abbreviation", "arabic", "english"),
                )
            )
    return sorted(found, key=lambda c: c.start)


def _prices(doc: _Text) -> list[Figure]:
    amounts = _amounts(doc)
    used: set[int] = set()
    found = []
    for currency in _currencies(doc):
        before = next(
            (
                i
                for i, a in enumerate(amounts)
                if i not in used
                and a.end <= currency.start
                and _adjacent(doc, a.end, currency.start)
            ),
            None,
        )
        after = next(
            (
                i
                for i, a in enumerate(amounts)
                if i not in used
                and a.start >= currency.end
                and _adjacent(doc, currency.end, a.start)
            ),
            None,
        )
        order = (before, after) if currency.number_first else (after, before)
        chosen = next((i for i in order if i is not None), None)
        if chosen is None:
            continue
        used.add(chosen)
        amount = amounts[chosen]
        start, end = min(amount.start, currency.start), max(amount.end, currency.end)
        found.append(doc.figure("price", start, end, (amount.value.normalize(), currency.code)))
    found.sort(key=lambda f: f.start)
    for figure in found:
        doc.claim(figure.start, figure.end)
    return found


# ── percentages ────────────────────────────────────────────────────────

_PERCENT_SIGN = re.compile(
    rf"(?:(?<![\d.,])(?P<before>{t.NUMBER})\s?%)|(?:%\s?(?P<after>{t.NUMBER})(?![\d]))"
)
_PERCENT_WORD = re.compile(
    rf"(?i)(?:per\s?cent|pct)(?![A-Za-z])|{t.arabic('بالمئة')}|{t.arabic('بالمائة')}|بالمية"
    rf"|{t.arabic('في المئة')}|{t.arabic('في المائة')}"
)
# Phrases that state a rate without a number.
_PERCENT_PHRASES = {
    "half price": 50, "half off": 50, "interest-free": 0, "interest free": 0,
    "zero interest": 0,
    "نصف السعر": 50, "بنصف السعر": 50, "نصف الثمن": 50, "نصف القيمة": 50,
    "بدون فوائد": 0, "بدون فائدة": 0, "بلا فوائد": 0, "بلا فائدة": 0, "دون فوائد": 0,
}  # fmt: skip
_PHRASE_VALUE = {t.fold(phrase): value for phrase, value in _PERCENT_PHRASES.items()}
_PERCENT_PHRASE = re.compile(
    "(?i)"
    + t.alternation([p for p in _PERCENT_PHRASES if p.isascii()])
    + "|"
    + t.alternation([p for p in _PERCENT_PHRASES if not p.isascii()], arabic_script=True)
)


def _percentages(doc: _Text) -> list[Figure]:
    found = []
    for match in _PERCENT_SIGN.finditer(doc.plain):
        number = match.group("before") or match.group("after")
        value = (t.read_number(number).normalize(),)
        found.append(doc.figure("percentage", match.start(), match.end(), value))
    for figure in found:
        doc.claim(figure.start, figure.end)

    amounts = _amounts(doc)
    for match in _PERCENT_WORD.finditer(doc.plain):
        amount = next(
            (a for a in amounts if a.end <= match.start() and _adjacent(doc, a.end, match.start())),
            None,
        )
        if amount is not None:
            value = (amount.value.normalize(),)
            found.append(doc.figure("percentage", amount.start, match.end(), value))
    for match in _PERCENT_PHRASE.finditer(doc.plain):
        value = (Decimal(_PHRASE_VALUE[t.fold(match.group(0))]),)
        found.append(doc.figure("percentage", match.start(), match.end(), value))

    found.sort(key=lambda f: f.start)
    for figure in found:
        doc.claim(figure.start, figure.end)
    return found


# ── promo codes ────────────────────────────────────────────────────────

_CODE_CHARS = "A-Za-z0-9_\\-"
_CODE_TOKEN = re.compile(
    rf"(?<![{_CODE_CHARS}])[A-Za-z0-9][{_CODE_CHARS}]{{2,24}}(?![{_CODE_CHARS}])"
)
_QUOTES = "\"'“”‘’«»"
# A word that announces a code, then nothing but a separator or a quote.
_CODE_CUE = re.compile(
    rf"(?i)(?:(?<![A-Za-z])(?:promo(?:tional)?\s+code|coupon(?:\s+code)?|voucher(?:\s+code)?"
    rf"|discount\s+code|code)"
    rf"|(?:ال)?(?:رمز|كود)(?:\s+(?:العرض|الخصم|الترويجي|القسيم[ةه]|الكوبون))?"
    rf"|(?:ال)?كوبون|(?:ال)?قسيم[ةه])\s*[:\-]?\s*[{_QUOTES}]?$"
)


def _looks_like_a_code(token: str, *, announced: bool) -> bool:
    letters = [c for c in token if c.isalpha()]
    has_digit = any(c.isdigit() for c in token)
    if not letters:
        return False
    all_caps = all(c.isupper() for c in letters)
    if announced:
        return has_digit or (all_caps and len(letters) >= 3)
    return all_caps and len(letters) >= 3 and has_digit


def _promo_codes(doc: _Text) -> list[Figure]:
    found = []
    for match in _CODE_TOKEN.finditer(doc.plain):
        token = match.group(0).rstrip("-_")
        announced = bool(_CODE_CUE.search(doc.plain[max(0, match.start() - 40) : match.start()]))
        if not _looks_like_a_code(token, announced=announced):
            continue
        end = match.start() + len(token)
        # Compared as typed: the digits keep the script they were written in.
        value = (doc.typed[match.start() : end].casefold(),)
        found.append(doc.figure("promo_code", match.start(), end, value))
    for figure in found:
        doc.claim(figure.start, figure.end)
    return found


# ── phone numbers ──────────────────────────────────────────────────────

_PHONE = re.compile(r"(?<![\w+])(?P<plus>\+)?\(?\d[\d\s\-.()]{3,}\d(?P<trailing_plus>\+)?(?![\w])")
_PHONE_CUE = re.compile(
    rf"(?i)(?:call|phone|tel|telephone|mobile|hotline|helpline|whatsapp|contact|dial|fax|sms"
    rf"|toll[\s-]?free|customer\s+(?:care|service)|call\s+cent(?:er|re)"
    rf"|{t.arabic('اتصل')}|{t.arabic('للاتصال')}|هاتف|تليفون|جوال|موبايل|{t.arabic('واتساب')}"
    rf"|{t.arabic('واتس اب')}|{t.arabic('الخط الساخن')}|{t.arabic('خدمة العملاء')}"
    rf"|{t.arabic('مركز الاتصال')}|{t.arabic('للاستفسار')}|تواصل|راسلنا|رقم)"
)
_COUNTRY_CODES = (
    "971", "966", "974", "973", "965", "968", "962", "961", "964", "963", "970", "967",
    "212", "213", "216", "218", "249", "20", "44", "33", "49", "90", "91", "92", "1",
)  # fmt: skip


def read_phone(digits: str, *, international: bool) -> tuple[str | None, str]:
    """(country code, national number). The country code is None when the
    number was written without an international prefix."""
    if digits.startswith("00"):
        digits, international = digits[2:], True
    if international:
        for code in _COUNTRY_CODES:
            if digits.startswith(code):
                return code, digits[len(code) :].lstrip("0")
        return "", digits
    if digits.startswith("0") and len(digits) >= 8:
        digits = digits[1:]  # the trunk zero of a national number
    return None, digits


def _phones(doc: _Text) -> list[Figure]:
    found = []
    for match in _PHONE.finditer(doc.plain):
        digits = re.sub(r"\D", "", match.group(0))
        if not 5 <= len(digits) <= 15:
            continue
        international = bool(match.group("plus") or match.group("trailing_plus"))
        announced = bool(_PHONE_CUE.search(doc.plain[max(0, match.start() - 40) : match.start()]))
        if not (international or digits.startswith("00") or announced):
            continue
        value = read_phone(digits, international=international)
        found.append(doc.figure("phone", match.start(), match.end(), value))
    for figure in found:
        doc.claim(figure.start, figure.end)
    return found


# ── all six ────────────────────────────────────────────────────────────


def extract(text: str) -> dict[str, list[Figure]]:
    """Every figure in `text`, by kind, in the order written."""
    doc = _Text(text)
    links = _links(doc)
    dates = _dates(doc)
    prices = _prices(doc)
    percentages = _percentages(doc)
    promo_codes = _promo_codes(doc)
    phones = _phones(doc)
    return {
        "price": prices,
        "percentage": percentages,
        "date": dates,
        "phone": phones,
        "link": links,
        "promo_code": promo_codes,
    }
