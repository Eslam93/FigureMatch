#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Did the May test suite run the lines that were wrong?

    python3 audit/replay/old_suite.py

Unpacks the backend as it stood at `take-home-2026-05-16`, installs it from
its own lockfile, and runs its own test suite against an empty Postgres
database, recording which test executed which line (coverage.py's dynamic
contexts). It then reports, for each of the four defects, whether the
suite executed the faulty line and which tests did.

The lines are found by their text, not by number, so the report cannot
drift from the source it describes.

It then repeats one experiment. The May integration tests replaced the
request's database session with one that never rolled back. The script
swaps in the fixture file from the commit that fixed that, changes nothing
else, and reruns the May auth tests on the May code. The test that asserts
reuse revokes the token family then fails, which is what it should have
done in May.

Why the other three defects went unnoticed is in `audit/README.md`. For the
default ref the script exits 1 if what it measures no longer matches what
that file says.

Needs git, uv and a Postgres 13+ server it may create a database on.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import harness

# The commit that made the integration tests run the real `get_db_session`
# (pull request #155), and the fixture file it changed.
FIXTURE_COMMIT = "3e1b3339ab413338f7641ed5133367443991c7ee"
FIXTURE_FILE = "tests/integration/conftest.py"
AUTH_TESTS = "tests/integration/test_auth_routes.py"


@dataclass(frozen=True)
class Line:
    defect: str
    file: str  # relative to backend/
    text: str  # the line, stripped of indentation
    role: str
    # What audit/README.md says about it: "tests" (some test executed it),
    # "import" (executed when the module loaded, by no test in particular)
    # or "none" (no test executed it).
    claim: str = "tests"


LINES: tuple[Line, ...] = (
    Line(
        defect="stolen-refresh-token",
        file="app/services/auth_service.py",
        text="revoked_count = await self._refresh_tokens.revoke_all_for_user(existing.user_id)",
        role="revokes the user's tokens on reuse; nothing commits it before the 401",
    ),
    Line(
        defect="stolen-refresh-token",
        file="app/db/session.py",
        text="await session.rollback()",
        role="the request's rollback on any error, which undid that revocation",
    ),
    Line(
        defect="stolen-refresh-token",
        file="app/db/session.py",
        text="await session.commit()",
        role="the request's commit on success",
        claim="none",
    ),
    Line(
        defect="text-cost",
        file="app/providers/llm/openai_provider.py",
        text='"gpt-5.4-mini-2026-03-17": (0.15, 0.60),',
        role="the price table entry: $0.15 and $0.60 where OpenAI charges $0.75 and $4.50",
        claim="import",
    ),
    Line(
        defect="text-cost",
        file="app/providers/llm/openai_provider.py",
        text="return (input_tokens * input_price + output_tokens * output_price) / 1_000_000",
        role="the arithmetic that uses that entry",
    ),
    Line(
        defect="default-image-model",
        file="app/core/config.py",
        text='openai_image_model: str = "gpt-image-1"',
        role="the default image model, shut down by OpenAI on 2026-10-23",
        claim="import",
    ),
    Line(
        defect="default-image-model",
        file="app/providers/image/openai_provider.py",
        text="response = await self._client.images.generate(**request_kwargs)",
        role="the call that sends the model name to OpenAI",
    ),
    Line(
        defect="rejected-password-echo",
        file="app/core/exceptions.py",
        text='details={"errors": jsonable_encoder(errors)},',
        role="puts Pydantic's raw errors, each with the rejected `input`, in the 422 body",
    ),
)

# Run with the backend's interpreter, from backend/, after the test run.
_ANALYSE = """
import json, os, sys
import coverage

spec = json.load(sys.stdin)
data = coverage.CoverageData(".coverage")
data.read()
measured = {os.path.relpath(f).replace(os.sep, "/"): f for f in data.measured_files()}
out = []
for item in spec:
    found = []
    path = item["file"]
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            source = handle.read().splitlines()
        contexts = data.contexts_by_lineno(measured[path]) if path in measured else {}
        for number, line in enumerate(source, start=1):
            if line.strip() != item["text"]:
                continue
            seen = contexts.get(number, [])
            found.append(
                {
                    "line": number,
                    "executed": number in contexts,
                    "at_import": "" in seen,
                    "tests": sorted({c.split("|")[0] for c in seen if c}),
                }
            )
    out.append({**item, "found": found})
json.dump(out, sys.stdout)
"""


