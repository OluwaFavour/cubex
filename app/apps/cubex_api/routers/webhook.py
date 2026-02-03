"""
Stripe webhook handler for cubex_api.

This module provides a single endpoint to handle all Stripe webhook events.
Implements event deduplication and secure signature verification.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_async_session
from app.shared.config import stripe_logger
from app.shared.db.crud import stripe_event_log_db, plan_db
from app.shared.services.payment.stripe.main import Stripe
from app.infrastructure.messaging import publish_event
from app.apps.cubex_api.services import subscription_service
from app.apps.cubex_api.db.crud import workspace_db


router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# ============================================================================
# Webhook Handler
# ============================================================================


@router.post(
    "/stripe",
    status_code=status.HTTP_200_OK,
    summary="Stripe webhook handler",
    description="""
## Stripe Webhook Handler

Receives and processes all Stripe webhook events for the cubex_api product.
This endpoint is called by Stripe when subscription-related events occur.

### Authentication

- Stripe webhook signature verification (not user authentication)
- Requires `Stripe-Signature` header from Stripe

### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Stripe-Signature` | ✅ | Stripe's webhook signature |
| `Content-Type` | ✅ | `application/json` |

### Request Body

Raw Stripe event payload (JSON). Structure varies by event type.

### Handled Events

| Event Type | Action |
|------------|--------|
| `checkout.session.completed` | Create subscription after successful checkout |
| `invoice.paid` | Update subscription period dates |
| `invoice.payment_failed` | Mark subscription as past_due |
| `customer.subscription.updated` | Sync subscription changes from Stripe |
| `customer.subscription.deleted` | Cancel subscription, freeze workspace |

### Response

```json
{
  "status": "success"
}
```

Or for already processed events:
```json
{
  "status": "already_processed"
}
```

### Error Responses

| Status | Reason |
|--------|--------|
| `400 Bad Request` | Missing signature header or invalid signature |

### Implementation Details

1. **Signature Verification**: Validates Stripe signature using webhook secret
2. **Event Deduplication**: Uses event ID to prevent double-processing
3. **Workspace Lookup**: Finds workspace via Stripe customer ID in database
4. **Graceful Degradation**: Returns 200 for unhandled event types

### Notes

