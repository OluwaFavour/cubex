"""
Refresh Token model for persistent session management.

"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.models.base import BaseModel

if TYPE_CHECKING:
    from app.core.db.models.user import User


class RefreshToken(BaseModel):
    """
    Model for storing refresh tokens.

    Refresh tokens are long-lived tokens stored in the database that allow
    users to obtain new access tokens without re-authenticating. This enables:
    - "Remember me" functionality with extended session duration
    - Multi-device session management
    - Secure token revocation (sign out, sign out all devices)

    Attributes:
        user_id: Foreign key to the user who owns this token.
        token_hash: SHA256 hash of the refresh token (never store plain tokens).
        expires_at: When this token expires.
        device_info: Optional device/client information (user agent, IP, etc.).
        revoked_at: When the token was revoked (None if still valid).
        user: Relationship to the User model.

    Example:
        >>> token = RefreshToken(
        ...     user_id=user.id,
        ...     token_hash=sha256_hash(refresh_token),
        ...     expires_at=datetime.now() + timedelta(days=7),
        ...     device_info="Mozilla/5.0...",
        ... )
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),  # SHA256 produces 64 hex characters
        unique=True,
        index=True,
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    device_info: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(  # noqa: F821
        "User",
        back_populates="refresh_tokens",
    )

    def __repr__(self) -> str:
        return (
            f"<RefreshToken(id={self.id}, user_id={self.user_id}, "
            f"expires_at={self.expires_at}, revoked={self.revoked_at is not None})>"
        )

    @property
    def is_valid(self) -> bool:
        """Check if the token is still valid (not expired and not revoked)."""
        now = datetime.now(timezone.utc)
        return self.revoked_at is None and self.expires_at > now and not self.is_deleted
