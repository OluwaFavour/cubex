"""
Subscription model for tracking billing across products.

"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.models.base import BaseModel
from app.core.enums import ProductType, SubscriptionStatus

# Forward reference for type hints
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.db.models.plan import Plan
    from app.core.db.models.subscription_context import (
        APISubscriptionContext,
        CareerSubscriptionContext,
    )


class Subscription(BaseModel):
    """
    Model for subscriptions across products.

    Product-agnostic subscription model that tracks Stripe subscription
    state, billing periods, and seat allocation. Linked to workspaces
    (API) or users (Career) via context tables.

    Attributes:
        plan_id: Foreign key to the subscribed plan.
        product_type: Product discriminator (API or CAREER).
        stripe_subscription_id: Stripe Subscription ID.
        stripe_customer_id: Stripe Customer ID.
        status: Current subscription status.
        seat_count: Number of seats (always 1 for Career).
        current_period_start: Start of current billing period.
        current_period_end: End of current billing period.
        cancel_at_period_end: Whether subscription cancels at period end.
        canceled_at: When subscription was canceled.
        trial_start: Trial period start (if applicable).
        trial_end: Trial period end (if applicable).
        amount: Current billing amount per period.
    """

    __tablename__ = "subscriptions"

    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "plans.id",
            ondelete="RESTRICT",
            comment="Prevent deleting plans with active subscriptions",
        ),
        nullable=False,
        index=True,
    )

    # Product discriminator
    product_type: Mapped[ProductType] = mapped_column(
        Enum(ProductType, native_enum=False, name="product_type"),
        nullable=False,
        index=True,
        default=ProductType.API,
        comment="Product this subscription belongs to (API or CAREER)",
    )

    # Stripe identifiers
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
        index=True,
        comment="Stripe Subscription ID (null for free plans)",
    )

    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
        comment="Stripe Customer ID",
    )

    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, native_enum=False, name="subscription_status"),
        nullable=False,
        index=True,
        default=SubscriptionStatus.ACTIVE,
    )

    # Seat management
    seat_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Number of seats purchased",
    )

    # Billing period
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Cancellation
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Trial period
    trial_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    trial_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Billing amount (for display/tracking)
    amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Current billing amount per period",
    )

    # Relationships
    plan: Mapped["Plan"] = relationship(
        "Plan",
        foreign_keys=[plan_id],
        lazy="selectin",
    )

    # Context relationships (one-to-one via uselist=False)
    api_context: Mapped["APISubscriptionContext | None"] = relationship(
        "APISubscriptionContext",
        back_populates="subscription",
        uselist=False,
        lazy="raise",
        cascade="all, delete-orphan",
    )

    career_context: Mapped["CareerSubscriptionContext | None"] = relationship(
        "CareerSubscriptionContext",
        back_populates="subscription",
        uselist=False,
        lazy="raise",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("seat_count >= 1", name="ck_subscriptions_seat_count_positive"),
        Index("ix_subscriptions_product_type_status", "product_type", "status"),
    )

    @property
    def is_active(self) -> bool:
        """Check if subscription is in active state."""
        return self.status in (
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING,
        )

    @property
    def is_canceled(self) -> bool:
        """Check if subscription is canceled."""
        return self.status == SubscriptionStatus.CANCELED

    @property
    def is_past_due(self) -> bool:
        """Check if subscription has payment issues."""
        return self.status in (
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.UNPAID,
        )

    @property
    def requires_action(self) -> bool:
        """Check if subscription requires user action."""
        return self.status in (
            SubscriptionStatus.INCOMPLETE,
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.UNPAID,
        )


class StripeEventLog(BaseModel):
    """
    Model for tracking processed Stripe webhook events.

    Used to prevent duplicate event processing (idempotency).

    Attributes:
        event_id: Stripe event ID (unique).
        event_type: Type of Stripe event (e.g., 'invoice.paid').
        processed_at: When the event was processed.
    """

    __tablename__ = "stripe_event_logs"

    event_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
        comment="Stripe event ID for deduplication",
    )

    event_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


__all__ = ["Subscription", "StripeEventLog"]
