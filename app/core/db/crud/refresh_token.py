"""
CRUD operations for RefreshToken model.

- Creating new tokens
- Looking up tokens by hash
- Revoking single tokens
- Revoking all tokens for a user (sign out all devices)
- Cleaning up expired tokens
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db.crud.base import BaseDB
from app.core.db.models.refresh_token import RefreshToken


class RefreshTokenDB(BaseDB[RefreshToken]):
    """
    Database operations for RefreshToken model.

    This class extends BaseDB to provide specialized operations for
    refresh token management including lookup, revocation, and cleanup.

    Example:
        >>> db = RefreshTokenDB()
        >>> token = await db.create(session, data={...})
        >>> found = await db.get_by_token_hash(session, "abc123...")
    """

    def __init__(self):
        super().__init__(model=RefreshToken)
        self.user_loader = selectinload(RefreshToken.user)

    async def get_by_token_hash(
        self,
        session: AsyncSession,
        token_hash: str,
        include_revoked: bool = False,
    ) -> RefreshToken | None:
        """
        Find a refresh token by its hash.

        Args:
            session: The database session.
            token_hash: The SHA256 hash of the refresh token.
            include_revoked: If True, include revoked tokens in results.

        Returns:
            The RefreshToken if found, None otherwise.

        Example:
            >>> token = await db.get_by_token_hash(session, "sha256hash...")
        """
        conditions = [
            self.model.token_hash == token_hash,
            self.model.is_deleted == False,  # noqa: E712
        ]

        if not include_revoked:
            conditions.append(self.model.revoked_at == None)  # noqa: E711

        return await self.get_one_by_conditions(
            session=session,
            conditions=conditions,
            options=[self.user_loader],
        )

    async def get_valid_token(
        self,
        session: AsyncSession,
        token_hash: str,
    ) -> RefreshToken | None:
        """
        Find a valid (not expired, not revoked) refresh token.

        Args:
            session: The database session.
            token_hash: The SHA256 hash of the refresh token.

        Returns:
            The valid RefreshToken if found, None otherwise.

        Example:
            >>> token = await db.get_valid_token(session, "sha256hash...")
            >>> if token:
            ...     print("Token is valid")
        """
        now = datetime.now(timezone.utc)

        conditions = [
            self.model.token_hash == token_hash,
            self.model.is_deleted == False,  # noqa: E712
            self.model.revoked_at == None,  # noqa: E711
            self.model.expires_at > now,
        ]

        return await self.get_one_by_conditions(
            session=session,
            conditions=conditions,
            options=[self.user_loader],
        )

    async def revoke(
        self,
        session: AsyncSession,
        token_hash: str,
        commit_self: bool = True,
    ) -> bool:
        """
        Revoke a refresh token by its hash.

        Args:
            session: The database session.
            token_hash: The SHA256 hash of the token to revoke.
            commit_self: Whether to commit the transaction.

        Returns:
            True if a token was revoked, False if token not found.

        Example:
            >>> revoked = await db.revoke(session, "sha256hash...")
        """
        now = datetime.now(timezone.utc)

        stmt = (
            update(self.model)
            .where(
                and_(
                    self.model.token_hash == token_hash,
                    self.model.revoked_at == None,  # noqa: E711
                )
            )
            .values(revoked_at=now, updated_at=now)
        )

        result = await session.execute(stmt)

        if commit_self:
            await session.commit()

        return result.rowcount > 0  # type: ignore[attr-defined]

    async def revoke_all_for_user(
        self,
        session: AsyncSession,
        user_id: UUID,
        commit_self: bool = True,
    ) -> int:
        """
        Revoke all refresh tokens for a user (sign out all devices).

        Args:
            session: The database session.
            user_id: The ID of the user whose tokens should be revoked.
            commit_self: Whether to commit the transaction.

        Returns:
            The number of tokens that were revoked.

        Example:
            >>> count = await db.revoke_all_for_user(session, user.id)
            >>> print(f"Revoked {count} tokens")
        """
        now = datetime.now(timezone.utc)

        stmt = (
            update(self.model)
            .where(
                and_(
                    self.model.user_id == user_id,
                    self.model.revoked_at == None,  # noqa: E711
                )
            )
            .values(revoked_at=now, updated_at=now)
        )

        result = await session.execute(stmt)

        if commit_self:
            await session.commit()

        return result.rowcount  # type: ignore[attr-defined]

    async def cleanup_expired(
        self,
        session: AsyncSession,
        commit_self: bool = True,
    ) -> int:
        """
        Soft-delete all expired and revoked tokens.

        This method marks tokens as deleted if they are either:
        - Expired (expires_at < now)
        - Revoked (revoked_at is not None)

        Args:
            session: The database session.
            commit_self: Whether to commit the transaction.

        Returns:
            The number of tokens that were cleaned up.

        Example:
            >>> count = await db.cleanup_expired(session)
            >>> print(f"Cleaned up {count} tokens")
        """
        now = datetime.now(timezone.utc)

        stmt = (
            update(self.model)
            .where(
                and_(
                    self.model.is_deleted == False,  # noqa: E712
                    # Expired OR revoked
                    (self.model.expires_at < now)
                    | (self.model.revoked_at != None),  # noqa: E711
                )
            )
            .values(is_deleted=True, deleted_at=now, updated_at=now)
        )

        result = await session.execute(stmt)

        if commit_self:
            await session.commit()

        return result.rowcount  # type: ignore[attr-defined]

    async def get_active_tokens_for_user(
        self,
        session: AsyncSession,
        user_id: UUID,
    ) -> list[RefreshToken]:
        """
        Get all active (non-expired, non-revoked) tokens for a user.

        Useful for displaying active sessions to the user.

        Args:
            session: The database session.
            user_id: The ID of the user.

        Returns:
            List of active RefreshToken instances.

        Example:
            >>> tokens = await db.get_active_tokens_for_user(session, user.id)
            >>> print(f"User has {len(tokens)} active sessions")
        """
        now = datetime.now(timezone.utc)

        conditions = [
            self.model.user_id == user_id,
            self.model.is_deleted == False,  # noqa: E712
            self.model.revoked_at == None,  # noqa: E711
            self.model.expires_at > now,
        ]

        return await self.get_by_conditions(  # type: ignore[return-value]
            session=session,
            conditions=conditions,
        )

