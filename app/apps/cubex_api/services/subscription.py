"""
Subscription service for cubex_api.

This module provides business logic for subscription management including
checkout sessions, seat management, and webhook handling. Uses context
tables to link subscriptions to workspaces.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_api.db.crud import (
    workspace_db,
    workspace_member_db,
)
from app.apps.cubex_api.db.models import Workspace
from app.shared.config import stripe_logger
from app.shared.db.crud import (
    api_subscription_context_db,
    plan_db,
    subscription_db,
    user_db,
)
from app.shared.db.models import Plan, User
from app.shared.db.models import Subscription as SubscriptionModel
from app.shared.enums import (
    MemberStatus,
    ProductType,
    SubscriptionStatus,
    WorkspaceStatus,
)
from app.shared.exceptions.types import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from app.shared.services.payment.stripe.main import Stripe
from app.infrastructure.messaging.publisher import publish_event
from app.shared.services.payment.stripe.types import (
    CheckoutSession,
    Invoice,
    LineItem,
    Subscription as StripeSubscription,
    SubscriptionData,
)


# ============================================================================
# Exceptions
# ============================================================================


class SubscriptionNotFoundException(NotFoundException):
    """Raised when subscription is not found."""

    def __init__(self, message: str = "Subscription not found."):
        super().__init__(message)


class PlanNotFoundException(NotFoundException):
    """Raised when plan is not found."""

    def __init__(self, message: str = "Plan not found."):
        super().__init__(message)


class InvalidSeatCountException(BadRequestException):
    """Raised when seat count is invalid."""

    def __init__(self, message: str = "Invalid seat count."):
        super().__init__(message)


class SeatDowngradeBlockedException(BadRequestException):
    """Raised when seat downgrade would leave enabled members without seats."""

    def __init__(
        self, message: str = "Cannot reduce seats below enabled member count."
    ):
        super().__init__(message)


class CannotUpgradeFreeWorkspace(BadRequestException):
    """Raised when trying to upgrade a non-free workspace."""

    def __init__(self, message: str = "Workspace already has a paid subscription."):
        super().__init__(message)


class StripeWebhookException(BadRequestException):
    """Raised for webhook processing errors."""

    def __init__(self, message: str = "Webhook processing failed."):
        super().__init__(message)


class WorkspaceAccessDeniedException(NotFoundException):
    """Raised when workspace is not found or access is denied."""

    def __init__(self, message: str = "Workspace not found or access denied."):
        super().__init__(message)


class AdminPermissionRequiredException(ForbiddenException):
    """Raised when admin permission is required."""

    def __init__(self, message: str = "Admin permission required."):
        super().__init__(message)


class OwnerPermissionRequiredException(ForbiddenException):
    """Raised when owner permission is required."""

    def __init__(self, message: str = "Only workspace owner can perform this action."):
        super().__init__(message)


class PlanDowngradeNotAllowedException(BadRequestException):
    """Raised when attempting to downgrade to a lower-tier plan."""

    def __init__(
        self,
        message: str = "Plan downgrades are not allowed. Please cancel and resubscribe.",
    ):
        super().__init__(message)


class SamePlanException(BadRequestException):
    """Raised when attempting to upgrade to the same plan."""

    def __init__(self, message: str = "Already subscribed to this plan."):
        super().__init__(message)


# ============================================================================
# Service
# ============================================================================


class SubscriptionService:
    """Service for subscription management."""

    async def get_subscription(
        self,
        session: AsyncSession,
        workspace_id: UUID,
    ) -> SubscriptionModel | None:
        """
        Get active subscription for a workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.

        Returns:
            Active subscription or None.
        """
        return await subscription_db.get_by_workspace(session, workspace_id)

    async def get_plan(
        self,
        session: AsyncSession,
        plan_id: UUID,
    ) -> Plan:
        """
        Get API plan by ID.

        Args:
            session: Database session.
            plan_id: Plan ID.

        Returns:
            Plan.

        Raises:
            PlanNotFoundException: If plan not found or not an API plan.
        """
        plan = await plan_db.get_by_id(session, plan_id)
        if not plan or plan.is_deleted or not plan.is_active:
            raise PlanNotFoundException()
        if plan.product_type != ProductType.API:
            raise PlanNotFoundException("Plan is not an API plan.")
        return plan

    async def get_active_plans(
        self,
        session: AsyncSession,
    ) -> list[Plan]:
        """
        Get all active API plans available for purchase.

        Args:
            session: Database session.

        Returns:
            List of active API plans.
        """
        return await plan_db.get_active_plans(session, product_type=ProductType.API)

    async def create_checkout_session(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        plan_id: UUID,
        seat_count: int,
        success_url: str,
        cancel_url: str,
        user: User,
    ) -> CheckoutSession:
        """
        Create a Stripe checkout session for subscription.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            plan_id: Plan ID to subscribe to.
            seat_count: Number of seats to purchase.
            success_url: URL to redirect after success.
            cancel_url: URL to redirect on cancel.
            user: User initiating the checkout.

        Returns:
            Stripe CheckoutSession.

        Raises:
            PlanNotFoundException: If plan not found.
            InvalidSeatCountException: If seat count is invalid.
            CannotUpgradeFreeWorkspace: If workspace already has paid subscription.
        """
        # Get plan
        plan = await self.get_plan(session, plan_id)

        if not plan.can_be_purchased:
            raise PlanNotFoundException("Plan is not available for purchase.")

        # Validate seat count
        if seat_count < plan.min_seats:
            raise InvalidSeatCountException(f"Minimum {plan.min_seats} seats required.")
        if plan.max_seats and seat_count > plan.max_seats:
            raise InvalidSeatCountException(f"Maximum {plan.max_seats} seats allowed.")

        # Check current subscription
        current_sub = await subscription_db.get_by_workspace(
            session, workspace_id, active_only=False
        )
        if current_sub and current_sub.is_active and current_sub.plan.is_paid:
            raise CannotUpgradeFreeWorkspace()

        # Ensure user has Stripe customer ID
        stripe_customer_id = await self._ensure_stripe_customer(session, user)

        # Create Stripe checkout session with dual line items (base + seats)
        line_items: list[LineItem] = [
            # Base price line item (always 1 unit)
            LineItem(
                price=plan.stripe_price_id,  # type: ignore
                quantity=1,
            )
        ]

        # Add seat price line item if plan has seat pricing
        if plan.has_seat_pricing:
            line_items.append(
                LineItem(
                    price=plan.seat_stripe_price_id,  # type: ignore
                    quantity=seat_count,
                )
            )

        subscription_data = SubscriptionData(
            metadata={
                "workspace_id": str(workspace_id),
                "plan_id": str(plan_id),
                "seat_count": str(seat_count),
                "product_type": "api",
            }
        )

        checkout_session = await Stripe.create_checkout_session(
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=line_items,
            mode="subscription",
            customer=stripe_customer_id,
            metadata={
                "workspace_id": str(workspace_id),
                "plan_id": str(plan_id),
                "seat_count": str(seat_count),
                "product_type": "api",
            },
            subscription_data=subscription_data,
        )

        stripe_logger.info(
            f"Created checkout session {checkout_session.id} for workspace {workspace_id}"
        )

        return checkout_session

    async def handle_checkout_completed(
        self,
        session: AsyncSession,
        stripe_subscription_id: str,
        stripe_customer_id: str,
        workspace_id: UUID,
        plan_id: UUID,
        seat_count: int,
        commit_self: bool = True,
    ) -> SubscriptionModel:
        """
        Handle successful checkout - create/update subscription.

        Args:
            session: Database session.
            stripe_subscription_id: Stripe subscription ID.
            stripe_customer_id: Stripe customer ID.
            workspace_id: Workspace ID.
            plan_id: Plan ID.
            seat_count: Number of seats.
            commit_self: Whether to commit.

        Returns:
            Created/updated subscription.
        """
        # Get Stripe subscription details
        stripe_sub: StripeSubscription = await Stripe.get_subscription(
            stripe_subscription_id
        )

        # Check if subscription already exists (idempotency)
        existing = await subscription_db.get_by_stripe_subscription_id(
            session, stripe_subscription_id
        )
        if existing:
            return existing

        # Deactivate any existing free subscription
        current_sub = await subscription_db.get_by_workspace(
            session, workspace_id, active_only=False
        )
        if current_sub:
            await subscription_db.update(
                session,
                current_sub.id,
                {"status": SubscriptionStatus.CANCELED},
                commit_self=False,
            )

        # Create new subscription
        # Get billing period and amount from subscription items
        current_period_start = None
        current_period_end = None
        amount = None
        if stripe_sub.items and stripe_sub.items.data:
            items_data = stripe_sub.items.data
            first_item = items_data[0]
            current_period_start = first_item.current_period_start
            current_period_end = first_item.current_period_end

            # Calculate total amount from all line items
            # For dual-line-item subscriptions: base_price + (seat_price * seat_count)
            # For single-line-item subscriptions: price * quantity
            total_amount_cents = 0
            for item in items_data:
                if item.price and item.price.unit_amount is not None:
                    item_quantity = item.quantity or 1
                    total_amount_cents += item.price.unit_amount * item_quantity
            if total_amount_cents > 0:
                amount = Decimal(total_amount_cents) / Decimal(100)

        subscription = await subscription_db.create(
            session,
            {
                "plan_id": plan_id,
                "product_type": ProductType.API,
                "stripe_subscription_id": stripe_subscription_id,
                "stripe_customer_id": stripe_customer_id,
                "status": SubscriptionStatus.ACTIVE,
                "seat_count": seat_count,
                "current_period_start": current_period_start,
                "current_period_end": current_period_end,
                "amount": amount,
            },
            commit_self=False,
        )

        # Link subscription to workspace via context
        # Check if workspace already has a context (from a previous subscription)
        existing_context = await api_subscription_context_db.get_by_workspace(
            session, workspace_id
        )
        if existing_context:
            # Update existing context to point to new subscription
            await api_subscription_context_db.update(
                session,
                existing_context.id,
                {"subscription_id": subscription.id},
                commit_self=False,
            )
        else:
            # Create new API subscription context
            await api_subscription_context_db.create(
                session,
                {
                    "subscription_id": subscription.id,
                    "workspace_id": workspace_id,
                },
                commit_self=False,
            )

        # Activate workspace
        await workspace_db.update_status(
            session, workspace_id, WorkspaceStatus.ACTIVE, commit_self=False
        )

        if commit_self:
            await session.commit()
        else:
            await session.flush()
        await session.refresh(subscription)

        stripe_logger.info(
            f"Subscription created: {subscription.id} for workspace {workspace_id}"
        )

        # Queue subscription activation email to workspace owner
        workspace = await workspace_db.get_by_id(session, workspace_id)
        if workspace:
            owner = await user_db.get_by_id(session, workspace.owner_id)
            plan = await plan_db.get_by_id(session, plan_id)
            if owner and plan:
                await publish_event(
                    "subscription_activated_emails",
                    {
                        "email": owner.email,
                        "user_name": owner.full_name,
                        "plan_name": plan.name,
                        "workspace_name": workspace.display_name,
                        "seat_count": seat_count,
                        "product_name": "Cubex API",
                    },
                )

        return subscription

    async def handle_subscription_updated(
        self,
        session: AsyncSession,
        stripe_subscription_id: str,
        commit_self: bool = True,
    ) -> SubscriptionModel | None:
        """
        Handle subscription update from Stripe webhook.

        Args:
            session: Database session.
            stripe_subscription_id: Stripe subscription ID.
            commit_self: Whether to commit.

        Returns:
            Updated subscription or None if not found.
        """
        # Get our subscription record
        subscription = await subscription_db.get_by_stripe_subscription_id(
            session, stripe_subscription_id
        )
        if not subscription:
            stripe_logger.warning(
                f"Subscription not found for Stripe ID: {stripe_subscription_id}"
            )
            return None

        # Get latest from Stripe
        stripe_sub: StripeSubscription = await Stripe.get_subscription(
            stripe_subscription_id
        )

        # Map Stripe status to our status
        status_map = {
            "active": SubscriptionStatus.ACTIVE,
            "past_due": SubscriptionStatus.PAST_DUE,
            "canceled": SubscriptionStatus.CANCELED,
            "incomplete": SubscriptionStatus.INCOMPLETE,
            "incomplete_expired": SubscriptionStatus.INCOMPLETE_EXPIRED,
            "trialing": SubscriptionStatus.TRIALING,
            "unpaid": SubscriptionStatus.UNPAID,
            "paused": SubscriptionStatus.PAUSED,
        }
        new_status = status_map.get(stripe_sub.status, SubscriptionStatus.ACTIVE)

        # Update subscription
        updates: dict[str, Any] = {
            "status": new_status,
            "cancel_at_period_end": stripe_sub.cancel_at_period_end or False,
        }

        # Get billing period and price from subscription items
        if stripe_sub.items and stripe_sub.items.data:
            items_data = stripe_sub.items.data
            first_item = items_data[0]

            # Check if billing period changed (renewal) - reset quota
            old_period_start = subscription.current_period_start
            new_period_start = first_item.current_period_start

            if old_period_start != new_period_start and new_period_start is not None:
                context = await api_subscription_context_db.get_by_subscription(
                    session, subscription.id
                )
                if context:
                    await api_subscription_context_db.reset_credits_used(
                        session, context.id, new_period_start
                    )
                    stripe_logger.info(
                        f"Billing period changed for subscription {stripe_subscription_id}: "
                        f"reset credits_used to 0"
                    )

            # Update billing period from first item
            updates["current_period_start"] = first_item.current_period_start
            updates["current_period_end"] = first_item.current_period_end

            # Determine subscription structure:
            # - Old: 1 item with base price, quantity = seat_count
            # - New: 2 items (base @ qty=1, seats @ qty=seat_count)
            is_dual_item = len(items_data) >= 2

            if is_dual_item:
                # New dual-line-item subscription
                # Find seat item by matching plan's seat_stripe_price_id
                seat_item = None
                base_item = None
                for item in items_data:
                    item_price_id = item.price.id if item.price else None
                    if (
                        subscription.plan.seat_stripe_price_id
                        and item_price_id == subscription.plan.seat_stripe_price_id
                    ):
                        seat_item = item
                    elif item_price_id == subscription.plan.stripe_price_id:
                        base_item = item

                # Sync seat count from seat item
                if seat_item and seat_item.quantity != subscription.seat_count:
                    updates["seat_count"] = seat_item.quantity
                    stripe_logger.info(
                        f"Seat count changed for subscription {stripe_subscription_id}: "
                        f"{subscription.seat_count} -> {seat_item.quantity}"
                    )

                # Calculate total amount (base + seats)
                total_amount_cents = 0
                if base_item and base_item.price and base_item.price.unit_amount:
                    base_qty = base_item.quantity or 1
                    total_amount_cents += base_item.price.unit_amount * base_qty
                if seat_item and seat_item.price and seat_item.price.unit_amount:
                    seat_qty = seat_item.quantity or 0
                    total_amount_cents += seat_item.price.unit_amount * seat_qty

                amount_dollars = Decimal(total_amount_cents) / Decimal(100)
                if subscription.amount != amount_dollars:
                    updates["amount"] = amount_dollars
                    stripe_logger.info(
                        f"Amount updated for subscription {stripe_subscription_id}: "
                        f"${amount_dollars}"
                    )
            else:
                # Old single-item subscription (legacy)
                # Sync plan if price changed (handles upgrades, external changes)
                stripe_price_id = first_item.price.id if first_item.price else None
                if (
                    stripe_price_id
                    and subscription.plan.stripe_price_id != stripe_price_id
                ):
                    new_plan = await plan_db.get_by_stripe_price_id(
                        session, stripe_price_id
                    )
                    if new_plan and new_plan.product_type == ProductType.API:
                        updates["plan_id"] = new_plan.id
                        stripe_logger.info(
                            f"Plan changed for subscription {stripe_subscription_id}: "
                            f"{subscription.plan.name} -> {new_plan.name}"
                        )
                    elif new_plan:
                        stripe_logger.warning(
                            f"Stripe price ID {stripe_price_id} belongs to non-API plan, "
                            f"ignoring for API subscription {stripe_subscription_id}"
                        )
                    else:
                        stripe_logger.warning(
                            f"Unknown Stripe price ID {stripe_price_id} for subscription "
                            f"{stripe_subscription_id}, plan not updated"
                        )

                # Sync seat count from quantity (legacy behavior)
                if (
                    first_item.quantity
                    and first_item.quantity != subscription.seat_count
                ):
                    updates["seat_count"] = first_item.quantity
                    stripe_logger.info(
                        f"Seat count changed for subscription {stripe_subscription_id}: "
                        f"{subscription.seat_count} -> {first_item.quantity}"
                    )

                # Sync billing amount (price * quantity)
                if first_item.price and first_item.price.unit_amount is not None:
                    quantity = first_item.quantity or 1
                    amount_cents = first_item.price.unit_amount * quantity
                    amount_dollars = Decimal(amount_cents) / Decimal(100)
                    if subscription.amount != amount_dollars:
                        updates["amount"] = amount_dollars
                        stripe_logger.info(
                            f"Amount updated for subscription {stripe_subscription_id}: "
                            f"${amount_dollars}"
                        )

        if stripe_sub.canceled_at:
            updates["canceled_at"] = stripe_sub.canceled_at

        subscription = await subscription_db.update(
            session, subscription.id, updates, commit_self=False
        )

        if not subscription:
            stripe_logger.warning(
                f"Failed to update subscription for Stripe ID: {stripe_subscription_id}"
            )
            return None

        # Get workspace_id from context for API subscriptions
        workspace_id: UUID | None = None
        if subscription.product_type == ProductType.API and subscription.api_context:
            workspace_id = subscription.api_context.workspace_id

        # Handle workspace status based on subscription status
        if workspace_id:
            if new_status == SubscriptionStatus.CANCELED:
                await self._freeze_workspace(session, workspace_id)
            elif new_status in (
                SubscriptionStatus.PAST_DUE,
                SubscriptionStatus.UNPAID,
            ):
                # Grace period - don't freeze immediately
                pass
            elif new_status == SubscriptionStatus.ACTIVE:
                # Reactivate if was frozen
                workspace = await workspace_db.get_by_id(session, workspace_id)
                if workspace and workspace.status == WorkspaceStatus.FROZEN:
                    await workspace_db.update_status(
                        session,
                        workspace_id,
                        WorkspaceStatus.ACTIVE,
                        commit_self=False,
                    )

        if commit_self:
            await session.commit()
        else:
            await session.flush()
        if subscription:
            await session.refresh(subscription)

        return subscription

    async def handle_subscription_deleted(
        self,
        session: AsyncSession,
        stripe_subscription_id: str,
        commit_self: bool = True,
    ) -> SubscriptionModel | None:
        """
        Handle subscription deletion from Stripe webhook.

        Args:
            session: Database session.
            stripe_subscription_id: Stripe subscription ID.
            commit_self: Whether to commit.

        Returns:
            Updated subscription or None if not found.
        """
        subscription = await subscription_db.get_by_stripe_subscription_id(
            session, stripe_subscription_id
        )
        if not subscription:
            return None

        # Get workspace_id from context for API subscriptions
        workspace_id: UUID | None = None
        if subscription.product_type == ProductType.API and subscription.api_context:
            workspace_id = subscription.api_context.workspace_id

        # Mark as canceled
        subscription = await subscription_db.update(
            session,
            subscription.id,
            {
                "status": SubscriptionStatus.CANCELED,
                "canceled_at": datetime.now(timezone.utc),
            },
            commit_self=False,
        )

        # Freeze workspace if this is an API subscription
        if workspace_id:
            await self._freeze_workspace(session, workspace_id)

        if commit_self:
            await session.commit()
        else:
            await session.flush()
        if subscription:
            await session.refresh(subscription)

        stripe_logger.info(
            f"Subscription {stripe_subscription_id} deleted, workspace frozen"
        )

        return subscription

    async def _freeze_workspace(
        self,
        session: AsyncSession,
        workspace_id: UUID,
    ) -> None:
        """
        Freeze workspace and disable all non-owner members.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
        """
        # Update workspace status
        await workspace_db.update_status(
            session, workspace_id, WorkspaceStatus.FROZEN, commit_self=False
        )

        # Disable all members except owner
        await workspace_member_db.disable_all_members(
            session, workspace_id, except_owner=True, commit_self=False
        )

        stripe_logger.info(f"Workspace {workspace_id} frozen")

    async def _ensure_stripe_customer(
        self,
        session: AsyncSession,
        user: User,
    ) -> str:
        """
        Ensure user has a Stripe customer ID, creating one if needed.

        Handles legacy users who signed up before customer-first implementation.

        Args:
            session: Database session.
            user: User to ensure has Stripe customer.

        Returns:
            Stripe customer ID.
        """
        if user.stripe_customer_id:
            return user.stripe_customer_id

        # Create Stripe customer for legacy user
        stripe_customer = await Stripe.create_customer(
            email=user.email,
            name=user.full_name,
            metadata={"user_id": str(user.id)},
        )

        await user_db.update(
            session,
            user.id,
            {"stripe_customer_id": stripe_customer.id},
            commit_self=False,
        )

        stripe_logger.info(
            f"Created Stripe customer {stripe_customer.id} for legacy user {user.email}"
        )
        return stripe_customer.id

    async def update_seat_count(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        new_seat_count: int,
        commit_self: bool = True,
    ) -> SubscriptionModel:
        """
        Update subscription seat count.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            new_seat_count: New number of seats.
            commit_self: Whether to commit.

        Returns:
            Updated subscription.

        Raises:
            SubscriptionNotFoundException: If no active subscription.
            InvalidSeatCountException: If seat count invalid.
            SeatDowngradeBlockedException: If enabled members exceed new count.
        """
        subscription = await subscription_db.get_by_workspace(session, workspace_id)
        if not subscription:
            raise SubscriptionNotFoundException()

        plan = subscription.plan
        if new_seat_count < plan.min_seats:
            raise InvalidSeatCountException(f"Minimum {plan.min_seats} seats required.")
        if plan.max_seats and new_seat_count > plan.max_seats:
            raise InvalidSeatCountException(f"Maximum {plan.max_seats} seats allowed.")

        # Check enabled member count
        enabled_count = await workspace_member_db.get_enabled_member_count(
            session, workspace_id
        )
        if new_seat_count < enabled_count:
            raise SeatDowngradeBlockedException(
                f"Cannot reduce to {new_seat_count} seats. "
                f"Currently {enabled_count} members enabled. "
                f"Disable members first."
            )

        # Determine proration behavior based on upgrade vs downgrade
        # - Upgrades (add seats): charge immediately with proration
        # - Downgrades (remove seats): effective at next billing period (no proration)
        is_downgrade = new_seat_count < subscription.seat_count
        proration_behavior = "none" if is_downgrade else "create_prorations"

        # Update Stripe subscription first (if exists)
        # If Stripe fails, exception propagates and transaction auto-rollbacks
        if subscription.stripe_subscription_id:
            await Stripe.update_subscription(
                subscription.stripe_subscription_id,
                quantity=new_seat_count,
                seat_price_id=plan.seat_stripe_price_id,
                proration_behavior=proration_behavior,  # type: ignore[arg-type]
            )

        subscription_id = subscription.id

        # Update our record
        updated_subscription = await subscription_db.update(
            session,
            subscription_id,
            {"seat_count": new_seat_count},
            commit_self=commit_self,
        )

        if not updated_subscription:
            raise SubscriptionNotFoundException(
                f"Subscription {subscription_id} not found after update"
            )

        stripe_logger.info(
            f"Subscription {updated_subscription.id} seats updated to {new_seat_count}"
        )

        return updated_subscription

    async def cancel_subscription(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        cancel_at_period_end: bool = True,
        commit_self: bool = True,
    ) -> SubscriptionModel:
        """
        Cancel a subscription.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            cancel_at_period_end: If True, cancel at end of period.
            commit_self: Whether to commit.

        Returns:
            Updated subscription.

        Raises:
            SubscriptionNotFoundException: If no active subscription.
        """
        subscription = await subscription_db.get_by_workspace(session, workspace_id)
        if not subscription:
            raise SubscriptionNotFoundException()

        subscription_id = subscription.id

        # Cancel in Stripe if exists
        if subscription.stripe_subscription_id:
            await Stripe.cancel_subscription(
                subscription.stripe_subscription_id,
                cancel_at_period_end=cancel_at_period_end,
            )

        # Update our record
        updates: dict[str, Any] = {"cancel_at_period_end": cancel_at_period_end}
        if not cancel_at_period_end:
            updates["status"] = SubscriptionStatus.CANCELED
            updates["canceled_at"] = datetime.now(timezone.utc)

        updated_subscription = await subscription_db.update(
            session,
            subscription_id,
            updates,
            commit_self=False,
        )

        if not updated_subscription:
            raise SubscriptionNotFoundException(
                f"Subscription {subscription_id} not found after update"
            )

        # If immediate cancellation, freeze workspace
        if not cancel_at_period_end:
            await self._freeze_workspace(session, workspace_id)

        if commit_self:
            await session.commit()
        else:
            await session.flush()
        await session.refresh(updated_subscription)

        stripe_logger.info(
            f"Subscription {updated_subscription.id} cancellation requested "
            f"(at_period_end={cancel_at_period_end})"
        )

        return updated_subscription

    async def reactivate_workspace(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        member_ids_to_enable: list[UUID] | None = None,
        commit_self: bool = True,
    ) -> Workspace:
        """
        Reactivate a frozen workspace after resubscription.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            member_ids_to_enable: Specific members to enable (must fit in seats).
            commit_self: Whether to commit.

        Returns:
            Reactivated workspace.

        Raises:
            SubscriptionNotFoundException: If no active subscription.
            InvalidSeatCountException: If too many members selected.
        """
        subscription = await subscription_db.get_by_workspace(session, workspace_id)
        if not subscription or not subscription.is_active:
            raise SubscriptionNotFoundException("No active subscription.")

        # Get all members
        members = await workspace_member_db.get_workspace_members(session, workspace_id)

        # Owner is always enabled
        owner_member = next((m for m in members if m.is_owner), None)
        if owner_member and owner_member.status == MemberStatus.DISABLED:
            await workspace_member_db.update_status(
                session, owner_member.id, MemberStatus.ENABLED, commit_self=False
            )

        # Enable selected members (if specified)
        if member_ids_to_enable:
            # Check seat count
            # +1 for owner who is always enabled
            if len(member_ids_to_enable) + 1 > subscription.seat_count:
                raise InvalidSeatCountException(
                    f"Cannot enable {len(member_ids_to_enable) + 1} members. "
                    f"Only {subscription.seat_count} seats available."
                )

            for member in members:
                if member.is_owner:
                    continue
                if member.id in member_ids_to_enable:
                    await workspace_member_db.update_status(
                        session, member.id, MemberStatus.ENABLED, commit_self=False
                    )

        # Activate workspace
        workspace = await workspace_db.update_status(
            session, workspace_id, WorkspaceStatus.ACTIVE, commit_self=False
        )

        if commit_self:
            await session.commit()
        else:
            await session.flush()
        if workspace:
            await session.refresh(workspace)

        return workspace  # type: ignore

    async def preview_upgrade(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        new_plan_id: UUID,
    ) -> Invoice:
        """
        Preview the cost of upgrading to a new plan.

        Returns a Stripe invoice preview showing prorated charges.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            new_plan_id: Target plan ID to upgrade to.

        Returns:
            Stripe Invoice preview with proration details.

        Raises:
            SubscriptionNotFoundException: If no active subscription.
            PlanNotFoundException: If target plan not found.
            PlanDowngradeNotAllowedException: If target plan is lower tier.
            SamePlanException: If already on target plan.
        """
        subscription = await subscription_db.get_by_workspace(session, workspace_id)
        if not subscription or not subscription.is_active:
            raise SubscriptionNotFoundException("No active subscription.")

        if not subscription.stripe_subscription_id:
            raise SubscriptionNotFoundException("Subscription has no Stripe ID.")

        # Get current and target plans
        current_plan = subscription.plan
        new_plan = await self.get_plan(session, new_plan_id)

        # Validate not same plan
        if current_plan.id == new_plan.id:
            raise SamePlanException()

        # Validate upgrade only (higher price = upgrade)
        if new_plan.price <= current_plan.price:
            raise PlanDowngradeNotAllowedException(
                f"Cannot downgrade from {current_plan.name} to {new_plan.name}. "
                "Please cancel and resubscribe to a different plan."
            )

        # Validate new plan's seat limits
        if new_plan.max_seats and subscription.seat_count > new_plan.max_seats:
            raise InvalidSeatCountException(
                f"Current seat count ({subscription.seat_count}) exceeds "
                f"target plan's maximum ({new_plan.max_seats}). "
                "Reduce seats before upgrading."
            )

        # Get Stripe preview
        if not new_plan.stripe_price_id:
            raise PlanNotFoundException("Target plan has no Stripe price.")

        invoice_preview = await Stripe.preview_invoice(
            subscription.stripe_subscription_id,
            new_plan.stripe_price_id,
        )

        stripe_logger.info(
            f"Preview upgrade for workspace {workspace_id}: "
            f"{current_plan.name} -> {new_plan.name}, "
            f"proration: {invoice_preview.proration_amount}"
        )

        return invoice_preview

    async def upgrade_plan(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        new_plan_id: UUID,
        commit_self: bool = True,
    ) -> SubscriptionModel:
        """
        Upgrade subscription to a higher-tier plan.

        Prorates the charge for the current billing period.
        Downgrades are not allowed - users must cancel and resubscribe.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            new_plan_id: Target plan ID to upgrade to.
            commit_self: Whether to commit.

        Returns:
            Updated subscription.

        Raises:
            SubscriptionNotFoundException: If no active subscription.
            PlanNotFoundException: If target plan not found.
            PlanDowngradeNotAllowedException: If target plan is lower tier.
            SamePlanException: If already on target plan.
            InvalidSeatCountException: If seat count exceeds new plan limits.
        """
        subscription = await subscription_db.get_by_workspace(session, workspace_id)
        if not subscription or not subscription.is_active:
            raise SubscriptionNotFoundException("No active subscription.")

        if not subscription.stripe_subscription_id:
            raise SubscriptionNotFoundException("Subscription has no Stripe ID.")

        # Get current and target plans
        current_plan = subscription.plan
        new_plan = await self.get_plan(session, new_plan_id)

        # Validate not same plan
        if current_plan.id == new_plan.id:
            raise SamePlanException()

        # Validate upgrade only (higher price = upgrade)
        if new_plan.price <= current_plan.price:
            raise PlanDowngradeNotAllowedException(
                f"Cannot downgrade from {current_plan.name} to {new_plan.name}. "
                "Please cancel and resubscribe to a different plan."
            )

        # Validate new plan's seat limits
        if new_plan.max_seats and subscription.seat_count > new_plan.max_seats:
            raise InvalidSeatCountException(
                f"Current seat count ({subscription.seat_count}) exceeds "
                f"target plan's maximum ({new_plan.max_seats}). "
                "Reduce seats before upgrading."
            )

        if not new_plan.stripe_price_id:
            raise PlanNotFoundException("Target plan has no Stripe price.")

        # Update Stripe subscription with new price
        # Proration is handled automatically by Stripe
        # For dual line item subscriptions (base + seats), update both:
        # - Base plan price: current_plan.stripe_price_id -> new_plan.stripe_price_id
        # - Seat price: current_plan.seat_stripe_price_id -> new_plan.seat_stripe_price_id
        await Stripe.update_subscription(
            subscription.stripe_subscription_id,
            new_price_id=new_plan.stripe_price_id,
            quantity=subscription.seat_count,
            seat_price_id=current_plan.seat_stripe_price_id,
            new_seat_price_id=new_plan.seat_stripe_price_id,
            proration_behavior="create_prorations",
        )

        # Update our database record
        subscription_id = subscription.id
        updated_subscription = await subscription_db.update(
            session,
            subscription_id,
            {"plan_id": new_plan.id},
            commit_self=commit_self,
        )

        if not updated_subscription:
            raise SubscriptionNotFoundException(
                f"Subscription {subscription_id} not found after update"
            )

        stripe_logger.info(
            f"Subscription {subscription_id} upgraded: "
            f"{current_plan.name} -> {new_plan.name}"
        )

        # Send upgrade confirmation email to workspace owner
        workspace = await workspace_db.get_by_id(session, workspace_id)
        if workspace and workspace.owner:
            await publish_event(
                "subscription_activated_emails",
                {
                    "email": workspace.owner.email,
                    "full_name": workspace.owner.full_name or "Valued Customer",
                    "plan_name": new_plan.name,
                    "product_type": ProductType.API.value,
                    "workspace_name": workspace.display_name,
                },
            )
            stripe_logger.info(
                f"Upgrade email queued for {workspace.owner.email}: "
                f"{current_plan.name} -> {new_plan.name}"
            )

        return updated_subscription


# Global service instance
subscription_service = SubscriptionService()


__all__ = [
    "SubscriptionService",
    "subscription_service",
    # Exceptions
    "SubscriptionNotFoundException",
    "PlanNotFoundException",
    "InvalidSeatCountException",
    "SeatDowngradeBlockedException",
    "CannotUpgradeFreeWorkspace",
    "StripeWebhookException",
    "WorkspaceAccessDeniedException",
    "AdminPermissionRequiredException",
    "OwnerPermissionRequiredException",
    "PlanDowngradeNotAllowedException",
    "SamePlanException",
]
