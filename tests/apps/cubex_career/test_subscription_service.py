"""
Test suite for Career subscription service — billing period reset.

Tests that handle_subscription_updated correctly resets credits_used
to 0 when the billing period changes (subscription renewal).

Run all tests:
    pytest tests/apps/cubex_career/test_subscription_service.py -v

Run with coverage:
    pytest tests/apps/cubex_career/test_subscription_service.py \
        --cov=app.apps.cubex_career.services.subscription \
        --cov-report=term-missing -v
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.enums import ProductType, SubscriptionStatus


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def career_service():
    """Get CareerSubscriptionService instance."""
    from app.apps.cubex_career.services.subscription import (
        CareerSubscriptionService,
    )

    return CareerSubscriptionService()


@pytest.fixture
def mock_career_subscription():
    """Create a mock Career DB subscription."""
    plan = MagicMock()
    plan.stripe_price_id = "price_career_123"
    plan.name = "Career Plus"
    plan.product_type = ProductType.CAREER

    subscription = MagicMock()
    subscription.id = uuid4()
    subscription.stripe_subscription_id = "sub_career_123"
    subscription.plan = plan
    subscription.plan_id = uuid4()
    subscription.product_type = ProductType.CAREER
    subscription.current_period_start = 1700000000  # Old period
    subscription.current_period_end = 1702678400
    subscription.amount = MagicMock()
    return subscription


@pytest.fixture
def mock_stripe_sub_same_period():
    """Mock Stripe subscription with SAME billing period (no renewal)."""
    price = MagicMock()
    price.id = "price_career_123"
    price.unit_amount = 2900  # $29.00

    item = MagicMock()
    item.price = price
    item.quantity = 1
    item.current_period_start = 1700000000  # Same as old
    item.current_period_end = 1702678400

    items = MagicMock()
    items.data = [item]

    stripe_sub = MagicMock()
    stripe_sub.status = "active"
    stripe_sub.cancel_at_period_end = False
    stripe_sub.canceled_at = None
    stripe_sub.items = items
    return stripe_sub


@pytest.fixture
def mock_stripe_sub_new_period():
    """Mock Stripe subscription with NEW billing period (renewal)."""
    price = MagicMock()
    price.id = "price_career_123"
    price.unit_amount = 2900  # $29.00

    item = MagicMock()
    item.price = price
    item.quantity = 1
    item.current_period_start = 1702678400  # New period!
    item.current_period_end = 1705356800

    items = MagicMock()
    items.data = [item]

    stripe_sub = MagicMock()
    stripe_sub.status = "active"
    stripe_sub.cancel_at_period_end = False
    stripe_sub.canceled_at = None
    stripe_sub.items = items
    return stripe_sub


# ============================================================================
# Billing Period Change — Credits Reset Tests
# ============================================================================


class TestHandleSubscriptionUpdatedCreditsReset:
    """Test that billing period changes correctly reset credits_used."""

    @pytest.mark.asyncio
    async def test_billing_period_changed_resets_credits(
        self,
        career_service,
        mock_career_subscription,
        mock_stripe_sub_new_period,
    ):
        """When billing period changes, credits_used is reset to 0."""
        mock_context = MagicMock()
        mock_context.id = uuid4()

        with (
            patch(
                "app.apps.cubex_career.services.subscription.subscription_db"
            ) as mock_sub_db,
            patch("app.apps.cubex_career.services.subscription.Stripe") as mock_stripe,
            patch(
                "app.apps.cubex_career.services.subscription.career_subscription_context_db"
            ) as mock_ctx_db,
        ):
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_career_subscription
            )
            mock_sub_db.update = AsyncMock(return_value=mock_career_subscription)
            mock_stripe.get_subscription = AsyncMock(
                return_value=mock_stripe_sub_new_period
            )
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=mock_context)
            mock_ctx_db.reset_credits_used = AsyncMock()

            mock_session = AsyncMock()
            await career_service.handle_subscription_updated(
                session=mock_session,
                stripe_subscription_id="sub_career_123",
            )

            mock_ctx_db.reset_credits_used.assert_called_once_with(
                mock_session, mock_context.id
            )

    @pytest.mark.asyncio
    async def test_same_billing_period_does_not_reset_credits(
        self,
        career_service,
        mock_career_subscription,
        mock_stripe_sub_same_period,
    ):
        """When billing period is unchanged, credits_used is NOT reset."""
        with (
            patch(
                "app.apps.cubex_career.services.subscription.subscription_db"
            ) as mock_sub_db,
            patch("app.apps.cubex_career.services.subscription.Stripe") as mock_stripe,
            patch(
                "app.apps.cubex_career.services.subscription.career_subscription_context_db"
            ) as mock_ctx_db,
        ):
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_career_subscription
            )
            mock_sub_db.update = AsyncMock(return_value=mock_career_subscription)
            mock_stripe.get_subscription = AsyncMock(
                return_value=mock_stripe_sub_same_period
            )

            mock_session = AsyncMock()
            await career_service.handle_subscription_updated(
                session=mock_session,
                stripe_subscription_id="sub_career_123",
            )

            # Should NOT have looked up context or reset credits
            mock_ctx_db.get_by_subscription.assert_not_called()
            mock_ctx_db.reset_credits_used.assert_not_called()

    @pytest.mark.asyncio
    async def test_billing_period_changed_no_context_skips_reset(
        self,
        career_service,
        mock_career_subscription,
        mock_stripe_sub_new_period,
    ):
        """When billing period changes but no context exists, no reset occurs."""
        with (
            patch(
                "app.apps.cubex_career.services.subscription.subscription_db"
            ) as mock_sub_db,
            patch("app.apps.cubex_career.services.subscription.Stripe") as mock_stripe,
            patch(
                "app.apps.cubex_career.services.subscription.career_subscription_context_db"
            ) as mock_ctx_db,
        ):
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_career_subscription
            )
            mock_sub_db.update = AsyncMock(return_value=mock_career_subscription)
            mock_stripe.get_subscription = AsyncMock(
                return_value=mock_stripe_sub_new_period
            )
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            await career_service.handle_subscription_updated(
                session=mock_session,
                stripe_subscription_id="sub_career_123",
            )

            mock_ctx_db.get_by_subscription.assert_called_once()
            mock_ctx_db.reset_credits_used.assert_not_called()

    @pytest.mark.asyncio
    async def test_billing_period_none_does_not_reset(
        self,
        career_service,
        mock_career_subscription,
        mock_stripe_sub_new_period,
    ):
        """When new_period_start is None, credits are NOT reset."""
        # Set the new period start to None
        mock_stripe_sub_new_period.items.data[0].current_period_start = None

        with (
            patch(
                "app.apps.cubex_career.services.subscription.subscription_db"
            ) as mock_sub_db,
            patch("app.apps.cubex_career.services.subscription.Stripe") as mock_stripe,
            patch(
                "app.apps.cubex_career.services.subscription.career_subscription_context_db"
            ) as mock_ctx_db,
        ):
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_career_subscription
            )
            mock_sub_db.update = AsyncMock(return_value=mock_career_subscription)
            mock_stripe.get_subscription = AsyncMock(
                return_value=mock_stripe_sub_new_period
            )

            mock_session = AsyncMock()
            await career_service.handle_subscription_updated(
                session=mock_session,
                stripe_subscription_id="sub_career_123",
            )

            mock_ctx_db.get_by_subscription.assert_not_called()
            mock_ctx_db.reset_credits_used.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscription_not_found_returns_none(
        self,
        career_service,
    ):
        """When subscription is not found, returns None without resetting."""
        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            result = await career_service.handle_subscription_updated(
                session=mock_session,
                stripe_subscription_id="sub_nonexistent",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_non_career_subscription_returns_none(
        self,
        career_service,
    ):
        """When subscription is not Career type, returns None without processing."""
        api_subscription = MagicMock()
        api_subscription.product_type = ProductType.API

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=api_subscription
            )

            mock_session = AsyncMock()
            result = await career_service.handle_subscription_updated(
                session=mock_session,
                stripe_subscription_id="sub_api_123",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_no_stripe_items_skips_reset(
        self,
        career_service,
        mock_career_subscription,
    ):
        """When Stripe subscription has no items, no reset occurs."""
        stripe_sub = MagicMock()
        stripe_sub.status = "active"
        stripe_sub.cancel_at_period_end = False
        stripe_sub.canceled_at = None
        stripe_sub.items = None

        with (
            patch(
                "app.apps.cubex_career.services.subscription.subscription_db"
            ) as mock_sub_db,
            patch("app.apps.cubex_career.services.subscription.Stripe") as mock_stripe,
            patch(
                "app.apps.cubex_career.services.subscription.career_subscription_context_db"
            ) as mock_ctx_db,
        ):
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_career_subscription
            )
            mock_sub_db.update = AsyncMock(return_value=mock_career_subscription)
            mock_stripe.get_subscription = AsyncMock(return_value=stripe_sub)

            mock_session = AsyncMock()
            await career_service.handle_subscription_updated(
                session=mock_session,
                stripe_subscription_id="sub_career_123",
            )

            mock_ctx_db.get_by_subscription.assert_not_called()
            mock_ctx_db.reset_credits_used.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_updates_period_in_subscription(
        self,
        career_service,
        mock_career_subscription,
        mock_stripe_sub_new_period,
    ):
        """After reset, subscription update includes new period start/end."""
        mock_context = MagicMock()
        mock_context.id = uuid4()

        with (
            patch(
                "app.apps.cubex_career.services.subscription.subscription_db"
            ) as mock_sub_db,
            patch("app.apps.cubex_career.services.subscription.Stripe") as mock_stripe,
            patch(
                "app.apps.cubex_career.services.subscription.career_subscription_context_db"
            ) as mock_ctx_db,
        ):
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_career_subscription
            )
            mock_sub_db.update = AsyncMock(return_value=mock_career_subscription)
            mock_stripe.get_subscription = AsyncMock(
                return_value=mock_stripe_sub_new_period
            )
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=mock_context)
            mock_ctx_db.reset_credits_used = AsyncMock()

            mock_session = AsyncMock()
            await career_service.handle_subscription_updated(
                session=mock_session,
                stripe_subscription_id="sub_career_123",
            )

            # Verify subscription update includes new period
            update_call = mock_sub_db.update.call_args
            updates = (
                update_call.args[2]
                if len(update_call.args) > 2
                else update_call.kwargs.get("data", {})
            )
            assert updates["current_period_start"] == 1702678400
            assert updates["current_period_end"] == 1705356800


# ============================================================================
# Phase 3: handle_checkout_completed Business Logic Tests
# ============================================================================


class TestHandleCheckoutCompleted:
    """Test suite for Career handle_checkout_completed business logic."""

    @pytest.fixture
    def career_service(self):
        from app.apps.cubex_career.services.subscription import (
            CareerSubscriptionService,
        )

        return CareerSubscriptionService()

    @pytest.fixture
    def mock_stripe_sub(self):
        """Create a basic mock Stripe subscription with single item."""
        price = MagicMock()
        price.id = "price_career_123"
        price.unit_amount = 2900  # $29.00

        item = MagicMock()
        item.price = price
        item.quantity = 1
        item.current_period_start = 1700000000
        item.current_period_end = 1702678400

        items = MagicMock()
        items.data = [item]

        stripe_sub = MagicMock()
        stripe_sub.id = "sub_career_123"
        stripe_sub.status = "active"
        stripe_sub.items = items
        return stripe_sub

    @pytest.mark.asyncio
    async def test_idempotency_returns_existing(
        self, career_service, mock_stripe_sub
    ):
        """If subscription already exists, return it without creating."""
        existing = MagicMock(id=uuid4())

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe:
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=existing
            )
            mock_sub_db.create = AsyncMock()

            result = await career_service.handle_checkout_completed(
                session=AsyncMock(),
                stripe_subscription_id="sub_career_123",
                stripe_customer_id="cus_123",
                user_id=uuid4(),
                plan_id=uuid4(),
            )

            assert result == existing
            mock_sub_db.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_deactivates_existing_free_subscription(
        self, career_service, mock_stripe_sub
    ):
        """Existing free subscription is marked CANCELED before creating new."""
        current_sub = MagicMock(id=uuid4())
        new_sub = MagicMock(id=uuid4())
        user_id = uuid4()

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_career.services.subscription.career_subscription_context_db"
        ) as mock_ctx_db, patch(
            "app.apps.cubex_career.services.subscription.user_db"
        ) as mock_user_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_career.services.subscription.publish_event"
        ):
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_user = AsyncMock(return_value=current_sub)
            mock_sub_db.update = AsyncMock(return_value=current_sub)
            mock_sub_db.create = AsyncMock(return_value=new_sub)
            mock_ctx_db.get_by_user = AsyncMock(return_value=None)
            mock_ctx_db.create = AsyncMock()
            mock_user_db.get_by_id = AsyncMock(return_value=None)
            mock_plan_db.get_by_id = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            await career_service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_career_123",
                stripe_customer_id="cus_123",
                user_id=user_id,
                plan_id=uuid4(),
            )

            # Verify old sub was canceled
            cancel_call = mock_sub_db.update.call_args
            cancel_data = (
                cancel_call.args[2]
                if len(cancel_call.args) > 2
                else cancel_call.kwargs.get("data", {})
            )
            assert cancel_data["status"] == SubscriptionStatus.CANCELED

    @pytest.mark.asyncio
    async def test_creates_subscription_with_career_product_type(
        self, career_service, mock_stripe_sub
    ):
        """New subscription has ProductType.CAREER and seat_count=1."""
        new_sub = MagicMock(id=uuid4())
        user_id = uuid4()
        plan_id = uuid4()

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_career.services.subscription.career_subscription_context_db"
        ) as mock_ctx_db, patch(
            "app.apps.cubex_career.services.subscription.user_db"
        ) as mock_user_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_career.services.subscription.publish_event"
        ):
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_user = AsyncMock(return_value=None)
            mock_sub_db.create = AsyncMock(return_value=new_sub)
            mock_ctx_db.get_by_user = AsyncMock(return_value=None)
            mock_ctx_db.create = AsyncMock()
            mock_user_db.get_by_id = AsyncMock(return_value=None)
            mock_plan_db.get_by_id = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            await career_service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_career_123",
                stripe_customer_id="cus_123",
                user_id=user_id,
                plan_id=plan_id,
            )

            create_data = mock_sub_db.create.call_args
            data = (
                create_data.args[1]
                if len(create_data.args) > 1
                else create_data.kwargs.get("data", {})
            )
            assert data["product_type"] == ProductType.CAREER
            assert data["seat_count"] == 1
            assert data["status"] == SubscriptionStatus.ACTIVE
            assert data["amount"] == Decimal("29.00")

    @pytest.mark.asyncio
    async def test_creates_new_context_when_none_exists(
        self, career_service, mock_stripe_sub
    ):
        """New context is created when user has no previous context."""
        new_sub = MagicMock(id=uuid4())
        user_id = uuid4()

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_career.services.subscription.career_subscription_context_db"
        ) as mock_ctx_db, patch(
            "app.apps.cubex_career.services.subscription.user_db"
        ) as mock_user_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_career.services.subscription.publish_event"
        ):
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_user = AsyncMock(return_value=None)
            mock_sub_db.create = AsyncMock(return_value=new_sub)
            mock_ctx_db.get_by_user = AsyncMock(return_value=None)
            mock_ctx_db.create = AsyncMock()
            mock_user_db.get_by_id = AsyncMock(return_value=None)
            mock_plan_db.get_by_id = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            await career_service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_career_123",
                stripe_customer_id="cus_123",
                user_id=user_id,
                plan_id=uuid4(),
            )

            mock_ctx_db.create.assert_called_once()
            create_data = mock_ctx_db.create.call_args
            data = (
                create_data.args[1]
                if len(create_data.args) > 1
                else create_data.kwargs.get("data", {})
            )
            assert data["user_id"] == user_id
            assert data["subscription_id"] == new_sub.id

    @pytest.mark.asyncio
    async def test_updates_existing_context(self, career_service, mock_stripe_sub):
        """Existing context is updated to point to the new subscription."""
        new_sub = MagicMock(id=uuid4())
        existing_ctx = MagicMock(id=uuid4())
        user_id = uuid4()

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_career.services.subscription.career_subscription_context_db"
        ) as mock_ctx_db, patch(
            "app.apps.cubex_career.services.subscription.user_db"
        ) as mock_user_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_career.services.subscription.publish_event"
        ):
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_user = AsyncMock(return_value=None)
            mock_sub_db.create = AsyncMock(return_value=new_sub)
            mock_ctx_db.get_by_user = AsyncMock(return_value=existing_ctx)
            mock_ctx_db.update = AsyncMock()
            mock_user_db.get_by_id = AsyncMock(return_value=None)
            mock_plan_db.get_by_id = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            await career_service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_career_123",
                stripe_customer_id="cus_123",
                user_id=user_id,
                plan_id=uuid4(),
            )

            mock_ctx_db.update.assert_called_once()
            update_data = mock_ctx_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["subscription_id"] == new_sub.id

    @pytest.mark.asyncio
    async def test_sends_activation_email(self, career_service, mock_stripe_sub):
        """Activation email is published for career user."""
        new_sub = MagicMock(id=uuid4())
        user = MagicMock(email="career@test.com", full_name="Career User")
        plan = MagicMock()
        plan.name = "Career Plus"
        user_id = uuid4()
        plan_id = uuid4()

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_career.services.subscription.career_subscription_context_db"
        ) as mock_ctx_db, patch(
            "app.apps.cubex_career.services.subscription.user_db"
        ) as mock_user_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_career.services.subscription.publish_event",
            new_callable=AsyncMock,
        ) as mock_publish:
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_user = AsyncMock(return_value=None)
            mock_sub_db.create = AsyncMock(return_value=new_sub)
            mock_ctx_db.get_by_user = AsyncMock(return_value=None)
            mock_ctx_db.create = AsyncMock()
            mock_user_db.get_by_id = AsyncMock(return_value=user)
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)

            mock_session = AsyncMock()
            await career_service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_career_123",
                stripe_customer_id="cus_123",
                user_id=user_id,
                plan_id=plan_id,
            )

            mock_publish.assert_called_once()
            payload = mock_publish.call_args[0][1]
            assert payload["email"] == "career@test.com"
            assert payload["plan_name"] == "Career Plus"
            assert payload["workspace_name"] is None
            assert payload["seat_count"] is None
            assert payload["product_name"] == "CueBX Career"


# ============================================================================
# Phase 4: handle_subscription_deleted Tests
# ============================================================================


class TestHandleSubscriptionDeleted:
    """Test suite for Career handle_subscription_deleted."""

    @pytest.fixture
    def career_service(self):
        from app.apps.cubex_career.services.subscription import (
            CareerSubscriptionService,
        )

        return CareerSubscriptionService()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, career_service):
        """Returns None when subscription not found in DB."""
        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)

            result = await career_service.handle_subscription_deleted(
                session=AsyncMock(),
                stripe_subscription_id="sub_not_found",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_not_career_type(self, career_service):
        """Returns None when subscription is not CAREER type."""
        sub = MagicMock(product_type=ProductType.API)

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=sub)

            result = await career_service.handle_subscription_deleted(
                session=AsyncMock(),
                stripe_subscription_id="sub_api_123",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_downgrades_to_free_plan(self, career_service):
        """Subscription is downgraded to free plan when deleted."""
        sub = MagicMock(id=uuid4(), product_type=ProductType.CAREER)
        free_plan = MagicMock(id=uuid4())
        updated_sub = MagicMock(id=sub.id)

        with (
            patch(
                "app.apps.cubex_career.services.subscription.subscription_db"
            ) as mock_sub_db,
            patch(
                "app.apps.cubex_career.services.subscription.plan_db"
            ) as mock_plan_db,
        ):
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=sub)
            mock_sub_db.update = AsyncMock(return_value=updated_sub)
            mock_plan_db.get_free_plan = AsyncMock(return_value=free_plan)

            result = await career_service.handle_subscription_deleted(
                session=AsyncMock(),
                stripe_subscription_id="sub_career_del",
            )

            assert result == updated_sub
            update_call = mock_sub_db.update.call_args
            data = (
                update_call.args[2]
                if len(update_call.args) > 2
                else update_call.kwargs.get("data", {})
            )
            assert data["status"] == SubscriptionStatus.ACTIVE
            assert data["plan_id"] == free_plan.id
            assert data["stripe_subscription_id"] is None
            assert data["cancel_at_period_end"] is False
            assert "canceled_at" in data

    @pytest.mark.asyncio
    async def test_falls_back_to_canceled_when_no_free_plan(self, career_service):
        """Falls back to CANCELED status when free plan is not found."""
        sub = MagicMock(id=uuid4(), product_type=ProductType.CAREER)
        updated_sub = MagicMock(id=sub.id)

        with (
            patch(
                "app.apps.cubex_career.services.subscription.subscription_db"
            ) as mock_sub_db,
            patch(
                "app.apps.cubex_career.services.subscription.plan_db"
            ) as mock_plan_db,
        ):
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=sub)
            mock_sub_db.update = AsyncMock(return_value=updated_sub)
            mock_plan_db.get_free_plan = AsyncMock(return_value=None)

            result = await career_service.handle_subscription_deleted(
                session=AsyncMock(),
                stripe_subscription_id="sub_career_del",
            )

            assert result == updated_sub
            update_call = mock_sub_db.update.call_args
            data = (
                update_call.args[2]
                if len(update_call.args) > 2
                else update_call.kwargs.get("data", {})
            )
            assert data["status"] == SubscriptionStatus.CANCELED
            assert "canceled_at" in data

    @pytest.mark.asyncio
    async def test_no_workspace_freeze_for_career(self, career_service):
        """Career deletion does NOT freeze any workspace."""
        sub = MagicMock(id=uuid4(), product_type=ProductType.CAREER)
        free_plan = MagicMock(id=uuid4())
        updated_sub = MagicMock(id=sub.id)

        with (
            patch(
                "app.apps.cubex_career.services.subscription.subscription_db"
            ) as mock_sub_db,
            patch(
                "app.apps.cubex_career.services.subscription.plan_db"
            ) as mock_plan_db,
        ):
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=sub)
            mock_sub_db.update = AsyncMock(return_value=updated_sub)
            mock_plan_db.get_free_plan = AsyncMock(return_value=free_plan)

            mock_session = AsyncMock()
            await career_service.handle_subscription_deleted(
                session=mock_session,
                stripe_subscription_id="sub_career_del",
            )

            # Career service has no workspace_db interactions
            # Just verify it completed without errors
            mock_sub_db.update.assert_called_once()


# ============================================================================
# Phase 5: handle_subscription_updated Extended Tests
# ============================================================================


class TestHandleSubscriptionUpdatedExtended:
    """Extended tests for Career handle_subscription_updated logic."""

    @pytest.fixture
    def career_service(self):
        from app.apps.cubex_career.services.subscription import (
            CareerSubscriptionService,
        )

        return CareerSubscriptionService()

    @pytest.fixture
    def mock_career_sub(self):
        """Create a mock Career DB subscription."""
        plan = MagicMock()
        plan.stripe_price_id = "price_career_123"
        plan.name = "Career Plus"
        plan.product_type = ProductType.CAREER

        sub = MagicMock()
        sub.id = uuid4()
        sub.plan = plan
        sub.plan_id = uuid4()
        sub.product_type = ProductType.CAREER
        sub.current_period_start = 1700000000
        sub.current_period_end = 1702678400
        sub.amount = None
        return sub

    def _make_stripe_sub(self, status="active", price_id="price_career_123"):
        """Helper to create a mock Stripe subscription."""
        price = MagicMock()
        price.id = price_id
        price.unit_amount = 2900

        item = MagicMock()
        item.price = price
        item.quantity = 1
        item.current_period_start = 1700000000
        item.current_period_end = 1702678400

        items = MagicMock()
        items.data = [item]

        stripe_sub = MagicMock()
        stripe_sub.status = status
        stripe_sub.cancel_at_period_end = False
        stripe_sub.canceled_at = None
        stripe_sub.items = items
        return stripe_sub

    @pytest.mark.asyncio
    async def test_status_mapping_active(self, career_service, mock_career_sub):
        """Stripe 'active' maps to ACTIVE."""
        stripe_sub = self._make_stripe_sub(status="active")

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_career.services.subscription.career_subscription_context_db"
        ) as mock_ctx_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_career_sub
            )
            mock_sub_db.update = AsyncMock(return_value=mock_career_sub)
            mock_stripe.get_subscription = AsyncMock(return_value=stripe_sub)
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=None)

            await career_service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="sub_career_123",
            )

            update_data = mock_sub_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["status"] == SubscriptionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_status_mapping_canceled(self, career_service, mock_career_sub):
        """Stripe 'canceled' maps to CANCELED."""
        stripe_sub = self._make_stripe_sub(status="canceled")

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_career.services.subscription.career_subscription_context_db"
        ) as mock_ctx_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_career_sub
            )
            mock_sub_db.update = AsyncMock(return_value=mock_career_sub)
            mock_stripe.get_subscription = AsyncMock(return_value=stripe_sub)
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=None)

            await career_service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="sub_career_123",
            )

            update_data = mock_sub_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["status"] == SubscriptionStatus.CANCELED

    @pytest.mark.asyncio
    async def test_amount_synced_from_stripe(self, career_service, mock_career_sub):
        """Amount is calculated from Stripe item price."""
        stripe_sub = self._make_stripe_sub()
        stripe_sub.items.data[0].price.unit_amount = 4900  # $49.00

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_career.services.subscription.career_subscription_context_db"
        ) as mock_ctx_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_career_sub
            )
            mock_sub_db.update = AsyncMock(return_value=mock_career_sub)
            mock_stripe.get_subscription = AsyncMock(return_value=stripe_sub)
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=None)

            await career_service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="sub_career_123",
            )

            update_data = mock_sub_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["amount"] == Decimal("49.00")

    @pytest.mark.asyncio
    async def test_canceled_at_propagated(self, career_service, mock_career_sub):
        """canceled_at from Stripe is propagated to DB update."""
        stripe_sub = self._make_stripe_sub(status="canceled")
        stripe_sub.canceled_at = 1702000000

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_career.services.subscription.career_subscription_context_db"
        ) as mock_ctx_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_career_sub
            )
            mock_sub_db.update = AsyncMock(return_value=mock_career_sub)
            mock_stripe.get_subscription = AsyncMock(return_value=stripe_sub)
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=None)

            await career_service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="sub_career_123",
            )

            update_data = mock_sub_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["canceled_at"] == 1702000000

    @pytest.mark.asyncio
    async def test_plan_synced_when_price_changes(self, career_service, mock_career_sub):
        """Plan is updated when Stripe price ID changes to a Career plan."""
        new_plan = MagicMock(id=uuid4(), product_type=ProductType.CAREER, name="Pro")
        stripe_sub = self._make_stripe_sub(price_id="price_new_career")

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_career.services.subscription.career_subscription_context_db"
        ) as mock_ctx_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_career_sub
            )
            mock_sub_db.update = AsyncMock(return_value=mock_career_sub)
            mock_stripe.get_subscription = AsyncMock(return_value=stripe_sub)
            mock_plan_db.get_by_stripe_price_id = AsyncMock(return_value=new_plan)
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=None)

            await career_service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="sub_career_123",
            )

            update_data = mock_sub_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["plan_id"] == new_plan.id


# ============================================================================
# Phase 6: Career create_free_subscription tests
# ============================================================================


class TestCreateFreeSubscription:
    """Tests for CareerSubscriptionService.create_free_subscription."""

    @pytest.fixture
    def career_service(self):
        from app.apps.cubex_career.services.subscription import (
            CareerSubscriptionService,
        )

        return CareerSubscriptionService()

    @pytest.mark.asyncio
    async def test_idempotency_returns_existing(self, career_service):
        """If user already has a subscription, return it."""
        existing = MagicMock(id=uuid4())
        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db:
            mock_sub_db.get_by_user = AsyncMock(return_value=existing)

            result = await career_service.create_free_subscription(
                session=AsyncMock(), user=MagicMock(id=uuid4())
            )

            assert result is existing

    @pytest.mark.asyncio
    async def test_creates_subscription_and_context(self, career_service):
        """Creates subscription + career context for new user."""
        user = MagicMock(id=uuid4())
        free_plan = MagicMock(id=uuid4())
        new_sub = MagicMock(id=uuid4())
        mock_session = AsyncMock()

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_career.services.subscription.career_subscription_context_db"
        ) as mock_ctx_db:
            mock_sub_db.get_by_user = AsyncMock(return_value=None)
            mock_sub_db.create = AsyncMock(return_value=new_sub)
            mock_plan_db.get_free_plan = AsyncMock(return_value=free_plan)
            mock_ctx_db.create = AsyncMock()

            result = await career_service.create_free_subscription(
                session=mock_session, user=user
            )

            assert result is new_sub
            # Verify subscription creation data
            sub_data = mock_sub_db.create.call_args.args[1]
            assert sub_data["plan_id"] == free_plan.id
            assert sub_data["product_type"] == ProductType.CAREER
            assert sub_data["status"] == SubscriptionStatus.ACTIVE
            assert sub_data["seat_count"] == 1
            # Verify context creation
            mock_ctx_db.create.assert_called_once()
            ctx_data = mock_ctx_db.create.call_args.args[1]
            assert ctx_data["subscription_id"] == new_sub.id
            assert ctx_data["user_id"] == user.id

    @pytest.mark.asyncio
    async def test_raises_when_no_free_plan(self, career_service):
        """Raises ValueError if free plan is not seeded."""
        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db:
            mock_sub_db.get_by_user = AsyncMock(return_value=None)
            mock_plan_db.get_free_plan = AsyncMock(return_value=None)

            with pytest.raises(ValueError):
                await career_service.create_free_subscription(
                    session=AsyncMock(), user=MagicMock(id=uuid4())
                )


# ============================================================================
# Phase 6: Career create_checkout_session tests
# ============================================================================


class TestCreateCheckoutSession:
    """Tests for CareerSubscriptionService.create_checkout_session."""

    @pytest.fixture
    def career_service(self):
        from app.apps.cubex_career.services.subscription import (
            CareerSubscriptionService,
        )

        return CareerSubscriptionService()

    @pytest.mark.asyncio
    async def test_happy_path_returns_checkout_session(self, career_service):
        """Successful checkout creates Stripe session and returns it."""
        user = MagicMock(id=uuid4(), email="u@test.com", full_name="Test")
        user.stripe_customer_id = "cus_123"
        plan = MagicMock(
            id=uuid4(),
            stripe_price_id="price_career_plus",
            can_be_purchased=True,
            product_type=ProductType.CAREER,
            is_active=True,
            is_deleted=False,
        )
        plan.name = "Career Plus"
        stripe_session = MagicMock(id="cs_123", url="https://checkout.stripe.com/x")

        with patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe:
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)
            mock_sub_db.get_by_user = AsyncMock(return_value=None)
            mock_stripe.create_checkout_session = AsyncMock(
                return_value=stripe_session
            )

            result = await career_service.create_checkout_session(
                session=AsyncMock(),
                plan_id=plan.id,
                success_url="https://app.test/success",
                cancel_url="https://app.test/cancel",
                user=user,
            )

            assert result is stripe_session
            mock_stripe.create_checkout_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_plan_not_found_raises(self, career_service):
        """Raises when plan does not exist."""
        from app.apps.cubex_career.services.subscription import (
            CareerPlanNotFoundException,
        )

        with patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db:
            mock_plan_db.get_by_id = AsyncMock(return_value=None)

            with pytest.raises(CareerPlanNotFoundException):
                await career_service.create_checkout_session(
                    session=AsyncMock(),
                    plan_id=uuid4(),
                    success_url="https://app.test/success",
                    cancel_url="https://app.test/cancel",
                    user=MagicMock(id=uuid4()),
                )

    @pytest.mark.asyncio
    async def test_existing_paid_subscription_raises(self, career_service):
        """Raises when user already has an active paid subscription."""
        from app.apps.cubex_career.services.subscription import (
            CareerSubscriptionAlreadyExistsException,
        )

        plan = MagicMock(
            can_be_purchased=True,
            product_type=ProductType.CAREER,
            stripe_price_id="price_x",
            is_active=True,
            is_deleted=False,
        )
        plan.name = "Career Plus"
        existing_sub = MagicMock(stripe_subscription_id="sub_existing")

        with patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db:
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)
            mock_sub_db.get_by_user = AsyncMock(return_value=existing_sub)

            with pytest.raises(CareerSubscriptionAlreadyExistsException):
                await career_service.create_checkout_session(
                    session=AsyncMock(),
                    plan_id=uuid4(),
                    success_url="https://app.test/success",
                    cancel_url="https://app.test/cancel",
                    user=MagicMock(id=uuid4()),
                )

    @pytest.mark.asyncio
    async def test_ensure_stripe_customer_called_for_new_customer(
        self, career_service
    ):
        """Creates a Stripe customer if user doesn't have one."""
        user = MagicMock(id=uuid4(), email="new@test.com", full_name="New User")
        user.stripe_customer_id = None
        plan = MagicMock(
            id=uuid4(),
            stripe_price_id="price_career_pro",
            can_be_purchased=True,
            product_type=ProductType.CAREER,
            is_active=True,
            is_deleted=False,
        )
        plan.name = "Career Pro"
        stripe_customer = MagicMock(id="cus_new_123")

        with patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_career.services.subscription.user_db"
        ) as mock_user_db:
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)
            mock_sub_db.get_by_user = AsyncMock(return_value=None)
            mock_stripe.create_customer = AsyncMock(return_value=stripe_customer)
            mock_stripe.create_checkout_session = AsyncMock(
                return_value=MagicMock(id="cs_x")
            )
            mock_user_db.update = AsyncMock()

            await career_service.create_checkout_session(
                session=AsyncMock(),
                plan_id=plan.id,
                success_url="https://app.test/success",
                cancel_url="https://app.test/cancel",
                user=user,
            )

            mock_stripe.create_customer.assert_called_once()
            mock_user_db.update.assert_called_once()


