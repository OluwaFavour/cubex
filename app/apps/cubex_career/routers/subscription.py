"""
Career Subscription router for cubex_career.

- Viewing Career plans
- Managing Career subscriptions
- Checkout sessions
- Plan upgrades
- Manual activation
"""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentActiveUser, get_async_session
from app.core.config import request_logger
from app.core.schemas.plan import (
    PlanResponse,
    PlanListResponse,
    FeatureResponse,
)
from app.apps.cubex_career.schemas.subscription import (
    CareerSubscriptionResponse,
    CareerCheckoutRequest,
    CareerCheckoutResponse,
    CareerUpgradePreviewRequest,
    CareerUpgradePreviewResponse,
    CareerUpgradeRequest,
    CareerCancelRequest,
    CareerMessageResponse,
)
from app.apps.cubex_career.services.subscription import (
    career_subscription_service,
    CareerSubscriptionNotFoundException,
)
from app.core.db.models import Plan, Subscription

router = APIRouter(prefix="/subscriptions")


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


def _build_subscription_response(
    subscription: Subscription, user_id: UUID
) -> CareerSubscriptionResponse:
    """Build CareerSubscriptionResponse from Subscription model."""
    return CareerSubscriptionResponse(
        id=subscription.id,
        user_id=user_id,
        plan_id=subscription.plan_id,
        status=subscription.status,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        canceled_at=subscription.canceled_at,
        plan=_build_plan_response(subscription.plan) if subscription.plan else None,
    )


