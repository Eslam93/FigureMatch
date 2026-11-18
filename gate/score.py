# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Scores the parity matcher on the labelled cases.

    uv run python score.py            print the score
    uv run python score.py --write    also write it to SCORE.md
    uv run python score.py --check    exit 1 unless SCORE.md is this run's score
    uv run python score.py --show     print the figures read in every case

Every case lists the check types it scores, each labelled `match` or
`mismatch`. The matcher's verdict for a type is `mismatch` if it found a
figure of that type with no equal partner, and `match` otherwise,
including when it found no figure of that type at all: a matcher that sees
nothing reports nothing.

Three kinds of error are counted apart, because they cost differently:

  false green  a labelled mismatch the matcher called a match. A wrong
               figure reaches a customer.
  false red    a labelled match the matcher called a mismatch. Someone
               checks a figure that was right.
  not read     a labelled match where the matcher found no figure of that
               type in either version. Its "match" compared nothing, so it
               is not counted as right.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from matcher import KINDS, compare

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases" / "labelled.jsonl"
SCORE = HERE / "SCORE.md"

_TITLES = {
    "price": "Price",
    "percentage": "Percentage",
    "date": "Date",
    "phone": "Phone",
    "link": "Link",
    "promo_code": "Promo code",
}


@dataclass(frozen=True)
class Scored:
    """One case, one check type."""

    case: str
    kind: str
    trap: str | None
    label: str
    verdict: str
    note: str

    @property
    def outcome(self) -> str:
        if self.label == "mismatch":
            return "caught" if self.verdict == "mismatch" else "false green"
        if self.verdict == "absent":
            return "not read"
        return "passed" if self.verdict == "match" else "false red"


def run() -> tuple[list[Scored], list[tuple[str, str]]]:
    """Score every labelled pair. Also returns the (case, type) pairs where
    the matcher reported a mismatch in a type the case does not label."""
    scored: list[Scored] = []
    unlabelled: list[tuple[str, str]] = []
    with CASES.open(encoding="utf-8") as handle:
        for line in handle:
            case = json.loads(line)
            results = compare(case["en"], case["ar"])
            for kind in KINDS:
                verdict = results[kind].verdict  # "absent", "match" or "mismatch"
                if kind in case["checks"]:
                    scored.append(
                        Scored(
                            case=case["id"],
                            kind=kind,
                            trap=case["trap"],
                            label=case["checks"][kind],
                            verdict=verdict,
                            note=case["note"],
                        )
                    )
                elif verdict == "mismatch":
                    unlabelled.append((case["id"], kind))
    return scored, unlabelled


def show() -> str:
    """What the matcher read in every case: the figures of each scored type
    in both versions, and what it could not pair."""
    lines = []
    with CASES.open(encoding="utf-8") as handle:
        for line in handle:
            case = json.loads(line)
            results = compare(case["en"], case["ar"])
            lines.append(f"{case['id']}")
            for kind in KINDS:
                result = results[kind]
                if kind not in case["checks"] and result.verdict == "absent":
                    continue
                label = case["checks"].get(kind, "not labelled")
                lines.append(f"  {kind}: labelled {label}, matcher says {result.verdict}")
                lines.append(
                    "    EN: " + (", ".join(f"{f.text} = {f.value}" for f in result.en) or "-")
                )
                lines.append(
                    "    AR: " + (", ".join(f"{f.text} = {f.value}" for f in result.ar) or "-")
                )
                for finding in result.findings:
                    en = finding.en.text if finding.en else "-"
                    ar = finding.ar.text if finding.ar else "-"
                    moved = " (an equal figure exists elsewhere)" if finding.elsewhere else ""
                    lines.append(f"    {finding.problem}: EN {en} | AR {ar}{moved}")
    return "\n".join(lines) + "\n"


def _count(scored: list[Scored], outcome: str) -> int:
    return sum(s.outcome == outcome for s in scored)


def _rate(part: int, whole: int) -> str:
    return f"{part} of {whole} ({part / whole:.0%})" if whole else "none to score"


