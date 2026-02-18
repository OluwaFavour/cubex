"""
Stripe webhook message handlers for async event processing.

This module contains handlers for processing Stripe webhook events from queues.
Events are processed asynchronously with retry capabilities and Redis-based
idempotency to prevent duplicate processing.

Supports both API (workspace-based) and Career (user-based) subscriptions.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import stripe_logger
from app.core.db import AsyncSessionLocal
from app.core.db.crud import (
    subscription_db,
    plan_db,
    user_db,
    api_subscription_context_db,
    career_subscription_context_db,
)
from app.core.db.models import Subscription
from app.core.enums import ProductType
from app.core.services import RedisService
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


# =============================================================================
# Idempotency Helpers
# =============================================================================


async def _is_event_already_processed(event_id: str) -> bool:
    """Check if a Stripe event has already been processed using Redis."""
    key = f"{STRIPE_EVENT_KEY_PREFIX}{event_id}"
    return await RedisService.exists(key)


async def _mark_event_as_processed(event_id: str) -> None:
    """Mark a Stripe event as successfully processed in Redis."""
    key = f"{STRIPE_EVENT_KEY_PREFIX}{event_id}"
    await RedisService.set_if_not_exists(key, "1", ttl=STRIPE_EVENT_TTL)


# =============================================================================
# Email Notification Helpers
# =============================================================================


async def _get_career_user_email_info(
    session: AsyncSession, subscription_id: UUID
) -> tuple[str, str] | None:
    """Get email and full_name for a Career subscription user."""
    context = await career_subscription_context_db.get_by_subscription(
        session, subscription_id
    )
    if not context:
        return None
    user = await user_db.get_by_id(session, context.user_id)
    if not user:
        return None
    return user.email, user.full_name or "Valued Customer"


async def _get_api_workspace_owner_email_info(
    session: AsyncSession, subscription_id: UUID
) -> tuple[str, str, str] | None:
    """Get email, full_name, and workspace_name for an API subscription owner."""
    context = await api_subscription_context_db.get_by_subscription(
        session, subscription_id
    )
    if not context:
        return None
    workspace = await workspace_db.get_by_id(session, context.workspace_id)
    if not workspace or not workspace.owner:
        return None
    return (
        workspace.owner.email,
        workspace.owner.full_name or "Valued Customer",
        workspace.display_name,
    )


async def _send_subscription_activated_email(
    session: AsyncSession,
    subscription: Subscription,
    old_plan_name: str,
) -> None:
    """Send plan change notification email."""
    if subscription.plan.product_type == ProductType.CAREER:
        info = await _get_career_user_email_info(session, subscription.id)
        if info:
            email, full_name = info
            await publish_event(
                "subscription_activated_emails",
                {
                    "email": email,
                    "full_name": full_name,
                    "plan_name": subscription.plan.name,
                    "product_type": ProductType.CAREER.value,
                },
            )
            stripe_logger.info(
                f"Plan change email queued for {email}: "
                f"{old_plan_name} -> {subscription.plan.name}"
            )
    else:
        info = await _get_api_workspace_owner_email_info(session, subscription.id)
        if info:
            email, full_name, workspace_name = info
            await publish_event(
                "subscription_activated_emails",
                {
                    "email": email,
                    "full_name": full_name,
                    "plan_name": subscription.plan.name,
                    "product_type": ProductType.API.value,
                    "workspace_name": workspace_name,
                },
            )
            stripe_logger.info(
                f"Plan change email queued for {email}: "
                f"{old_plan_name} -> {subscription.plan.name}"
            )


async def _send_subscription_canceled_email(
    session: AsyncSession,
    subscription: Subscription,
    plan_name: str,
) -> None:
    """Send subscription cancellation notification email."""
    if subscription.plan.product_type == ProductType.CAREER:
        info = await _get_career_user_email_info(session, subscription.id)
        if info:
            email, full_name = info
            await publish_event(
                "subscription_canceled_emails",
                {
                    "email": email,
                    "user_name": full_name,
                    "plan_name": plan_name,
                    "workspace_name": None,
                    "product_name": "CueBX Career",
                },
            )
    else:
        info = await _get_api_workspace_owner_email_info(session, subscription.id)
        if info:
            email, full_name, workspace_name = info
            await publish_event(
                "subscription_canceled_emails",
                {
                    "email": email,
                    "user_name": full_name,
                    "plan_name": plan_name,
                    "workspace_name": workspace_name,
                    "product_name": "CueBX API",
                },
            )


async def _send_payment_failed_email(
    session: AsyncSession,
    subscription: Subscription,
    plan_name: str,
    amount_str: str | None,
) -> None:
    """Send payment failure notification email."""
    if subscription.product_type == ProductType.CAREER:
        info = await _get_career_user_email_info(session, subscription.id)
        if info:
            email, full_name = info
            await publish_event(
                "payment_failed_emails",
                {
                    "email": email,
                    "user_name": full_name,
                    "plan_name": plan_name,
                    "workspace_name": None,
                    "amount": amount_str,
                    "product_name": "CueBX Career",
                },
            )
    else:
        info = await _get_api_workspace_owner_email_info(session, subscription.id)
        if info:
            email, full_name, workspace_name = info
            await publish_event(
                "payment_failed_emails",
                {
                    "email": email,
                    "user_name": full_name,
                    "plan_name": plan_name,
                    "workspace_name": workspace_name,
                    "amount": amount_str,
                    "product_name": "CueBX API",
                },
            )


# =============================================================================
# Checkout Processing Helpers
# =============================================================================


async def _process_career_checkout(
    stripe_subscription_id: str,
    stripe_customer_id: str,
    user_id: UUID,
    plan_id: UUID,
) -> None:
    """Process checkout completion for Career subscription."""
    stripe_logger.info(
        f"Processing Career checkout completed: user={user_id}, "
        f"subscription={stripe_subscription_id}"
    )
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


async def _process_api_checkout(
    stripe_subscription_id: str,
    stripe_customer_id: str,
    workspace_id: UUID,
    plan_id: UUID,
    seat_count: int,
) -> None:
    """Process checkout completion for API subscription."""
    stripe_logger.info(
        f"Processing API checkout completed: workspace={workspace_id}, "
        f"subscription={stripe_subscription_id}"
    )
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


# =============================================================================
# Subscription Update/Delete Helpers
# =============================================================================


async def _process_subscription_update(stripe_subscription_id: str) -> None:
    """Process subscription update event."""
    stripe_logger.info(f"Processing subscription updated: {stripe_subscription_id}")

    async with AsyncSessionLocal.begin() as session:
        subscription = await subscription_db.get_by_stripe_subscription_id(
            session, stripe_subscription_id
        )
        if not subscription:
            stripe_logger.warning(
                f"Subscription {stripe_subscription_id} not found, skipping update"
            )
            return

        old_plan_id = subscription.plan_id
        old_plan_name = subscription.plan.name

        # Route to appropriate service
        if subscription.plan.product_type == ProductType.CAREER:
            updated = await career_subscription_service.handle_subscription_updated(
                session,
                stripe_subscription_id=stripe_subscription_id,
                commit_self=False,
            )
            stripe_logger.info(f"Career subscription updated: {stripe_subscription_id}")
        else:
            updated = await api_subscription_service.handle_subscription_updated(
                session,
                stripe_subscription_id=stripe_subscription_id,
                commit_self=False,
            )
            stripe_logger.info(f"API subscription updated: {stripe_subscription_id}")

        # Send email if plan changed
        if updated and updated.plan_id != old_plan_id:
            await _send_subscription_activated_email(session, updated, old_plan_name)


async def _process_subscription_deletion(stripe_subscription_id: str) -> None:
    """Process subscription deletion event."""
    stripe_logger.info(f"Processing subscription deleted: {stripe_subscription_id}")

    async with AsyncSessionLocal.begin() as session:
        subscription = await subscription_db.get_by_stripe_subscription_id(
            session, stripe_subscription_id
        )
        if not subscription:
            stripe_logger.warning(
                f"Subscription {stripe_subscription_id} not found, skipping delete"
            )
            return

        plan = await plan_db.get_by_id(session, subscription.plan_id)
        plan_name = plan.name if plan else "your plan"

        # Route to appropriate service
        if subscription.plan.product_type == ProductType.CAREER:
            await career_subscription_service.handle_subscription_deleted(
                session,
                stripe_subscription_id=stripe_subscription_id,
                commit_self=False,
            )
            stripe_logger.info(f"Career subscription deleted: {stripe_subscription_id}")
        else:
            await api_subscription_service.handle_subscription_deleted(
                session,
                stripe_subscription_id=stripe_subscription_id,
                commit_self=False,
            )
            stripe_logger.info(f"API subscription deleted: {stripe_subscription_id}")

        # Send cancellation email
        await _send_subscription_canceled_email(session, subscription, plan_name)


async def _process_payment_failure(
    stripe_subscription_id: str | None,
    amount_due: int | None,
) -> None:
    """Process payment failure - send notification email."""
    if not stripe_subscription_id:
        return

    async with AsyncSessionLocal() as session:
        subscription = await subscription_db.get_by_stripe_subscription_id(
            session, stripe_subscription_id
        )
        if not subscription:
            return

        plan = await plan_db.get_by_id(session, subscription.plan_id)
        plan_name = plan.name if plan else "your plan"
        amount_str = f"${amount_due / 100:.2f}" if amount_due else None

        await _send_payment_failed_email(session, subscription, plan_name, amount_str)


# =============================================================================
# Main Event Handlers
# =============================================================================


async def handle_stripe_checkout_completed(event: dict[str, Any]) -> None:
    """
    Handle checkout.session.completed events from Stripe.

    Routes to API or Career service based on product_type in metadata.
    """
    event_id = event["event_id"]

    if await _is_event_already_processed(event_id):
        stripe_logger.info(f"Checkout event {event_id} already processed, skipping")
        return

    stripe_subscription_id = event["stripe_subscription_id"]
    stripe_customer_id = event["stripe_customer_id"]
    product_type = event.get("product_type", "api")
    plan_id = UUID(event["plan_id"])

    try:
        if product_type == "career":
            await _process_career_checkout(
                stripe_subscription_id,
                stripe_customer_id,
                UUID(event["user_id"]),
                plan_id,
            )
        else:
            await _process_api_checkout(
                stripe_subscription_id,
                stripe_customer_id,
                UUID(event["workspace_id"]),
                plan_id,
                event["seat_count"],
            )
        await _mark_event_as_processed(event_id)
    except Exception as e:
        entity_id = event.get("user_id") or event.get("workspace_id")
        stripe_logger.error(f"Failed to process checkout for {entity_id}: {e}")
        raise


async def handle_stripe_subscription_updated(event: dict[str, Any]) -> None:
    """
    Handle customer.subscription.created/updated events from Stripe.

    Routes to API or Career service based on the subscription's plan product type.
    """
    event_id = event["event_id"]

    if await _is_event_already_processed(event_id):
        stripe_logger.info(
            f"Subscription updated event {event_id} already processed, skipping"
        )
        return

    stripe_subscription_id = event["stripe_subscription_id"]

    try:
        await _process_subscription_update(stripe_subscription_id)
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
    """
    event_id = event["event_id"]

    if await _is_event_already_processed(event_id):
        stripe_logger.info(
            f"Subscription deleted event {event_id} already processed, skipping"
        )
        return

    stripe_subscription_id = event["stripe_subscription_id"]

    try:
        await _process_subscription_deletion(stripe_subscription_id)
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
    """
    event_id = event["event_id"]

    if await _is_event_already_processed(event_id):
        stripe_logger.info(
            f"Payment failed event {event_id} already processed, skipping"
        )
        return

    stripe_subscription_id = event.get("stripe_subscription_id")
    customer_email = event.get("customer_email")
    amount_due = event.get("amount_due")

    stripe_logger.warning(
        f"Payment failed for subscription {stripe_subscription_id}, customer: {customer_email}"
    )

    try:
        await _process_payment_failure(stripe_subscription_id, amount_due)
    except Exception as e:
        stripe_logger.error(f"Failed to queue payment failed email: {e}")

    await _mark_event_as_processed(event_id)


__all__ = [
    "handle_stripe_checkout_completed",
    "handle_stripe_subscription_updated",
    "handle_stripe_subscription_deleted",
    "handle_stripe_payment_failed",
]
