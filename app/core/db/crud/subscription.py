"""
CRUD operations for Subscription and StripeEventLog models.

"""

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.db.crud.base import BaseDB
from app.core.db.models.subscription import Subscription, StripeEventLog
from app.core.db.models.subscription_context import (
    APISubscriptionContext,
    CareerSubscriptionContext,
)
from app.core.enums import ProductType, SubscriptionStatus


class SubscriptionDB(BaseDB[Subscription]):
    """CRUD operations for Subscription model."""

    def __init__(self):
        super().__init__(Subscription)
        self.plan_loader = joinedload(Subscription.plan)

    async def get_by_workspace(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        active_only: bool = True,
    ) -> Subscription | None:
        """
        Get API subscription for a workspace via context table.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            active_only: If True, only return active subscriptions.

        Returns:
            The subscription or None if not found.
        """
        stmt = (
            select(Subscription)
            .join(
                APISubscriptionContext,
                Subscription.id == APISubscriptionContext.subscription_id,
            )
            .where(
                APISubscriptionContext.workspace_id == workspace_id,
                Subscription.is_deleted.is_(False),
                Subscription.product_type == ProductType.API,
            )
            .options(joinedload(Subscription.api_context))
        )

        if active_only:
            stmt = stmt.where(
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
                )
            )

        result = await session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_by_user(
        self,
        session: AsyncSession,
        user_id: UUID,
        active_only: bool = True,
    ) -> Subscription | None:
        """
        Get Career subscription for a user via context table.

        Args:
            session: Database session.
            user_id: User ID.
            active_only: If True, only return active subscriptions.

        Returns:
            The subscription or None if not found.
        """
        stmt = (
            select(Subscription)
            .join(
                CareerSubscriptionContext,
                Subscription.id == CareerSubscriptionContext.subscription_id,
            )
            .where(
                CareerSubscriptionContext.user_id == user_id,
                Subscription.is_deleted.is_(False),
                Subscription.product_type == ProductType.CAREER,
            )
            .options(joinedload(Subscription.career_context))
        )

        if active_only:
            stmt = stmt.where(
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
                )
            )

        result = await session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_by_stripe_subscription_id(
        self,
        session: AsyncSession,
        stripe_subscription_id: str,
    ) -> Subscription | None:
        """
        Get subscription by Stripe subscription ID.

        Eagerly loads ``api_context`` and ``career_context`` so callers
        can inspect the related workspace/user without extra queries.

        Args:
            session: Database session.
            stripe_subscription_id: Stripe Subscription ID.

        Returns:
            The subscription or None if not found.
        """
        return await self.get_one_by_filters(
            session,
            {
                "stripe_subscription_id": stripe_subscription_id,
                "is_deleted": False,
            },
            options=[
                joinedload(Subscription.api_context),
                joinedload(Subscription.career_context),
            ],
        )

    async def get_by_stripe_customer_id(
        self,
        session: AsyncSession,
        stripe_customer_id: str,
    ) -> Sequence[Subscription]:
        """
        Get all subscriptions for a Stripe customer.

        Args:
            session: Database session.
            stripe_customer_id: Stripe Customer ID.

        Returns:
            List of subscriptions.
        """
        return await self.get_by_filters(
            session,
            {
                "stripe_customer_id": stripe_customer_id,
                "is_deleted": False,
            },
        )

    async def update_status(
        self,
        session: AsyncSession,
        subscription_id: UUID,
        status: SubscriptionStatus,
        commit_self: bool = True,
    ) -> Subscription | None:
        """
        Update subscription status.

        Args:
            session: Database session.
            subscription_id: Subscription ID.
            status: New status.
            commit_self: Whether to commit the transaction.

        Returns:
            Updated subscription or None if not found.
        """
        return await self.update(
            session,
            subscription_id,
            {"status": status},
            commit_self=commit_self,
        )


class StripeEventLogDB(BaseDB[StripeEventLog]):
    """CRUD operations for StripeEventLog model (webhook deduplication)."""

    def __init__(self):
        super().__init__(StripeEventLog)

    async def is_event_processed(
        self,
        session: AsyncSession,
        event_id: str,
    ) -> bool:
        """
        Check if a Stripe event has already been processed.

        Args:
            session: Database session.
            event_id: Stripe event ID.

        Returns:
            True if event was already processed.
        """
        return await self.exists(session, {"event_id": event_id})

    async def mark_event_processed(
        self,
        session: AsyncSession,
        event_id: str,
        event_type: str,
        commit_self: bool = True,
    ) -> StripeEventLog:
        """
        Mark a Stripe event as processed.

        Args:
            session: Database session.
            event_id: Stripe event ID.
            event_type: Type of event.
            commit_self: Whether to commit the transaction.

        Returns:
            Created event log entry.
        """
        return await self.create(
            session,
            {
                "event_id": event_id,
                "event_type": event_type,
                "processed_at": datetime.now(timezone.utc),
            },
            commit_self=commit_self,
        )


__all__ = ["SubscriptionDB", "StripeEventLogDB"]
