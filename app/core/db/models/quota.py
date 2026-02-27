"""
- FeatureCostConfig: Defines internal credit cost per feature
- PlanPricingRule: Defines pricing multipliers, credit allocations, and rate limits per plan
"""

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.db.models.base import BaseModel
from app.core.enums import FeatureKey, ProductType

if TYPE_CHECKING:
    from app.core.db.models.plan import Plan


class FeatureCostConfig(BaseModel):
    """
    Model for endpoint cost configuration.

    Defines the internal credit cost for each API endpoint.
    This allows dynamic pricing based on endpoint resource consumption.

    Attributes:
        feature: The API feature key (e.g., 'api.analyze').
        internal_cost_credits: The internal credit cost for calling this endpoint.
    """

    __tablename__ = "feature_cost_configs"

    feature_key: Mapped[FeatureKey] = mapped_column(
        Enum(FeatureKey, native_enum=False, name="feature_key"),
        nullable=False,
        unique=True,
        index=True,
        comment="Feature Key (e.g., 'api.analyze')",
    )
    product_type: Mapped[ProductType] = mapped_column(
        Enum(ProductType, native_enum=False, name="product_type"),
        nullable=False,
        index=True,
        comment="Product this plan belongs to (API or CAREER)",
    )
    internal_cost_credits: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        comment="Internal credit cost for this feature",
    )

    __table_args__ = (Index("ix_feature_cost_configs_feature_lookup", "feature_key"),)


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
            None means unlimited.
        rate_limit_per_day: The maximum number of API requests allowed per day.
            None means unlimited.
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
        comment="Pricing multiplier (1.0 = standard rate)",
    )

    credits_allocation: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        comment="Credits allocated to users on this plan",
    )

    rate_limit_per_minute: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum API requests allowed per minute (None = unlimited)",
    )
    rate_limit_per_day: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum API requests allowed per day (None = unlimited)",
    )

    # Relationship
    plan: Mapped["Plan"] = relationship("Plan", back_populates="pricing_rule")

    __table_args__ = (
        UniqueConstraint("plan_id", name="uq_plan_pricing_rules_plan_id"),
    )