# ============================================================================
# Phase 6: Career cancel_subscription tests
# ============================================================================


class TestCancelSubscription:
    """Tests for CareerSubscriptionService.cancel_subscription."""

    @pytest.fixture
    def career_service(self):
        from app.apps.cubex_career.services.subscription import (
            CareerSubscriptionService,
        )

        return CareerSubscriptionService()

    @pytest.mark.asyncio
    async def test_cancel_at_period_end(self, career_service):
        """Cancel at period end sets flag but keeps ACTIVE status."""
        sub = MagicMock(
            id=uuid4(),
            stripe_subscription_id="sub_cancel_test",
        )
        updated_sub = MagicMock(id=sub.id)

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe:
            mock_sub_db.get_by_user = AsyncMock(return_value=sub)
            mock_sub_db.update = AsyncMock(return_value=updated_sub)
            mock_stripe.cancel_subscription = AsyncMock()

            result = await career_service.cancel_subscription(
                session=AsyncMock(),
                user_id=uuid4(),
                cancel_at_period_end=True,
            )

            assert result is updated_sub
            mock_stripe.cancel_subscription.assert_called_once_with(
                "sub_cancel_test", cancel_at_period_end=True
            )
            update_data = mock_sub_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["cancel_at_period_end"] is True
            assert "status" not in data  # Not immediately canceled

    @pytest.mark.asyncio
    async def test_cancel_immediately(self, career_service):
        """Immediate cancel sets CANCELED status and canceled_at."""
        sub = MagicMock(
            id=uuid4(),
            stripe_subscription_id="sub_cancel_now",
        )
        updated_sub = MagicMock(id=sub.id)

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe:
            mock_sub_db.get_by_user = AsyncMock(return_value=sub)
            mock_sub_db.update = AsyncMock(return_value=updated_sub)
            mock_stripe.cancel_subscription = AsyncMock()

            result = await career_service.cancel_subscription(
                session=AsyncMock(),
                user_id=uuid4(),
                cancel_at_period_end=False,
            )

            assert result is updated_sub
            update_data = mock_sub_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["status"] == SubscriptionStatus.CANCELED
            assert data["canceled_at"] is not None

    @pytest.mark.asyncio
    async def test_not_found_raises(self, career_service):
        """Raises when no subscription found for user."""
        from app.apps.cubex_career.services.subscription import (
            CareerSubscriptionNotFoundException,
        )

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db:
            mock_sub_db.get_by_user = AsyncMock(return_value=None)

            with pytest.raises(CareerSubscriptionNotFoundException):
                await career_service.cancel_subscription(
                    session=AsyncMock(), user_id=uuid4()
                )


