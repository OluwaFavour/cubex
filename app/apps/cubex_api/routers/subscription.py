"""
Subscription router for cubex_api.

This module provides endpoints for:
- Viewing plans
- Managing subscriptions
- Checkout sessions
- Seat management
"""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_async_session
from app.shared.config import request_logger
from app.shared.dependencies.auth import CurrentActiveUser
from app.apps.cubex_api.db.crud import workspace_member_db
from app.apps.cubex_api.schemas import (
    PlanResponse,
    PlanListResponse,
    SubscriptionResponse,
    CheckoutRequest,
    CheckoutResponse,
    SeatUpdateRequest,
    CancelSubscriptionRequest,
    ReactivateRequest,
    MessageResponse,
    FeatureResponse,
    UpgradePreviewRequest,
    UpgradePreviewResponse,
    UpgradeRequest,
)
from app.apps.cubex_api.services import (
    subscription_service,
    WorkspaceAccessDeniedException,
    AdminPermissionRequiredException,
    OwnerPermissionRequiredException,
    SubscriptionNotFoundException,
)
from app.shared.db.models import Plan, Subscription


router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


# ============================================================================
# Helper Functions
# ============================================================================


def _build_plan_response(plan: Plan) -> PlanResponse:
    """Build PlanResponse from Plan model."""
    return PlanResponse(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        price=plan.price,
        display_price=plan.display_price,
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
    subscription: Subscription, workspace_id: UUID
) -> SubscriptionResponse:
    """Build SubscriptionResponse from Subscription model."""
    return SubscriptionResponse(
        id=subscription.id,
        workspace_id=workspace_id,
        plan_id=subscription.plan_id,
        status=subscription.status,
        seat_count=subscription.seat_count,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        canceled_at=subscription.canceled_at,
        plan=_build_plan_response(subscription.plan) if subscription.plan else None,
    )


# ============================================================================
# Plan Endpoints
# ============================================================================


