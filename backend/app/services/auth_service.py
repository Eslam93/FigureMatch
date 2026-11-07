"""Auth business logic: register, login, refresh, logout, current user.

The refresh path uses single-use rotation: the incoming token is claimed
atomically (`consume_if_active`) and a fresh pair is issued in the same
transaction. If the atomic claim misses but a matching row exists in
the revoked state, that's reuse — a previously-spent token presented
again — and the entire session family for that user is revoked. That
revocation is committed before the 401 is raised, so the request's
rollback-on-error can't undo it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, UnauthorizedError, ValidationError
from app.core.logging import get_logger
from app.core.security import (
    PasswordTooWeakError,
    create_access_token,
    generate_refresh_token,
    get_dummy_password_hash,
    hash_password,
    hash_refresh_token,
    validate_password_strength,
    verify_password,
)
from app.db.models import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository

log = get_logger(__name__)


@dataclass(frozen=True)
class AuthTokens:
    """The pair issued on login / register.

    `access_token` goes in the response body; `refresh_token_raw` is the
    value the route sets into an httpOnly cookie.
    """

    access_token: str
    access_expires_in: int
    refresh_token_raw: str
    refresh_expires_at: datetime


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._refresh_tokens = RefreshTokenRepository(session)

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, AuthTokens]:
        try:
            validate_password_strength(password)
        except PasswordTooWeakError as exc:
            raise ValidationError(str(exc), code="WEAK_PASSWORD") from exc

        try:
            user = await self._users.create(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
            )
        except IntegrityError as exc:
            # The unique constraint on users.email — case-insensitive via CITEXT.
            await self._session.rollback()
            raise ConflictError(
                "Email is already registered.",
                code="EMAIL_TAKEN",
                details={"field": "email"},
            ) from exc

        tokens = await self._mint_tokens(user, user_agent=user_agent, ip_address=ip_address)
        return user, tokens

    async def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, AuthTokens]:
        user = await self._users.find_by_email(email)
        # ALWAYS run bcrypt verify, even when the email is unknown — use a
        # cached dummy hash for the missing case. Without this, the unknown
        # email path returns in ~5ms and the wrong-password path in ~250ms,
        # making registered emails distinguishable by latency. Same response
        # body + same compute cost = no enumeration via timing.
        password_ok = verify_password(
            password,
            user.password_hash if user is not None else get_dummy_password_hash(),
        )
        if user is None or not password_ok:
            raise UnauthorizedError("Invalid email or password.", code="INVALID_CREDENTIALS")
        await self._users.touch_last_login(user)
        tokens = await self._mint_tokens(user, user_agent=user_agent, ip_address=ip_address)
        return user, tokens

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self._users.find_by_id(user_id)
        if user is None:
            raise UnauthorizedError("Authenticated user no longer exists.")
        return user

    async def refresh(
        self,
        *,
        raw_refresh: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, AuthTokens]:
        """Rotate a refresh token. Single-use; reuse triggers family revocation.

        Concurrent legitimate refreshes with the same raw token are
        indistinguishable from replay-by-attacker: only one transaction
        wins the atomic claim, and the loser's view (revoked row) looks
        identical to reuse. We treat both as compromise, which revokes
        every refresh token the user holds and so signs them out on every
        device. The client-side mitigation is request deduplication — a
        well-behaved SPA should serialize its refresh requests across all
        of its tabs, not just behind one tab's in-flight promise.
        """
        token_hash = hash_refresh_token(raw_refresh)
        claimed_user_id = await self._refresh_tokens.consume_if_active(token_hash)

        if claimed_user_id is None:
            await self._handle_refresh_miss(token_hash)
            raise UnauthorizedError(
                "Refresh token is invalid or expired.",
                code="INVALID_REFRESH_TOKEN",
            )

        user = await self._users.find_by_id(claimed_user_id)
        if user is None:
            # The user was deleted between issuing the token and refresh.
            # The token is already revoked (we just claimed it), so no
            # further cleanup is needed.
            raise UnauthorizedError(
                "Refresh token is invalid or expired.",
                code="INVALID_REFRESH_TOKEN",
            )

        tokens = await self._mint_tokens(
            user,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return user, tokens

    async def logout(self, *, raw_refresh: str | None) -> None:
        """Revoke the given refresh token if it exists. Idempotent.

        No-op when the cookie is missing or the token is unknown — the
        cookie clears on the response side regardless. Intentionally
        does NOT trigger reuse detection: a user calling logout with a
        revoked token is confused, not compromised.
        """
        if not raw_refresh:
            return
        token_hash = hash_refresh_token(raw_refresh)
        await self._refresh_tokens.revoke_by_hash(token_hash)

    async def _handle_refresh_miss(self, token_hash: str) -> None:
        """Decide what a `consume_if_active` miss means and react.

        Four causes of a miss:
          1. The hash never existed → no action (unknown token).
          2. Row exists, `revoked_at IS NULL`, expired → no action
             (legitimate token that the user waited too long to refresh).
          3. Row exists, revoked, AND would still be valid → reuse
             signal. Mass-revoke the user's active token family and
             commit it straight away.
          4. Row exists, revoked, AND already expired → no action.
             This is an old cookie from a logged-out session resurfacing
             (browser cookie cache, backup restore, etc.). The attacker
             value of an expired-and-revoked token is zero, so treating
             it as compromise would punish users for harmless cookie
             weirdness. Reuse detection only fires when the replayed
             token would otherwise still grant access.
        """
        existing = await self._refresh_tokens.find_by_hash(token_hash)
        if existing is None or existing.revoked_at is None:
            return
        if existing.expires_at <= datetime.now(UTC):
            return
        revoked_count = await self._refresh_tokens.revoke_all_for_user(existing.user_id)
        # Commit now: the caller raises a 401 next, and get_db_session rolls
        # back on any exception, which would silently undo this revocation.
        await self._session.commit()
        log.warning(
            "refresh_token_reuse_detected",
            user_id=str(existing.user_id),
            revoked_token_id=str(existing.id),
            family_revoked_count=revoked_count,
        )

    async def _mint_tokens(
        self,
        user: User,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthTokens:
        settings = get_settings()
        access_token = create_access_token(subject=str(user.id))
        raw_refresh, hashed_refresh = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_token_ttl_seconds)
        await self._refresh_tokens.create(
            user_id=user.id,
            token_hash=hashed_refresh,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return AuthTokens(
            access_token=access_token,
            access_expires_in=settings.jwt_access_token_ttl_seconds,
            refresh_token_raw=raw_refresh,
            refresh_expires_at=expires_at,
        )
