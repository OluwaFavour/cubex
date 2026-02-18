"""
CRUD operations for Quota models.

This module provides database operations for endpoint cost configurations
and plan pricing rules.
"""

from decimal import Decimal
from typing import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.apps.cubex_api.db.models.quota import EndpointCostConfig, PlanPricingRule
from app.core.db.crud.base import BaseDB
from app.core.exceptions.types import DatabaseException


class EndpointCostConfigDB(BaseDB[EndpointCostConfig]):
    """CRUD operations for EndpointCostConfig model."""

    def __init__(self):
        """Initialize with EndpointCostConfig model."""
        super().__init__(EndpointCostConfig)

    async def get_by_endpoint(
        self,
        session: AsyncSession,
        endpoint: str,
    ) -> EndpointCostConfig | None:
        """
        Get endpoint cost configuration by endpoint path.

        Args:
            session: Database session.
            endpoint: The API endpoint path.

        Returns:
            EndpointCostConfig or None if not found.
        """
        return await self.get_one_by_filters(
            session,
            {"endpoint": endpoint, "is_deleted": False},
        )

    async def get_all_active(
        self,
        session: AsyncSession,
    ) -> Sequence[EndpointCostConfig]:
        """
        Get all active endpoint cost configurations.

        Args:
            session: Database session.

        Returns:
            List of active endpoint cost configurations.
        """
        stmt = select(EndpointCostConfig).where(
            EndpointCostConfig.is_deleted == False  # noqa: E712
        )
        try:
            result = await session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            raise DatabaseException(
                f"Error getting endpoint cost configs: {str(e)}"
            ) from e

    async def create_or_update(
        self,
        session: AsyncSession,
        endpoint: str,
        internal_cost_credits: Decimal,
    ) -> EndpointCostConfig:
        """
        Create or update an endpoint cost configuration.

        If the endpoint already exists, updates its cost. Otherwise creates new.

        Args:
            session: Database session.
            endpoint: The API endpoint path.
            internal_cost_credits: The internal credit cost.

        Returns:
            Created or updated EndpointCostConfig.

        Raises:
            DatabaseException: If update fails unexpectedly.
        """
        existing = await self.get_by_endpoint(session, endpoint)
        if existing:
            updated = await self.update(
                session,
                existing.id,
                {"internal_cost_credits": internal_cost_credits},
            )
            if updated is None:
                raise DatabaseException(
                    f"Failed to update EndpointCostConfig for endpoint {endpoint}"
                )
            return updated
        return await self.create(
            session,
            {"endpoint": endpoint, "internal_cost_credits": internal_cost_credits},
        )


class PlanPricingRuleDB(BaseDB[PlanPricingRule]):
    """CRUD operations for PlanPricingRule model."""

    def __init__(self):
        """Initialize with PlanPricingRule model."""
        super().__init__(PlanPricingRule)
        self.plan_loader = selectinload(PlanPricingRule.plan)

    async def get_by_plan_id(
        self,
        session: AsyncSession,
        plan_id: UUID,
    ) -> PlanPricingRule | None:
        """
        Get plan pricing rule by plan ID.

        Args:
            session: Database session.
            plan_id: The plan UUID.

        Returns:
            PlanPricingRule or None if not found.
        """
        return await self.get_one_by_filters(
            session,
            {"plan_id": plan_id, "is_deleted": False},
        )

    async def get_all_active(
        self,
        session: AsyncSession,
    ) -> Sequence[PlanPricingRule]:
        """
        Get all active plan pricing rules.

        Args:
            session: Database session.

        Returns:
            List of active plan pricing rules.
        """
        stmt = select(PlanPricingRule).where(
            PlanPricingRule.is_deleted == False  # noqa: E712
        )
        try:
            result = await session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            raise DatabaseException(
                f"Error getting plan pricing rules: {str(e)}"
            ) from e

    async def create_or_update(
        self,
        session: AsyncSession,
        plan_id: UUID,
        multiplier: Decimal | None = None,
        credits_allocation: Decimal | None = None,
        rate_limit_per_minute: int | None = None,
    ) -> PlanPricingRule:
        """
        Create or update a plan pricing rule.

        If the plan already has a pricing rule, updates it. Otherwise creates new.

        Args:
            session: Database session.
            plan_id: The plan UUID.
            multiplier: The pricing multiplier (optional).
            credits_allocation: The credits allocation (optional).
            rate_limit_per_minute: The rate limit per minute (optional).

        Returns:
            Created or updated PlanPricingRule.

        Raises:
            DatabaseException: If update fails unexpectedly.
        """
        existing = await self.get_by_plan_id(session, plan_id)

        update_data: dict = {}
        if multiplier is not None:
            update_data["multiplier"] = multiplier
        if credits_allocation is not None:
            update_data["credits_allocation"] = credits_allocation
        if rate_limit_per_minute is not None:
            update_data["rate_limit_per_minute"] = rate_limit_per_minute

        if existing:
            if update_data:
                updated = await self.update(session, existing.id, update_data)
                if updated is None:
                    raise DatabaseException(
                        f"Failed to update PlanPricingRule for plan {plan_id}"
                    )
                return updated
            return existing

        # For new creation, use defaults for non-provided values
        create_data: dict = {"plan_id": plan_id}
        if multiplier is not None:
            create_data["multiplier"] = multiplier
        if credits_allocation is not None:
            create_data["credits_allocation"] = credits_allocation
        if rate_limit_per_minute is not None:
            create_data["rate_limit_per_minute"] = rate_limit_per_minute

        return await self.create(session, create_data)


# Global instances for dependency injection
endpoint_cost_config_db = EndpointCostConfigDB()
plan_pricing_rule_db = PlanPricingRuleDB()


__all__ = [
    "EndpointCostConfigDB",
    "PlanPricingRuleDB",
    "endpoint_cost_config_db",
    "plan_pricing_rule_db",
]
