"""
Plan model for subscription plans.

This module provides the Plan model for defining subscription tiers
with features, pricing, and Stripe integration.
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Iterable

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
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.shared.db.models.base import BaseModel
from app.shared.enums import PlanType, ProductType

if TYPE_CHECKING:
    from app.apps.cubex_api.db.models.quota import PlanPricingRule


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
        price: Base monthly price (0.00 for free plans or seat-only pricing).
        display_price: Human-readable base price (e.g., "$19/month").
        stripe_price_id: Stripe Price ID for base subscription billing.
        seat_price: Per-seat monthly price (0.00 for unlimited seats or flat-rate plans).
        seat_display_price: Human-readable seat price (e.g., "$5/seat/month").
        seat_stripe_price_id: Stripe Price ID for per-seat billing.
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
        comment="Stripe Price ID for base subscription",
    )

    # Per-seat pricing (for workspace-based plans)
    seat_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
        comment="Per-seat monthly price",
    )

    seat_display_price: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Human-readable seat price (e.g., '$5/seat/month')",
    )

    seat_stripe_price_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
        comment="Stripe Price ID for per-seat billing",
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
        CheckConstraint("seat_price >= 0", name="ck_plans_seat_price_non_negative"),
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
        # PAID plans must have at least one Stripe price ID for billing
        CheckConstraint(
            """
            type = 'FREE'
            OR (type = 'PAID' AND (stripe_price_id IS NOT NULL OR seat_stripe_price_id IS NOT NULL))
            """,
            name="ck_plans_paid_has_stripe_id",
        ),
        # Unique per product_type (allows "Free" for both API and Career)
        UniqueConstraint("name", "product_type", name="uq_plans_name_product_type"),
    )

    def __str__(self) -> str:
        return self.name

    @validates("type", "price", "stripe_price_id", "seat_price", "seat_stripe_price_id")
    def _validate_type_price_and_stripe(self, key: str, value: Any) -> Any:
        """
        Ensure consistency between plan type, prices, and Stripe IDs.

        FREE plans must have price=0, seat_price=0, and no Stripe IDs.
        PAID plans can have base price and/or seat price (at least one Stripe ID required).
        """
        prospective_type = value if key == "type" else getattr(self, "type", None)
        prospective_price = value if key == "price" else getattr(self, "price", None)
        prospective_seat_price = (
            value if key == "seat_price" else getattr(self, "seat_price", None)
        )
        prospective_price_id = (
            value
            if key == "stripe_price_id"
            else getattr(self, "stripe_price_id", None)
        )
        prospective_seat_price_id = (
            value
            if key == "seat_stripe_price_id"
            else getattr(self, "seat_stripe_price_id", None)
        )

        def _has_positive_value(val: Any) -> bool:
            try:
                return val is not None and float(val) > 0
            except (TypeError, ValueError):
                return False

        has_positive_price = _has_positive_value(prospective_price)
        has_positive_seat_price = _has_positive_value(prospective_seat_price)
        has_stripe_id = bool(prospective_price_id)
        has_seat_stripe_id = bool(prospective_seat_price_id)

        if prospective_type == PlanType.FREE:
            if has_positive_price or has_positive_seat_price:
                raise ValueError(
                    "Plan declared as FREE but has a non-zero price or seat price"
                )
            if has_stripe_id or has_seat_stripe_id:
                raise ValueError("Plan declared as FREE but has a Stripe ID")

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
        # PAID plans need at least one Stripe price ID
        return self.is_paid and (
            self.stripe_price_id is not None or self.seat_stripe_price_id is not None
        )

    @property
    def has_seat_pricing(self) -> bool:
        """Check if plan uses per-seat pricing."""
        return self.seat_stripe_price_id is not None

    # Relationship to pricing rule
    pricing_rule: Mapped["PlanPricingRule | None"] = relationship(
        "PlanPricingRule",
        back_populates="plan",
        uselist=False,
        lazy="selectin",
    )


__all__ = ["Plan", "FeatureSchema"]
