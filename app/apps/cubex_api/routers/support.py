"""
Support router for cubex_api.

This module provides endpoints for support-related functionality
such as sales inquiries.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_api.db.crud.support import sales_request_db
from app.apps.cubex_api.schemas.support import (
    ContactSalesRequest,
    ContactSalesResponse,
)
from app.core.dependencies import get_async_session
from app.core.config import request_logger
from app.core.services import rate_limit_by_email

router = APIRouter(prefix="/support")

# Rate limiter: 3 requests per email per hour
_check_email_rate_limit = rate_limit_by_email(limit=3, window=3600)


@router.post(
    "/contact-sales",
    response_model=ContactSalesResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a sales inquiry",
    description="""
## Submit Sales Inquiry

Submit a request to be contacted by the sales team.

### Rate Limiting

- **3 requests per email per hour**
- Rate limit is based on the email address provided

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `first_name` | string | Yes | First name (1-255 chars) |
| `last_name` | string | Yes | Last name (1-255 chars) |
| `email` | string | Yes | Valid email address |
| `message` | string | No | Optional message (max 5000 chars) |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique request identifier |
| `message` | string | Confirmation message |
| `status` | string | Request status (pending) |

### Notes

- No authentication required
- Sales team will respond via the provided email
""",
    responses={
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Rate limit exceeded. Try again in 3600 seconds."
                    }
                }
            },
        },
    },
)
async def contact_sales(
    request: Request,
    data: ContactSalesRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ContactSalesResponse:
    """Submit a sales inquiry request."""
    request_logger.info(f"POST /support/contact-sales - email={data.email}")

    # Check rate limit by email
    await _check_email_rate_limit(data.email, request.url.path)

    # Create sales request record
    async with session.begin():
        sales_request = await sales_request_db.create(
            session,
            data={
                "first_name": data.first_name,
                "last_name": data.last_name,
                "email": data.email,
                "message": data.message,
            },
            commit_self=False,
        )

    request_logger.info(
        f"POST /support/contact-sales - created request={sales_request.id}"
    )

    return ContactSalesResponse(
        id=sales_request.id,
        message="Thank you for your inquiry. Our sales team will contact you shortly.",
        status=sales_request.status,
    )


__all__ = ["router"]
