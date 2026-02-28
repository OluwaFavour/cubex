"""
Schemas for support-related endpoints.

"""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.core.enums import SalesRequestStatus


class ContactSalesRequest(BaseModel):
    """Request schema for contact-sales endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "message": "I'm interested in enterprise pricing for my team.",
            }
        }
    )

    first_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, strip_whitespace=True),
        Field(description="First name of the requester"),
    ]
    last_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, strip_whitespace=True),
        Field(description="Last name of the requester"),
    ]
    email: Annotated[
        EmailStr,
        Field(description="Email address for follow-up contact"),
    ]
    message: Annotated[
        str | None,
        StringConstraints(max_length=5000, strip_whitespace=True),
        Field(
            default=None, description="Optional message with details about the inquiry"
        ),
    ]


class ContactSalesResponse(BaseModel):
    """Response schema for contact-sales endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "message": "Thank you for your inquiry. Our sales team will contact you shortly.",
                "status": "pending",
            }
        }
    )

    id: UUID = Field(description="Unique identifier for the sales request")
    message: str = Field(description="Confirmation message")
    status: SalesRequestStatus = Field(description="Current status of the request")


__all__ = [
    "ContactSalesRequest",
    "ContactSalesResponse",
]
