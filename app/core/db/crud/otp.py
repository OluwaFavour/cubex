"""
CRUD operations for OTPToken model.

This module provides database operations for OTP token management including
creation, verification, and cleanup of expired tokens.
"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.crud.base import BaseDB
from app.core.db.models.otp import OTPToken
from app.core.enums import OTPPurpose
from app.core.exceptions.types import DatabaseException


class OTPTokenDB(BaseDB[OTPToken]):
    """
    CRUD operations for OTPToken model.

    Provides specialized methods for OTP token management including
    finding valid tokens by hash, incrementing attempt counts, and
    marking tokens as used.
    """

    def __init__(self):
        """Initialize OTPTokenDB with the OTPToken model."""
        super().__init__(model=OTPToken)

    async def get_valid_token_by_hash(
        self,
        session: AsyncSession,
        code_hash: str,
        email: str,
        purpose: OTPPurpose,
    ) -> OTPToken | None:
        """
        Retrieve a valid (non-expired, unused) OTP token by its hash.

        This method finds an OTP token that matches the given hash, email,
        and purpose, and has not expired or been used.

        Args:
            session: The async database session.
            code_hash: The HMAC-SHA256 hash of the OTP code.
            email: The email address the OTP was sent to.
            purpose: The purpose of the OTP.

        Returns:
            The OTPToken if found and valid, None otherwise.

        Raises:
            DatabaseException: If a database error occurs.
        """
        try:
            now = datetime.now(timezone.utc)
            return await self.get_one_by_conditions(
                session=session,
                conditions=[
                    self.model.code_hash == code_hash,
                    self.model.email == email,
                    self.model.purpose == purpose,
                    self.model.expires_at > now,
                    self.model.used_at.is_(None),
                    self.model.is_deleted.is_(False),
                ],
            )
        except Exception as e:
            raise DatabaseException(
                f"Error retrieving valid OTP token: {str(e)}"
            ) from e

    async def get_latest_token_for_email(
        self,
        session: AsyncSession,
        email: str,
        purpose: OTPPurpose,
    ) -> OTPToken | None:
        """
        Retrieve the latest OTP token for an email and purpose.

        This method finds the most recently created OTP token for the
        given email and purpose, regardless of expiration or usage status.
        Useful for checking if a recent OTP exists before sending a new one.

        Args:
            session: The async database session.
            email: The email address.
            purpose: The purpose of the OTP.

        Returns:
            The most recent OTPToken if found, None otherwise.

        Raises:
            DatabaseException: If a database error occurs.
        """
        try:
            result = await self.get_all(
                session=session,
                filters=[
                    self.model.email == email,
                    self.model.purpose == purpose,
                    self.model.is_deleted == False,  # noqa: E712
                ],
                order_by=[self.model.created_at.desc()],
                limit=1,
            )
            return result[0] if result else None
        except Exception as e:
            raise DatabaseException(
                f"Error retrieving latest OTP token: {str(e)}"
            ) from e

    async def increment_attempts(
        self,
        session: AsyncSession,
        token: OTPToken,
        commit_self: bool = True,
    ) -> OTPToken:
        """
        Increment the attempt counter for an OTP token.

        Args:
            session: The async database session.
            token: The OTP token to update.
            commit_self: Whether to commit the session after updating.

        Returns:
            The updated OTPToken.

        Raises:
            DatabaseException: If a database error occurs.
        """
        try:
            token.attempts += 1
            session.add(token)
            if commit_self:
                await session.commit()
            else:
                await session.flush()
            await session.refresh(token)
            return token
        except Exception as e:
            raise DatabaseException(f"Error incrementing OTP attempts: {str(e)}") from e

    async def mark_as_used(
        self,
        session: AsyncSession,
        token: OTPToken,
        commit_self: bool = True,
    ) -> OTPToken:
        """
        Mark an OTP token as used.

        Args:
            session: The async database session.
            token: The OTP token to mark as used.
            commit_self: Whether to commit the session after updating.

        Returns:
            The updated OTPToken.

        Raises:
            DatabaseException: If a database error occurs.
        """
        try:
            token.used_at = datetime.now(timezone.utc)
            session.add(token)
            if commit_self:
                await session.commit()
            else:
                await session.flush()
            await session.refresh(token)
            return token
        except Exception as e:
            raise DatabaseException(f"Error marking OTP as used: {str(e)}") from e

    async def invalidate_previous_tokens(
        self,
        session: AsyncSession,
        email: str,
        purpose: OTPPurpose,
        commit_self: bool = True,
    ) -> int:
        """
        Soft-delete all previous unused OTP tokens for an email and purpose.

        This should be called when sending a new OTP to ensure only
        the latest OTP is valid.

        Args:
            session: The async database session.
            email: The email address.
            purpose: The purpose of the OTP.
            commit_self: Whether to commit the session after updating.

        Returns:
            The number of tokens invalidated.

        Raises:
            DatabaseException: If a database error occurs.
        """
        try:

            now = datetime.now(timezone.utc)
            result = await self.update_by_conditions(
                session=session,
                conditions=[
                    self.model.email == email,
                    self.model.purpose == purpose,
                    self.model.used_at.is_(None),
                    self.model.is_deleted.is_(False),
                ],
                updates={
                    "is_deleted": True,
                    "deleted_at": now,
                },
                commit_self=commit_self,
            )
            return result
        except Exception as e:
            raise DatabaseException(
                f"Error invalidating previous OTP tokens: {str(e)}"
            ) from e


__all__ = ["OTPTokenDB"]
