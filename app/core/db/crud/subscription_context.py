"""
CRUD operations for subscription context models.

"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.db.crud.base import BaseDB
from app.core.db.models.subscription_context import (
    APISubscriptionContext,
    CareerSubscriptionContext,
)


class APISubscriptionContextDB(BaseDB[APISubscriptionContext]):
    """CRUD operations for APISubscriptionContext model."""

    def __init__(self):
        super().__init__(APISubscriptionContext)

    async def get_by_workspace(
        self,
        session: AsyncSession,
        workspace_id: UUID,
    ) -> APISubscriptionContext | None:
        """
        Get API subscription context for a workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.

        Returns:
            The context or None if not found.
        """
        stmt = (
            select(APISubscriptionContext)
            .where(
                APISubscriptionContext.workspace_id == workspace_id,
                APISubscriptionContext.is_deleted.is_(False),
            )
            .options(joinedload(APISubscriptionContext.subscription))
        )
        result = await session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_by_subscription(
        self,
        session: AsyncSession,
        subscription_id: UUID,
    ) -> APISubscriptionContext | None:
        """
        Get API subscription context for a subscription.

        Args:
            session: Database session.
            subscription_id: Subscription ID.

        Returns:
            The context or None if not found.
        """
        stmt = (
            select(APISubscriptionContext)
            .where(
                APISubscriptionContext.subscription_id == subscription_id,
                APISubscriptionContext.is_deleted.is_(False),
            )
            .options(joinedload(APISubscriptionContext.workspace))
        )
        result = await session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def increment_credits_used(
        self,
        session: AsyncSession,
        context_id: UUID,
        amount: Decimal,
    ) -> None:
        """
        Atomically increment credits_used.

        Uses UPDATE ... SET credits_used = credits_used + amount
        for thread-safe atomic increment.

        Args:
            session: Database session.
            context_id: Context ID.
            amount: Amount to add.
        """
        stmt = (
            update(APISubscriptionContext)
            .where(
                APISubscriptionContext.id == context_id,
                APISubscriptionContext.is_deleted.is_(False),
            )
            .values(credits_used=APISubscriptionContext.credits_used + amount)
        )
        await session.execute(stmt)

    async def reset_credits_used(
        self,
        session: AsyncSession,
        context_id: UUID,
    ) -> None:
        """
        Reset credits_used to 0.

        Called when billing period changes (subscription renewal).

        Args:
            session: Database session.
            context_id: Context ID.
        """
        stmt = (
            update(APISubscriptionContext)
            .where(
                APISubscriptionContext.id == context_id,
                APISubscriptionContext.is_deleted.is_(False),
            )
            .values(credits_used=Decimal("0.00"))
        )
        await session.execute(stmt)


class CareerSubscriptionContextDB(BaseDB[CareerSubscriptionContext]):
    """CRUD operations for CareerSubscriptionContext model."""

    def __init__(self):
        super().__init__(CareerSubscriptionContext)

    async def get_by_user(
        self,
        session: AsyncSession,
        user_id: UUID,
    ) -> CareerSubscriptionContext | None:
        """
        Get Career subscription context for a user.

        Args:
            session: Database session.
            user_id: User ID.

        Returns:
            The context or None if not found.
        """
        stmt = (
            select(CareerSubscriptionContext)
            .where(
                CareerSubscriptionContext.user_id == user_id,
                CareerSubscriptionContext.is_deleted.is_(False),
            )
            .options(joinedload(CareerSubscriptionContext.subscription))
        )
        result = await session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_by_subscription(
        self,
        session: AsyncSession,
        subscription_id: UUID,
    ) -> CareerSubscriptionContext | None:
        """
        Get Career subscription context for a subscription.

        Args:
            session: Database session.
            subscription_id: Subscription ID.

        Returns:
            The context or None if not found.
        """
        stmt = (
            select(CareerSubscriptionContext)
            .where(
                CareerSubscriptionContext.subscription_id == subscription_id,
                CareerSubscriptionContext.is_deleted.is_(False),
            )
            .options(joinedload(CareerSubscriptionContext.user))
        )
        result = await session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def increment_credits_used(
        self,
        session: AsyncSession,
        context_id: UUID,
        amount: Decimal,
    ) -> None:
        """
        Atomically increment credits_used.

        Uses UPDATE ... SET credits_used = credits_used + amount
        for thread-safe atomic increment.

        Args:
            session: Database session.
            context_id: Context ID.
            amount: Amount to add.
        """
        stmt = (
            update(CareerSubscriptionContext)
            .where(
                CareerSubscriptionContext.id == context_id,
                CareerSubscriptionContext.is_deleted.is_(False),
            )
            .values(credits_used=CareerSubscriptionContext.credits_used + amount)
        )
        await session.execute(stmt)

    async def reset_credits_used(
        self,
        session: AsyncSession,
        context_id: UUID,
    ) -> None:
        """
        Reset credits_used to 0.

        Called when billing period changes (subscription renewal).

        Args:
            session: Database session.
            context_id: Context ID.
        """
        stmt = (
            update(CareerSubscriptionContext)
            .where(
                CareerSubscriptionContext.id == context_id,
                CareerSubscriptionContext.is_deleted.is_(False),
            )
            .values(credits_used=Decimal("0.00"))
        )
        await session.execute(stmt)


__all__ = ["APISubscriptionContextDB", "CareerSubscriptionContextDB"]

