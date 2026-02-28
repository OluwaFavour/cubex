"""
Career Subscription service for cubex_career.

"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import stripe_logger
from app.core.db.crud import (
    career_subscription_context_db,
    plan_db,
    subscription_db,
    user_db,
)
from app.core.db.models import Plan, User
from app.core.db.models import Subscription as SubscriptionModel
from app.core.enums import ProductType, SubscriptionStatus
from app.core.exceptions.types import (
    BadRequestException,
    NotFoundException,
)
from app.core.services.payment.stripe.main import Stripe
from app.core.services.event_publisher import get_publisher
from app.core.services.payment.stripe.types import (
    CheckoutSession,
    Invoice,
    LineItem,
    Subscription as StripeSubscription,
    SubscriptionData,
)


class CareerSubscriptionNotFoundException(NotFoundException):
    """Raised when Career subscription is not found."""

    def __init__(self, message: str = "Career subscription not found."):
        super().__init__(message)


class CareerPlanNotFoundException(NotFoundException):
    """Raised when Career plan is not found."""

    def __init__(self, message: str = "Career plan not found."):
        super().__init__(message)


class CareerSubscriptionAlreadyExistsException(BadRequestException):
    """Raised when user already has a paid Career subscription."""

    def __init__(self, message: str = "Already have an active Career subscription."):
        super().__init__(message)


class CareerPlanDowngradeNotAllowedException(BadRequestException):
    """Raised when attempting to downgrade to a lower-tier plan."""

    def __init__(
        self,
        message: str = (
            "Plan downgrades are not allowed. Please cancel and resubscribe."
        ),
    ):
        super().__init__(message)


class CareerSamePlanException(BadRequestException):
    """Raised when attempting to upgrade to the same plan."""

    def __init__(self, message: str = "Already subscribed to this plan."):
        super().__init__(message)


class CareerSubscriptionService:
    """Service for Career subscription management."""

    async def get_subscription(
        self,
        session: AsyncSession,
        user_id: UUID,
    ) -> SubscriptionModel | None:
        """
        Get active Career subscription for a user.

        Args:
            session: Database session.
            user_id: User ID.

        Returns:
            Active subscription or None.
        """
        return await subscription_db.get_by_user(session, user_id)

    async def get_plan(
        self,
        session: AsyncSession,
        plan_id: UUID,
    ) -> Plan:
        """
        Get Career plan by ID.

        Args:
            session: Database session.
            plan_id: Plan ID.

        Returns:
            Plan.

        Raises:
            CareerPlanNotFoundException: If plan not found or not a Career plan.
        """
        plan = await plan_db.get_by_id(session, plan_id)
        if not plan or plan.is_deleted or not plan.is_active:
            raise CareerPlanNotFoundException()
        if plan.product_type != ProductType.CAREER:
            raise CareerPlanNotFoundException("Plan is not a Career plan.")
        return plan

    async def get_active_plans(
        self,
        session: AsyncSession,
    ) -> list[Plan]:
        """
        Get all active Career plans available for purchase.

        Args:
            session: Database session.

        Returns:
            List of active Career plans.
        """
        return await plan_db.get_active_plans(session, product_type=ProductType.CAREER)

    async def create_free_subscription(
        self,
        session: AsyncSession,
        user: User,
        commit_self: bool = True,
    ) -> SubscriptionModel:
        """
        Create a free Career subscription for a user.

        This is called automatically on user signup. Idempotent - returns
        existing subscription if one already exists.

        Args:
            session: Database session.
            user: User to create subscription for.
            commit_self: Whether to commit the transaction.

        Returns:
            Created or existing subscription.
        """
        # Check if user already has a Career subscription (idempotent)
        existing = await subscription_db.get_by_user(
            session, user.id, active_only=False
        )
        if existing:
            stripe_logger.debug(
                f"Career subscription already exists for user {user.id}"
            )
            return existing

        # Get free plan for Career product (must exist - seeded in migrations)
        free_plan = await plan_db.get_free_plan(
            session, product_type=ProductType.CAREER
        )
        if not free_plan:
            raise ValueError("Free Career plan not found. Ensure plans are seeded.")

        # Create subscription (free plan, no Stripe)
        subscription = await subscription_db.create(
            session,
            {
                "plan_id": free_plan.id,
                "product_type": ProductType.CAREER,
                "status": SubscriptionStatus.ACTIVE,
                "seat_count": 1,  # Career is always single-user
            },
            commit_self=False,
        )

        await career_subscription_context_db.create(
            session,
            {
                "subscription_id": subscription.id,
                "user_id": user.id,
            },
            commit_self=False,
        )

        if commit_self:
            await session.commit()
        else:
            await session.flush()
        await session.refresh(subscription)

        stripe_logger.info(
            f"Career free subscription created: {subscription.id} for user {user.id}"
        )

        return subscription

    async def create_checkout_session(
        self,
        session: AsyncSession,
        plan_id: UUID,
        success_url: str,
        cancel_url: str,
        user: User,
    ) -> CheckoutSession:
        """
        Create a Stripe checkout session for Career subscription.

        Args:
            session: Database session.
            plan_id: Plan ID to subscribe to.
            success_url: URL to redirect after success.
            cancel_url: URL to redirect on cancel.
            user: User initiating the checkout.

        Returns:
            Stripe CheckoutSession.

        Raises:
            CareerPlanNotFoundException: If plan not found.
            CareerSubscriptionAlreadyExistsException: If user already has paid sub.
        """
        plan = await self.get_plan(session, plan_id)

        if not plan.can_be_purchased:
            raise CareerPlanNotFoundException("Plan is not available for purchase.")

        current_sub = await subscription_db.get_by_user(
            session, user.id, active_only=False
        )
        if current_sub and current_sub.is_active and current_sub.plan.is_paid:
            raise CareerSubscriptionAlreadyExistsException()

        stripe_customer_id = await self._ensure_stripe_customer(session, user)

        line_items = [
            LineItem(
                price=plan.stripe_price_id,  # type: ignore
                quantity=1,  # Career is always single-user
            )
        ]

        subscription_data = SubscriptionData(
            metadata={
                "user_id": str(user.id),
                "plan_id": str(plan_id),
                "product_type": "career",
            }
        )

        checkout_session = await Stripe.create_checkout_session(
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=line_items,
            mode="subscription",
            customer=stripe_customer_id,
            metadata={
                "user_id": str(user.id),
                "plan_id": str(plan_id),
                "product_type": "career",
            },
            subscription_data=subscription_data,
        )

        stripe_logger.info(
            f"Created Career checkout session {checkout_session.id} for user {user.id}"
        )

        return checkout_session

    async def handle_checkout_completed(
        self,
        session: AsyncSession,
        stripe_subscription_id: str,
        stripe_customer_id: str,
        user_id: UUID,
        plan_id: UUID,
        commit_self: bool = True,
    ) -> SubscriptionModel:
        """
        Handle successful checkout - create/update Career subscription.

        Args:
            session: Database session.
            stripe_subscription_id: Stripe subscription ID.
            stripe_customer_id: Stripe customer ID.
            user_id: User ID.
            plan_id: Plan ID.
            commit_self: Whether to commit.

        Returns:
            Created/updated subscription.
        """
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
        current_sub = await subscription_db.get_by_user(
            session, user_id, active_only=False
        )
        if current_sub:
            await subscription_db.update(
                session,
                current_sub.id,
                {"status": SubscriptionStatus.CANCELED},
                commit_self=False,
            )

        current_period_start = None
        current_period_end = None
        amount = None
        if stripe_sub.items and stripe_sub.items.data:
            first_item = stripe_sub.items.data[0]
            current_period_start = first_item.current_period_start
            current_period_end = first_item.current_period_end
            # Calculate amount (Career is always quantity=1)
            if first_item.price and first_item.price.unit_amount is not None:
                amount = Decimal(first_item.price.unit_amount) / Decimal(100)

        subscription = await subscription_db.create(
            session,
            {
                "plan_id": plan_id,
                "product_type": ProductType.CAREER,
                "stripe_subscription_id": stripe_subscription_id,
                "stripe_customer_id": stripe_customer_id,
                "status": SubscriptionStatus.ACTIVE,
                "seat_count": 1,  # Career is always single-user
                "current_period_start": current_period_start,
                "current_period_end": current_period_end,
                "amount": amount,
            },
            commit_self=False,
        )

        # Link subscription to user via context
        # Check if user already has a context (from a previous subscription)
        existing_context = await career_subscription_context_db.get_by_user(
            session, user_id
        )
        if existing_context:
            await career_subscription_context_db.update(
                session,
                existing_context.id,
                {"subscription_id": subscription.id},
                commit_self=False,
            )
        else:
            await career_subscription_context_db.create(
                session,
                {
                    "subscription_id": subscription.id,
                    "user_id": user_id,
                },
                commit_self=False,
            )

        if commit_self:
            await session.commit()
        else:
            await session.flush()
        await session.refresh(subscription)

        stripe_logger.info(
            f"Career subscription created: {subscription.id} for user {user_id}"
        )

        # Queue subscription activation email to user
        user = await user_db.get_by_id(session, user_id)
        plan = await plan_db.get_by_id(session, plan_id)
        if user and plan:
            await get_publisher()(
                "subscription_activated_emails",
                {
                    "email": user.email,
                    "user_name": user.full_name,
                    "plan_name": plan.name,
                    "workspace_name": None,  # Career is user-based
                    "seat_count": None,  # Career is always single-user
                    "product_name": "CueBX Career",
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
        Handle Career subscription update from Stripe webhook.

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
            stripe_logger.warning(
                f"Career subscription not found for Stripe ID: {stripe_subscription_id}"
            )
            return None

        if subscription.product_type != ProductType.CAREER:
            stripe_logger.debug(
                f"Subscription {stripe_subscription_id} is not Career type, skipping"
            )
            return None

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

        updates: dict[str, Any] = {
            "status": new_status,
            "cancel_at_period_end": stripe_sub.cancel_at_period_end or False,
        }

        if stripe_sub.items and stripe_sub.items.data:
            first_item = stripe_sub.items.data[0]

            # Check if billing period changed (renewal) - reset quota
            old_period_start = subscription.current_period_start
            new_period_start = first_item.current_period_start

            if old_period_start != new_period_start and new_period_start is not None:
                context = await career_subscription_context_db.get_by_subscription(
                    session, subscription.id
                )
                if context:
                    await career_subscription_context_db.reset_credits_used(
                        session, context.id
                    )
                    stripe_logger.info(
                        f"Billing period changed for career subscription {stripe_subscription_id}: "
                        f"reset credits_used to 0"
                    )

            updates["current_period_start"] = first_item.current_period_start
            updates["current_period_end"] = first_item.current_period_end

            # Sync plan if price changed (handles upgrades, external changes)
            stripe_price_id = first_item.price.id if first_item.price else None
            if stripe_price_id and subscription.plan.stripe_price_id != stripe_price_id:
                new_plan = await plan_db.get_by_stripe_price_id(
                    session, stripe_price_id
                )
                if new_plan and new_plan.product_type == ProductType.CAREER:
                    updates["plan_id"] = new_plan.id
                    stripe_logger.info(
                        f"Career plan changed for subscription {stripe_subscription_id}: "
                        f"{subscription.plan.name} -> {new_plan.name}"
                    )
                elif new_plan:
                    stripe_logger.warning(
                        f"Stripe price ID {stripe_price_id} belongs to non-Career plan, "
                        f"ignoring for Career subscription {stripe_subscription_id}"
                    )
                else:
                    stripe_logger.warning(
                        f"Unknown Stripe price ID {stripe_price_id} for Career subscription "
                        f"{stripe_subscription_id}, plan not updated"
                    )

            # Sync billing amount (Career is always quantity=1)
            if first_item.price and first_item.price.unit_amount is not None:
                amount_dollars = Decimal(first_item.price.unit_amount) / Decimal(100)
                if subscription.amount != amount_dollars:
                    updates["amount"] = amount_dollars
                    stripe_logger.info(
                        f"Career amount updated for subscription {stripe_subscription_id}: "
                        f"${amount_dollars}"
                    )

        if stripe_sub.canceled_at:
            updates["canceled_at"] = stripe_sub.canceled_at

        subscription = await subscription_db.update(
            session, subscription.id, updates, commit_self=False
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
        Handle Career subscription deletion from Stripe webhook.

        Marks the subscription as canceled, then downgrades it to the free
        plan so the user retains basic access.

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

        if subscription.product_type != ProductType.CAREER:
            stripe_logger.debug(
                f"Subscription {stripe_subscription_id} is not Career type, skipping"
            )
            return None

        # Downgrade to free plan
        free_plan = await plan_db.get_free_plan(
            session, product_type=ProductType.CAREER
        )
        if not free_plan:
            stripe_logger.error(
                "Free Career plan not found — cannot downgrade, marking as canceled only"
            )
            subscription = await subscription_db.update(
                session,
                subscription.id,
                {
                    "status": SubscriptionStatus.CANCELED,
                    "canceled_at": datetime.now(timezone.utc),
                },
                commit_self=commit_self,
            )
            return subscription

        subscription = await subscription_db.update(
            session,
            subscription.id,
            {
                "status": SubscriptionStatus.ACTIVE,
                "plan_id": free_plan.id,
                "stripe_subscription_id": None,
                "canceled_at": datetime.now(timezone.utc),
                "cancel_at_period_end": False,
            },
            commit_self=commit_self,
        )

        stripe_logger.info(
            f"Career subscription {stripe_subscription_id} deleted — "
            f"downgraded to free plan {free_plan.id}"
        )

        return subscription

    async def _ensure_stripe_customer(
        self,
        session: AsyncSession,
        user: User,
    ) -> str:
        """
        Ensure user has a Stripe customer ID, creating one if needed.

        Args:
            session: Database session.
            user: User to ensure has Stripe customer.

        Returns:
            Stripe customer ID.
        """
        if user.stripe_customer_id:
            return user.stripe_customer_id

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

    async def cancel_subscription(
        self,
        session: AsyncSession,
        user_id: UUID,
        cancel_at_period_end: bool = True,
        commit_self: bool = True,
    ) -> SubscriptionModel:
        """
        Cancel a Career subscription.

        Args:
            session: Database session.
            user_id: User ID.
            cancel_at_period_end: If True, cancel at end of period.
            commit_self: Whether to commit.

        Returns:
            Updated subscription.

        Raises:
            CareerSubscriptionNotFoundException: If no active subscription.
        """
        subscription = await subscription_db.get_by_user(session, user_id)
        if not subscription:
            raise CareerSubscriptionNotFoundException()

        subscription_id = subscription.id

        if subscription.stripe_subscription_id:
            await Stripe.cancel_subscription(
                subscription.stripe_subscription_id,
                cancel_at_period_end=cancel_at_period_end,
            )

        updates: dict[str, Any] = {"cancel_at_period_end": cancel_at_period_end}
        if not cancel_at_period_end:
            # Immediate cancellation: downgrade to free plan right away
            # so the user isn't left in a CANCELED state until the webhook fires.
            free_plan = await plan_db.get_free_plan(
                session, product_type=ProductType.CAREER
            )
            if free_plan:
                updates["status"] = SubscriptionStatus.ACTIVE
                updates["plan_id"] = free_plan.id
                updates["stripe_subscription_id"] = None
                updates["cancel_at_period_end"] = False
                updates["canceled_at"] = datetime.now(timezone.utc)
            else:
                stripe_logger.error(
                    "Free Career plan not found — marking as canceled only"
                )
                updates["status"] = SubscriptionStatus.CANCELED
                updates["canceled_at"] = datetime.now(timezone.utc)

        updated_subscription = await subscription_db.update(
            session,
            subscription_id,
            updates,
            commit_self=commit_self,
        )

        if not updated_subscription:
            raise CareerSubscriptionNotFoundException(
                f"Subscription {subscription_id} not found after update"
            )

        stripe_logger.info(
            f"Career subscription {updated_subscription.id} cancellation requested "
            f"(at_period_end={cancel_at_period_end})"
        )

        return updated_subscription

    async def preview_upgrade(
        self,
        session: AsyncSession,
        user_id: UUID,
        new_plan_id: UUID,
    ) -> Invoice:
        """
        Preview the cost of upgrading to a new Career plan.

        Returns a Stripe invoice preview showing prorated charges.

        Args:
            session: Database session.
            user_id: User ID.
            new_plan_id: Target plan ID to upgrade to.

        Returns:
            Stripe Invoice preview with proration details.

        Raises:
            CareerSubscriptionNotFoundException: If no active subscription.
            CareerPlanNotFoundException: If target plan not found.
            CareerPlanDowngradeNotAllowedException: If target plan is lower tier.
            CareerSamePlanException: If already on target plan.
        """
        subscription = await subscription_db.get_by_user(session, user_id)
        if not subscription or not subscription.is_active:
            raise CareerSubscriptionNotFoundException("No active subscription.")

        if not subscription.stripe_subscription_id:
            raise CareerSubscriptionNotFoundException("Subscription has no Stripe ID.")

        current_plan = subscription.plan
        new_plan = await self.get_plan(session, new_plan_id)

        if current_plan.id == new_plan.id:
            raise CareerSamePlanException()

        # Validate upgrade only (higher rank = upgrade)
        if new_plan.rank <= current_plan.rank:
            raise CareerPlanDowngradeNotAllowedException(
                f"Cannot downgrade from {current_plan.name} to {new_plan.name}. "
                "Please cancel and resubscribe to a different plan."
            )

        if not new_plan.stripe_price_id:
            raise CareerPlanNotFoundException("Target plan has no Stripe price.")

        invoice_preview = await Stripe.preview_invoice(
            subscription.stripe_subscription_id,
            new_price_id=new_plan.stripe_price_id,
        )

        stripe_logger.info(
            f"Career upgrade preview for user {user_id}: "
            f"{current_plan.name} -> {new_plan.name}, "
            f"proration: {invoice_preview.proration_amount}"
        )

        return invoice_preview

    async def upgrade_plan(
        self,
        session: AsyncSession,
        user_id: UUID,
        new_plan_id: UUID,
        commit_self: bool = True,
    ) -> SubscriptionModel:
        """
        Upgrade Career subscription to a higher-tier plan.

        Prorates the charge for the current billing period.
        Downgrades are not allowed - users must cancel and resubscribe.

        Args:
            session: Database session.
            user_id: User ID.
            new_plan_id: Target plan ID to upgrade to.
            commit_self: Whether to commit.

        Returns:
            Updated subscription.

        Raises:
            CareerSubscriptionNotFoundException: If no active subscription.
            CareerPlanNotFoundException: If target plan not found.
            CareerPlanDowngradeNotAllowedException: If target plan is lower tier.
            CareerSamePlanException: If already on target plan.
        """
        subscription = await subscription_db.get_by_user(session, user_id)
        if not subscription or not subscription.is_active:
            raise CareerSubscriptionNotFoundException("No active subscription.")

        if not subscription.stripe_subscription_id:
            raise CareerSubscriptionNotFoundException("Subscription has no Stripe ID.")

        current_plan = subscription.plan
        new_plan = await self.get_plan(session, new_plan_id)

        if current_plan.id == new_plan.id:
            raise CareerSamePlanException()

        # Validate upgrade only (higher rank = upgrade)
        if new_plan.rank <= current_plan.rank:
            raise CareerPlanDowngradeNotAllowedException(
                f"Cannot downgrade from {current_plan.name} to {new_plan.name}. "
                "Please cancel and resubscribe to a different plan."
            )

        if not new_plan.stripe_price_id:
            raise CareerPlanNotFoundException("Target plan has no Stripe price.")

        await Stripe.update_subscription(
            subscription.stripe_subscription_id,
            new_price_id=new_plan.stripe_price_id,
            quantity=1,  # Career is always single-user
            proration_behavior="create_prorations",
        )

        subscription_id = subscription.id
        updated_subscription = await subscription_db.update(
            session,
            subscription_id,
            {"plan_id": new_plan.id},
            commit_self=commit_self,
        )

        if not updated_subscription:
            raise CareerSubscriptionNotFoundException(
                f"Subscription {subscription_id} not found after update"
            )

        stripe_logger.info(
            f"Career subscription {subscription_id} upgraded: "
            f"{current_plan.name} -> {new_plan.name}"
        )

        return updated_subscription


# Global service instance
career_subscription_service = CareerSubscriptionService()


__all__ = [
    "CareerSubscriptionService",
    "career_subscription_service",
    # Exceptions
    "CareerSubscriptionNotFoundException",
    "CareerPlanNotFoundException",
    "CareerSubscriptionAlreadyExistsException",
    "CareerPlanDowngradeNotAllowedException",
    "CareerSamePlanException",
]