# ============================================================================
# Phase 6: Career preview_upgrade tests
# ============================================================================


class TestPreviewUpgrade:
    """Tests for CareerSubscriptionService.preview_upgrade."""

    @pytest.fixture
    def career_service(self):
        from app.apps.cubex_career.services.subscription import (
            CareerSubscriptionService,
        )

        return CareerSubscriptionService()

    def _make_sub(self, plan_id=None, plan_rank=1):
        plan = MagicMock(
            id=plan_id or uuid4(), rank=plan_rank,
            is_active=True, is_deleted=False, product_type=ProductType.CAREER,
        )
        plan.name = "Starter"
        plan.stripe_price_id = "price_starter"
        sub = MagicMock(
            id=uuid4(),
            stripe_subscription_id="sub_preview_test",
            plan=plan,
            plan_id=plan.id,
        )
        return sub

    @pytest.mark.asyncio
    async def test_happy_path_returns_invoice(self, career_service):
        """Successful preview returns Stripe invoice preview."""
        current_plan_id = uuid4()
        sub = self._make_sub(plan_id=current_plan_id, plan_rank=1)
        new_plan = MagicMock(
            id=uuid4(), rank=2, stripe_price_id="price_pro",
            is_active=True, is_deleted=False, product_type=ProductType.CAREER,
        )
        new_plan.name = "Pro"
        invoice = MagicMock(amount_due=1500)

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe:
            mock_sub_db.get_by_user = AsyncMock(return_value=sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=new_plan)
            mock_stripe.preview_invoice = AsyncMock(return_value=invoice)

            result = await career_service.preview_upgrade(
                session=AsyncMock(),
                user_id=uuid4(),
                new_plan_id=new_plan.id,
            )

            assert result is invoice
            mock_stripe.preview_invoice.assert_called_once()

    @pytest.mark.asyncio
    async def test_same_plan_raises(self, career_service):
        """Raises when trying to preview same plan."""
        from app.apps.cubex_career.services.subscription import (
            CareerSamePlanException,
        )

        plan_id = uuid4()
        sub = self._make_sub(plan_id=plan_id)

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db:
            mock_sub_db.get_by_user = AsyncMock(return_value=sub)
            new_plan = MagicMock(
                id=plan_id, rank=1,
                is_active=True, is_deleted=False, product_type=ProductType.CAREER,
            )
            mock_plan_db.get_by_id = AsyncMock(return_value=new_plan)

            with pytest.raises(CareerSamePlanException):
                await career_service.preview_upgrade(
                    session=AsyncMock(),
                    user_id=uuid4(),
                    new_plan_id=plan_id,
                )

    @pytest.mark.asyncio
    async def test_downgrade_raises(self, career_service):
        """Raises when target plan has lower rank."""
        from app.apps.cubex_career.services.subscription import (
            CareerPlanDowngradeNotAllowedException,
        )

        sub = self._make_sub(plan_rank=3)
        new_plan = MagicMock(
            id=uuid4(), rank=2, stripe_price_id="price_lower",
            is_active=True, is_deleted=False, product_type=ProductType.CAREER,
        )
        new_plan.name = "Lower"

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db:
            mock_sub_db.get_by_user = AsyncMock(return_value=sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=new_plan)

            with pytest.raises(CareerPlanDowngradeNotAllowedException):
                await career_service.preview_upgrade(
                    session=AsyncMock(),
                    user_id=uuid4(),
                    new_plan_id=new_plan.id,
                )

    @pytest.mark.asyncio
    async def test_not_found_raises(self, career_service):
        """Raises when subscription not found."""
        from app.apps.cubex_career.services.subscription import (
            CareerSubscriptionNotFoundException,
        )

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db:
            mock_sub_db.get_by_user = AsyncMock(return_value=None)

            with pytest.raises(CareerSubscriptionNotFoundException):
                await career_service.preview_upgrade(
                    session=AsyncMock(),
                    user_id=uuid4(),
                    new_plan_id=uuid4(),
                )


