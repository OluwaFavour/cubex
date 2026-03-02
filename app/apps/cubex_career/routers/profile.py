"""
Career Profile router for cubex_career.

- Get authenticated user's career profile with subscription and credit details.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentActiveUser, get_async_session
from app.core.config import request_logger
from app.core.db.crud import career_subscription_context_db, user_db
from app.core.exceptions.types import NotFoundException
from app.core.services.quota_cache import QuotaCacheService
from app.core.schemas.plan import PlanResponse, FeatureResponse
from app.core.db.models import Plan
from app.apps.cubex_career.schemas.profile import CareerProfileResponse

router = APIRouter(prefix="/profile")


def _build_plan_response(plan: Plan) -> PlanResponse:
    """Build PlanResponse from Plan model."""
    return PlanResponse(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        price=plan.price,
        display_price=plan.display_price,
        seat_price=plan.seat_price,
        seat_display_price=plan.seat_display_price,
        is_active=plan.is_active,
        trial_days=plan.trial_days,
        type=plan.type,
        features=[
            FeatureResponse(
                title=f.get("title", ""),
                description=f.get("description"),
                value=f.get("value"),
                category=f.get("category"),
            )
            for f in plan.features
        ],
        max_seats=plan.max_seats,
        min_seats=plan.min_seats,
    )


@router.get(
    "",
    response_model=CareerProfileResponse,
    summary="Get career profile",
    description="""
## Get Career Profile

Retrieve the authenticated user's profile along with career subscription
and credit usage details.

### Authorization

- User must be authenticated

### Response

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | User identifier |
| `email` | string | User's email address |
| `email_verified` | boolean | Whether email is verified |
| `full_name` | string | User's display name |
| `avatar_url` | string | URL to avatar image |
| `is_active` | boolean | Account active status |
| `created_at` | datetime | Account creation timestamp |
| `updated_at` | datetime | Last modification timestamp |
| `has_password` | boolean | Whether user has a password set |
| `oauth_providers` | array | Linked OAuth providers |
| `subscription_status` | string | Career subscription status (`active`, `canceled`, etc.) or `null` |
| `plan` | object | Current career plan details or `null` |
| `credits_used` | decimal | Credits used this billing period or `null` |
| `credits_limit` | decimal | Total credits allocated by plan or `null` |
| `credits_remaining` | decimal | Remaining credits or `null` |

### Notes

- If the user has no career subscription, all career-specific fields
  (`subscription_status`, `plan`, `credits_used`, `credits_limit`,
  `credits_remaining`) are returned as `null`.
- Credit information reflects the current billing period.
""",
    responses={
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
    },
)
async def get_career_profile(
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CareerProfileResponse:
    """Get the authenticated user's career profile."""
    request_logger.info(f"GET /career/profile - user={current_user.id}")

    async with session.begin():
        # Reload user with OAuth accounts for has_password / oauth_providers
        user = await user_db.get_by_id(
            session=session,
            id=current_user.id,
            options=[user_db.oauth_accounts_loader],
        )
        if user is None:
            raise NotFoundException("User not found")

        # Base profile fields
        has_password = user.password_hash is not None
        oauth_providers = (
            [acc.provider for acc in user.oauth_accounts] if user.oauth_accounts else []
        )

        # Career subscription context
        context = await career_subscription_context_db.get_by_user(session, user.id)

        if context is None:
            return CareerProfileResponse(
                id=user.id,
                email=user.email,
                email_verified=user.email_verified,
                full_name=user.full_name,
                avatar_url=user.avatar_url,
                is_active=user.is_active,
                created_at=user.created_at,
                updated_at=user.updated_at,
                has_password=has_password,
                oauth_providers=oauth_providers,
            )

        subscription = context.subscription
        plan = subscription.plan if subscription else None
        plan_config = (
            await QuotaCacheService.get_plan_config(session, subscription.plan_id)
            if subscription
            else None
        )

        credits_used = context.credits_used
        credits_limit = (
            plan_config.credits_allocation if plan_config else Decimal("0.00")
        )
        credits_remaining = credits_limit - credits_used

        return CareerProfileResponse(
            id=user.id,
            email=user.email,
            email_verified=user.email_verified,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            has_password=has_password,
            oauth_providers=oauth_providers,
            subscription_status=subscription.status if subscription else None,
            plan=_build_plan_response(plan) if plan else None,
            credits_used=credits_used,
            credits_limit=credits_limit,
            credits_remaining=credits_remaining,
        )
