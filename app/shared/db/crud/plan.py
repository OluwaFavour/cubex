"""
CRUD operations for Plan model.

This module provides database operations for managing subscription plans.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db.crud.base import BaseDB
from app.shared.db.models.plan import Plan
from app.shared.enums import PlanType, ProductType


class PlanDB(BaseDB[Plan]):
    """CRUD operations for Plan model."""

    def __init__(self):
        super().__init__(Plan)

    async def get_active_plans(
        self,
        session: AsyncSession,
        plan_type: PlanType | None = None,
        product_type: ProductType | None = None,
    ) -> list[Plan]:
        """
        Get all active plans, optionally filtered by type and product.

        Args:
            session: Database session.
            plan_type: Optional filter by plan type.
            product_type: Optional filter by product type (API or CAREER).

        Returns:
            List of active plans.
        """
        filters: dict[str, bool | PlanType | ProductType] = {
            "is_active": True,
            "is_deleted": False,
        }
        if plan_type:
            filters["type"] = plan_type
        if product_type:
            filters["product_type"] = product_type

        plans = await self.get_by_filters(
            session, filters, order_by=[self.model.price.asc()]
        )
        return list(plans)

    async def get_free_plan(
        self,
        session: AsyncSession,
        product_type: ProductType = ProductType.API,
    ) -> Plan | None:
        """
        Get the active free plan for a product type.

        Args:
            session: Database session.
            product_type: Product type (API or CAREER).

        Returns:
            The free plan or None if not found.
        """
        return await self.get_one_by_filters(
            session,
            {
                "type": PlanType.FREE,
                "product_type": product_type,
                "is_active": True,
                "is_deleted": False,
            },
        )

    async def get_by_stripe_price_id(
        self,
        session: AsyncSession,
        stripe_price_id: str,
    ) -> Plan | None:
        """
        Get plan by Stripe price ID.

        Args:
            session: Database session.
            stripe_price_id: Stripe Price ID.

        Returns:
            The plan or None if not found.
        """
        return await self.get_one_by_filters(
            session,
            {"stripe_price_id": stripe_price_id, "is_deleted": False},
        )


__all__ = ["PlanDB"]
