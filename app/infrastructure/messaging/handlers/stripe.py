"""
Stripe webhook message handlers for async event processing.

This module contains handlers for processing Stripe webhook events from queues.
Events are processed asynchronously with retry capabilities and Redis-based
idempotency to prevent duplicate processing.

Supports both API (workspace-based) and Career (user-based) subscriptions.
"""

from typing import Any
from uuid import UUID

from app.shared.config import stripe_logger
from app.shared.db import AsyncSessionLocal
from app.shared.db.crud import (
    subscription_db,
    plan_db,
    user_db,
    api_subscription_context_db,
    career_subscription_context_db,
)
from app.shared.enums import ProductType
from app.shared.services import RedisService
from app.apps.cubex_api.services import subscription_service as api_subscription_service
from app.apps.cubex_api.db.crud import workspace_db
from app.apps.cubex_career.services import (
    career_subscription_service,
)
from app.infrastructure.messaging.publisher import publish_event


# Redis key prefix for Stripe event deduplication
STRIPE_EVENT_KEY_PREFIX = "stripe_event:"
# TTL for processed event markers (48 hours)
STRIPE_EVENT_TTL = 48 * 3600


async def _is_event_already_processed(event_id: str) -> bool:
    """
    Check if a Stripe event has already been processed using Redis.

    Only checks if the key exists - does NOT set it.
    Use _mark_event_as_processed() after successful processing.

    Args:
        event_id: The Stripe event ID.

    Returns:
        True if event was already processed, False if it's new.
    """
    key = f"{STRIPE_EVENT_KEY_PREFIX}{event_id}"
    return await RedisService.exists(key)


async def _mark_event_as_processed(event_id: str) -> None:
    """
    Mark a Stripe event as successfully processed in Redis.

    Uses set_if_not_exists for atomic operation (race condition safe).
    Should only be called after successful event processing.

    Args:
        event_id: The Stripe event ID.
    """
    key = f"{STRIPE_EVENT_KEY_PREFIX}{event_id}"
    await RedisService.set_if_not_exists(key, "1", ttl=STRIPE_EVENT_TTL)


