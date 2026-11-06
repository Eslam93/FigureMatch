"""A `.env` written for an older backend must keep loading.

Developers copy `.env.example` to `.env` once and keep it, so settings the
backend drops (here `USE_REDIS` / `REDIS_URL`) linger in those files, and
the old compose file injected `REDIS_URL` as well. `Settings` ignores
unknown keys (`extra="ignore"`), so the stale entries must not stop boot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


def test_stale_redis_settings_do_not_block_boot(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("USE_REDIS=true\nREDIS_URL=redis://redis:6379/0\n", encoding="utf-8")
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")

    settings = Settings(_env_file=env_file)

    assert not hasattr(settings, "use_redis")
    assert not hasattr(settings, "redis_url")