# ============================================================================
# Phase 6: Career upgrade_plan tests
# ============================================================================


class TestUpgradePlan:
    """Tests for CareerSubscriptionService.upgrade_plan."""

    @pytest.fixture
    def career_service(self):
        from app.apps.cubex_career.services.subscription import (
            CareerSubscriptionService,
        )

        return CareerSubscriptionService()

    def _make_sub(self, plan_id=None, plan_rank=1):
        plan = MagicMock(
            id=plan_id or uuid4(), rank=plan_rank,
            is_active=True, is_deleted=False, product_type=ProductType.CAREER,
        )
        plan.name = "Starter"
        plan.stripe_price_id = "price_starter"
        sub = MagicMock(
            id=uuid4(),
            stripe_subscription_id="sub_upgrade_test",
            plan=plan,
            plan_id=plan.id,
        )
        return sub

    @pytest.mark.asyncio
    async def test_happy_path_upgrades_plan(self, career_service):
        """Successful upgrade updates Stripe and DB."""
        sub = self._make_sub(plan_rank=1)
        new_plan = MagicMock(
            id=uuid4(), rank=2, stripe_price_id="price_pro",
            is_active=True, is_deleted=False, product_type=ProductType.CAREER,
        )
        new_plan.name = "Pro"
        updated_sub = MagicMock(id=sub.id)

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_career.services.subscription.Stripe"
        ) as mock_stripe:
            mock_sub_db.get_by_user = AsyncMock(return_value=sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=new_plan)
            mock_stripe.update_subscription = AsyncMock()
            mock_sub_db.update = AsyncMock(return_value=updated_sub)

            result = await career_service.upgrade_plan(
                session=AsyncMock(),
                user_id=uuid4(),
                new_plan_id=new_plan.id,
            )

            assert result is updated_sub
            mock_stripe.update_subscription.assert_called_once()
            # Verify DB plan_id updated
            update_data = mock_sub_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["plan_id"] == new_plan.id

    @pytest.mark.asyncio
    async def test_same_plan_raises(self, career_service):
        """Raises when upgrading to same plan."""
        from app.apps.cubex_career.services.subscription import (
            CareerSamePlanException,
        )

        plan_id = uuid4()
        sub = self._make_sub(plan_id=plan_id)

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db:
            mock_sub_db.get_by_user = AsyncMock(return_value=sub)
            new_plan = MagicMock(
                id=plan_id, rank=1,
                is_active=True, is_deleted=False, product_type=ProductType.CAREER,
            )
            mock_plan_db.get_by_id = AsyncMock(return_value=new_plan)

            with pytest.raises(CareerSamePlanException):
                await career_service.upgrade_plan(
                    session=AsyncMock(),
                    user_id=uuid4(),
                    new_plan_id=plan_id,
                )

    @pytest.mark.asyncio
    async def test_downgrade_raises(self, career_service):
        """Raises when target plan rank is lower."""
        from app.apps.cubex_career.services.subscription import (
            CareerPlanDowngradeNotAllowedException,
        )

        sub = self._make_sub(plan_rank=3)
        new_plan = MagicMock(
            id=uuid4(), rank=1, stripe_price_id="price_low",
            is_active=True, is_deleted=False, product_type=ProductType.CAREER,
        )
        new_plan.name = "Lower"

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_career.services.subscription.plan_db"
        ) as mock_plan_db:
            mock_sub_db.get_by_user = AsyncMock(return_value=sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=new_plan)

            with pytest.raises(CareerPlanDowngradeNotAllowedException):
                await career_service.upgrade_plan(
                    session=AsyncMock(),
                    user_id=uuid4(),
                    new_plan_id=new_plan.id,
                )

    @pytest.mark.asyncio
    async def test_not_found_raises(self, career_service):
        """Raises when subscription not found."""
        from app.apps.cubex_career.services.subscription import (
            CareerSubscriptionNotFoundException,
        )

        with patch(
            "app.apps.cubex_career.services.subscription.subscription_db"
        ) as mock_sub_db:
            mock_sub_db.get_by_user = AsyncMock(return_value=None)

            with pytest.raises(CareerSubscriptionNotFoundException):
                await career_service.upgrade_plan(
                    session=AsyncMock(),
                    user_id=uuid4(),
                    new_plan_id=uuid4(),
                )