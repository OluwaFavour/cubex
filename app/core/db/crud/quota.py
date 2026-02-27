"""
CRUD operations for Quota models.

"""

from decimal import Decimal
from typing import TYPE_CHECKING, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.db.models.quota import FeatureCostConfig, PlanPricingRule
from app.core.db.crud.base import BaseDB
from app.core.exceptions.types import DatabaseException

if TYPE_CHECKING:
    from app.core.enums import FeatureKey


class FeatureCostConfigDB(BaseDB[FeatureCostConfig]):
    """CRUD operations for FeatureCostConfig model."""

    def __init__(self):
        """Initialize with FeatureCostConfig model."""
        super().__init__(FeatureCostConfig)

    async def get_by_feature_key(
        self,
        session: AsyncSession,
        feature_key: "FeatureKey",
    ) -> FeatureCostConfig | None:
        """
        Get feature cost configuration by feature key.

        Args:
            session: Database session.
            feature_key: The feature key (e.g., FeatureKey.API_CAREER_PATH).

        Returns:
            FeatureCostConfig or None if not found.
        """
        return await self.get_one_by_filters(
            session,
            {"feature_key": feature_key, "is_deleted": False},
        )

    async def get_all_active(
        self,
        session: AsyncSession,
    ) -> Sequence[FeatureCostConfig]:
        """
        Get all active feature cost configurations.

        Args:
            session: Database session.

        Returns:
            List of active feature cost configurations.
        """
        stmt = select(FeatureCostConfig).where(
            FeatureCostConfig.is_deleted == False  # noqa: E712
        )
        try:
            result = await session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            raise DatabaseException(
                f"Error getting feature cost configs: {str(e)}"
            ) from e

    async def create_or_update(
        self,
        session: AsyncSession,
        feature_key: "FeatureKey",
        internal_cost_credits: Decimal,
    ) -> FeatureCostConfig:
        """
        Create or update a feature cost configuration.

        If the feature key already exists, updates its cost. Otherwise creates new.

        Args:
            session: Database session.
            feature_key: The feature key (e.g., FeatureKey.API_CAREER_PATH).
            internal_cost_credits: The internal credit cost.

        Returns:
            Created or updated FeatureCostConfig.

        Raises:
            DatabaseException: If update fails unexpectedly.
        """
        existing = await self.get_by_feature_key(session, feature_key)
        if existing:
            updated = await self.update(
                session,
                existing.id,
                {"internal_cost_credits": internal_cost_credits},
            )
            if updated is None:
                raise DatabaseException(
                    f"Failed to update FeatureCostConfig for feature {feature_key}"
                )
            return updated
        return await self.create(
            session,
            {
                "feature_key": feature_key,
                "internal_cost_credits": internal_cost_credits,
            },
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
        rate_limit_per_day: int | None = None,
    ) -> PlanPricingRule:
        """
        Create or update a plan pricing rule.

        If the plan already has a pricing rule, updates it. Otherwise creates new.

        Args:
            session: Database session.
            plan_id: The plan UUID.
            multiplier: The pricing multiplier (optional on update).
            credits_allocation: The credits allocation (optional on update).
            rate_limit_per_minute: Max requests/minute (None = unlimited).
            rate_limit_per_day: Max requests/day (None = unlimited).

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
        if rate_limit_per_day is not None:
            update_data["rate_limit_per_day"] = rate_limit_per_day

        if existing:
            if update_data:
                updated = await self.update(session, existing.id, update_data)
                if updated is None:
                    raise DatabaseException(
                        f"Failed to update PlanPricingRule for plan {plan_id}"
                    )
                return updated
            return existing

        create_data: dict = {"plan_id": plan_id}
        if multiplier is not None:
            create_data["multiplier"] = multiplier
        if credits_allocation is not None:
            create_data["credits_allocation"] = credits_allocation
        if rate_limit_per_minute is not None:
            create_data["rate_limit_per_minute"] = rate_limit_per_minute
        if rate_limit_per_day is not None:
            create_data["rate_limit_per_day"] = rate_limit_per_day

        return await self.create(session, create_data)


# Global instances for dependency injection
feature_cost_config_db = FeatureCostConfigDB()
plan_pricing_rule_db = PlanPricingRuleDB()


__all__ = [
    "FeatureCostConfigDB",
    "PlanPricingRuleDB",
    "feature_cost_config_db",
    "plan_pricing_rule_db",
]
