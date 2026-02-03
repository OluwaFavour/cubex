"""
Subscription context models for product-specific subscription linking.

This module provides context tables that link subscriptions to their
domain entities (workspaces for API, users for Career) via one-to-one
relationships with unique constraints.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db.models.base import BaseModel

# Forward references for type hints
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.apps.cubex_api.db.models.workspace import Workspace
    from app.shared.db.models.subscription import Subscription
    from app.shared.db.models.user import User


class APISubscriptionContext(BaseModel):
    """
    Context table linking API subscriptions to workspaces.

    Enforces one-to-one relationship: each workspace can have at most
    one subscription, and each subscription can belong to at most one
    workspace.

    Attributes:
        subscription_id: Foreign key to subscription (unique).
        workspace_id: Foreign key to workspace (unique).
    """

    __tablename__ = "api_subscription_contexts"

    subscription_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "subscriptions.id",
            ondelete="CASCADE",
            comment="Delete context when subscription is deleted",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            ondelete="CASCADE",
            comment="Delete context when workspace is deleted",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    # Relationships
    subscription: Mapped["Subscription"] = relationship(
        "Subscription",
        foreign_keys=[subscription_id],
        back_populates="api_context",
        lazy="selectin",
    )

    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        foreign_keys=[workspace_id],
        back_populates="api_subscription_context",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            name="uq_api_subscription_context_subscription",
        ),
        UniqueConstraint(
            "workspace_id",
            name="uq_api_subscription_context_workspace",
        ),
    )


class CareerSubscriptionContext(BaseModel):
    """
    Context table linking Career subscriptions to users.

    Enforces one-to-one relationship: each user can have at most
    one career subscription, and each subscription can belong to
    at most one user.

    Attributes:
        subscription_id: Foreign key to subscription (unique).
        user_id: Foreign key to user (unique).
    """

    __tablename__ = "career_subscription_contexts"

    subscription_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "subscriptions.id",
            ondelete="CASCADE",
            comment="Delete context when subscription is deleted",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            comment="Delete context when user is deleted",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    # Relationships
    subscription: Mapped["Subscription"] = relationship(
        "Subscription",
        foreign_keys=[subscription_id],
        back_populates="career_context",
        lazy="selectin",
    )

    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="career_subscription_context",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            name="uq_career_subscription_context_subscription",
        ),
        UniqueConstraint(
            "user_id",
            name="uq_career_subscription_context_user",
        ),
    )


__all__ = ["APISubscriptionContext", "CareerSubscriptionContext"]
