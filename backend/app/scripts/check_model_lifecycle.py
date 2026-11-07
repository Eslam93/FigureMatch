"""Check the configured OpenAI models against the catalog and OpenAI's
deprecations page.

Run from `backend/`:

    uv run python -m app.scripts.check_model_lifecycle [--days N] [--no-fetch]
        [--deprecations-url URL]

Offline check: the configured text and image models (read through
`Settings`, so in CI they are the shipped defaults) must be in
`app/core/model_catalog.py`, priced for their slot, not shut down, and not
due to shut down within `--days` days (default 30).

Online check (skipped with `--no-fetch`): fetch OpenAI's deprecations page
and fail if a configured id appears in a table's deprecated-model column.
An id that only appears as a recommended replacement does not count. A check
that can't see must not pass quietly, so it also fails when the page can't
be fetched, yields no parsable rows, or no longer shows every model the
catalog records a shutdown for in a deprecated-model column (a table whose
layout changed would otherwise drop out of the check unnoticed).

Output is plain lines on stdout, plus `::error::` / `::warning::`
annotations under GitHub Actions. Exit code 0 means OK; 1 means a problem
was found or the check could not verify.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from typing import Literal

import httpx
from pydantic import ValidationError

from app.core import model_catalog
from app.core.config import Settings, shipped_openai_model
from app.core.model_catalog import ModelEntry, ModelKind, ModelStatus

# OpenAI's canonical URL; platform.openai.com/docs/deprecations redirects here.
DEFAULT_DEPRECATIONS_URL = "https://developers.openai.com/api/docs/deprecations"
DEFAULT_DAYS = 30

_FETCH_TIMEOUT_SECONDS = 30.0
# Fetched the way a regular browser would; it is a public docs page.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

Level = Literal["ok", "warning", "error"]


@dataclass(frozen=True, slots=True)
class Finding:
    level: Level
    message: str


@dataclass(frozen=True, slots=True)
class ConfiguredModel:
    env_var: str
    model_id: str
    kind: ModelKind


@dataclass(frozen=True, slots=True)
class DeprecationRow:
    """One table row: the ids in its deprecated-model column, the shutdown
    date (YYYY-MM-DD when parseable) and the substitute column's text."""

    model_ids: tuple[str, ...]
    shutdown: str
    substitute: str


# ── HTML table parsing ─────────────────────────────────────────────────

# Typographic hyphens (the page writes some dates with U+2011) become ASCII
# so ids and dates compare exactly. No-break spaces are handled by split().
_HYPHENS = str.maketrans(dict.fromkeys("\u2010\u2011\u2012\u2212", "-"))
# Model ids never contain these, so they safely split a cell with no <code>.
_ID_SEPARATORS = re.compile(r"[\s,;|()]+")

_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_WRITTEN_DATE = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b")
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")

# A header containing "model" names the deprecated-model column unless it is
# the substitute column ("Recommended replacement") or a price column.
_SUBSTITUTE_WORDS = ("substitute", "replacement", "recommended")
_NOT_MODEL_WORDS = (*_SUBSTITUTE_WORDS, "price")


def _clean(text: str) -> str:
    return " ".join(text.translate(_HYPHENS).split())


def _iso_date(text: str) -> str:
    """The first date in `text` as YYYY-MM-DD, else `text` unchanged. The
    page mixes "2026-05-12", "October 23, 2026" and "Dec 1, 2026"."""
    iso = _ISO_DATE.search(text)
    if iso:
        return iso.group(0)
    written = _WRITTEN_DATE.search(text)
    if written:
        month_name, day, year = written.groups()
        prefix = month_name[:3].lower()
        if prefix in _MONTHS:
            try:
                return date(int(year), _MONTHS.index(prefix) + 1, int(day)).isoformat()
            except ValueError:
                return text
    return text


@dataclass
class _Cell:
    is_header: bool
    parts: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return _clean("".join(self.parts))


@dataclass
class _Table:
    header: list[str] = field(default_factory=list)
    rows: list[list[_Cell]] = field(default_factory=list)
    row: list[_Cell] | None = None
    cell: _Cell | None = None
    code: list[str] | None = None

    def close_code(self) -> None:
        if self.code is not None and self.cell is not None:
            code_text = _clean("".join(self.code))
            if code_text:
                self.cell.codes.append(code_text)
        self.code = None

    def close_cell(self) -> None:
        self.close_code()
        if self.cell is not None and self.row is not None:
            self.row.append(self.cell)
        self.cell = None

    def close_row(self) -> None:
        self.close_cell()
        if self.row:
            if all(cell.is_header for cell in self.row):
                if not self.header:
                    self.header = [cell.text for cell in self.row]
            else:
                self.rows.append(self.row)
        self.row = None


