"""
OTP Token model for storing one-time password verification codes.

"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.models.base import BaseModel
from app.core.db.models.user import User
from app.core.enums import OTPPurpose


class OTPToken(BaseModel):
    """
    Model for storing OTP (One-Time Password) tokens.

    OTP codes are stored as HMAC-SHA256 hashes for security while remaining
    queryable in the database. Each token has an expiration time and tracks
    verification attempts to prevent brute-force attacks.

    Attributes:
        user_id: Optional foreign key to the user (None for pre-registration OTPs).
        email: Email address the OTP was sent to.
        code_hash: HMAC-SHA256 hash of the OTP code (indexed for queries).
        purpose: The purpose of the OTP (email verification, password reset, etc.).
        expires_at: When the OTP expires.
        used_at: When the OTP was successfully used (None if unused).
        attempts: Number of verification attempts made.
    """

    __tablename__ = "otp_tokens"

    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            comment="Delete OTP when user is deleted",
        ),
        nullable=True,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    code_hash: Mapped[str] = mapped_column(
        String(64),  # SHA256 hex digest is 64 characters
        nullable=False,
        index=True,
    )

    purpose: Mapped[OTPPurpose] = mapped_column(
        Enum(OTPPurpose, native_enum=False, name="otp_purpose"),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Relationship to User (optional - for tracking)
    user: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[user_id],
    )


__all__ = ["OTPToken"]