async def handle_stripe_checkout_completed(event: dict[str, Any]) -> None:
    """
    Handle checkout.session.completed events from Stripe.

    Routes to API or Career service based on product_type in metadata.

    Args:
        event: Event data containing:
            - event_id (str): Stripe event ID for idempotency
            - stripe_subscription_id (str): Stripe subscription ID
            - stripe_customer_id (str): Stripe customer ID
            - product_type (str): "api" or "career"
            - workspace_id (str | None): Workspace UUID (for API)
            - user_id (str | None): User UUID (for Career)
            - plan_id (str): Plan UUID
            - seat_count (int): Number of seats (API only)

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
    product_type = event.get("product_type", "api")
    plan_id = UUID(event["plan_id"])

    if product_type == "career":
        # Career subscription (user-based)
        user_id = UUID(event["user_id"])
        stripe_logger.info(
            f"Processing Career checkout completed: user={user_id}, "
            f"subscription={stripe_subscription_id}"
        )

        try:
            async with AsyncSessionLocal.begin() as session:
                await career_subscription_service.handle_checkout_completed(
                    session,
                    stripe_subscription_id=stripe_subscription_id,
                    stripe_customer_id=stripe_customer_id,
                    user_id=user_id,
                    plan_id=plan_id,
                    commit_self=False,
                )

            stripe_logger.info(
                f"Career checkout completed processed successfully: user={user_id}"
            )
            # Mark event as processed only after successful completion
            await _mark_event_as_processed(event_id)
        except Exception as e:
            stripe_logger.error(
                f"Failed to process Career checkout completed for user {user_id}: {e}"
            )
            raise
    else:
        # API subscription (workspace-based)
        workspace_id = UUID(event["workspace_id"])
        seat_count = event["seat_count"]
        stripe_logger.info(
            f"Processing API checkout completed: workspace={workspace_id}, "
            f"subscription={stripe_subscription_id}"
        )

        try:
            async with AsyncSessionLocal.begin() as session:
                await api_subscription_service.handle_checkout_completed(
                    session,
                    stripe_subscription_id=stripe_subscription_id,
                    stripe_customer_id=stripe_customer_id,
                    workspace_id=workspace_id,
                    plan_id=plan_id,
                    seat_count=seat_count,
                    commit_self=False,
                )

            stripe_logger.info(
                f"API checkout completed processed successfully: workspace={workspace_id}"
            )
            # Mark event as processed only after successful completion
            await _mark_event_as_processed(event_id)
        except Exception as e:
            stripe_logger.error(
                f"Failed to process API checkout completed for workspace {workspace_id}: {e}"
            )
            raise


async def handle_stripe_subscription_updated(event: dict[str, Any]) -> None:
    """
    Handle customer.subscription.created/updated events from Stripe.

    Routes to API or Career service based on the subscription's plan product type.

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
            # Look up subscription to determine product type
            subscription = await subscription_db.get_by_stripe_subscription_id(
                session, stripe_subscription_id
            )

            if not subscription:
                stripe_logger.warning(
                    f"Subscription {stripe_subscription_id} not found, skipping update"
                )
                return

            # Route to appropriate service based on plan's product type
            if subscription.plan.product_type == ProductType.CAREER:
                await career_subscription_service.handle_subscription_updated(
                    session,
                    stripe_subscription_id=stripe_subscription_id,
                    commit_self=False,
                )
                stripe_logger.info(
                    f"Career subscription updated: {stripe_subscription_id}"
                )
            else:
                await api_subscription_service.handle_subscription_updated(
                    session,
                    stripe_subscription_id=stripe_subscription_id,
                    commit_self=False,
                )
                stripe_logger.info(
                    f"API subscription updated: {stripe_subscription_id}"
                )

        # Mark event as processed only after successful completion
        await _mark_event_as_processed(event_id)

    except Exception as e:
        stripe_logger.error(
            f"Failed to process subscription updated {stripe_subscription_id}: {e}"
        )
        raise