- Always returns 200 to Stripe (even for unhandled events)
- Events are logged for debugging
- Workspace freeze occurs 3 days after subscription deletion
""",
    responses={
        200: {
            "description": "Event processed successfully",
            "content": {"application/json": {"example": {"status": "success"}}},
        },
        400: {
            "description": "Invalid signature or missing header",
            "content": {
                "application/json": {"example": {"detail": "Invalid signature"}}
            },
        },
    },
)
async def handle_stripe_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, str]:
    """Handle Stripe webhook events."""
    # Get raw body and signature
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    if not sig_header:
        stripe_logger.warning("Webhook received without Stripe-Signature header")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header",
        )

    # Verify signature and construct event
    try:
        event = Stripe.verify_webhook_signature(
            payload, {"Stripe-Signature": sig_header}
        )
    except Exception as e:
        stripe_logger.error(f"Webhook signature verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        )

    event_id: str | None = event.get("id")
    event_type: str | None = event.get("type")

    stripe_logger.info(f"Received webhook: {event_type} ({event_id})")

    # Validate required fields
    if not event_id or not event_type:
        stripe_logger.warning("Webhook missing event id or type")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing event id or type",
        )

    # Deduplicate: check if event was already processed
    async with session.begin():
        if await stripe_event_log_db.is_event_processed(session, event_id):
            stripe_logger.info(f"Event {event_id} already processed, skipping")
            return {"status": "already_processed"}

        # Mark event as processed (before handling to prevent race conditions)
        await stripe_event_log_db.mark_event_processed(
            session, event_id, event_type, commit_self=False
        )

    # Route to appropriate handler
    try:
        async with session.begin():
            await _route_event(session, event_type, event)
    except Exception as e:
        stripe_logger.error(f"Error handling webhook {event_type}: {e}")
        # Still return 200 to prevent Stripe retries for app errors
        # Log the error for investigation

    return {"status": "received"}


async def _route_event(
    session: AsyncSession,
    event_type: str,
    event: dict[str, Any],
) -> None:
    """
    Route Stripe event to appropriate handler.

    Args:
        session: Database session.
        event_type: Type of Stripe event.
        event: Full event object.
    """
    data = event.get("data", {})
    obj = data.get("object", {})

    handlers = {
        "checkout.session.completed": _handle_checkout_completed,
        "customer.subscription.created": _handle_subscription_updated,
        "customer.subscription.updated": _handle_subscription_updated,
        "customer.subscription.deleted": _handle_subscription_deleted,
        "invoice.paid": _handle_invoice_paid,
        "invoice.payment_failed": _handle_payment_failed,
    }

    handler = handlers.get(event_type)
    if handler:
        await handler(session, obj)
    else:
        stripe_logger.debug(f"Unhandled event type: {event_type}")


async def _handle_checkout_completed(
    session: AsyncSession,
    checkout_session: dict[str, Any],
) -> None:
    """
    Handle checkout.session.completed event.

    Activates subscription after successful payment.
    """
    mode = checkout_session.get("mode")
    if mode != "subscription":
        stripe_logger.debug(f"Ignoring checkout session with mode: {mode}")
        return

    # Get metadata
    metadata = checkout_session.get("metadata", {})
    workspace_id_str = metadata.get("workspace_id")
    plan_id_str = metadata.get("plan_id")
    seat_count_str = metadata.get("seat_count", "1")

    if not workspace_id_str or not plan_id_str:
        stripe_logger.warning(
            f"Checkout session missing metadata: workspace_id={workspace_id_str}, plan_id={plan_id_str}"
        )
        return

    try:
        workspace_id = UUID(workspace_id_str)
        plan_id = UUID(plan_id_str)
        seat_count = int(seat_count_str)
    except (ValueError, TypeError) as e:
        stripe_logger.error(f"Invalid metadata format: {e}")
        return

    # Get subscription ID from checkout session
    stripe_subscription_id = checkout_session.get("subscription")
    stripe_customer_id = checkout_session.get("customer")

    if not stripe_subscription_id:
        stripe_logger.warning("Checkout session missing subscription ID")
        return

    if not stripe_customer_id:
        stripe_logger.warning("Checkout session missing customer ID")
        return

    await subscription_service.handle_checkout_completed(
        session,
        stripe_subscription_id=stripe_subscription_id,
        stripe_customer_id=stripe_customer_id,
        workspace_id=workspace_id,
        plan_id=plan_id,
        seat_count=seat_count,
        commit_self=False,
    )

    stripe_logger.info(
        f"Checkout completed for workspace {workspace_id}, subscription {stripe_subscription_id}"
    )

    # Queue subscription activated email to workspace owner
    try:
        workspace = await workspace_db.get_by_id(session, workspace_id)
        plan = await plan_db.get_by_id(session, plan_id)
        if workspace and workspace.owner:
            await publish_event(
                "subscription_activated_emails",
                {
                    "email": workspace.owner.email,
                    "user_name": workspace.owner.full_name,
                    "plan_name": plan.name if plan else None,
                    "workspace_name": workspace.display_name,
                    "seat_count": seat_count,
                    "product_name": "Cubex API",
                },
            )
            stripe_logger.info(
                f"Subscription activated email queued for {workspace.owner.email}"
            )
    except Exception as e:
        # Log but don't fail the webhook for email queue errors
        stripe_logger.error(f"Failed to queue subscription activated email: {e}")


async def _handle_subscription_updated(
    session: AsyncSession,
    subscription: dict[str, Any],
) -> None:
    """
    Handle customer.subscription.created/updated events.

    Syncs subscription status with Stripe.
    """
    stripe_subscription_id = subscription.get("id")
    if not stripe_subscription_id:
        return

    await subscription_service.handle_subscription_updated(
        session,
        stripe_subscription_id=stripe_subscription_id,
        commit_self=False,
    )

    stripe_logger.info(f"Subscription updated: {stripe_subscription_id}")


async def _handle_subscription_deleted(
    session: AsyncSession,
    subscription: dict[str, Any],
) -> None:
    """
    Handle customer.subscription.deleted event.

    Freezes workspace when subscription is canceled.
    """
    stripe_subscription_id = subscription.get("id")
    if not stripe_subscription_id:
        return

    deleted_subscription = await subscription_service.handle_subscription_deleted(
        session,
        stripe_subscription_id=stripe_subscription_id,
        commit_self=False,
    )

    stripe_logger.info(f"Subscription deleted: {stripe_subscription_id}")

    # Queue subscription canceled email to workspace owner
    if deleted_subscription and deleted_subscription.api_context:
        try:
            workspace_id = deleted_subscription.api_context.workspace_id
            workspace = await workspace_db.get_by_id(session, workspace_id)
            plan = await plan_db.get_by_id(session, deleted_subscription.plan_id)
            if workspace and workspace.owner:
                await publish_event(
                    "subscription_canceled_emails",
                    {
                        "email": workspace.owner.email,
                        "user_name": workspace.owner.full_name,
                        "plan_name": plan.name if plan else None,
                        "workspace_name": workspace.display_name,
                        "product_name": "Cubex API",
                    },
                )
                stripe_logger.info(
                    f"Subscription canceled email queued for {workspace.owner.email}"
                )
        except Exception as e:
            # Log but don't fail the webhook for email queue errors
            stripe_logger.error(f"Failed to queue subscription canceled email: {e}")


async def _handle_invoice_paid(
    session: AsyncSession,
    invoice: dict[str, Any],
) -> None:
    """
    Handle invoice.paid event.

    Updates billing period on successful payment.
    """
    stripe_subscription_id = invoice.get("subscription")
    if not stripe_subscription_id:
        return

    # Just sync the subscription state
    await subscription_service.handle_subscription_updated(
        session,
        stripe_subscription_id=stripe_subscription_id,
        commit_self=False,
    )

    stripe_logger.info(f"Invoice paid for subscription: {stripe_subscription_id}")


async def _handle_payment_failed(
    session: AsyncSession,
    invoice: dict[str, Any],
) -> None:
    """
    Handle invoice.payment_failed event.

    Queues payment failure notification and logs the event.
    Subscription status will be updated via customer.subscription.updated event.
    """
    from app.shared.db.crud import subscription_db

    stripe_subscription_id = invoice.get("subscription")
    customer_email = invoice.get("customer_email")
    amount_due = invoice.get("amount_due", 0)  # Amount in cents

    stripe_logger.warning(
        f"Payment failed for subscription {stripe_subscription_id}, "
        f"customer: {customer_email}"
    )

    # Queue payment failed email to workspace owner
    if stripe_subscription_id:
        try:
            subscription = await subscription_db.get_by_stripe_subscription_id(
                session, stripe_subscription_id
            )
            if subscription and subscription.api_context:
                workspace_id = subscription.api_context.workspace_id
                workspace = await workspace_db.get_by_id(session, workspace_id)
                plan = await plan_db.get_by_id(session, subscription.plan_id)
                if workspace and workspace.owner:
                    # Convert cents to dollars
                    amount_str = f"{amount_due / 100:.2f}" if amount_due else None
                    await publish_event(
                        "payment_failed_emails",
                        {
                            "email": workspace.owner.email,
                            "user_name": workspace.owner.full_name,
                            "plan_name": plan.name if plan else None,
                            "workspace_name": workspace.display_name,
                            "amount": amount_str,
                            "update_payment_url": None,  # Could be configured from settings
                            "product_name": "Cubex API",
                        },
                    )
                    stripe_logger.info(
                        f"Payment failed email queued for {workspace.owner.email}"
                    )
        except Exception as e:
            # Log but don't fail the webhook for email queue errors
            stripe_logger.error(f"Failed to queue payment failed email: {e}")


__all__ = ["router"]
