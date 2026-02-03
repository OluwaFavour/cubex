"""
Stripe webhook message handlers for async event processing.

This module contains handlers for processing Stripe webhook events from queues.
Events are processed asynchronously with retry capabilities and Redis-based
idempotency to prevent duplicate processing.
"""

from typing import Any
from uuid import UUID

from app.shared.config import stripe_logger
from app.shared.db import AsyncSessionLocal
from app.shared.services import RedisService
from app.apps.cubex_api.services import subscription_service


# Redis key prefix for Stripe event deduplication
STRIPE_EVENT_KEY_PREFIX = "stripe_event:"
# TTL for processed event markers (48 hours)
STRIPE_EVENT_TTL = 48 * 3600


async def _is_event_already_processed(event_id: str) -> bool:
    """
    Check if a Stripe event has already been processed using Redis.

    Uses atomic set-if-not-exists to prevent race conditions.

    Args:
        event_id: The Stripe event ID.

    Returns:
        True if event was already processed, False if it's new.
    """
    key = f"{STRIPE_EVENT_KEY_PREFIX}{event_id}"
    is_new = await RedisService.set_if_not_exists(key, "1", ttl=STRIPE_EVENT_TTL)
    return not is_new


async def handle_stripe_checkout_completed(event: dict[str, Any]) -> None:
    """
    Handle checkout.session.completed events from Stripe.

    Activates subscription after successful payment.

    Args:
        event: Event data containing:
            - event_id (str): Stripe event ID for idempotency
            - stripe_subscription_id (str): Stripe subscription ID
            - stripe_customer_id (str): Stripe customer ID
            - workspace_id (str): Workspace UUID
            - plan_id (str): Plan UUID
            - seat_count (int): Number of seats

    Raises:
        Exception: If processing fails, exception is raised to trigger retry.
    """
    event_id = event["event_id"]

    # Idempotency check
    if await _is_event_already_processed(event_id):
        stripe_logger.info(
            f"Checkout completed event {event_id} already processed, skipping"
        )
        return

    stripe_subscription_id = event["stripe_subscription_id"]
    stripe_customer_id = event["stripe_customer_id"]
    workspace_id = UUID(event["workspace_id"])
    plan_id = UUID(event["plan_id"])
    seat_count = event["seat_count"]

    stripe_logger.info(
        f"Processing checkout completed: workspace={workspace_id}, "
        f"subscription={stripe_subscription_id}"
    )

    try:
        async with AsyncSessionLocal.begin() as session:
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
            f"Checkout completed processed successfully: workspace={workspace_id}"
        )
    except Exception as e:
        stripe_logger.error(
            f"Failed to process checkout completed for workspace {workspace_id}: {e}"
        )
        raise


async def handle_stripe_subscription_updated(event: dict[str, Any]) -> None:
    """
    Handle customer.subscription.created/updated events from Stripe.

    Syncs subscription status with Stripe.

    Args:
        event: Event data containing:
            - event_id (str): Stripe event ID for idempotency
            - stripe_subscription_id (str): Stripe subscription ID

    Raises:
        Exception: If processing fails, exception is raised to trigger retry.
    """
    event_id = event["event_id"]

    # Idempotency check
    if await _is_event_already_processed(event_id):
        stripe_logger.info(
            f"Subscription updated event {event_id} already processed, skipping"
        )
        return

    stripe_subscription_id = event["stripe_subscription_id"]

    stripe_logger.info(f"Processing subscription updated: {stripe_subscription_id}")

    try:
        async with AsyncSessionLocal.begin() as session:
            await subscription_service.handle_subscription_updated(
                session,
                stripe_subscription_id=stripe_subscription_id,
                commit_self=False,
            )

        stripe_logger.info(
            f"Subscription updated processed successfully: {stripe_subscription_id}"
        )
    except Exception as e:
        stripe_logger.error(
            f"Failed to process subscription updated {stripe_subscription_id}: {e}"
        )
        raise


async def handle_stripe_subscription_deleted(event: dict[str, Any]) -> None:
    """
    Handle customer.subscription.deleted events from Stripe.

    Freezes workspace when subscription is canceled.

    Args:
        event: Event data containing:
            - event_id (str): Stripe event ID for idempotency
            - stripe_subscription_id (str): Stripe subscription ID

    Raises:
        Exception: If processing fails, exception is raised to trigger retry.
    """
    event_id = event["event_id"]

    # Idempotency check
    if await _is_event_already_processed(event_id):
        stripe_logger.info(
            f"Subscription deleted event {event_id} already processed, skipping"
        )
        return

    stripe_subscription_id = event["stripe_subscription_id"]

    stripe_logger.info(f"Processing subscription deleted: {stripe_subscription_id}")

    try:
        async with AsyncSessionLocal.begin() as session:
            await subscription_service.handle_subscription_deleted(
                session,
                stripe_subscription_id=stripe_subscription_id,
                commit_self=False,
            )

        stripe_logger.info(
            f"Subscription deleted processed successfully: {stripe_subscription_id}"
        )
    except Exception as e:
        stripe_logger.error(
            f"Failed to process subscription deleted {stripe_subscription_id}: {e}"
        )
        raise


async def handle_stripe_payment_failed(event: dict[str, Any]) -> None:
    """
    Handle invoice.payment_failed events from Stripe.

    Logs payment failure. Subscription status will be updated
    via customer.subscription.updated event.

    Args:
        event: Event data containing:
            - event_id (str): Stripe event ID for idempotency
            - stripe_subscription_id (str | None): Stripe subscription ID
            - customer_email (str | None): Customer email

    Note:
        This handler only logs the failure. Stripe will send its own
        dunning emails, and the subscription status update will come
        via a separate subscription.updated event.
    """
    event_id = event["event_id"]

    # Idempotency check
    if await _is_event_already_processed(event_id):
        stripe_logger.info(
            f"Payment failed event {event_id} already processed, skipping"
        )
        return

    stripe_subscription_id = event.get("stripe_subscription_id")
    customer_email = event.get("customer_email")

    stripe_logger.warning(
        f"Payment failed for subscription {stripe_subscription_id}, "
        f"customer: {customer_email}"
    )

    # Could send notification email here in the future
    # For now, just log - Stripe will send its own dunning emails


__all__ = [
    "handle_stripe_checkout_completed",
    "handle_stripe_subscription_updated",
    "handle_stripe_subscription_deleted",
    "handle_stripe_payment_failed",
]