class _TableParser(HTMLParser):
    """Collects every <table>: its first all-<th> row as the header, the
    other rows as cells with their <code> texts kept apart. Tolerates
    omitted </td>, </th> and </tr> end tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[_Table] = []
        self._open: list[_Table] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._open.append(_Table())
            return
        if not self._open:
            return
        table = self._open[-1]
        if tag == "tr":
            table.close_row()
            table.row = []
        elif tag in ("td", "th"):
            table.close_cell()
            if table.row is not None:
                table.cell = _Cell(is_header=tag == "th")
        elif tag == "code" and table.cell is not None:
            table.code = []

    def handle_endtag(self, tag: str) -> None:
        if not self._open:
            return
        table = self._open[-1]
        if tag == "table":
            table.close_row()
            self.tables.append(self._open.pop())
        elif tag == "tr":
            table.close_row()
        elif tag in ("td", "th"):
            table.close_cell()
        elif tag == "code":
            table.close_code()

    def handle_data(self, data: str) -> None:
        if not self._open:
            return
        table = self._open[-1]
        if table.cell is not None:
            table.cell.parts.append(data)
            if table.code is not None:
                table.code.append(data)


def _column(header: Sequence[str], wanted: Callable[[str], bool]) -> int | None:
    return next((i for i, title in enumerate(header) if wanted(title.lower())), None)


def _is_model_header(title: str) -> bool:
    return "model" in title and not any(word in title for word in _NOT_MODEL_WORDS)


def _is_substitute_header(title: str) -> bool:
    return any(word in title for word in _SUBSTITUTE_WORDS)


def _cell_text(cells: Sequence[_Cell], index: int | None) -> str:
    if index is None or index >= len(cells):
        return ""
    return cells[index].text


def _model_ids(cell: _Cell) -> tuple[str, ...]:
    if cell.codes:
        return tuple(cell.codes)
    return tuple(token for token in _ID_SEPARATORS.split(cell.text) if token)


def parse_deprecations(html: str) -> list[DeprecationRow]:
    """Rows of every table that has a deprecated-model column. Tables
    without one (changelogs, "System" tables) are skipped."""
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    rows: list[DeprecationRow] = []
    for table in parser.tables:
        model_col = _column(table.header, _is_model_header)
        if model_col is None:
            continue
        date_col = _column(table.header, lambda title: "date" in title)
        substitute_col = _column(table.header, _is_substitute_header)
        for cells in table.rows:
            if model_col >= len(cells):
                continue
            ids = _model_ids(cells[model_col])
            if ids:
                rows.append(
                    DeprecationRow(
                        model_ids=ids,
                        shutdown=_iso_date(_cell_text(cells, date_col)),
                        substitute=_cell_text(cells, substitute_col),
                    )
                )
    return rows


# ── checks ─────────────────────────────────────────────────────────────


def fetch_deprecations_page(url: str) -> str:
    """GET `url` like a browser would. Raises `httpx.HTTPError` on failure."""
    response = httpx.get(
        url,
        headers=_BROWSER_HEADERS,
        timeout=_FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def configured_models(settings: Settings) -> tuple[ConfiguredModel, ...]:
    return (
        ConfiguredModel("OPENAI_TEXT_MODEL", settings.openai_text_model, "text"),
        ConfiguredModel("OPENAI_IMAGE_MODEL", settings.openai_image_model, "image"),
    )


def _switch_to(entry: ModelEntry, kind: ModelKind) -> str:
    """What the setting should hold instead of `entry`. The catalog's
    replacement is of `entry`'s kind, so for a model in the wrong slot it
    would be wrong too; the slot's shipped default is named instead."""
    if entry.kind == kind and entry.replacement is not None:
        return entry.replacement
    return f"{shipped_openai_model(kind)} (the shipped {kind} default)"


def _offline_check(model: ConfiguredModel, *, days: int, on: date) -> list[Finding]:
    label = f"{model.env_var}={model.model_id}"
    status = model_catalog.classify(model.model_id, model.kind, on=on)
    if status is ModelStatus.UNKNOWN:
        return [
            Finding(
                "error",
                f"{label} is not in app/core/model_catalog.py; add it with verified prices.",
            )
        ]
    entry = model_catalog.MODEL_CATALOG[model.model_id]
    if status is ModelStatus.RETIRED:
        return [
            Finding(
                "error",
                f"{label} was shut down by OpenAI on {entry.shutdown_on}; "
                f"switch to {_switch_to(entry, model.kind)}.",
            )
        ]
    findings: list[Finding] = []
    if status is ModelStatus.WRONG_KIND:
        findings.append(
            Finding(
                "error",
                f"{label} is catalogued as kind={entry.kind}, but this setting needs "
                f"kind={model.kind}.",
            )
        )
    elif status is ModelStatus.UNPRICED:
        findings.append(
            Finding("error", f"{label} has no verified price in app/core/model_catalog.py.")
        )
    remaining = model_catalog.days_until_shutdown(entry, on=on)
    if remaining is not None:
        level: Level = "error" if model_catalog.shuts_down_within(entry, days, on=on) else "warning"
        findings.append(
            Finding(
                level,
                f"{label} shuts down on {entry.shutdown_on}, in {remaining} days; "
                f"switch to {_switch_to(entry, model.kind)}.",
            )
        )
    if not findings:
        findings.append(Finding("ok", f"{label} is catalogued, priced, with no shutdown date."))
    return findings


