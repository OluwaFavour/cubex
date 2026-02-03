"""
Stripe webhook handler for shared use across cubex apps.

This module provides a single endpoint to handle all Stripe webhook events.
Implements secure signature verification and publishes events to message queues
for async processing with retry capabilities.

Business logic is NOT handled here - only signature verification and event routing.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.shared.config import webhook_logger
from app.shared.services.payment.stripe.main import Stripe
from app.infrastructure.messaging.publisher import publish_event


router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# ============================================================================
# Event Type to Queue Mapping
# ============================================================================

EVENT_QUEUE_MAPPING: dict[str, str] = {
    "checkout.session.completed": "stripe_checkout_completed",
    "customer.subscription.created": "stripe_subscription_updated",
    "customer.subscription.updated": "stripe_subscription_updated",
    "customer.subscription.deleted": "stripe_subscription_deleted",
    "invoice.paid": "stripe_subscription_updated",
    "invoice.payment_failed": "stripe_payment_failed",
}


# ============================================================================
# Webhook Handler
# ============================================================================


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def handle_stripe_webhook(request: Request) -> dict[str, str]:
    """
    Handle Stripe webhook events.

    This endpoint receives all Stripe events, verifies the signature,
    and publishes them to appropriate message queues for async processing.

    Key principles:
    - Verifies Stripe signature
    - Returns 200 OK immediately after publishing
    - Business logic handled by message consumers
    - Idempotency handled by message handlers via Redis
    """
    # Get raw body and signature
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    if not sig_header:
        webhook_logger.warning("Webhook received without Stripe-Signature header")
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
        webhook_logger.error(f"Webhook signature verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        )

    event_id: str | None = event.get("id")
    event_type: str | None = event.get("type")

    webhook_logger.info(f"Received webhook: {event_type} ({event_id})")

    # Validate required fields
    if not event_id or not event_type:
        webhook_logger.warning("Webhook missing event id or type")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing event id or type",
        )

    # Get queue name for this event type
    queue_name = EVENT_QUEUE_MAPPING.get(event_type)
    if not queue_name:
        webhook_logger.debug(f"Unhandled event type: {event_type}")
        return {"status": "ignored"}

    # Extract event data and publish to queue
    data = event.get("data", {})
    obj = data.get("object", {})

    try:
        message = _build_queue_message(event_id, event_type, obj)
        await publish_event(queue_name, message)
        webhook_logger.info(f"Published {event_type} to queue {queue_name}")
    except Exception as e:
        webhook_logger.error(f"Failed to publish event {event_id} to queue: {e}")
        # Still return 200 to prevent Stripe retries - we'll handle via dead letter
        return {"status": "publish_failed"}

    return {"status": "received"}


def _build_queue_message(
    event_id: str,
    event_type: str,
    obj: dict[str, Any],
) -> dict[str, Any]:
    """
    Build queue message payload from Stripe event object.

    Args:
        event_id: Stripe event ID (for idempotency).
        event_type: Type of Stripe event.
        obj: The event object data.

    Returns:
        Message payload for the queue.
    """
    # Common fields for all messages
    message: dict[str, Any] = {"event_id": event_id}

    if event_type == "checkout.session.completed":
        # Extract metadata for checkout completion
        metadata = obj.get("metadata", {})
        message.update(
            {
                "stripe_subscription_id": obj.get("subscription"),
                "stripe_customer_id": obj.get("customer"),
                "workspace_id": metadata.get("workspace_id"),
                "plan_id": metadata.get("plan_id"),
                "seat_count": int(metadata.get("seat_count", "1")),
            }
        )

    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
    ):
        message["stripe_subscription_id"] = obj.get("id")

    elif event_type == "customer.subscription.deleted":
        message["stripe_subscription_id"] = obj.get("id")

    elif event_type == "invoice.paid":
        message["stripe_subscription_id"] = obj.get("subscription")

    elif event_type == "invoice.payment_failed":
        message.update(
            {
                "stripe_subscription_id": obj.get("subscription"),
                "customer_email": obj.get("customer_email"),
            }
        )

    return message


__all__ = ["router"]
