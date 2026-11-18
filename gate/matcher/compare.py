# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Pairs the figures of an English text with those of its Arabic version.

For each kind of figure the two sequences are aligned in the order they
were written: the longest run of equal figures that keeps both orders is
paired, and whatever is left over on either side is a finding. A kind is
a match only when nothing is left over.

Order matters on purpose. The labelling rules pair figures by what they
are attached to, which a matcher that reads no words cannot see. Order is
the nearest thing it can see: two rates swapped between flights and
hotels leave both versions with the same set of rates and a different
order. Two figures swapped without changing the order stay invisible.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from matcher.extract import CURRENCY_FAMILIES, KINDS, Figure, extract


def _same_currency(a: str, b: str) -> bool:
    if a == b:
        return True
    for family, members in CURRENCY_FAMILIES.items():
        if (a == family and b in members) or (b == family and a in members):
            return True
    return False


def _same_price(en: Figure, ar: Figure) -> bool:
    return en.value[0] == ar.value[0] and _same_currency(en.value[1], ar.value[1])


def _same_phone(en: Figure, ar: Figure) -> bool:
    (code_a, number_a), (code_b, number_b) = en.value, ar.value
    if code_a is not None and code_b is not None:
        return bool(code_a == code_b and number_a == number_b)
    if code_a is None and code_b is None:
        return bool(number_a == number_b)
    # One was written with its country code and one without: equal if the
    # national numbers agree, however the shorter form spelt its prefix.
    code, national, local = (
        (code_a, number_a, number_b) if code_a is not None else (code_b, number_b, number_a)
    )
    return local in (national, f"{code}{national}", f"0{national}")


def _same_link(en: Figure, ar: Figure) -> bool:
    """Same target once the language marker is set aside, and each version's
    marker, if it has one, names its own language."""
    return bool(en.value[:3] == ar.value[:3] and en.value[3] != "ar" and ar.value[3] != "en")


def _same_value(en: Figure, ar: Figure) -> bool:
    return bool(en.value == ar.value)


_SAME: dict[str, Callable[[Figure, Figure], bool]] = {
    "price": _same_price,
    "percentage": _same_value,
    "date": _same_value,
    "phone": _same_phone,
    "link": _same_link,
    "promo_code": _same_value,
}


def same(en: Figure, ar: Figure) -> bool:
    """Whether an English figure and an Arabic one are the same figure."""
    return _SAME[en.kind](en, ar)


@dataclass(frozen=True)
class Finding:
    """A figure with no equal partner. `problem` is one of:

    different  the two versions have a figure in the same place, not equal
    missing    the English has a figure the Arabic lacks
    extra      the Arabic has a figure the English lacks

    `elsewhere` is True when an equal figure does exist in the other
    version, at another position: the figure moved, or is repeated a
    different number of times.
    """

    kind: str
    problem: str
    en: Figure | None
    ar: Figure | None
    elsewhere: bool = False


@dataclass
class KindResult:
    kind: str
    en: list[Figure]
    ar: list[Figure]
    pairs: list[tuple[Figure, Figure]] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        """ "absent" (no such figure in either version), "match" or "mismatch"."""
        if not self.en and not self.ar:
            return "absent"
        return "mismatch" if self.findings else "match"


def _align(en: list[Figure], ar: list[Figure]) -> list[tuple[int, int]]:
    """Index pairs of the longest common subsequence under `same`."""
    rows, cols = len(en), len(ar)
    longest = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(rows - 1, -1, -1):
        for j in range(cols - 1, -1, -1):
            if same(en[i], ar[j]):
                longest[i][j] = longest[i + 1][j + 1] + 1
            else:
                longest[i][j] = max(longest[i + 1][j], longest[i][j + 1])
    pairs = []
    i = j = 0
    while i < rows and j < cols:
        if same(en[i], ar[j]):
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif longest[i + 1][j] >= longest[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def _compare_kind(kind: str, en: list[Figure], ar: list[Figure]) -> KindResult:
    result = KindResult(kind=kind, en=en, ar=ar)
    aligned = _align(en, ar)
    result.pairs = [(en[i], ar[j]) for i, j in aligned]

    # Walk the gaps between aligned pairs. Inside one gap, leftover figures
    # are taken to answer each other position by position.
    en_edge = ar_edge = 0
    for i, j in [*aligned, (len(en), len(ar))]:
        left, right = en[en_edge:i], ar[ar_edge:j]
        for position in range(max(len(left), len(right))):
            en_figure = left[position] if position < len(left) else None
            ar_figure = right[position] if position < len(right) else None
            problem = (
                "different" if en_figure and ar_figure else "missing" if en_figure else "extra"
            )
            result.findings.append(Finding(kind, problem, en_figure, ar_figure))
        en_edge, ar_edge = i + 1, j + 1

    def exists_elsewhere(finding: Finding) -> bool:
        if finding.en and any(same(finding.en, other) for other in ar):
            return True
        return bool(finding.ar and any(same(other, finding.ar) for other in en))

    result.findings = [
        Finding(f.kind, f.problem, f.en, f.ar, elsewhere=exists_elsewhere(f))
        for f in result.findings
    ]
    return result


def compare(en_text: str, ar_text: str) -> dict[str, KindResult]:
    """The parity check: every kind of figure, English against Arabic."""
    en, ar = extract(en_text), extract(ar_text)
    return {kind: _compare_kind(kind, en[kind], ar[kind]) for kind in KINDS}
