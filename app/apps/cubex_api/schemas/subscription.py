"""
Pydantic schemas for subscription endpoints.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.core.enums import PlanType, SubscriptionStatus


class FeatureResponse(BaseModel):
    """Schema for plan feature."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "API Rate Limit",
                "description": "Number of API calls per minute",
                "value": "1000",
                "category": "limits",
            }
        }
    )

    title: str
    description: str | None = None
    value: str | bool | None = None
    category: str | None = None


class PlanResponse(BaseModel):
    """Schema for plan response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "pro",
                "description": "Professional plan with advanced features",
                "price": "29.99",
                "display_price": "$29.99/month",
                "seat_price": "5.00",
                "seat_display_price": "$5/seat/month",
                "is_active": True,
                "trial_days": 14,
                "type": "paid",
                "features": [
                    {
                        "title": "API Rate Limit",
                        "description": "Number of API calls per minute",
                        "value": "1000",
                        "category": "limits",
                    }
                ],
                "max_seats": 50,
                "min_seats": 1,
            }
        },
    )

    id: UUID
    name: str
    description: str | None
    price: Decimal
    display_price: str | None
    seat_price: Decimal
    seat_display_price: str | None
    is_active: bool
    trial_days: int | None
    type: PlanType
    features: list[FeatureResponse] = []
    max_seats: int | None
    min_seats: int


class PlanListResponse(BaseModel):
    """Schema for list of plans."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "plans": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "name": "pro",
                        "description": "Professional plan",
                        "price": "29.99",
                        "display_price": "$29.99/month",
                        "seat_price": "5.00",
                        "seat_display_price": "$5/seat/month",
                        "is_active": True,
                        "trial_days": 14,
                        "type": "paid",
                        "features": [],
                        "max_seats": 50,
                        "min_seats": 1,
                    }
                ]
            }
        }
    )

    plans: list[PlanResponse]


class SubscriptionResponse(BaseModel):
    """Schema for subscription response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "workspace_id": "550e8400-e29b-41d4-a716-446655440001",
                "plan_id": "550e8400-e29b-41d4-a716-446655440002",
                "status": "active",
                "seat_count": 5,
                "current_period_start": "2024-01-15T00:00:00Z",
                "current_period_end": "2024-02-15T00:00:00Z",
                "cancel_at_period_end": False,
                "canceled_at": None,
                "credits_allocation": "5000.00",
                "credits_used": "1250.50",
                "plan": None,
            }
        },
    )

    id: UUID
    workspace_id: UUID
    plan_id: UUID
    status: SubscriptionStatus
    seat_count: int
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    canceled_at: datetime | None
    credits_allocation: Decimal = Field(
        description="Total credits allocated for the billing period"
    )
    credits_used: Decimal = Field(
        description="Credits used in the current billing period"
    )
    plan: PlanResponse | None = None


class CheckoutRequest(BaseModel):
    """Schema for creating a checkout session."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "plan_id": "550e8400-e29b-41d4-a716-446655440000",
                "seat_count": 5,
                "success_url": "https://app.cubex.com/checkout/success",
                "cancel_url": "https://app.cubex.com/checkout/cancel",
            }
        }
    )

    plan_id: UUID
    seat_count: Annotated[int, Field(ge=1, le=100, description="Number of seats")]
    success_url: HttpUrl
    cancel_url: HttpUrl


class CheckoutResponse(BaseModel):
    """Schema for checkout session response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_abc123",
                "session_id": "cs_test_abc123def456",
            }
        }
    )

    checkout_url: str
    session_id: str


class SeatUpdateRequest(BaseModel):
    """Schema for updating seat count."""

    model_config = ConfigDict(json_schema_extra={"example": {"seat_count": 10}})

    seat_count: Annotated[int, Field(ge=1, le=100, description="New seat count")]


class CancelSubscriptionRequest(BaseModel):
    """Schema for canceling subscription."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"cancel_at_period_end": True}}
    )

    cancel_at_period_end: bool = True


class ReactivateRequest(BaseModel):
    """Schema for reactivating a frozen workspace."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "member_ids_to_enable": [
                    "550e8400-e29b-41d4-a716-446655440000",
                    "550e8400-e29b-41d4-a716-446655440001",
                ]
            }
        }
    )

    member_ids_to_enable: list[UUID] | None = None


class MessageResponse(BaseModel):
    """Generic message response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"message": "Operation completed successfully", "success": True}
        }
    )

    message: str
    success: bool = True


class UpgradePreviewRequest(BaseModel):
    """Schema for requesting an upgrade preview."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "new_plan_id": "550e8400-e29b-41d4-a716-446655440000",
                "new_seat_count": 10,
            }
        }
    )

    new_plan_id: UUID | None = None
    new_seat_count: (
        Annotated[int, Field(ge=1, le=100, description="New seat count")] | None
    ) = None

    @model_validator(mode="after")
    def at_least_one_field_required(self) -> "UpgradePreviewRequest":
        """Ensure at least one field is provided."""
        if self.new_plan_id is None and self.new_seat_count is None:
            raise ValueError(
                "At least one field must be provided in upgrade_preview "
                "(new_plan_id or new_seat_count)"
            )
        return self


class UpgradePreviewResponse(BaseModel):
    """Schema for upgrade preview response with proration details."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_plan": "Basic",
                "new_plan": "Professional",
                "current_seat_count": 5,
                "new_seat_count": 10,
                "proration_amount": "15.50",
                "total_due": "29.99",
                "currency": "usd",
                "billing_period_end": "2024-02-15T00:00:00Z",
            }
        }
    )

    current_plan: str
    new_plan: str
    current_seat_count: int
    new_seat_count: int
    proration_amount: Decimal = Field(
        description="Amount credited/charged for unused time on current plan"
    )
    total_due: Decimal = Field(description="Total amount due immediately upon upgrade")
    currency: str
    billing_period_end: datetime | None = Field(
        description="When the current billing period ends"
    )


class UpgradeRequest(BaseModel):
    """Schema for upgrading to a new plan."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "new_plan_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        }
    )

    new_plan_id: UUID


__all__ = [
    "FeatureResponse",
    "PlanResponse",
    "PlanListResponse",
    "SubscriptionResponse",
    "CheckoutRequest",
    "CheckoutResponse",
    "SeatUpdateRequest",
    "CancelSubscriptionRequest",
    "ReactivateRequest",
    "MessageResponse",
    "UpgradePreviewRequest",
    "UpgradePreviewResponse",
    "UpgradeRequest",
]
