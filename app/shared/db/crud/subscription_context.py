"""
CRUD operations for subscription context models.

This module provides database operations for managing the context tables
that link subscriptions to workspaces (API) or users (Career).
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.shared.db.crud.base import BaseDB
from app.shared.db.models.subscription_context import (
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


__all__ = ["APISubscriptionContextDB", "CareerSubscriptionContextDB"]
