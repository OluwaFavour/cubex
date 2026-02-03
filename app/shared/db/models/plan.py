"""
Plan model for subscription plans.

This module provides the Plan model for defining subscription tiers
with features, pricing, and Stripe integration.
"""

from decimal import Decimal
from typing import Any, Iterable

from pydantic import BaseModel as PydanticBaseModel, ConfigDict, ValidationError
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.shared.db.models.base import BaseModel
from app.shared.enums import PlanType, ProductType


# ============================================================================
# Pydantic Feature Schema (for validation)
# ============================================================================


class FeatureSchema(PydanticBaseModel):
    """Schema for validating plan features stored in JSONB."""

    title: str
    description: str | None = None
    value: str | bool | None = None
    category: str | None = None

    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Plan Model
# ============================================================================


class Plan(BaseModel):
    """
    Model for subscription plans.

    Plans define pricing tiers with features and Stripe integration.
    Supports both free and paid plans with optional trial periods.

    Attributes:
        name: Unique plan name (e.g., "Professional", "Basic").
        description: Optional plan description.
        price: Monthly price (0.00 for free plans).
        display_price: Human-readable price (e.g., "$19/month").
        stripe_price_id: Stripe Price ID for billing.
        is_active: Whether plan is available for purchase.
        trial_days: Optional trial period in days.
        type: Plan type (FREE or PAID).
        features: List of plan features as validated dicts.
        max_seats: Maximum allowed seats for this plan (None = unlimited).
        min_seats: Minimum required seats (default 1).
    """

    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="Plan name - must match product_type",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Price is required; 0.00 indicates free plan
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )

    display_price: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # Stripe fields (optional for free plans)
    stripe_price_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        index=True,
        default=True,
    )

    trial_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    type: Mapped[PlanType] = mapped_column(
        Enum(PlanType, native_enum=False, name="plan_type"),
        nullable=False,
        index=True,
        default=PlanType.PAID,
    )

    product_type: Mapped[ProductType] = mapped_column(
        Enum(ProductType, native_enum=False, name="product_type"),
        nullable=False,
        index=True,
        default=ProductType.API,
        comment="Product this plan belongs to (API or CAREER)",
    )

    # Features as list of dicts (validated via Pydantic)
    features: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    # Seat limits for workspace plans
    max_seats: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum seats allowed (None = unlimited)",
    )

    min_seats: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Minimum seats required",
    )

    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_plans_price_non_negative"),
        CheckConstraint("min_seats >= 1", name="ck_plans_min_seats_positive"),
        CheckConstraint(
            "max_seats IS NULL OR max_seats >= min_seats",
            name="ck_plans_max_seats_valid",
        ),
        # Validate plan name matches product_type
        CheckConstraint(
            """
            (product_type = 'api' AND name IN ('Free', 'Basic', 'Professional'))
            OR
            (product_type = 'career' AND name IN ('Free', 'Plus Plan', 'Pro Plan'))
            """,
            name="ck_plans_name_matches_product_type",
        ),
        # Unique per product_type (allows "Free" for both API and Career)
        UniqueConstraint("name", "product_type", name="uq_plans_name_product_type"),
    )

    def __str__(self) -> str:
        return self.name

    @validates("type", "price", "stripe_price_id")
    def _validate_type_price_and_stripe(self, key: str, value: Any) -> Any:
        """
        Ensure consistency between plan type, price, and Stripe IDs.

        FREE plans must have price=0 and no Stripe IDs.
        PAID plans should have Stripe IDs for billing operations.
        """
        prospective_type = value if key == "type" else getattr(self, "type", None)
        prospective_price = value if key == "price" else getattr(self, "price", None)
        prospective_price_id = (
            value
            if key == "stripe_price_id"
            else getattr(self, "stripe_price_id", None)
        )

        try:
            has_positive_price = (
                prospective_price is not None and float(prospective_price) > 0
            )
        except (TypeError, ValueError):
            has_positive_price = False

        has_stripe_id = bool(prospective_price_id)

        if prospective_type == PlanType.FREE:
            if has_positive_price or has_stripe_id:
                raise ValueError(
                    "Plan declared as FREE but has a non-zero price or Stripe ID"
                )

        return value

    @validates("features")
    def _validate_features(self, key: str, value: Iterable[dict]) -> list[dict]:
        """Validate features against FeatureSchema."""
        validated: list[dict] = []
        for item in value or []:
            try:
                f = FeatureSchema.model_validate(item)
            except ValidationError as exc:
                raise ValueError(f"Invalid feature entry: {exc}") from exc
            validated.append(f.model_dump())
        return validated

    @property
    def is_free(self) -> bool:
        """Check if this is a free plan."""
        return self.type == PlanType.FREE

    @property
    def is_paid(self) -> bool:
        """Check if this is a paid plan."""
        return self.type == PlanType.PAID

    @property
    def can_be_purchased(self) -> bool:
        """Check if plan can be purchased via Stripe."""
        if not self.is_active:
            return False
        return self.is_paid and self.stripe_price_id is not None


__all__ = ["Plan", "FeatureSchema"]
