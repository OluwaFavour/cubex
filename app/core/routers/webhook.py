"""
Stripe webhook handler for core use across cubex apps.

Business logic is NOT handled here - only signature verification and event routing.
"""

from typing import Any

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.config import webhook_logger
from app.core.exceptions.types import BadRequestException
from app.core.services.payment.stripe.main import Stripe
from app.core.services.event_publisher import get_publisher


router = APIRouter(prefix="/webhooks")


EVENT_QUEUE_MAPPING: dict[str, str] = {
    "checkout.session.completed": "stripe_checkout_completed",
    "customer.subscription.created": "stripe_subscription_updated",
    "customer.subscription.updated": "stripe_subscription_updated",
    "customer.subscription.deleted": "stripe_subscription_deleted",
    "customer.subscription.paused": "stripe_subscription_updated",
    "customer.subscription.resumed": "stripe_subscription_updated",
    "invoice.paid": "stripe_subscription_updated",
    "invoice.payment_failed": "stripe_payment_failed",
    "invoice.payment_action_required": "stripe_payment_failed",
}


@router.post(
    "/stripe",
    status_code=status.HTTP_200_OK,
    summary="Handle Stripe webhook events",
    description="""
Receives and processes Stripe webhook events with secure signature verification.

This endpoint is called by Stripe to notify the application of payment events.
Events are verified using webhook signature and then published to message queues
for asynchronous processing.

**Handled Event Types:**
- `checkout.session.completed` - New subscription checkout completed
- `customer.subscription.created` - Subscription created
- `customer.subscription.updated` - Subscription modified (plan change, renewal)
- `customer.subscription.deleted` - Subscription cancelled
- `customer.subscription.paused` - Subscription paused
- `customer.subscription.resumed` - Subscription resumed
- `invoice.paid` - Invoice successfully paid
- `invoice.payment_failed` - Invoice payment failed
- `invoice.payment_action_required` - Payment requires customer action (SCA)

**Processing Flow:**
1. Verify Stripe signature header
2. Parse and validate event payload
3. Publish to appropriate message queue
4. Return 200 OK immediately (async processing)

**Note:** This endpoint should only be called by Stripe's webhook system.
Configure the webhook URL in your Stripe Dashboard.
    """,
    responses={
        200: {
            "description": "Webhook received and processed",
            "content": {
                "application/json": {
                    "examples": {
                        "received": {
                            "summary": "Event received and queued",
                            "value": {"status": "received"},
                        },
                        "ignored": {
                            "summary": "Unhandled event type",
                            "value": {"status": "ignored"},
                        },
                    }
                }
            },
        },
        400: {
            "description": "Invalid request - missing signature or verification failed",
            "content": {
                "application/json": {
                    "examples": {
                        "missing_signature": {
                            "summary": "Missing Stripe-Signature header",
                            "value": {"detail": "Missing Stripe-Signature header"},
                        },
                        "invalid_signature": {
                            "summary": "Signature verification failed",
                            "value": {"detail": "Invalid signature"},
                        },
                        "missing_fields": {
                            "summary": "Missing event id or type",
                            "value": {"detail": "Missing event id or type"},
                        },
                    }
                }
            },
        },
        500: {
            "description": "Internal error - event could not be queued; Stripe will retry",
            "content": {
                "application/json": {
                    "example": {"status": "publish_failed"},
                }
            },
        },
    },
    tags=["Webhooks"],
    response_model=None,
)
async def handle_stripe_webhook(request: Request) -> dict[str, str] | Response:
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
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    if not sig_header:
        webhook_logger.warning("Webhook received without Stripe-Signature header")
        raise BadRequestException("Missing Stripe-Signature header")

    try:
        event = Stripe.verify_webhook_signature(
            payload, {"Stripe-Signature": sig_header}
        )
    except Exception as e:
        webhook_logger.error(f"Webhook signature verification failed: {e}")
        raise BadRequestException("Invalid signature") from e

    event_id: str | None = event.get("id")
    event_type: str | None = event.get("type")

    webhook_logger.info(f"Received webhook: {event_type} ({event_id})")

    if not event_id or not event_type:
        webhook_logger.warning("Webhook missing event id or type")
        raise BadRequestException("Missing event id or type")

    queue_name = EVENT_QUEUE_MAPPING.get(event_type)
    if not queue_name:
        webhook_logger.debug(f"Unhandled event type: {event_type}")
        return {"status": "ignored"}

    data = event.get("data", {})
    obj = data.get("object", {})

    try:
        message = _build_queue_message(event_id, event_type, obj)
        await get_publisher()(queue_name, message)
        webhook_logger.info(f"Published {event_type} to queue {queue_name}")
    except Exception as e:
        webhook_logger.error(f"Failed to publish event {event_id} to queue: {e}")
        # Return 500 so Stripe retries the event (up to 72h with exponential backoff).
        # This is safer than swallowing failures — Stripe has robust retry logic.
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "publish_failed"},
        )

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
    message: dict[str, Any] = {"event_id": event_id}

    if event_type == "checkout.session.completed":
        metadata = obj.get("metadata", {})
        message.update(
            {
                "stripe_subscription_id": obj.get("subscription"),
                "stripe_customer_id": obj.get("customer"),
                "workspace_id": metadata.get("workspace_id"),
                "user_id": metadata.get("user_id"),
                "plan_id": metadata.get("plan_id"),
                "seat_count": int(metadata.get("seat_count", "1")),
                "product_type": metadata.get("product_type", "api"),
            }
        )

    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.paused",
        "customer.subscription.resumed",
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
                "amount_due": obj.get("amount_due"),
            }
        )

    elif event_type == "invoice.payment_action_required":
        message.update(
            {
                "stripe_subscription_id": obj.get("subscription"),
                "customer_email": obj.get("customer_email"),
                "amount_due": obj.get("amount_due"),
            }
        )

    return message


__all__ = ["router"]