@router.get(
    "/plans",
    response_model=PlanListResponse,
    summary="List all subscription plans",
    description="""
## List Available Subscription Plans

Retrieve all active subscription plans available for workspace subscriptions.
Plans are returned in order of price tier (Free → Pro → Enterprise).

### Response

Returns a list of plans, each containing:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique plan identifier |
| `name` | string | Plan display name (e.g., "Free", "Pro") |
| `description` | string | Plan description |
| `price` | decimal | Monthly price in dollars |
| `display_price` | string | Formatted price (e.g., "$29/month") |
| `features` | array | List of plan features |
| `max_seats` | integer | Maximum allowed seats |
| `min_seats` | integer | Minimum required seats |

### Example Response

```json
{
  "plans": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Free",
      "price": 0.00,
      "max_seats": 1,
      "features": [...]
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "name": "Pro",
      "price": 29.00,
      "max_seats": 10,
      "features": [...]
    }
  ]
}
```

### Notes

- Only **active** plans are returned
- Plans are specific to the **API product** (workspace-based)
- For Career plans, use `/career/subscriptions/plans`
""",
)
async def list_plans(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> PlanListResponse:
    """List all active plans available for purchase."""
    request_logger.info("GET /subscriptions/plans")
    async with session.begin():
        plans = await subscription_service.get_active_plans(session)
        request_logger.info(f"GET /subscriptions/plans returned {len(plans)} plans")
        return PlanListResponse(plans=[_build_plan_response(p) for p in plans])


@router.get(
    "/plans/{plan_id}",
    response_model=PlanResponse,
    summary="Get plan details",
    description="""
## Get Subscription Plan Details

Retrieve detailed information about a specific subscription plan.

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `plan_id` | UUID | The unique identifier of the plan |

### Response

Returns the complete plan details including all features and pricing information.

### Error Responses

| Status | Reason |
|--------|--------|
| `404 Not Found` | Plan does not exist or is inactive |

### Notes

- Both active and inactive plans can be retrieved by ID
- Use this to display plan details before checkout
""",
    responses={
        404: {
            "description": "Plan not found",
            "content": {"application/json": {"example": {"detail": "Plan not found."}}},
        },
    },
)
async def get_plan(
    plan_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> PlanResponse:
    """Get plan details."""
    request_logger.info(f"GET /subscriptions/plans/{plan_id}")
    async with session.begin():
        plan = await subscription_service.get_plan(session, plan_id)
        return _build_plan_response(plan)


# ============================================================================
# Subscription Endpoints
# ============================================================================


@router.get(
    "/workspaces/{workspace_id}",
    response_model=SubscriptionResponse | None,
    summary="Get workspace subscription",
    description="""
## Get Workspace Subscription

Retrieve the current subscription for a workspace. Returns `null` if the
workspace has no active subscription.

### Authorization

- User must be a **member** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace to get subscription for |

### Response

Returns the subscription details including:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Subscription identifier |
| `workspace_id` | UUID | Associated workspace |
| `plan_id` | UUID | Current plan |
| `status` | string | Subscription status (`active`, `canceled`, `past_due`, etc.) |
| `seat_count` | integer | Number of purchased seats |
| `current_period_start` | datetime | Billing period start |
| `current_period_end` | datetime | Billing period end |
| `cancel_at_period_end` | boolean | Whether subscription will cancel at period end |
| `plan` | object | Full plan details |

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not a member of the workspace |

### Notes

- Returns `null` (not 404) if workspace exists but has no subscription
- Personal workspaces automatically have a free subscription
""",
    responses={
        403: {
            "description": "Access denied",
            "content": {
                "application/json": {
                    "example": {"detail": "Access to this workspace is denied."}
                }
            },
        },
    },
)
async def get_workspace_subscription(
    workspace_id: UUID,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> SubscriptionResponse | None:
    """Get subscription for a workspace."""
    request_logger.info(
        f"GET /subscriptions/workspaces/{workspace_id} - user={current_user.id}"
    )
    async with session.begin():
        # Check access
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )
        if not member:
            raise WorkspaceAccessDeniedException()

        subscription = await subscription_service.get_subscription(
            session, workspace_id
        )
        if not subscription:
            return None
        return _build_subscription_response(subscription, workspace_id)


@router.post(
    "/workspaces/{workspace_id}/checkout",
    response_model=CheckoutResponse,
    summary="Create checkout session",
    description="""
## Create Stripe Checkout Session

Create a Stripe checkout session to subscribe the workspace to a paid plan.
Redirects the user to Stripe's hosted checkout page.

### Authorization

- User must be an **admin** or **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace to subscribe |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `plan_id` | UUID | ✅ | The plan to subscribe to |
| `seat_count` | integer | ❌ | Number of seats (default: 1) |
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
| `403 Forbidden` | User is not an admin of the workspace |
| `404 Not Found` | Plan not found |
| `400 Bad Request` | Invalid seat count for plan |

### Notes

- Seat count must be between plan's `min_seats` and `max_seats`
- If workspace already has a subscription, upgrading should use `/upgrade` instead
""",
    responses={
        403: {
            "description": "Admin permission required",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin permission required."}
                }
            },
        },
    },
)
async def create_checkout(
    workspace_id: UUID,
    data: CheckoutRequest,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CheckoutResponse:
    """Create a Stripe checkout session for subscription."""
    request_logger.info(
        f"POST /subscriptions/workspaces/{workspace_id}/checkout "
        f"- user={current_user.id} plan={data.plan_id} seats={data.seat_count}"
    )
    async with session.begin():
        # Check admin access
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )
        if not member or not member.is_admin:
            raise AdminPermissionRequiredException()

        checkout_session = await subscription_service.create_checkout_session(
            session,
            workspace_id=workspace_id,
            plan_id=data.plan_id,
            seat_count=data.seat_count,
            success_url=str(data.success_url),
            cancel_url=str(data.cancel_url),
            user=current_user,
        )

        return CheckoutResponse(
            checkout_url=checkout_session.url or "",
            session_id=checkout_session.id,
        )


@router.patch(
    "/workspaces/{workspace_id}/seats",
    response_model=SubscriptionResponse,
    summary="Update seat count",
    description="""
## Update Subscription Seat Count

Adjust the number of seats on an active workspace subscription.
Changes are prorated and take effect immediately.

### Authorization

- User must be an **admin** or **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace to update |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `seat_count` | integer | ✅ | New number of seats |

### Response

Returns the updated subscription with new seat count and billing details.

### Proration Rules

- **Adding seats**: Immediately billed for the prorated amount
- **Removing seats**: Credit applied to next billing cycle
- Cannot reduce seats below current member count

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not an admin of the workspace |
| `404 Not Found` | No active subscription found |
| `400 Bad Request` | Seat count out of range or below member count |

### Notes

- Seat count must be between plan's `min_seats` and `max_seats`
- Cannot reduce seats below current workspace member count
- Changes update Stripe subscription immediately
""",
    responses={
        403: {
            "description": "Admin permission required",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin permission required."}
                }
            },
        },
        404: {
            "description": "No active subscription",
            "content": {
                "application/json": {
                    "example": {"detail": "No active subscription found."}
                }
            },
        },
    },
)
async def update_seats(
    workspace_id: UUID,
    data: SeatUpdateRequest,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> SubscriptionResponse:
    """Update subscription seat count."""
    request_logger.info(
        f"PATCH /subscriptions/workspaces/{workspace_id}/seats "
        f"- user={current_user.id} seats={data.seat_count}"
    )
    async with session.begin():
        # Check admin access
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )
        if not member or not member.is_admin:
            raise AdminPermissionRequiredException()

        subscription = await subscription_service.update_seat_count(
            session,
            workspace_id=workspace_id,
            new_seat_count=data.seat_count,
            commit_self=False,
        )
        return _build_subscription_response(subscription, workspace_id)