async def handle_stripe_subscription_deleted(event: dict[str, Any]) -> None:
    """
    Handle customer.subscription.deleted events from Stripe.

    Routes to API or Career service based on the subscription's plan product type.
    Freezes workspace (API) or downgrades user (Career) when subscription is canceled.

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
            # Look up subscription to determine product type
            subscription = await subscription_db.get_by_stripe_subscription_id(
                session, stripe_subscription_id
            )

            if not subscription:
                stripe_logger.warning(
                    f"Subscription {stripe_subscription_id} not found, skipping delete"
                )
                return

            # Get plan info for email
            plan = await plan_db.get_by_id(session, subscription.plan_id)
            plan_name = plan.name if plan else "your plan"

            # Route to appropriate service based on plan's product type
            if subscription.plan.product_type == ProductType.CAREER:
                await career_subscription_service.handle_subscription_deleted(
                    session,
                    stripe_subscription_id=stripe_subscription_id,
                    commit_self=False,
                )
                stripe_logger.info(
                    f"Career subscription deleted: {stripe_subscription_id}"
                )

                # Queue cancellation email for Career user
                context = await career_subscription_context_db.get_by_subscription(
                    session, subscription.id
                )
                if context:
                    user = await user_db.get_by_id(session, context.user_id)
                    if user:
                        await publish_event(
                            "subscription_canceled_emails",
                            {
                                "email": user.email,
                                "user_name": user.full_name,
                                "plan_name": plan_name,
                                "workspace_name": None,
                                "product_name": "Cubex Career",
                            },
                        )
            else:
                await api_subscription_service.handle_subscription_deleted(
                    session,
                    stripe_subscription_id=stripe_subscription_id,
                    commit_self=False,
                )
                stripe_logger.info(
                    f"API subscription deleted: {stripe_subscription_id}"
                )

                # Queue cancellation email for API workspace owner
                context = await api_subscription_context_db.get_by_subscription(
                    session, subscription.id
                )
                if context:
                    workspace = await workspace_db.get_by_id(
                        session, context.workspace_id
                    )
                    if workspace:
                        owner = await user_db.get_by_id(session, workspace.owner_id)
                        if owner:
                            await publish_event(
                                "subscription_canceled_emails",
                                {
                                    "email": owner.email,
                                    "user_name": owner.full_name,
                                    "plan_name": plan_name,
                                    "workspace_name": workspace.display_name,
                                    "product_name": "Cubex API",
                                },
                            )

        # Mark event as processed only after successful completion
        await _mark_event_as_processed(event_id)

    except Exception as e:
        stripe_logger.error(
            f"Failed to process subscription deleted {stripe_subscription_id}: {e}"
        )
        raise


async def handle_stripe_payment_failed(event: dict[str, Any]) -> None:
    """
    Handle invoice.payment_failed events from Stripe.

    Sends payment failure notification email and logs the failure.
    Subscription status will be updated via customer.subscription.updated event.

    Args:
        event: Event data containing:
            - event_id (str): Stripe event ID for idempotency
            - stripe_subscription_id (str | None): Stripe subscription ID
            - customer_email (str | None): Customer email
            - amount_due (int | None): Amount due in cents

    Note:
        The subscription status update will come via a separate
        subscription.updated event from Stripe.
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
    amount_due = event.get("amount_due")

    stripe_logger.warning(
        f"Payment failed for subscription {stripe_subscription_id}, "
        f"customer: {customer_email}"
    )

    # Send payment failed email if we have subscription info
    if stripe_subscription_id:
        try:
            async with AsyncSessionLocal() as session:
                subscription = await subscription_db.get_by_stripe_subscription_id(
                    session, stripe_subscription_id
                )

                if subscription:
                    plan = await plan_db.get_by_id(session, subscription.plan_id)
                    plan_name = plan.name if plan else "your plan"

                    # Format amount (convert cents to dollars)
                    amount_str = None
                    if amount_due:
                        amount_str = f"${amount_due / 100:.2f}"

                    if subscription.product_type == ProductType.CAREER:
                        # Career subscription - email the user
                        context = (
                            await career_subscription_context_db.get_by_subscription(
                                session, subscription.id
                            )
                        )
                        if context:
                            user = await user_db.get_by_id(session, context.user_id)
                            if user:
                                await publish_event(
                                    "payment_failed_emails",
                                    {
                                        "email": user.email,
                                        "user_name": user.full_name,
                                        "plan_name": plan_name,
                                        "workspace_name": None,
                                        "amount": amount_str,
                                        "product_name": "Cubex Career",
                                    },
                                )
                    else:
                        # API subscription - email the workspace owner
                        context = await api_subscription_context_db.get_by_subscription(
                            session, subscription.id
                        )
                        if context:
                            workspace = await workspace_db.get_by_id(
                                session, context.workspace_id
                            )
                            if workspace:
                                owner = await user_db.get_by_id(
                                    session, workspace.owner_id
                                )
                                if owner:
                                    await publish_event(
                                        "payment_failed_emails",
                                        {
                                            "email": owner.email,
                                            "user_name": owner.full_name,
                                            "plan_name": plan_name,
                                            "workspace_name": workspace.display_name,
                                            "amount": amount_str,
                                            "product_name": "Cubex API",
                                        },
                                    )
        except Exception as e:
            # Don't fail the handler if email queueing fails
            stripe_logger.error(f"Failed to queue payment failed email: {e}")

    # Mark event as processed
    await _mark_event_as_processed(event_id)


__all__ = [
    "handle_stripe_checkout_completed",
    "handle_stripe_subscription_updated",
    "handle_stripe_subscription_deleted",
    "handle_stripe_payment_failed",
]
