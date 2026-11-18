# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Data access for the `refresh_tokens` table.

The rotation primitive (`consume_if_active`) uses a single UPDATE that
checks both `revoked_at IS NULL` and `expires_at > now()` in the same
statement, so concurrent reuse of the same raw token cannot mint two
new pairs — only one transaction sees the row as still claimable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def find_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Plain lookup by hash. Returns rows regardless of revoke/expiry state.

        Used by reuse detection — when `consume_if_active` reports nothing
        to claim, the service needs to disambiguate "never existed" from
        "existed but already revoked" (the second case is the compromise
        signal).
        """
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def consume_if_active(self, token_hash: str) -> uuid.UUID | None:
        """Atomically revoke a token iff it's currently active. Returns user_id.

        The UPDATE matches `revoked_at IS NULL AND expires_at > now()` in
        the same statement, so two concurrent refresh attempts on the
        same raw token race for the row — exactly one wins, and the
        loser sees None here. The loser is then routed through the
        reuse-detection branch by the caller.

        Returns None if no active row matched. Caller cannot tell which
        of {not found, already revoked, expired} caused the miss; it
        must call `find_by_hash` to disambiguate.
        """
        now = datetime.now(UTC)
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .values(revoked_at=now)
            .returning(RefreshToken.user_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Mass-revoke every active refresh token for a user.

        Used on suspected-reuse: the entire session family is invalidated
        because we can't distinguish "attacker has the cookie" from "legit
        user's tab raced with another tab". Forcing re-login is the
        conservative choice.

        Returns the number of rows revoked (zero is a valid outcome — the
        user might have no active sessions left). Useful for telemetry.

        Uses RETURNING to count rows instead of `result.rowcount` — the
        latter isn't on the generic `Result[Any]` mypy sees from
        `session.execute`, and the row count here is small by definition.
        """
        now = datetime.now(UTC)
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .returning(RefreshToken.id)
        )
        result = await self._session.execute(stmt)
        return len(result.all())

    async def revoke_by_hash(self, token_hash: str) -> bool:
        """Revoke the matching active token, if any. Idempotent.

        Used by logout — unconditional cleanup. We deliberately do NOT
        treat an already-revoked or unknown token as suspicious here;
        logout must be safe to call from any client state, including
        "I'm not sure if I'm logged in." Reuse detection only fires
        on `consume_if_active`, the rotation primitive.

        Returns True if a row was updated, False otherwise.
        """
        now = datetime.now(UTC)
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .returning(RefreshToken.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
