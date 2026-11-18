# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Database package — declarative `Base`, common mixins, async session plumbing.

Importing this package also imports every model so they are registered with
`Base.metadata`. This is what Alembic's autogenerate inspects.
"""

# Import the models package for its side effect (model registration).
# The `noqa: F401` keeps lint happy about the "unused" import.
from app.db import models  # noqa: F401
from app.db.base import Base, SoftDeleteMixin, TimestampedMixin
from app.db.session import (
    DbSession,
    check_db_health,
    close_db_engine,
    get_db_session,
    get_engine,
    get_sessionmaker,
)

__all__ = [
    "Base",
    "DbSession",
    "SoftDeleteMixin",
    "TimestampedMixin",
    "check_db_health",
    "close_db_engine",
    "get_db_session",
    "get_engine",
    "get_sessionmaker",
]
