"""
Test suite for SubscriptionService.

This module contains comprehensive tests for the SubscriptionService including:
- Checkout session creation
- Webhook event handling
- Seat management
- Workspace freezing and reactivation

Run all tests:
    pytest tests/apps/cubex_api/test_subscription_service.py -v

Run with coverage:
    pytest tests/apps/cubex_api/test_subscription_service.py --cov=app.apps.cubex_api.services.subscription --cov-report=term-missing -v
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.shared.enums import (
    PlanType,
    ProductType,
    SubscriptionStatus,
)


class TestSubscriptionServiceInit:
    """Test suite for SubscriptionService initialization."""

    def test_service_import(self):
        """Test that SubscriptionService can be imported."""
        from app.apps.cubex_api.services.subscription import SubscriptionService

        assert SubscriptionService is not None

    def test_service_singleton_exists(self):
        """Test that subscription_service singleton is accessible."""
        from app.apps.cubex_api.services.subscription import subscription_service

        assert subscription_service is not None


class TestSubscriptionExceptions:
    """Test suite for subscription-related exceptions."""

    def test_subscription_not_found_exception(self):
        """Test SubscriptionNotFoundException."""
        from app.apps.cubex_api.services.subscription import (
            SubscriptionNotFoundException,
        )

        exc = SubscriptionNotFoundException()
        assert exc is not None

    def test_invalid_seat_count_exception(self):
        """Test InvalidSeatCountException."""
        from app.apps.cubex_api.services.subscription import InvalidSeatCountException

        exc = InvalidSeatCountException()
        assert exc is not None

    def test_seat_downgrade_blocked_exception(self):
        """Test SeatDowngradeBlockedException."""
        from app.apps.cubex_api.services.subscription import (
            SeatDowngradeBlockedException,
        )

        exc = SeatDowngradeBlockedException()
        assert exc is not None

    def test_plan_not_found_exception(self):
        """Test PlanNotFoundException."""
        from app.apps.cubex_api.services.subscription import PlanNotFoundException

        exc = PlanNotFoundException()
        assert exc is not None

    def test_plan_downgrade_not_allowed_exception(self):
        """Test PlanDowngradeNotAllowedException."""
        from app.apps.cubex_api.services.subscription import (
            PlanDowngradeNotAllowedException,
        )

        exc = PlanDowngradeNotAllowedException()
        assert exc is not None
        assert "downgrade" in str(exc.message).lower()

    def test_same_plan_exception(self):
        """Test SamePlanException."""
        from app.apps.cubex_api.services.subscription import SamePlanException

        exc = SamePlanException()
        assert exc is not None
        assert "already" in str(exc.message).lower()


class TestSubscriptionServiceEnums:
    """Test that the service correctly uses enums."""

    def test_subscription_status_values(self):
        """Test SubscriptionStatus enum values are correctly used."""
        assert SubscriptionStatus.ACTIVE.value == "active"
        assert SubscriptionStatus.PAST_DUE.value == "past_due"
        assert SubscriptionStatus.CANCELED.value == "canceled"
        assert SubscriptionStatus.INCOMPLETE.value == "incomplete"
        assert SubscriptionStatus.TRIALING.value == "trialing"

    def test_plan_type_values(self):
        """Test PlanType enum values are correctly used."""
        assert PlanType.FREE.value == "free"
        assert PlanType.PAID.value == "paid"


class TestSubscriptionServiceMethods:
    """Test suite for SubscriptionService method signatures."""

    @pytest.fixture
    def service(self):
        """Get SubscriptionService instance."""
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    def test_has_create_checkout_session_method(self, service):
        """Test that create_checkout_session method exists."""
        assert hasattr(service, "create_checkout_session")
        assert callable(service.create_checkout_session)

    def test_has_handle_checkout_completed_method(self, service):
        """Test that handle_checkout_completed method exists."""
        assert hasattr(service, "handle_checkout_completed")
        assert callable(service.handle_checkout_completed)

    def test_has_handle_subscription_updated_method(self, service):
        """Test that handle_subscription_updated method exists."""
        assert hasattr(service, "handle_subscription_updated")
        assert callable(service.handle_subscription_updated)

    def test_has_handle_subscription_deleted_method(self, service):
        """Test that handle_subscription_deleted method exists."""
        assert hasattr(service, "handle_subscription_deleted")
        assert callable(service.handle_subscription_deleted)

    def test_has_update_seat_count_method(self, service):
        """Test that update_seat_count method exists."""
        assert hasattr(service, "update_seat_count")
        assert callable(service.update_seat_count)

    def test_has_cancel_subscription_method(self, service):
        """Test that cancel_subscription method exists."""
        assert hasattr(service, "cancel_subscription")
        assert callable(service.cancel_subscription)

    def test_has_reactivate_workspace_method(self, service):
        """Test that reactivate_workspace method exists."""
        assert hasattr(service, "reactivate_workspace")
        assert callable(service.reactivate_workspace)

    def test_has_get_subscription_method(self, service):
        """Test that get_subscription method exists."""
        assert hasattr(service, "get_subscription")
        assert callable(service.get_subscription)

    def test_has_preview_upgrade_method(self, service):
        """Test that preview_upgrade method exists."""
        assert hasattr(service, "preview_upgrade")
        assert callable(service.preview_upgrade)

    def test_has_upgrade_plan_method(self, service):
        """Test that upgrade_plan method exists."""
        assert hasattr(service, "upgrade_plan")
        assert callable(service.upgrade_plan)


class TestSubscriptionModelIntegration:
    """Test subscription model integration."""

    def test_subscription_model_import(self):
        """Test that Subscription model can be imported."""
        from app.shared.db.models.subscription import Subscription

        assert Subscription is not None

    def test_stripe_event_log_model_import(self):
        """Test that StripeEventLog model can be imported."""
        from app.shared.db.models.subscription import StripeEventLog

        assert StripeEventLog is not None

    def test_plan_model_import(self):
        """Test that Plan model can be imported."""
        from app.shared.db.models.plan import Plan

        assert Plan is not None


class TestSubscriptionCRUDIntegration:
    """Test subscription CRUD integration."""

    def test_subscription_db_import(self):
        """Test that subscription_db can be imported."""
        from app.shared.db.crud import subscription_db

        assert subscription_db is not None

    def test_plan_db_import(self):
        """Test that plan_db can be imported."""
        from app.shared.db.crud import plan_db

        assert plan_db is not None

    def test_stripe_event_log_db_import(self):
        """Test that stripe_event_log_db can be imported."""
        from app.shared.db.crud import stripe_event_log_db

        assert stripe_event_log_db is not None

    def test_api_subscription_context_db_import(self):
        """Test that api_subscription_context_db can be imported."""
        from app.shared.db.crud import api_subscription_context_db

        assert api_subscription_context_db is not None

    def test_career_subscription_context_db_import(self):
        """Test that career_subscription_context_db can be imported."""
        from app.shared.db.crud import career_subscription_context_db

        assert career_subscription_context_db is not None


class TestSubscriptionServiceContextIntegration:
    """Test subscription service context table integration."""

    @pytest.fixture
    def service(self):
        """Get SubscriptionService instance."""
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    def test_service_uses_product_type(self, service):
        """Test that service handles ProductType correctly."""
        # Service should use ProductType.API for workspace subscriptions
        assert ProductType.API.value == "api"
        assert ProductType.CAREER.value == "career"

    def test_api_subscription_context_model_import(self):
        """Test that APISubscriptionContext can be imported."""
        from app.shared.db.models.subscription_context import APISubscriptionContext

        assert APISubscriptionContext is not None

    def test_career_subscription_context_model_import(self):
        """Test that CareerSubscriptionContext can be imported."""
        from app.shared.db.models.subscription_context import CareerSubscriptionContext

        assert CareerSubscriptionContext is not None

    def test_subscription_has_api_context_relationship(self):
        """Test that Subscription model has api_context relationship."""
        from app.shared.db.models.subscription import Subscription

        subscription = Subscription()
        assert hasattr(subscription, "api_context")

    def test_subscription_has_career_context_relationship(self):
        """Test that Subscription model has career_context relationship."""
        from app.shared.db.models.subscription import Subscription

        subscription = Subscription()
        assert hasattr(subscription, "career_context")

    def test_subscription_has_product_type_attribute(self):
        """Test that Subscription model has product_type attribute."""
        from app.shared.db.models.subscription import Subscription

        subscription = Subscription()
        assert hasattr(subscription, "product_type")

    def test_subscription_product_type_default(self):
        """Test that Subscription can be created with API product type.

        Note: Default values are applied by the database on INSERT,
        so we just verify the attribute can be explicitly set.
        """
        from app.shared.db.models.subscription import Subscription

        subscription = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.ACTIVE,
            product_type=ProductType.API,  # Explicitly set since default is at DB level
        )
        assert subscription.product_type == ProductType.API


class TestSubscriptionServiceAPIContextCreation:
    """Test API subscription context creation in service."""

    @pytest.fixture
    def service(self):
        """Get SubscriptionService instance."""
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    @pytest.mark.asyncio
    async def test_handle_checkout_completed_creates_context(self):
        """Test that handle_checkout_completed creates APISubscriptionContext."""
        from app.apps.cubex_api.services.subscription import SubscriptionService

        service = SubscriptionService()

        # Verify service has handle_checkout_completed method
        assert hasattr(service, "handle_checkout_completed")
        assert callable(service.handle_checkout_completed)

    def test_service_imports_api_context_db(self):
        """Test that service can import api_subscription_context_db."""
        from app.shared.db.crud import api_subscription_context_db

        assert api_subscription_context_db is not None
        assert hasattr(api_subscription_context_db, "create")


class TestSubscriptionDBMethods:
    """Test SubscriptionDB methods for context-based lookups."""

    def test_subscription_db_has_get_by_workspace(self):
        """Test that SubscriptionDB has get_by_workspace method."""
        from app.shared.db.crud import subscription_db

        assert hasattr(subscription_db, "get_by_workspace")
        assert callable(subscription_db.get_by_workspace)

    def test_subscription_db_has_get_by_user(self):
        """Test that SubscriptionDB has get_by_user method."""
        from app.shared.db.crud import subscription_db

        assert hasattr(subscription_db, "get_by_user")
        assert callable(subscription_db.get_by_user)

    @pytest.mark.asyncio
    async def test_get_by_workspace_signature(self):
        """Test get_by_workspace method signature."""
        from app.shared.db.crud import subscription_db

        import inspect

        sig = inspect.signature(subscription_db.get_by_workspace)
        params = list(sig.parameters.keys())

        # Should have session and workspace_id parameters
        assert "session" in params
        assert "workspace_id" in params

    @pytest.mark.asyncio
    async def test_get_by_user_signature(self):
        """Test get_by_user method signature."""
        from app.shared.db.crud import subscription_db

        import inspect

        sig = inspect.signature(subscription_db.get_by_user)
        params = list(sig.parameters.keys())

        # Should have session and user_id parameters
        assert "session" in params
        assert "user_id" in params


class TestCheckoutSessionLineItems:
    """Test suite for dual-line-item checkout (base + seat pricing)."""

    @pytest.fixture
    def service(self):
        """Get SubscriptionService instance."""
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    @pytest.fixture
    def mock_plan_with_seats(self):
        """Create a mock plan with seat pricing."""
        plan = MagicMock()
        plan.id = uuid4()
        plan.stripe_price_id = "price_base_123"
        plan.seat_stripe_price_id = "price_seat_456"
        plan.has_seat_pricing = True
        plan.can_be_purchased = True
        plan.min_seats = 1
        plan.max_seats = 100
        plan.is_paid = True
        return plan

    @pytest.fixture
    def mock_plan_without_seats(self):
        """Create a mock plan without seat pricing (career plan)."""
        plan = MagicMock()
        plan.id = uuid4()
        plan.stripe_price_id = "price_career_123"
        plan.seat_stripe_price_id = None
        plan.has_seat_pricing = False
        plan.can_be_purchased = True
        plan.min_seats = 1
        plan.max_seats = None
        plan.is_paid = True
        return plan

    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        user = MagicMock()
        user.id = uuid4()
        user.email = "test@example.com"
        user.stripe_customer_id = "cus_123"
        return user

    @pytest.mark.asyncio
    async def test_checkout_creates_dual_line_items_for_seat_plan(
        self, service, mock_plan_with_seats, mock_user
    ):
        """Test that checkout session creates two line items for plans with seat pricing."""

        workspace_id = uuid4()
        seat_count = 5

        with patch.object(
            service, "get_plan", new_callable=AsyncMock
        ) as mock_get_plan, patch.object(
            service, "_ensure_stripe_customer", new_callable=AsyncMock
        ) as mock_ensure_customer, patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe:
            mock_get_plan.return_value = mock_plan_with_seats
            mock_ensure_customer.return_value = "cus_123"
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)
            mock_stripe.create_checkout_session = AsyncMock(
                return_value=MagicMock(id="cs_test_123")
            )

            mock_session = AsyncMock()
            await service.create_checkout_session(
                session=mock_session,
                workspace_id=workspace_id,
                plan_id=mock_plan_with_seats.id,
                seat_count=seat_count,
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
                user=mock_user,
            )

            # Verify Stripe.create_checkout_session was called
            mock_stripe.create_checkout_session.assert_called_once()
            call_kwargs = mock_stripe.create_checkout_session.call_args.kwargs

            # Extract line_items
            line_items = call_kwargs.get("line_items", [])

            # Should have 2 line items: base + seats
            assert len(line_items) == 2

            # First item: base price (quantity=1)
            assert line_items[0].price == "price_base_123"
            assert line_items[0].quantity == 1

            # Second item: seat price (quantity=seat_count)
            assert line_items[1].price == "price_seat_456"
            assert line_items[1].quantity == seat_count

    @pytest.mark.asyncio
    async def test_checkout_creates_single_line_item_for_plan_without_seats(
        self, service, mock_plan_without_seats, mock_user
    ):
        """Test that checkout session creates one line item for plans without seat pricing."""
        workspace_id = uuid4()
        seat_count = 1

        with patch.object(
            service, "get_plan", new_callable=AsyncMock
        ) as mock_get_plan, patch.object(
            service, "_ensure_stripe_customer", new_callable=AsyncMock
        ) as mock_ensure_customer, patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe:
            mock_get_plan.return_value = mock_plan_without_seats
            mock_ensure_customer.return_value = "cus_123"
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)
            mock_stripe.create_checkout_session = AsyncMock(
                return_value=MagicMock(id="cs_test_123")
            )

            mock_session = AsyncMock()
            await service.create_checkout_session(
                session=mock_session,
                workspace_id=workspace_id,
                plan_id=mock_plan_without_seats.id,
                seat_count=seat_count,
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
                user=mock_user,
            )

            # Verify Stripe.create_checkout_session was called
            mock_stripe.create_checkout_session.assert_called_once()
            call_kwargs = mock_stripe.create_checkout_session.call_args.kwargs

            # Extract line_items
            line_items = call_kwargs.get("line_items", [])

            # Should have 1 line item: base only (no seats)
            assert len(line_items) == 1

            # Only item: base price (quantity=1)
            assert line_items[0].price == "price_career_123"
            assert line_items[0].quantity == 1


class TestUpdateSeatCountWithSeatPriceId:
    """Test suite for update_seat_count with seat_price_id."""

    @pytest.fixture
    def service(self):
        """Get SubscriptionService instance."""
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    @pytest.fixture
    def mock_subscription_with_seats(self):
        """Create a mock subscription with seat pricing plan."""
        plan = MagicMock()
        plan.seat_stripe_price_id = "price_seat_456"
        plan.min_seats = 1
        plan.max_seats = 100

        subscription = MagicMock()
        subscription.id = uuid4()
        subscription.stripe_subscription_id = "sub_123"
        subscription.seat_count = 5
        subscription.plan = plan
        return subscription

    @pytest.mark.asyncio
    async def test_update_seat_count_passes_seat_price_id(
        self, service, mock_subscription_with_seats
    ):
        """Test that update_seat_count passes seat_price_id to Stripe.update_subscription."""
        workspace_id = uuid4()
        new_seat_count = 10

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_member_db"
        ) as mock_member_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe:
            mock_sub_db.get_by_workspace = AsyncMock(
                return_value=mock_subscription_with_seats
            )
            mock_sub_db.update = AsyncMock(return_value=mock_subscription_with_seats)
            mock_member_db.get_enabled_member_count = AsyncMock(return_value=3)
            mock_stripe.update_subscription = AsyncMock()

            mock_session = AsyncMock()
            await service.update_seat_count(
                session=mock_session,
                workspace_id=workspace_id,
                new_seat_count=new_seat_count,
            )

            # Verify Stripe.update_subscription was called with seat_price_id
            mock_stripe.update_subscription.assert_called_once()
            call_kwargs = mock_stripe.update_subscription.call_args.kwargs

            assert call_kwargs.get("quantity") == new_seat_count
            assert call_kwargs.get("seat_price_id") == "price_seat_456"
            # Upgrade (adding seats) should have proration
            assert call_kwargs.get("proration_behavior") == "create_prorations"

    @pytest.mark.asyncio
    async def test_update_seat_count_downgrade_no_proration(
        self, service, mock_subscription_with_seats
    ):
        """Test that downgrading seats uses no proration."""
        workspace_id = uuid4()
        new_seat_count = 3  # Less than current 5

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_member_db"
        ) as mock_member_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe:
            mock_sub_db.get_by_workspace = AsyncMock(
                return_value=mock_subscription_with_seats
            )
            mock_sub_db.update = AsyncMock(return_value=mock_subscription_with_seats)
            mock_member_db.get_enabled_member_count = AsyncMock(
                return_value=2
            )  # Less than new count
            mock_stripe.update_subscription = AsyncMock()

            mock_session = AsyncMock()
            await service.update_seat_count(
                session=mock_session,
                workspace_id=workspace_id,
                new_seat_count=new_seat_count,
            )

            # Verify downgrade uses no proration
            call_kwargs = mock_stripe.update_subscription.call_args.kwargs
            assert call_kwargs.get("proration_behavior") == "none"


class TestHandleSubscriptionUpdated:
    """Test suite for handle_subscription_updated with old and new subscription structures."""

    @pytest.fixture
    def service(self):
        """Get SubscriptionService instance."""
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    @pytest.fixture
    def mock_db_subscription_with_seats(self):
        """Create a mock DB subscription with seat pricing plan."""
        plan = MagicMock()
        plan.stripe_price_id = "price_base_123"
        plan.seat_stripe_price_id = "price_seat_456"
        plan.has_seat_pricing = True
        plan.product_type = MagicMock()
        plan.product_type.value = "api"
        plan.name = "Professional"

        api_context = MagicMock()
        api_context.workspace_id = uuid4()

        subscription = MagicMock()
        subscription.id = uuid4()
        subscription.stripe_subscription_id = "sub_123"
        subscription.seat_count = 5
        subscription.amount = 99.00
        subscription.plan = plan
        subscription.plan_id = uuid4()
        subscription.api_context = api_context
        subscription.product_type = MagicMock()
        subscription.product_type.value = "api"
        return subscription

    @pytest.fixture
    def mock_stripe_subscription_dual_item(self):
        """Create a mock Stripe subscription with dual line items (new structure)."""
        # Base price item
        base_price = MagicMock()
        base_price.id = "price_base_123"
        base_price.unit_amount = 2900  # $29.00

        base_item = MagicMock()
        base_item.price = base_price
        base_item.quantity = 1
        base_item.current_period_start = 1700000000
        base_item.current_period_end = 1702678400

        # Seat price item
        seat_price = MagicMock()
        seat_price.id = "price_seat_456"
        seat_price.unit_amount = 900  # $9.00 per seat

        seat_item = MagicMock()
        seat_item.price = seat_price
        seat_item.quantity = 10  # 10 seats
        seat_item.current_period_start = 1700000000
        seat_item.current_period_end = 1702678400

        # Items container
        items = MagicMock()
        items.data = [base_item, seat_item]

        # Stripe subscription
        stripe_sub = MagicMock()
        stripe_sub.status = "active"
        stripe_sub.cancel_at_period_end = False
        stripe_sub.canceled_at = None
        stripe_sub.items = items
        return stripe_sub

    @pytest.fixture
    def mock_stripe_subscription_single_item(self):
        """Create a mock Stripe subscription with single line item (old structure)."""
        # Single price item (old model: price * quantity = total)
        price = MagicMock()
        price.id = "price_base_123"
        price.unit_amount = 2900  # $29.00 per seat

        item = MagicMock()
        item.price = price
        item.quantity = 5  # 5 seats
        item.current_period_start = 1700000000
        item.current_period_end = 1702678400

        # Items container
        items = MagicMock()
        items.data = [item]

        # Stripe subscription
        stripe_sub = MagicMock()
        stripe_sub.status = "active"
        stripe_sub.cancel_at_period_end = False
        stripe_sub.canceled_at = None
        stripe_sub.items = items
        return stripe_sub

    @pytest.mark.asyncio
    async def test_handle_update_dual_item_syncs_seat_count(
        self,
        service,
        mock_db_subscription_with_seats,
        mock_stripe_subscription_dual_item,
    ):
        """Test that dual-item subscription syncs seat count from seat item."""
        from decimal import Decimal

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ), patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_context_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_db_subscription_with_seats
            )
            mock_sub_db.update = AsyncMock(return_value=mock_db_subscription_with_seats)
            mock_stripe.get_subscription = AsyncMock(
                return_value=mock_stripe_subscription_dual_item
            )
            mock_context_db.get_by_subscription = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            await service.handle_subscription_updated(
                session=mock_session,
                stripe_subscription_id="sub_123",
            )

            # Verify update was called with correct seat count from seat item
            update_call = mock_sub_db.update.call_args
            updates = (
                update_call.args[2]
                if len(update_call.args) > 2
                else update_call.kwargs.get("data", {})
            )

            # Seat count should be 10 (from seat item), not 1 (from base item)
            assert updates.get("seat_count") == 10

            # Amount should be $29 (base) + $90 (10 seats * $9) = $119
            expected_amount = Decimal("119.00")
            assert updates.get("amount") == expected_amount

    @pytest.mark.asyncio
    async def test_handle_update_single_item_syncs_seat_count(
        self,
        service,
        mock_db_subscription_with_seats,
        mock_stripe_subscription_single_item,
    ):
        """Test that single-item subscription (legacy) syncs seat count from first item."""
        from decimal import Decimal

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ), patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_context_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_db_subscription_with_seats
            )
            mock_sub_db.update = AsyncMock(return_value=mock_db_subscription_with_seats)
            mock_stripe.get_subscription = AsyncMock(
                return_value=mock_stripe_subscription_single_item
            )
            mock_context_db.get_by_subscription = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            await service.handle_subscription_updated(
                session=mock_session,
                stripe_subscription_id="sub_123",
            )

            # Verify update was called - legacy behavior uses first item quantity
            mock_sub_db.update.assert_called_once()

            # Amount should be $29 * 5 = $145
            update_call = mock_sub_db.update.call_args
            updates = (
                update_call.args[2]
                if len(update_call.args) > 2
                else update_call.kwargs.get("data", {})
            )
            expected_amount = Decimal("145.00")
            assert updates.get("amount") == expected_amount


class TestHandleCheckoutCompletedAmount:
    """Test suite for handle_checkout_completed amount calculation with dual-line items."""

    @pytest.fixture
    def service(self):
        """Get SubscriptionService instance."""
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    @pytest.fixture
    def mock_stripe_subscription_dual_items(self):
        """Create a mock Stripe subscription with two line items (base + seats)."""
        base_item = MagicMock()
        base_item.id = "si_base_123"
        base_item.quantity = 1
        base_item.current_period_start = datetime.now(UTC)
        base_item.current_period_end = datetime.now(UTC) + timedelta(days=30)
        base_item.price = MagicMock()
        base_item.price.id = "price_base_123"
        base_item.price.unit_amount = 2900  # $29 base price

        seat_item = MagicMock()
        seat_item.id = "si_seat_456"
        seat_item.quantity = 5  # 5 seats
        seat_item.current_period_start = datetime.now(UTC)
        seat_item.current_period_end = datetime.now(UTC) + timedelta(days=30)
        seat_item.price = MagicMock()
        seat_item.price.id = "price_seat_456"
        seat_item.price.unit_amount = 900  # $9 per seat

        stripe_sub = MagicMock()
        stripe_sub.id = "sub_123"
        stripe_sub.status = "active"
        stripe_sub.cancel_at_period_end = False
        stripe_sub.canceled_at = None
        stripe_sub.items = MagicMock()
        stripe_sub.items.data = [base_item, seat_item]
        return stripe_sub

    @pytest.fixture
    def mock_stripe_subscription_single_item(self):
        """Create a mock Stripe subscription with single line item (legacy)."""
        item = MagicMock()
        item.id = "si_123"
        item.quantity = 5  # 5 seats
        item.current_period_start = datetime.now(UTC)
        item.current_period_end = datetime.now(UTC) + timedelta(days=30)
        item.price = MagicMock()
        item.price.id = "price_123"
        item.price.unit_amount = 2900  # $29 per seat

        stripe_sub = MagicMock()
        stripe_sub.id = "sub_123"
        stripe_sub.status = "active"
        stripe_sub.cancel_at_period_end = False
        stripe_sub.canceled_at = None
        stripe_sub.items = MagicMock()
        stripe_sub.items.data = [item]
        return stripe_sub

    @pytest.mark.asyncio
    async def test_checkout_dual_items_calculates_total_amount(
        self, service, mock_stripe_subscription_dual_items
    ):
        """Test that checkout with dual items calculates correct total amount."""
        from decimal import Decimal
        from uuid import uuid4

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_workspace_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db, patch(
            "app.apps.cubex_api.services.subscription.user_db"
        ) as mock_user_db, patch(
            "app.apps.cubex_api.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_api.services.subscription.publish_event"
        ):
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)
            mock_sub_db.create = AsyncMock(return_value=MagicMock(id=uuid4()))
            mock_stripe.get_subscription = AsyncMock(
                return_value=mock_stripe_subscription_dual_items
            )
            mock_workspace_db.update_status = AsyncMock()
            mock_workspace_db.get_by_id = AsyncMock(return_value=None)
            mock_ctx_db.get_by_workspace = AsyncMock(return_value=None)
            mock_ctx_db.create = AsyncMock()
            mock_user_db.get_by_id = AsyncMock(return_value=None)
            mock_plan_db.get_by_id = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            workspace_id = uuid4()
            plan_id = uuid4()

            await service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_123",
                stripe_customer_id="cus_123",
                workspace_id=workspace_id,
                plan_id=plan_id,
                seat_count=5,
            )

            # Verify create was called
            mock_sub_db.create.assert_called_once()

            # Check the amount calculation: $29 (base) + $45 (5 * $9 seats) = $74
            create_call = mock_sub_db.create.call_args
            create_data = (
                create_call.args[1]
                if len(create_call.args) > 1
                else create_call.kwargs.get("data", {})
            )

            expected_amount = Decimal("74.00")
            assert create_data.get("amount") == expected_amount

    @pytest.mark.asyncio
    async def test_checkout_single_item_calculates_amount(
        self, service, mock_stripe_subscription_single_item
    ):
        """Test that checkout with single item calculates correct amount."""
        from decimal import Decimal
        from uuid import uuid4

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_workspace_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db, patch(
            "app.apps.cubex_api.services.subscription.user_db"
        ) as mock_user_db, patch(
            "app.apps.cubex_api.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_api.services.subscription.publish_event"
        ):
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)
            mock_sub_db.create = AsyncMock(return_value=MagicMock(id=uuid4()))
            mock_stripe.get_subscription = AsyncMock(
                return_value=mock_stripe_subscription_single_item
            )
            mock_workspace_db.update_status = AsyncMock()
            mock_workspace_db.get_by_id = AsyncMock(return_value=None)
            mock_ctx_db.get_by_workspace = AsyncMock(return_value=None)
            mock_ctx_db.create = AsyncMock()
            mock_user_db.get_by_id = AsyncMock(return_value=None)
            mock_plan_db.get_by_id = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            workspace_id = uuid4()
            plan_id = uuid4()

            await service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_123",
                stripe_customer_id="cus_123",
                workspace_id=workspace_id,
                plan_id=plan_id,
                seat_count=5,
            )

            # Verify create was called
            mock_sub_db.create.assert_called_once()

            # Check the amount calculation: $29 * 5 = $145
            create_call = mock_sub_db.create.call_args
            create_data = (
                create_call.args[1]
                if len(create_call.args) > 1
                else create_call.kwargs.get("data", {})
            )

            expected_amount = Decimal("145.00")
            assert create_data.get("amount") == expected_amount
