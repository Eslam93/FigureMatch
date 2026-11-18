# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Data access for the `users` table.

Repositories are thin async helpers — no business logic, no validation,
no auth context. The service layer owns those concerns.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def find_by_email(self, email: str) -> User | None:
        # `User.email` is CITEXT — comparison is case-insensitive at the DB level.
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        full_name: str,
    ) -> User:
        user = User(email=email, password_hash=password_hash, full_name=full_name)
        self._session.add(user)
        await self._session.flush()
        return user

    async def touch_last_login(self, user: User) -> None:
        user.last_login_at = datetime.now(UTC)
        await self._session.flush()
