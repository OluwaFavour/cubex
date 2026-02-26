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

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.enums import ProductType


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
