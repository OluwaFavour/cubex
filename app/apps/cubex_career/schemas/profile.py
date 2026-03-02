"""
Pydantic schemas for Career profile endpoint.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from typing import Annotated

from app.core.enums import OAuthProviders, SubscriptionStatus
from app.core.schemas.plan import PlanResponse


class CareerProfileResponse(BaseModel):
    """Response schema for career profile with subscription/credit details."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "email_verified": True,
                "full_name": "John Doe",
                "avatar_url": "https://example.com/avatar.jpg",
                "is_active": True,
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-20T15:45:00Z",
                "has_password": True,
                "oauth_providers": ["google"],
                "subscription_status": "active",
                "plan": None,
                "credits_used": "5.50",
                "credits_limit": "100.00",
                "credits_remaining": "94.50",
            }
        },
    )

    # User fields (same as ProfileResponse)
    id: UUID
    email: EmailStr
    email_verified: bool
    full_name: str | None
    avatar_url: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    has_password: Annotated[
        bool,
        Field(description="Whether user has a password set (false for OAuth-only)"),
    ]
    oauth_providers: Annotated[
        list[OAuthProviders],
        Field(default_factory=list, description="List of linked OAuth providers"),
    ]

    # Career-specific fields (None when no subscription exists)
    subscription_status: Annotated[
        SubscriptionStatus | None,
        Field(description="Current career subscription status"),
    ] = None
    plan: Annotated[
        PlanResponse | None,
        Field(description="Current career subscription plan"),
    ] = None
    credits_used: Annotated[
        Decimal | None,
        Field(description="Credits used in current billing period"),
    ] = None
    credits_limit: Annotated[
        Decimal | None,
        Field(description="Total credits allocated by current plan"),
    ] = None
    credits_remaining: Annotated[
        Decimal | None,
        Field(description="Remaining credits (limit - used)"),
    ] = None
