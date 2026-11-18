#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Turns the outputs of one `numbers` workflow run into a dated file.

    python3 .github/scripts/numbers.py WORK_DIR OUT_DIR

WORK_DIR holds what the workflow's checks wrote: JUnit XML from pytest,
coverage.py's JSON, Vitest's and Jest's JSON reports, `reuse lint --json`,
the audit replay's JSON and the gate's score JSON. A check whose output is
missing is reported as "not measured", never guessed.

The file is written to OUT_DIR/<YYYY-MM-DD>.md, dated in UTC, and the same
text is printed. The run's commit, address and tool versions come from the
environment GitHub Actions sets. Its links point at the commit it measured,
so they work from the `numbers` branch, where CI keeps these files.
Standard library only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

NOT_MEASURED = "not measured: the check left no output"


def _load(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _junit(path: Path) -> dict[str, int] | None:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in total:
            total[key] += int(suite.get(key, 0))
    total["passed"] = total["tests"] - total["failures"] - total["errors"] - total["skipped"]
    return total


def _pytest(path: Path) -> str:
    counts = _junit(path)
    if counts is None:
        return NOT_MEASURED
    failed = counts["failures"] + counts["errors"]
    return f"{counts['passed']} passed, {failed} failed, {counts['skipped']} skipped"


def _coverage(path: Path) -> str:
    data = _load(path)
    if not data:
        return NOT_MEASURED
    totals = data["totals"]
    return (
        f"{totals['percent_covered']:.2f}% ({totals['covered_lines']} of "
        f"{totals['num_statements']} lines, {totals.get('covered_branches', 0)} of "
        f"{totals.get('num_branches', 0)} branches)"
    )


def _vitest(path: Path) -> str:
    data = _load(path)
    if not data:
        return NOT_MEASURED
    return (
        f"{data['numPassedTests']} passed, {data['numFailedTests']} failed, "
        f"in {len(data['testResults'])} files"
    )


def _jest(path: Path) -> str:
    data = _load(path)
    if not data:
        return NOT_MEASURED
    snapshots = data.get("snapshot", {})
    return (
        f"{data['numPassedTests']} passed, {data['numFailedTests']} failed, "
        f"in {data['numTotalTestSuites']} suites; {snapshots.get('matched', 0)} of "
        f"{snapshots.get('total', 0)} snapshots matched"
    )


def _reuse(path: Path) -> str:
    data = _load(path)
    if not data:
        return NOT_MEASURED
    summary = data["summary"]
    both = min(summary["files_with_copyright_info"], summary["files_with_licensing_info"])
    verdict = "compliant" if summary["compliant"] else "NOT compliant"
    return f"{both} of {summary['files_total']} files; {verdict}"


def _replay(path: Path) -> tuple[str, str | None]:
    data = _load(path)
    if not data:
        return NOT_MEASURED, None
    before, after = data["refs"]["before"], data["refs"]["after"]
    failed = sum(r["verdict"] == "fail" for r in before["results"])
    passed = sum(r["verdict"] == "pass" for r in after["results"])
    total = len(before["results"])
    verdict = "reproduced" if data["reproduced"] else "NOT reproduced"
    text = (
        f"{verdict}: {failed} of {total} probes fail on `{before['ref']}` and "
        f"{passed} of {total} pass on this commit"
    )
    return text, str(data.get("postgres") or "") or None


def _gate(score_path: Path, tests_path: Path) -> tuple[str, str]:
    data = _load(score_path)
    if not data:
        labelled = NOT_MEASURED
    else:
        right = data["caught"] + data["passed"]
        labelled = (
            f"{right} of {data['pairs']} pairs right, in {data['cases']} cases: "
            f"{data['false_green']} false green, {data['false_red']} false red, "
            f"{data['not_read']} not read"
        )
    return labelled, _pytest(tests_path)


def _version(command: list[str]) -> str | None:
    try:
        out = subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or out.stderr).strip().splitlines()
    return text[0] if text else None


def render(work: Path, measured_at: datetime) -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    ref = os.environ.get("GITHUB_REF_NAME", "")
    run_url = f"{server}/{repo}/actions/runs/{run_id}/attempts/{attempt}" if run_id else None
    commit_url = f"{server}/{repo}/commit/{sha}" if sha else None

    def at_commit(text: str, path: str, kind: str = "tree") -> str:
        """`text` linked to `path` as it was at the measured commit."""
        return f"[{text}]({server}/{repo}/{kind}/{sha}/{path})" if repo and sha else text

    replay, postgres = _replay(work / "replay.json")
    gate_labelled, gate_tests = _gate(work / "gate-score.json", work / "gate-junit.xml")
    runner = " ".join(
        part
        for part in (os.environ.get("ImageOS"), os.environ.get("ImageVersion"))
        if part
    )
    def labelled(version: str | None, prefix: str, suffix: str = "") -> str | None:
        return f"{prefix}{version}{suffix}" if version else None

    versions = [
        labelled(_version(["python3", "--version"]), "", " for the scripts"),
        labelled(
            _version(["uv", "run", "--directory", "backend", "python", "--version"]),
            "",
            " for the backend",
        ),
        labelled(_version(["node", "--version"]), "Node "),
        labelled(_version(["pnpm", "--version"]), "pnpm "),
        labelled(postgres, "Postgres "),
    ]

    lines = [
        f"# CI numbers, {measured_at:%Y-%m-%d}",
        "",
        "Measured, written and committed by the "
        + at_commit("`numbers`", ".github/workflows/numbers.yml", "blob")
        + " workflow",
        "on GitHub's runner. No person typed these figures.",
        "",
        f"- Measured at: {measured_at:%Y-%m-%dT%H:%M:%SZ}",
        f"- Commit: [`{sha[:7]}`]({commit_url}) on `{ref}`" if commit_url else "- Commit: unknown",
        f"- Run: {run_url}" if run_url else "- Run: not on GitHub Actions",
        f"- Runner image: {runner}" if runner else "- Runner image: unknown",
        "- Versions: " + ", ".join(v for v in versions if v),
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Backend tests (pytest, against Postgres) | {_pytest(work / 'backend-junit.xml')} |",
        f"| Backend coverage of `app/` | {_coverage(work / 'backend-coverage.json')} |",
        f"| Frontend tests (Vitest) | {_vitest(work / 'frontend.json')} |",
        f"| Infrastructure tests (Jest) | {_jest(work / 'infra.json')} |",
        f"| Files that state an author and licence (`reuse lint`) | {_reuse(work / 'reuse.json')} |",
        f"| Audit replay ({at_commit('`audit/`', 'audit')}) | {replay} |",
        f"| Gate matcher on the labelled cases ({at_commit('`gate/`', 'gate')}) | {gate_labelled} |",
        f"| Gate matcher's fresh test cases | {gate_tests} |",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.split("\n\n")[1].strip(), file=sys.stderr)
        return 2
    work, out = Path(argv[1]), Path(argv[2])
    measured_at = datetime.now(UTC)
    text = render(work, measured_at)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{measured_at:%Y-%m-%d}.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