@router.get(
    "/plans",
    response_model=PlanListResponse,
    summary="List Career plans",
    description="""
## List Career Plans

Retrieve all active Career subscription plans available for purchase.

### Authorization

- Public endpoint (no authentication required)

### Response

| Field | Type | Description |
|-------|------|-------------|
| `plans` | array | List of available plans |
| `plans[].id` | UUID | Plan identifier |
| `plans[].name` | string | Plan name (e.g., "Career Free", "Career Pro") |
| `plans[].description` | string | Plan description |
| `plans[].price` | decimal | Monthly price |
| `plans[].display_price` | string | Formatted price string |
| `plans[].type` | string | Always `career` |
| `plans[].features` | array | Included features |

### Notes

- Only active plans are returned
- Free tier is always available
- Career plans are user-based (not workspace-based)
""",
)
async def list_career_plans(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> PlanListResponse:
    """List all active Career plans available for purchase."""
    request_logger.info("GET /career/subscriptions/plans")
    async with session.begin():
        plans = await career_subscription_service.get_active_plans(session)
        request_logger.info(
            f"GET /career/subscriptions/plans returned {len(plans)} plans"
        )
        return PlanListResponse(plans=[_build_plan_response(p) for p in plans])


@router.get(
    "/plans/{plan_id}",
    response_model=PlanResponse,
    summary="Get Career plan details",
    description="""
## Get Career Plan Details

Retrieve detailed information about a specific Career plan.

### Authorization

- Public endpoint (no authentication required)

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `plan_id` | UUID | The plan identifier |

### Response

Returns the complete plan details including all features.

### Error Responses

| Status | Reason |
|--------|--------|
| `404 Not Found` | Plan does not exist |

### Notes

- Both active and inactive plans can be retrieved by ID
""",
    responses={
        404: {
            "description": "Plan not found",
            "content": {"application/json": {"example": {"detail": "Plan not found."}}},
        },
    },
)
async def get_career_plan(
    plan_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> PlanResponse:
    """Get Career plan details."""
    request_logger.info(f"GET /career/subscriptions/plans/{plan_id}")
    async with session.begin():
        plan = await career_subscription_service.get_plan(session, plan_id)
        return _build_plan_response(plan)


@router.get(
    "",
    response_model=CareerSubscriptionResponse | None,
    summary="Get my Career subscription",
    description="""
## Get My Career Subscription

Retrieve the current user's Career subscription. Returns `null` if no
subscription exists.

### Authorization

- User must be authenticated

### Response

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Subscription identifier |
| `user_id` | UUID | User's ID |
| `plan_id` | UUID | Current plan |
| `status` | string | `active`, `canceled`, `past_due`, etc. |
| `current_period_start` | datetime | Billing period start |
| `current_period_end` | datetime | Billing period end |
| `cancel_at_period_end` | boolean | Whether cancellation is scheduled |
| `canceled_at` | datetime | When cancellation was requested |
| `plan` | object | Full plan details |

### Notes

- Returns `null` (not 404) if user has no Career subscription
- Users get a free Career subscription at signup
""",
)
async def get_my_career_subscription(
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CareerSubscriptionResponse | None:
    """Get current user's Career subscription."""
    request_logger.info(f"GET /career/subscriptions - user={current_user.id}")
    async with session.begin():
        subscription = await career_subscription_service.get_subscription(
            session, current_user.id
        )
        if not subscription:
            return None
        return _build_subscription_response(subscription, current_user.id)


@router.post(
    "/checkout",
    response_model=CareerCheckoutResponse,
    summary="Create Career checkout session",
    description="""
## Create Career Checkout Session

Create a Stripe checkout session to subscribe to a paid Career plan.
Redirects the user to Stripe's hosted checkout page.

### Authorization

- User must be authenticated

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `plan_id` | UUID | ✅ | The Career plan to subscribe to |
| `success_url` | string | ✅ | URL to redirect after successful payment |
| `cancel_url` | string | ✅ | URL to redirect if user cancels |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `checkout_url` | string | Stripe checkout page URL |
| `session_id` | string | Stripe session ID for tracking |

### Checkout Flow

1. Call this endpoint to create a checkout session
2. Redirect user to `checkout_url`
3. User completes payment on Stripe
4. Stripe redirects to `success_url`
5. Webhook updates subscription in database

### Error Responses

| Status | Reason |
|--------|--------|
| `404 Not Found` | Plan not found |

### Notes

- Career subscriptions are per-user (no seat management)
- Upgrading existing subscription should use `/upgrade` instead
""",
    responses={
        404: {
            "description": "Plan not found",
            "content": {"application/json": {"example": {"detail": "Plan not found."}}},
        },
    },
)
async def create_career_checkout(
    request_data: CareerCheckoutRequest,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CareerCheckoutResponse:
    """Create a Stripe checkout session for Career subscription."""
    request_logger.info(
        f"POST /career/subscriptions/checkout - user={current_user.id} "
        f"plan={request_data.plan_id}"
    )
    async with session.begin():
        checkout_session = await career_subscription_service.create_checkout_session(
            session=session,
            plan_id=request_data.plan_id,
            success_url=str(request_data.success_url),
            cancel_url=str(request_data.cancel_url),
            user=current_user,
        )

        request_logger.info(
            f"POST /career/subscriptions/checkout - created session "
            f"{checkout_session.id}"
        )

        return CareerCheckoutResponse(
            checkout_url=checkout_session.url or "",
            session_id=checkout_session.id,
        )


@router.post(
    "/preview-upgrade",
    response_model=CareerUpgradePreviewResponse,
    summary="Preview Career upgrade",
    description="""
## Preview Career Plan Upgrade Cost

Preview the cost of upgrading to a different Career plan before committing.
Returns detailed proration information.

### Authorization

- User must be authenticated
- User must have an active Career subscription

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `new_plan_id` | UUID | ✅ | The plan to upgrade to |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `current_plan` | string | Name of current plan |
| `new_plan` | string | Name of new plan |
| `proration_amount` | integer | Proration in cents |
| `total_due` | decimal | Total to charge (in dollars) |
| `currency` | string | Currency code (e.g., "usd") |
| `billing_period_end` | datetime | Current period end date |

### Error Responses

| Status | Reason |
|--------|--------|
| `404 Not Found` | No active subscription or plan not found |

### Notes

- This is a **preview only** - no changes are made
- Use the `/upgrade` endpoint to execute the upgrade
""",
    responses={
        404: {
            "description": "Subscription or plan not found",
            "content": {
                "application/json": {
                    "example": {"detail": "No active Career subscription found."}
                }
            },
        },
    },
)
async def preview_career_upgrade(
    request_data: CareerUpgradePreviewRequest,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CareerUpgradePreviewResponse:
    """Preview the cost of upgrading to a new Career plan."""
    request_logger.info(
        f"POST /career/subscriptions/preview-upgrade - user={current_user.id} "
        f"new_plan={request_data.new_plan_id}"
    )
    async with session.begin():
        current_sub = await career_subscription_service.get_subscription(
            session, current_user.id
        )
        if not current_sub:
            raise CareerSubscriptionNotFoundException()

        new_plan = await career_subscription_service.get_plan(
            session, request_data.new_plan_id
        )

        invoice = await career_subscription_service.preview_upgrade(
            session=session,
            user_id=current_user.id,
            new_plan_id=request_data.new_plan_id,
        )

        total_due = Decimal(invoice.amount_due) / Decimal(100)

        return CareerUpgradePreviewResponse(
            current_plan=current_sub.plan.name,
            new_plan=new_plan.name,
            proration_amount=invoice.proration_amount,
            total_due=total_due,
            currency=invoice.currency,
            billing_period_end=current_sub.current_period_end,
        )


@router.post(
    "/upgrade",
    response_model=CareerSubscriptionResponse,
    summary="Upgrade Career plan",
    description="""
## Upgrade Career Subscription Plan

Upgrade the user's Career subscription to a different plan.
Proration is calculated and charged immediately.

### Authorization

- User must be authenticated
- User must have an active Career subscription

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `new_plan_id` | UUID | ✅ | The plan to upgrade to |

### Response

Returns the updated subscription with new plan details.

### Upgrade Process

1. **Preview first**: Use `/preview-upgrade` to see costs
2. **Execute upgrade**: Call this endpoint
3. **Proration applied**: Charged immediately via Stripe
4. **New plan active**: Takes effect immediately

### Error Responses

| Status | Reason |
|--------|--------|
| `404 Not Found` | No active subscription or plan not found |

### Notes

- Upgrades and downgrades are both supported
- Changes reflect immediately in Stripe
""",
    responses={
        404: {
            "description": "Subscription not found",
            "content": {
                "application/json": {
                    "example": {"detail": "No active Career subscription found."}
                }
            },
        },
    },
)
async def upgrade_career_plan(
    request_data: CareerUpgradeRequest,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CareerSubscriptionResponse:
    """Upgrade to a different Career plan."""
    request_logger.info(
        f"POST /career/subscriptions/upgrade - user={current_user.id} "
        f"new_plan={request_data.new_plan_id}"
    )
    async with session.begin():
        subscription = await career_subscription_service.upgrade_plan(
            session=session,
            user_id=current_user.id,
            new_plan_id=request_data.new_plan_id,
        )

        request_logger.info(
            f"POST /career/subscriptions/upgrade - upgraded to plan "
            f"{subscription.plan_id}"
        )

        return _build_subscription_response(subscription, current_user.id)


@router.post(
    "/cancel",
    response_model=CareerMessageResponse,
    summary="Cancel Career subscription",
    description="""
## Cancel Career Subscription

Cancel the user's Career subscription. By default, cancellation takes effect
at the end of the current billing period.

### Authorization

- User must be authenticated
- User must have an active Career subscription

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cancel_at_period_end` | boolean | ❌ | If `true` (default), cancels at period end. If `false`, cancels immediately |

### Response

```json
{
  "message": "Subscription will be cancelled at end of billing period.",
  "success": true
}
```

### Cancellation Behavior

**At Period End (`cancel_at_period_end=true`):**
- Subscription remains active until `current_period_end`
- User retains Career features until then
- Can be reactivated before period ends

**Immediate (`cancel_at_period_end=false`):**
- Subscription cancelled immediately
- User reverts to free tier
- Prorated refund issued (if applicable)

### Error Responses

| Status | Reason |
|--------|--------|
| `404 Not Found` | No active subscription found |

### Notes

- After cancellation, user reverts to Career Free tier
- Resubscription requires new checkout session
""",
    responses={
        404: {
            "description": "Subscription not found",
            "content": {
                "application/json": {
                    "example": {"detail": "No active Career subscription found."}
                }
            },
        },
    },
)
async def cancel_career_subscription(
    request_data: CareerCancelRequest,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CareerMessageResponse:
    """Cancel Career subscription."""
    request_logger.info(
        f"POST /career/subscriptions/cancel - user={current_user.id} "
        f"at_period_end={request_data.cancel_at_period_end}"
    )
    async with session.begin():
        await career_subscription_service.cancel_subscription(
            session=session,
            user_id=current_user.id,
            cancel_at_period_end=request_data.cancel_at_period_end,
        )

        if request_data.cancel_at_period_end:
            message = "Subscription will be cancelled at end of billing period."
        else:
            message = "Subscription has been cancelled immediately."

        return CareerMessageResponse(message=message, success=True)


@router.post(
    "/activate",
    response_model=CareerSubscriptionResponse,
    summary="Activate Career subscription",
    description="""
## Activate Career Subscription

Manually create a free Career subscription if one doesn't exist.
This is a fallback endpoint for users whose automatic subscription
creation failed during signup.

### Authorization

- User must be authenticated

### Response

Returns the Career subscription (created or existing):

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Subscription identifier |
| `user_id` | UUID | User's ID |
| `plan_id` | UUID | Free Career plan ID |
| `status` | string | `active` |
| `plan` | object | Free Career plan details |

### Idempotent Behavior

This endpoint is idempotent:
- If Career subscription exists, returns it
- If not, creates free Career subscription

### Notes

- Career subscriptions are automatically created at signup
- This endpoint is a safety net for edge cases
- Always creates the free tier subscription
""",
)
async def activate_career_subscription(
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CareerSubscriptionResponse:
    """Manually activate Career subscription."""
    request_logger.info(f"POST /career/subscriptions/activate - user={current_user.id}")
    async with session.begin():
        subscription = await career_subscription_service.create_free_subscription(
            session=session,
            user=current_user,
            commit_self=False,
        )

    request_logger.info(
        f"POST /career/subscriptions/activate - subscription={subscription.id}"
    )

    return _build_subscription_response(subscription, current_user.id)


__all__ = ["router"]