def _run_suite(tree: harness.Checkout) -> tuple[str, str]:
    """Run the ref's own tests with per-test coverage. Returns pytest's last
    line and the total coverage percentage."""
    env = harness.backend_env({"DATABASE_URL": tree.database_url})
    tree.migrate(env)
    pytest = subprocess.run(
        [
            str(tree.python),
            "-m",
            "pytest",
            "--cov=app",
            "--cov-context=test",
            "--cov-report=",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=tree.backend,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line for line in pytest.stdout.strip().splitlines() if line.strip()]
    summary = lines[-1].strip("= ") if lines else f"pytest exited {pytest.returncode}"
    if not (tree.backend / ".coverage").exists():
        raise harness.ReplayError(f"the test run left no coverage data:\n{pytest.stdout[-2000:]}")
    total = harness.run_cmd(
        [str(tree.python), "-m", "coverage", "report", "--format=total", "--precision=2"],
        cwd=tree.backend,
        env=env,
        what="coverage report",
    ).stdout.strip()
    return summary, total


def _analyse(tree: harness.Checkout) -> list[dict[str, Any]]:
    spec = [line.__dict__ for line in LINES]
    proc = subprocess.run(
        [str(tree.python), "-c", _ANALYSE],
        cwd=tree.backend,
        env=harness.backend_env({}),
        input=json.dumps(spec),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise harness.ReplayError(f"coverage analysis failed:\n{proc.stderr[-2000:]}")
    return list(json.loads(proc.stdout))


def _rerun_with_fixed_fixture(tree: harness.Checkout, repo: Path) -> dict[str, Any]:
    """Swap in the corrected fixture file and rerun the ref's own auth tests."""
    fixture = harness.run_cmd(
        ["git", "show", f"{FIXTURE_COMMIT}:backend/{FIXTURE_FILE}"],
        cwd=repo,
        what=f"git show {FIXTURE_COMMIT[:7]}:backend/{FIXTURE_FILE}",
    ).stdout
    (tree.backend / FIXTURE_FILE).write_text(fixture, encoding="utf-8")
    pytest = subprocess.run(
        [str(tree.python), "-m", "pytest", AUTH_TESTS, "-q", "-p", "no:cacheprovider"],
        cwd=tree.backend,
        env=harness.backend_env({"DATABASE_URL": tree.database_url}),
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line.strip() for line in pytest.stdout.splitlines() if line.strip()]
    return {
        "fixture_commit": FIXTURE_COMMIT,
        "fixture_file": FIXTURE_FILE,
        "tests": AUTH_TESTS,
        "pytest": lines[-1].strip("= ") if lines else f"pytest exited {pytest.returncode}",
        "failed": [line.split(" ", 2)[1] for line in lines if line.startswith("FAILED ")],
        "assertions": [line for line in lines if line.startswith("E   ")][:4],
    }


REUSE_TEST = f"{AUTH_TESTS}::test_refresh_reuse_revokes_entire_family"


def _observed(found: dict[str, Any]) -> str:
    if found["tests"]:
        return "tests"
    if found["at_import"]:
        return "import"
    return "none"


def disagreements(report: list[dict[str, Any]], rerun: dict[str, Any]) -> list[str]:
    """Where this run differs from what audit/README.md says about the tag."""
    problems = []
    for item in report:
        where = f"{item['file']}: {item['text']}"
        if len(item["found"]) != 1:
            problems.append(f"{where}: found {len(item['found'])} times, expected once")
        elif _observed(item["found"][0]) != item["claim"]:
            problems.append(
                f"{where}: executed by {_observed(item['found'][0])!r}, "
                f"the README says {item['claim']!r}"
            )
    revoke = _tests_of(report, LINES[0].file, LINES[0].text)
    rollback = _tests_of(report, LINES[1].file, LINES[1].text)
    if revoke & rollback:
        problems.append("a test executed both the reuse revocation and the request's rollback")
    if rerun["failed"] != [REUSE_TEST]:
        problems.append(
            f"with the corrected fixture, the failing tests were {rerun['failed']}, "
            f"expected only {REUSE_TEST}"
        )
    return problems


def _tests_of(report: list[dict[str, Any]], file: str, text: str) -> set[str]:
    for item in report:
        if item["file"] == file and item["text"] == text:
            return {t for found in item["found"] for t in found["tests"]}
    return set()


def _print_report(
    tree: harness.Checkout,
    report: list[dict[str, Any]],
    rerun: dict[str, Any],
    *,
    summary: str,
    total: str,
    ran_at: str,
) -> None:
    print()
    print(f"The test suite of {tree.ref} @ {tree.commit[:7]}, run {ran_at}")
    print(f"  pytest: {summary}")
    print(f"  line and branch coverage of app/: {total}%")
    defect = None
    for item in report:
        if item["defect"] != defect:
            defect = item["defect"]
            print()
            print(f"{defect}")
        if not item["found"]:
            print(f"  {item['file']}: line not present at this ref")
            print(f"      {item['text']}")
            continue
        for found in item["found"]:
            tests = found["tests"]
            if tests:
                ran = f"executed by {len(tests)} test{'s' if len(tests) != 1 else ''}"
            elif found["at_import"]:
                ran = "executed once, when the module was imported; by no test in particular"
            elif found["executed"]:
                ran = "executed"
            else:
                ran = "NOT executed by any test"
            print(f"  {item['file']}:{found['line']}  {ran}")
            print(f"      {item['text']}")
            print(f"      ({item['role']})")
            for test in tests:
                print(f"        - {test}")

    revoke = _tests_of(report, LINES[0].file, LINES[0].text)
    rollback = _tests_of(report, LINES[1].file, LINES[1].text)
    print()
    print(
        "Tests that executed both the reuse revocation and the request's rollback: "
        f"{len(revoke & rollback)} (of {len(revoke)} that ran the revocation and "
        f"{len(rollback)} that ran the rollback)."
    )

    print()
    print(f"The same auth tests on the same code, with {rerun['fixture_file']}")
    print(f"taken from {rerun['fixture_commit'][:7]} so requests use the real session handling:")
    print(f"  pytest {rerun['tests']}: {rerun['pytest']}")
    for test in rerun["failed"]:
        print(f"    FAILED {test}")
    for line in rerun["assertions"]:
        print(f"      {line}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report whether the May test suite executed the four faulty lines."
    )
    parser.add_argument("--ref", default=harness.DEFAULT_BEFORE, help="the ref to examine")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("REPLAY_DATABASE_URL", harness.DEFAULT_DATABASE_URL),
        help=(
            "a Postgres login allowed to create a database "
            f"(default: $REPLAY_DATABASE_URL, else {harness.DEFAULT_DATABASE_URL})"
        ),
    )
    parser.add_argument("--json", type=Path, help="also write the result to this file")
    args = parser.parse_args(argv)

    for tool in ("git", "uv"):
        if shutil.which(tool) is None:
            print(f"error: {tool} is not on PATH", file=sys.stderr)
            return 2

    ran_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    work = Path(tempfile.mkdtemp(prefix="figurematch-oldsuite-"))
    tree: harness.Checkout | None = None
    try:
        print(f"{args.ref}: installing from its lockfile and running its tests", flush=True)
        tree = harness.checkout(
            args.ref,
            repo=harness.repo_root(),
            dest=work,
            admin_url=args.database_url,
            database=f"figurematch_oldsuite_{os.getpid()}",
        )
        tree.create_database()
        repo = harness.repo_root()
        summary, total = _run_suite(tree)
        report = _analyse(tree)
        rerun = _rerun_with_fixed_fixture(tree, repo)
    except harness.ReplayError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if tree is not None:
            tree.drop_database()
        shutil.rmtree(work, ignore_errors=True)

    _print_report(tree, report, rerun, summary=summary, total=total, ran_at=ran_at)
    if args.json:
        payload = {
            "ran_at": ran_at,
            "ref": tree.ref,
            "commit": tree.commit,
            "pytest": summary,
            "coverage_percent": total,
            "lines": report,
            "auth_tests_with_real_session_handling": rerun,
        }
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.ref != harness.DEFAULT_BEFORE:
        return 0
    problems = disagreements(report, rerun)
    print()
    if problems:
        print("This run does NOT match what audit/README.md says:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("This run matches what audit/README.md says about the May suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
