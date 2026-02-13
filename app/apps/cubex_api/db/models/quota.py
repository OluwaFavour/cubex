"""
Quota models for cubex_api.

This module provides models for API usage pricing and cost configuration:
- EndpointCostConfig: Defines internal credit cost per endpoint
- PlanPricingRule: Defines pricing multipliers, credit allocations, and rate limits per plan
"""

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.shared.db.models.base import BaseModel

if TYPE_CHECKING:
    from app.shared.db.models.plan import Plan


class EndpointCostConfig(BaseModel):
    """
    Model for endpoint cost configuration.

    Defines the internal credit cost for each API endpoint.
    This allows dynamic pricing based on endpoint resource consumption.

    Attributes:
        endpoint: The API endpoint path (e.g., '/api/v1/analyze').
        internal_cost_credits: The internal credit cost for calling this endpoint.
    """

    __tablename__ = "endpoint_cost_configs"

    endpoint: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        unique=True,
        index=True,
        comment="API endpoint path (e.g., '/api/v1/analyze')",
    )

    internal_cost_credits: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        default=Decimal("1.0"),
        comment="Internal credit cost for this endpoint",
    )

    __table_args__ = (Index("ix_endpoint_cost_configs_endpoint_lookup", "endpoint"),)

    @validates("endpoint")
    def normalize_endpoint(self, key: str, value: str) -> str:
        """Normalize endpoint to lowercase for consistent lookups."""
        return value.lower() if value else value


class PlanPricingRule(BaseModel):
    """
    Model for plan pricing rules.

    Defines pricing multipliers, credit allocations, and rate limits for
    different subscription plans. The multiplier adjusts the base endpoint
    cost for billing purposes.

    Attributes:
        plan_id: Foreign key to the plan this rule applies to.
        multiplier: The pricing multiplier (e.g., 1.0 for standard, 0.8 for discount).
        credits_allocation: The number of credits allocated to users on this plan.
        rate_limit_per_minute: The maximum number of API requests allowed per minute.
    """

    __tablename__ = "plan_pricing_rules"

    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "plans.id",
            ondelete="CASCADE",
            comment="Delete rule when plan is deleted",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    multiplier: Mapped[Decimal] = mapped_column(
        Numeric(precision=8, scale=2),
        nullable=False,
        default=Decimal("1.0"),
        comment="Pricing multiplier (1.0 = standard rate)",
    )

    credits_allocation: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        default=Decimal("5000.0"),
        comment="Credits allocated to users on this plan",
    )

    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=20,
        comment="Maximum API requests allowed per minute",
    )

    # Relationship
    plan: Mapped["Plan"] = relationship("Plan", back_populates="pricing_rule")

    __table_args__ = (
        UniqueConstraint("plan_id", name="uq_plan_pricing_rules_plan_id"),
    )