@router.post(
    "/workspaces/{workspace_id}/cancel",
    response_model=SubscriptionResponse,
    summary="Cancel subscription",
    description="""
## Cancel Workspace Subscription

Cancel the workspace subscription. By default, cancellation takes effect at the
end of the current billing period, allowing continued access until then.

### Authorization

- User must be the **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace to cancel subscription for |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cancel_at_period_end` | boolean | ❌ | If `true` (default), cancels at period end. If `false`, cancels immediately |

### Response

Returns the updated subscription with cancellation details.

### Cancellation Behavior

**At Period End (`cancel_at_period_end=true`):**
- Subscription remains active until `current_period_end`
- Members retain full access
- `cancel_at_period_end` flag is set to `true`
- Can be reactivated before period ends

**Immediate (`cancel_at_period_end=false`):**
- Subscription cancelled immediately
- Workspace becomes frozen
- All members disabled except owner
- Prorated refund issued (if applicable)

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not the workspace owner |
| `404 Not Found` | No active subscription found |

### Notes

- Only workspace **owner** can cancel (not admins)
- Immediate cancellation triggers workspace freeze
- Resubscription requires checkout session
""",
    responses={
        403: {
            "description": "Owner permission required",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Only workspace owner can cancel subscription."
                    }
                }
            },
        },
    },
)
async def cancel_subscription(
    workspace_id: UUID,
    data: CancelSubscriptionRequest,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> SubscriptionResponse:
    """Cancel workspace subscription."""
    request_logger.info(
        f"POST /subscriptions/workspaces/{workspace_id}/cancel "
        f"- user={current_user.id} at_period_end={data.cancel_at_period_end}"
    )
    async with session.begin():
        # Check owner access (only owner can cancel)
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )
        if not member or not member.is_owner:
            raise OwnerPermissionRequiredException(
                "Only workspace owner can cancel subscription."
            )

        subscription = await subscription_service.cancel_subscription(
            session,
            workspace_id=workspace_id,
            cancel_at_period_end=data.cancel_at_period_end,
            commit_self=False,
        )
        return _build_subscription_response(subscription, workspace_id)


@router.post(
    "/workspaces/{workspace_id}/reactivate",
    response_model=MessageResponse,
    summary="Reactivate workspace",
    description="""
## Reactivate Frozen Workspace

Reactivate a frozen workspace after subscription cancellation and resubscription.
This endpoint enables workspace access for specified members.

### Authorization

- User must be the **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace to reactivate |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `member_ids_to_enable` | UUID[] | ❌ | List of member IDs to enable. If not specified, only owner is enabled |

### Response

```json
{
  "message": "Workspace reactivated successfully."
}
```

### Reactivation Flow

1. Owner resubscribes to a plan (creates new subscription)
2. Call this endpoint to unfreeze workspace
3. Specify which members to enable (limited by seat count)
4. Additional members can be enabled via seat management

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not the workspace owner |
| `404 Not Found` | Workspace not found |
| `400 Bad Request` | Requested members exceed seat count |

### Notes

- Only workspace **owner** can reactivate
- Number of enabled members cannot exceed subscription seat count
- Members not enabled remain in workspace but cannot access it
""",
    responses={
        403: {
            "description": "Owner permission required",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Only workspace owner can reactivate workspace."
                    }
                }
            },
        },
    },
)
async def reactivate_workspace(
    workspace_id: UUID,
    data: ReactivateRequest,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """Reactivate a frozen workspace after resubscription."""
    request_logger.info(
        f"POST /subscriptions/workspaces/{workspace_id}/reactivate - user={current_user.id}"
    )
    async with session.begin():
        # Check owner access
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )
        if not member or not member.is_owner:
            raise OwnerPermissionRequiredException(
                "Only workspace owner can reactivate workspace."
            )

        await subscription_service.reactivate_workspace(
            session,
            workspace_id=workspace_id,
            member_ids_to_enable=data.member_ids_to_enable,
            commit_self=False,
        )
        return MessageResponse(message="Workspace reactivated successfully.")


