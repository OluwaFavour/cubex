from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db.models.base import BaseModel
from app.shared.enums import OAuthProviders

if TYPE_CHECKING:
    from app.shared.db.models.refresh_token import RefreshToken
    from app.shared.db.models.subscription import Subscription
    from app.shared.db.models.subscription_context import CareerSubscriptionContext


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    full_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    avatar_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=True,
        comment="Stripe Customer ID for billing across all products",
    )

    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        "OAuthAccount",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Career subscription context relationship (one-to-one)
    career_subscription_context: Mapped["CareerSubscriptionContext | None"] = (
        relationship(
            "CareerSubscriptionContext",
            back_populates="user",
            uselist=False,
            lazy="selectin",
            cascade="all, delete-orphan",
        )
    )

    # Association proxy for convenient access: user.career_subscription
    career_subscription: AssociationProxy["Subscription | None"] = association_proxy(
        "career_subscription_context",
        "subscription",
    )


class OAuthAccount(BaseModel):
    __tablename__ = "oauth_accounts"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            comment="Delete account when user is deleted",
        ),
        nullable=False,
    )

    provider: Mapped[OAuthProviders] = mapped_column(
        Enum(OAuthProviders, native_enum=False, name="oauth_providers"),
        nullable=False,
    )

    provider_account_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="oauth_accounts",
    )
