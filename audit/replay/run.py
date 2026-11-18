#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Replay the November 2026 audit against two versions of the backend.

    python3 audit/replay/run.py

For each of two git refs (by default the tag `take-home-2026-05-16` and
`HEAD`) this script:

  1. unpacks that ref's `backend/` into a scratch directory,
  2. installs it from its own lockfile with `uv sync --frozen`,
  3. creates an empty Postgres database and runs that ref's migrations,
  4. starts that ref's backend on its default model settings, pointed at a
     local stand-in for OpenAI (`fake_openai.py`),
  5. runs the four probes in `probes.py` against it over HTTP.

The probes and the stand-in are the same files for both refs. The audit is
reproduced when every probe fails on the first ref and passes on the
second, and the script exits 0 only then (1 if not, 2 if it could not run).

Needs git, uv and a Postgres server it may create databases on (see
`--database-url`). It makes no call to OpenAI and needs no API key.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import harness
import probes
from fake_openai import FakeOpenAIServer

DEFAULT_AFTER = "HEAD"
_EXPECTED = {"before": "fail", "after": "pass"}


@dataclass
class RefRun:
    role: str  # "before" or "after"
    ref: str
    commit: str = ""
    results: list[probes.Result] = field(default_factory=list)

    def verdicts(self) -> dict[str, str]:
        return {r.probe: r.verdict for r in self.results}

    def name(self) -> str:
        short = self.commit[:7]
        return short if self.ref.startswith(short) else f"{self.ref} @ {short}"


def _wait_until_healthy(api: str, server: subprocess.Popen[bytes], log: Path) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline and server.poll() is None:
        try:
            reply = probes.call("GET", f"{api}/health")
            if reply.status == 200 and reply.json()["dependencies"]["db"] == "ok":
                return
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.5)
    tail = log.read_text(errors="replace")[-3000:] if log.exists() else ""
    raise harness.ReplayError(f"the backend did not become healthy. Its log ends:\n{tail}")


def replay_ref(run: RefRun, *, repo: Path, work: Path, admin_url: str) -> str:
    """Install, boot and probe one ref. Returns the Postgres server version."""
    print(f"[{run.role}] {run.ref}: installing from its lockfile", flush=True)
    tree = harness.checkout(
        run.ref,
        repo=repo,
        dest=work / run.role,
        admin_url=admin_url,
        database=f"figurematch_replay_{run.role}_{os.getpid()}",
    )
    run.commit = tree.commit
    pg_version = tree.postgres_version()
    tree.create_database()
    fake = FakeOpenAIServer()
    server: subprocess.Popen[bytes] | None = None
    try:
        # Only what the backend cannot run without. No model is named, so
        # each ref runs on the defaults it shipped with.
        env = harness.backend_env(
            {
                "ENVIRONMENT": "local",
                "AI_PROVIDER_MODE": "openai",
                "OPENAI_API_KEY": "sk-replay-not-a-real-key",
                "OPENAI_BASE_URL": fake.base_url,
                "DATABASE_URL": tree.database_url,
            }
        )
        tree.migrate(env)
        fake.start()
        port = harness.free_port()
        api = f"http://127.0.0.1:{port}/api/v1"
        log = work / f"{run.role}-backend.log"
        with log.open("wb") as log_file:
            server = subprocess.Popen(
                [
                    str(tree.python),
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=tree.backend,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            _wait_until_healthy(api, server, log)
            print(f"[{run.role}] backend up, running {len(probes.PROBES)} probes", flush=True)
            run.results = probes.run_all(probes.Target(api=api, openai_origin=fake.origin))
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
        fake.stop()
        tree.drop_database()
    return pg_version


def reproduced(before: RefRun, after: RefRun) -> bool:
    return all(v == "fail" for v in before.verdicts().values()) and all(
        v == "pass" for v in after.verdicts().values()
    )


def _print_report(before: RefRun, after: RefRun, *, pg_version: str, ran_at: str) -> None:
    print()
    print(f"Audit replay, {ran_at}, Postgres {pg_version}")
    print()
    print(f"  before  {before.name()}   expected: every probe fails, the defects are present")
    print(f"  after   {after.name()}   expected: every probe passes")
    print()
    width = max(len(p.name) for p in probes.PROBES) + 2
    print(f"  {'probe':<{width}}{'before':<8}after")
    after_verdicts = after.verdicts()
    for result in before.results:
        after_verdict = after_verdicts[result.probe].upper()
        print(f"  {result.probe:<{width}}{result.verdict.upper():<8}{after_verdict}")
    for run in (before, after):
        print()
        print(f"  What each probe saw on {run.name()}:")
        for result in run.results:
            print(f"    {result.probe}: {result.observed}")
    print()
    total = len(probes.PROBES)
    failed_before = sum(v == "fail" for v in before.verdicts().values())
    passed_after = sum(v == "pass" for v in after_verdicts.values())
    verdict = "REPRODUCED" if reproduced(before, after) else "NOT REPRODUCED"
    print(
        f"{verdict}: {failed_before} of {total} probes fail on {before.name()} "
        f"and {passed_after} of {total} pass on {after.name()}."
    )
    for run in (before, after):
        for probe, got in run.verdicts().items():
            if got != _EXPECTED[run.role]:
                print(f"  {run.role} {probe}: {got}, expected {_EXPECTED[run.role]}")


def _as_json(before: RefRun, after: RefRun, *, pg_version: str, ran_at: str) -> dict[str, Any]:
    return {
        "ran_at": ran_at,
        "postgres": pg_version,
        "reproduced": reproduced(before, after),
        "refs": {
            run.role: {
                "ref": run.ref,
                "commit": run.commit,
                "expected_verdict": _EXPECTED[run.role],
                "results": [result.as_dict() for result in run.results],
            }
            for run in (before, after)
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay the November 2026 audit against two versions of the backend."
    )
    parser.add_argument(
        "--before", default=harness.DEFAULT_BEFORE, help="the ref that has the defects"
    )
    parser.add_argument("--after", default=DEFAULT_AFTER, help="the ref that has the fixes")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("REPLAY_DATABASE_URL", harness.DEFAULT_DATABASE_URL),
        help=(
            "a Postgres login allowed to create databases; two are created and "
            f"dropped (default: $REPLAY_DATABASE_URL, else {harness.DEFAULT_DATABASE_URL})"
        ),
    )
    parser.add_argument("--json", type=Path, help="also write the result to this file")
    parser.add_argument("--keep", action="store_true", help="keep the scratch directory")
    args = parser.parse_args(argv)

    for tool in ("git", "uv"):
        if shutil.which(tool) is None:
            print(f"error: {tool} is not on PATH", file=sys.stderr)
            return 2

    ran_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    before = RefRun(role="before", ref=args.before)
    after = RefRun(role="after", ref=args.after)
    work = Path(tempfile.mkdtemp(prefix="figurematch-replay-"))
    try:
        repo = harness.repo_root()
        pg_version = ""
        for run in (before, after):
            pg_version = replay_ref(run, repo=repo, work=work, admin_url=args.database_url)
    except harness.ReplayError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(f"scratch directory kept for inspection: {work}", file=sys.stderr)
        return 2

    _print_report(before, after, pg_version=pg_version, ran_at=ran_at)
    if args.json:
        report = _as_json(before, after, pg_version=pg_version, ran_at=ran_at)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.keep:
        print(f"scratch directory kept: {work}")
    else:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if reproduced(before, after) else 1


if __name__ == "__main__":
    sys.exit(main())