@router.post(
    "/workspaces/{workspace_id}/preview-upgrade",
    response_model=UpgradePreviewResponse,
    summary="Preview plan upgrade",
    description="""
## Preview Plan Upgrade Cost

Preview the cost of upgrading to a different plan before committing.
Returns detailed proration information showing charges and credits.

### Authorization

- User must be an **admin** or **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace to preview upgrade for |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `new_plan_id` | UUID | ✅ | The plan to upgrade/downgrade to |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `current_plan_name` | string | Name of current plan |
| `new_plan_name` | string | Name of new plan |
| `proration_date` | datetime | When proration is calculated |
| `amount_due` | integer | Amount to charge (in cents) |
| `credit` | integer | Credit from unused time (in cents) |
| `currency` | string | Currency code (e.g., "usd") |

### Proration Calculation

The preview shows:
- **Credit**: Unused time on current plan
- **Charge**: Cost of new plan for remaining period
- **Net Amount**: What will be charged at upgrade

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not an admin of the workspace |
| `404 Not Found` | No active subscription or plan not found |

### Notes

- This is a **preview only** - no changes are made
- Use the `/upgrade` endpoint to execute the upgrade
- Amounts are in the smallest currency unit (cents for USD)
""",
    responses={
        403: {
            "description": "Admin permission required",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin permission required."}
                }
            },
        },
        404: {
            "description": "Subscription or plan not found",
            "content": {
                "application/json": {
                    "example": {"detail": "No active subscription found."}
                }
            },
        },
    },
)
async def preview_upgrade(
    workspace_id: UUID,
    data: UpgradePreviewRequest,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> UpgradePreviewResponse:
    """Preview the cost of upgrading to a new plan."""
    request_logger.info(
        f"POST /subscriptions/workspaces/{workspace_id}/preview-upgrade "
        f"- user={current_user.id} new_plan={data.new_plan_id}"
    )
    async with session.begin():
        # Check admin access
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )
        if not member or not member.is_admin:
            raise AdminPermissionRequiredException()

        # Get current subscription for plan name
        current_sub = await subscription_service.get_subscription(session, workspace_id)
        if not current_sub:
            raise SubscriptionNotFoundException()

        current_plan = current_sub.plan
        new_plan = await subscription_service.get_plan(session, data.new_plan_id)

        # Get preview from Stripe
        invoice_preview = await subscription_service.preview_upgrade(
            session,
            workspace_id=workspace_id,
            new_plan_id=data.new_plan_id,
        )

        # Convert cents to dollars for response
        total_due = Decimal(invoice_preview.amount_due) / Decimal(100)

        return UpgradePreviewResponse(
            current_plan=current_plan.name,
            new_plan=new_plan.name,
            proration_amount=invoice_preview.proration_amount,
            total_due=total_due,
            currency=invoice_preview.currency,
            billing_period_end=current_sub.current_period_end,
        )


@router.post(
    "/workspaces/{workspace_id}/upgrade",
    response_model=SubscriptionResponse,
    summary="Upgrade subscription plan",
    description="""
## Upgrade Subscription Plan

Upgrade the workspace subscription to a different plan.
Proration is calculated and charged immediately.

### Authorization

- User must be an **admin** or **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace to upgrade |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `new_plan_id` | UUID | ✅ | The plan to upgrade to |

### Response

Returns the updated subscription with the new plan details.

### Upgrade Process

1. **Preview first**: Use `/preview-upgrade` to see costs
2. **Execute upgrade**: Call this endpoint
3. **Proration applied**: Charged immediately via Stripe
4. **New plan active**: Takes effect immediately

### Billing

- Credit for unused time on old plan
- Charge for remaining period on new plan
- Net amount charged to payment method

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not an admin of the workspace |
| `404 Not Found` | No active subscription or plan not found |
| `400 Bad Request` | Invalid upgrade (e.g., current seats exceed new plan limit) |

### Notes

- Upgrades and downgrades are both supported
- For downgrades, ensure current seat count fits new plan limits
- Changes are reflected immediately in Stripe
""",
    responses={
        403: {
            "description": "Admin permission required",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin permission required."}
                }
            },
        },
        404: {
            "description": "Subscription not found",
            "content": {
                "application/json": {
                    "example": {"detail": "No active subscription found."}
                }
            },
        },
    },
)
async def upgrade_plan(
    workspace_id: UUID,
    data: UpgradeRequest,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> SubscriptionResponse:
    """Upgrade subscription to a different plan."""
    request_logger.info(
        f"POST /subscriptions/workspaces/{workspace_id}/upgrade "
        f"- user={current_user.id} new_plan={data.new_plan_id}"
    )
    async with session.begin():
        # Check admin access
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )
        if not member or not member.is_admin:
            raise AdminPermissionRequiredException()

        subscription = await subscription_service.upgrade_plan(
            session,
            workspace_id=workspace_id,
            new_plan_id=data.new_plan_id,
            commit_self=False,
        )
        return _build_subscription_response(subscription, workspace_id)


__all__ = ["router"]
