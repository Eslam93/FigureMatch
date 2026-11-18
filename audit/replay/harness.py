# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""What `run.py` and `old_suite.py` share: getting one ref's backend onto
disk, installed from its own lockfile, with an empty database to itself.

Standard library only. Each backend brings its own dependencies, and its
own interpreter is used for anything that needs them (asyncpg, alembic).
"""

from __future__ import annotations

import io
import os
import socket
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent

DEFAULT_BEFORE = "take-home-2026-05-16"
DEFAULT_DATABASE_URL = "postgresql://app:app@localhost:5432/app"

# Run with a backend's own interpreter, which has asyncpg. The admin URL
# arrives in the environment so it is not shown in the process list.
_DB_ADMIN = """
import asyncio, os, sys
import asyncpg

async def main(action, name):
    conn = await asyncpg.connect(os.environ["REPLAY_ADMIN_URL"])
    try:
        if action == "version":
            print(await conn.fetchval("SHOW server_version"))
            return
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        if action == "create":
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()

asyncio.run(main(sys.argv[1], sys.argv[2]))
"""

# Variables a backend process may inherit. Everything else is dropped, so a
# model name, key or database URL in the caller's shell cannot leak in.
_PASS_THROUGH = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT")


class ReplayError(Exception):
    """The run could not be carried out (as opposed to: it gave a result)."""


def run_cmd(
    cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None, what: str
) -> subprocess.CompletedProcess[str]:
    """Run to completion; raise `ReplayError` with the output's tail on failure."""
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).strip()[-2000:]
        raise ReplayError(f"{what} failed (exit {proc.returncode}):\n{tail}")
    return proc


def repo_root() -> Path:
    out = run_cmd(["git", "rev-parse", "--show-toplevel"], cwd=HERE, what="git rev-parse")
    return Path(out.stdout.strip())


def resolve(ref: str, repo: Path) -> str:
    """The full commit id `ref` names."""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ReplayError(
            f"git cannot resolve {ref!r}. If it is the tag, fetch it first: "
            f"git fetch origin tag {ref}"
        )
    return proc.stdout.strip()


def backend_env(extra: dict[str, str]) -> dict[str, str]:
    env = {k: os.environ[k] for k in _PASS_THROUGH if k in os.environ}
    env.update(extra)
    return env


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass(frozen=True)
class Checkout:
    """One ref's backend: unpacked, installed, with a database of its own."""

    ref: str
    commit: str
    backend: Path
    python: Path
    admin_url: str
    database: str

    @property
    def database_url(self) -> str:
        """The URL the backend connects with (asyncpg driver, own database)."""
        parts = urlsplit(self.admin_url)
        return urlunsplit(("postgresql+asyncpg", parts.netloc, f"/{self.database}", "", ""))

    def _admin(self, action: str, name: str) -> str:
        out = run_cmd(
            [str(self.python), "-c", _DB_ADMIN, action, name],
            cwd=self.backend,
            env=backend_env({"REPLAY_ADMIN_URL": self.admin_url}),
            what=f"database {action}",
        )
        return out.stdout.strip()

    def postgres_version(self) -> str:
        return self._admin("version", "-")

    def create_database(self) -> None:
        self._admin("create", self.database)

    def drop_database(self) -> None:
        self._admin("drop", self.database)

    def migrate(self, env: dict[str, str]) -> None:
        run_cmd(
            [str(self.python), "-m", "alembic", "upgrade", "head"],
            cwd=self.backend,
            env=env,
            what="alembic upgrade head",
        )


def _venv_python(backend: Path) -> Path:
    for candidate in (backend / ".venv/bin/python", backend / ".venv/Scripts/python.exe"):
        if candidate.exists():
            return candidate
    raise ReplayError(f"no virtualenv interpreter under {backend / '.venv'}")


def checkout(ref: str, *, repo: Path, dest: Path, admin_url: str, database: str) -> Checkout:
    """Unpack `backend/` as committed at `ref` into `dest` and install it
    with `uv sync --frozen`, so it runs on the dependencies it was locked to."""
    commit = resolve(ref, repo)
    archive = subprocess.run(
        ["git", "archive", "--format=tar", commit, "backend"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        raise ReplayError(f"git archive {commit} failed: {archive.stderr.decode()[-500:]}")
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:  # a Python from before the `filter` argument
            tar.extractall(dest)
    backend = dest / "backend"

    tool_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    run_cmd(["uv", "sync", "--frozen"], cwd=backend, env=tool_env, what="uv sync --frozen")
    return Checkout(
        ref=ref,
        commit=commit,
        backend=backend,
        python=_venv_python(backend),
        admin_url=admin_url,
        database=database,
    )
