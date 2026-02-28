"""
Shared plan schemas used by both cubex_api and cubex_career.

These schemas represent the Plan model which lives in ``app.core.db.models.plan``
and are therefore shared infrastructure, not product-specific.
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import PlanType


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
        },
    )

    plans: list[PlanResponse]


__all__ = [
    "FeatureResponse",
    "PlanResponse",
    "PlanListResponse",
]
