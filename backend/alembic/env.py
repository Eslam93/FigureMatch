# SPDX-FileCopyrightText: 2009-2026 Michael Bayer
# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Alembic environment — async edition.

Adapted from the official `async` template in the SQLAlchemy 2.0 docs.
The synchronous parts of Alembic run inside `connection.run_sync()` so
nothing about the user-facing CLI changes (`alembic upgrade head` etc.).
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Importing `app.db` triggers model registration on Base.metadata,
# which is what autogenerate compares the live DB against.
import app.db  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base

# Alembic Config object.
config = context.config

# Configure Python logging from the ini file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the SQLAlchemy URL with whatever the app settings resolved to.
# This means migrations always target the same DB the app talks to — no risk
# of `alembic.ini` and `.env` drifting.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

# `target_metadata` is what Alembic compares against to autogenerate diffs.
# It must include every mapped table — models are imported via `app.db.base`
# transitively (each model module imports Base from here).
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection.

    Emits SQL to stdout. Useful for review or for shipping a release bundle
    of SQL to a DBA. Triggered by `alembic upgrade head --sql`.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Sync core of an online migration. Called from `connection.run_sync`."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Open an async engine, hand the sync work off to `do_run_migrations`."""
    section = config.get_section(config.config_ini_section) or {}
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # one-off; no pooling for migrations
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online mode — bridges the async runner."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
