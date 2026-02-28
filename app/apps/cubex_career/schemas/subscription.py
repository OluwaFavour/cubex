"""
Pydantic schemas for Career subscription endpoints.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.core.schemas.plan import PlanResponse
from app.core.enums import SubscriptionStatus


class CareerSubscriptionResponse(BaseModel):
    """Schema for Career subscription response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "550e8400-e29b-41d4-a716-446655440001",
                "plan_id": "550e8400-e29b-41d4-a716-446655440002",
                "status": "active",
                "current_period_start": "2024-01-15T00:00:00Z",
                "current_period_end": "2024-02-15T00:00:00Z",
                "cancel_at_period_end": False,
                "canceled_at": None,
                "plan": None,
            }
        },
    )

    id: UUID
    user_id: UUID
    plan_id: UUID
    status: SubscriptionStatus
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    canceled_at: datetime | None
    plan: PlanResponse | None = None


class CareerCheckoutRequest(BaseModel):
    """Schema for creating a Career checkout session."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "plan_id": "550e8400-e29b-41d4-a716-446655440000",
                "success_url": "https://app.cubex.com/career/checkout/success",
                "cancel_url": "https://app.cubex.com/career/checkout/cancel",
            }
        }
    )

    plan_id: UUID
    success_url: HttpUrl
    cancel_url: HttpUrl


class CareerCheckoutResponse(BaseModel):
    """Schema for Career checkout session response."""

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


class CareerUpgradePreviewRequest(BaseModel):
    """Schema for requesting a Career upgrade preview."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "new_plan_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        }
    )

    new_plan_id: UUID


class CareerUpgradePreviewResponse(BaseModel):
    """Schema for Career upgrade preview response with proration details."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_plan": "Plus",
                "new_plan": "Pro",
                "proration_amount": "10.00",
                "total_due": "19.99",
                "currency": "usd",
                "billing_period_end": "2024-02-15T00:00:00Z",
            }
        }
    )

    current_plan: str
    new_plan: str
    proration_amount: Decimal = Field(
        description="Amount credited/charged for unused time on current plan"
    )
    total_due: Decimal = Field(description="Total amount due immediately upon upgrade")
    currency: str
    billing_period_end: datetime | None = Field(
        description="When the current billing period ends"
    )


class CareerUpgradeRequest(BaseModel):
    """Schema for upgrading to a new Career plan."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "new_plan_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        }
    )

    new_plan_id: UUID


class CareerCancelRequest(BaseModel):
    """Schema for canceling Career subscription."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"cancel_at_period_end": True}}
    )

    cancel_at_period_end: bool = True


class CareerMessageResponse(BaseModel):
    """Generic message response for Career endpoints."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"message": "Operation completed successfully", "success": True}
        }
    )

    message: str
    success: bool = True


__all__ = [
    "CareerSubscriptionResponse",
    "CareerCheckoutRequest",
    "CareerCheckoutResponse",
    "CareerUpgradePreviewRequest",
    "CareerUpgradePreviewResponse",
    "CareerUpgradeRequest",
    "CareerCancelRequest",
    "CareerMessageResponse",
]