def offline_findings(models: Sequence[ConfiguredModel], *, days: int, on: date) -> list[Finding]:
    return [finding for model in models for finding in _offline_check(model, days=days, on=on)]


def _missing_known_shutdowns(rows: Sequence[DeprecationRow]) -> list[str]:
    """Catalogued models with a shutdown date that no parsed row lists.

    OpenAI's page lists each of them, so a missing one means a table was
    skipped (e.g. its header was reworded), and that table's other rows
    went unchecked too.
    """
    listed = {model_id for row in rows for model_id in row.model_ids}
    return [
        entry.model_id
        for entry in model_catalog.MODEL_CATALOG.values()
        if entry.shutdown_on is not None and entry.model_id not in listed
    ]


def online_findings(models: Sequence[ConfiguredModel], *, url: str) -> list[Finding]:
    try:
        html = fetch_deprecations_page(url)
    except httpx.HTTPError as exc:
        # One line: httpx puts a newline inside HTTPStatusError messages.
        detail = " ".join(str(exc).split())
        return [
            Finding(
                "error",
                f"Could not verify against {url}: fetch failed ({type(exc).__name__}: {detail}).",
            )
        ]
    rows = parse_deprecations(html)
    if not rows:
        return [
            Finding(
                "error",
                f"Could not verify against {url}: no deprecation table rows could be "
                "parsed, so the page layout may have changed.",
            )
        ]
    missing = _missing_known_shutdowns(rows)
    if missing:
        return [
            Finding(
                "error",
                f"Could not verify against {url}: models the catalog lists with a "
                "shutdown date are missing from every parsed deprecated-model column "
                f"({', '.join(missing)}), so the page layout may have changed.",
            )
        ]
    findings: list[Finding] = []
    for model in models:
        label = f"{model.env_var}={model.model_id}"
        hits = [row for row in rows if model.model_id in row.model_ids]
        for row in hits:
            findings.append(
                Finding(
                    "error",
                    f"{label} is listed as deprecated on {url}: shutdown "
                    f"{row.shutdown or 'not given'}, replacement "
                    f"{row.substitute or 'not given'}.",
                )
            )
        if not hits:
            findings.append(
                Finding("ok", f"{label} is not listed as deprecated ({len(rows)} rows checked).")
            )
    return findings


def run(*, days: int, fetch: bool, deprecations_url: str) -> list[Finding]:
    try:
        settings = Settings()
    except ValidationError as exc:
        reasons = "; ".join(error["msg"] for error in exc.errors())
        return [Finding("error", f"Settings refused the current configuration: {reasons}")]
    models = configured_models(settings)
    findings = offline_findings(models, days=days, on=model_catalog.today())
    if fetch:
        findings += online_findings(models, url=deprecations_url)
    return findings


# ── CLI ────────────────────────────────────────────────────────────────


def _emit(line: str) -> None:
    """One line on stdout (ruff's T20 rule rules out print())."""
    try:
        sys.stdout.write(line + "\n")
    except UnicodeEncodeError:  # e.g. a legacy Windows console code page
        sys.stdout.write(line.encode("ascii", "backslashreplace").decode("ascii") + "\n")


def _annotation(finding: Finding) -> str:
    """A GitHub Actions workflow command, with its message escaped."""
    message = finding.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::{finding.level}::{message}"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.check_model_lifecycle",
        description=(
            "Fail if a configured OpenAI model is unknown, unpriced, shut down, "
            "shutting down soon, or listed on OpenAI's deprecations page."
        ),
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help="fail when a catalogued shutdown is this many days away or less "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="skip the online check against OpenAI's deprecations page",
    )
    parser.add_argument(
        "--deprecations-url",
        default=DEFAULT_DEPRECATIONS_URL,
        help="deprecations page to check (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    findings = run(days=args.days, fetch=not args.no_fetch, deprecations_url=args.deprecations_url)
    annotate = os.environ.get("GITHUB_ACTIONS") == "true"
    for finding in findings:
        _emit(f"{finding.level.upper()}: {finding.message}")
        if annotate and finding.level != "ok":
            _emit(_annotation(finding))
    errors = sum(1 for finding in findings if finding.level == "error")
    if errors:
        _emit(f"FAIL: {errors} problem(s) with the configured OpenAI models.")
        return 1
    _emit("PASS: no problems with the configured OpenAI models.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