def _type_row(title: str, scored: list[Scored]) -> str:
    caught, false_green = _count(scored, "caught"), _count(scored, "false green")
    passed, false_red = _count(scored, "passed"), _count(scored, "false red")
    not_read = _count(scored, "not read")
    flagged = caught + false_red
    return (
        f"| {title} | {len(scored)} | {caught + false_green} | {caught} | {false_green} "
        f"| {passed + false_red + not_read} | {passed} | {false_red} | {not_read} "
        f"| {_rate(false_green, caught + false_green)} | {_rate(caught, flagged)} |"
    )


def render(scored: list[Scored], unlabelled: list[tuple[str, str]]) -> str:
    cases = len({s.case for s in scored})
    lines = [
        "# The matcher's score on the labelled cases",
        "",
        "Written by `score.py`. Do not edit by hand: `uv run python score.py --check` fails",
        "if this file is not what the matcher produces.",
        "",
        f"{cases} cases, {len(scored)} scored pairs of (case, check type).",
        "",
        "A **false green** is a labelled mismatch the matcher called a match. A **false red**",
        "is a labelled match it called a mismatch. **Not read** is a labelled match where the",
        "matcher found no figure of that type in either version, so its match compared nothing.",
        "The false-green rate is false greens over labelled mismatches. Precision is the share",
        "of the matcher's mismatch verdicts that the labels agree with.",
        "",
        "A verdict can also be right for the wrong reason, which this table cannot show. The",
        "figures the matcher read for every case are printed by `uv run python score.py --show`.",
        "",
        "## By check type",
        "",
        "| Type | Pairs | Labelled mismatch | Caught | False green | Labelled match "
        "| Passed | False red | Not read | False-green rate | Precision |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for kind in KINDS:
        lines.append(_type_row(_TITLES[kind], [s for s in scored if s.kind == kind]))
    lines.append(_type_row("**All**", scored))

    green = [s for s in scored if s.trap == "false_green" and s.label == "mismatch"]
    red = [s for s in scored if s.trap == "false_red" and s.label == "match"]
    plain = [s for s in scored if s.trap is None]
    wrong_plain = len(plain) - _count(plain, "caught") - _count(plain, "passed")
    lines += [
        "",
        "## The traps",
        "",
        "A false-green trap is a mismatch written so that a careless check calls it a match.",
        "A false-red trap is a match written so that a careless check flags it.",
        "",
        "| Cases | Pairs | Right | Wrong |",
        "|---|---|---|---|",
        f"| False-green traps | {len(green)} | {_count(green, 'caught')} caught "
        f"| {_count(green, 'false green')} called a match |",
        f"| False-red traps | {len(red)} | {_count(red, 'passed')} passed "
        f"| {_count(red, 'false red')} flagged, {_count(red, 'not read')} not read |",
        f"| Plain cases | {len(plain)} | {len(plain) - wrong_plain} | {wrong_plain} |",
    ]

    for outcome, heading in (
        ("false green", "False greens"),
        ("false red", "False reds"),
        ("not read", "Not read"),
    ):
        wrong = [s for s in scored if s.outcome == outcome]
        lines += ["", f"## {heading}", ""]
        if not wrong:
            lines.append("None.")
        for s in wrong:
            trap = f", a {s.trap.replace('_', '-')} trap" if s.trap else ""
            lines.append(f"- `{s.case}` ({_TITLES[s.kind].lower()}{trap}): {s.note}")

    lines += ["", "## Mismatches reported in a type the case does not label", ""]
    if not unlabelled:
        lines.append("None.")
    for case, kind in unlabelled:
        lines.append(f"- `{case}`: {_TITLES[kind].lower()}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score the parity matcher on the labelled cases.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="write the score to SCORE.md")
    group.add_argument("--check", action="store_true", help="fail unless SCORE.md is up to date")
    group.add_argument("--show", action="store_true", help="print what was read in each case")
    args = parser.parse_args(argv)

    if args.show:
        print(show(), end="")
        return 0

    report = render(*run())
    if args.check:
        if not SCORE.exists() or SCORE.read_text(encoding="utf-8") != report:
            print("SCORE.md is not what the matcher produces. Run: uv run python score.py --write")
            return 1
        print("SCORE.md matches this run.")
        return 0
    print(report, end="")
    if args.write:
        SCORE.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
