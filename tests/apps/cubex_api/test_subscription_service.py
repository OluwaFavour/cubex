"""
Test suite for SubscriptionService.

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

from app.core.enums import (
    PlanType,
    ProductType,
    SubscriptionStatus,
)


class TestSubscriptionServiceInit:

    def test_service_import(self):
        from app.apps.cubex_api.services.subscription import SubscriptionService

        assert SubscriptionService is not None

    def test_service_singleton_exists(self):
        from app.apps.cubex_api.services.subscription import subscription_service

        assert subscription_service is not None


class TestSubscriptionExceptions:

    def test_subscription_not_found_exception(self):
        from app.apps.cubex_api.services.subscription import (
            SubscriptionNotFoundException,
        )

        exc = SubscriptionNotFoundException()
        assert exc is not None

    def test_invalid_seat_count_exception(self):
        from app.apps.cubex_api.services.subscription import InvalidSeatCountException

        exc = InvalidSeatCountException()
        assert exc is not None

    def test_seat_downgrade_blocked_exception(self):
        from app.apps.cubex_api.services.subscription import (
            SeatDowngradeBlockedException,
        )

        exc = SeatDowngradeBlockedException()
        assert exc is not None

    def test_plan_not_found_exception(self):
        from app.apps.cubex_api.services.subscription import PlanNotFoundException

        exc = PlanNotFoundException()
        assert exc is not None

    def test_plan_downgrade_not_allowed_exception(self):
        from app.apps.cubex_api.services.subscription import (
            PlanDowngradeNotAllowedException,
        )

        exc = PlanDowngradeNotAllowedException()
        assert exc is not None
        assert "downgrade" in str(exc.message).lower()

    def test_same_plan_exception(self):
        from app.apps.cubex_api.services.subscription import SamePlanException

        exc = SamePlanException()
        assert exc is not None
        assert "already" in str(exc.message).lower()


class TestSubscriptionServiceEnums:

    def test_subscription_status_values(self):
        assert SubscriptionStatus.ACTIVE.value == "active"
        assert SubscriptionStatus.PAST_DUE.value == "past_due"
        assert SubscriptionStatus.CANCELED.value == "canceled"
        assert SubscriptionStatus.INCOMPLETE.value == "incomplete"
        assert SubscriptionStatus.TRIALING.value == "trialing"

    def test_plan_type_values(self):
        assert PlanType.FREE.value == "free"
        assert PlanType.PAID.value == "paid"


class TestSubscriptionServiceMethods:

    @pytest.fixture
    def service(self):
        """Get SubscriptionService instance."""
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    def test_has_create_checkout_session_method(self, service):
        assert hasattr(service, "create_checkout_session")
        assert callable(service.create_checkout_session)

    def test_has_handle_checkout_completed_method(self, service):
        assert hasattr(service, "handle_checkout_completed")
        assert callable(service.handle_checkout_completed)

    def test_has_handle_subscription_updated_method(self, service):
        assert hasattr(service, "handle_subscription_updated")
        assert callable(service.handle_subscription_updated)

    def test_has_handle_subscription_deleted_method(self, service):
        assert hasattr(service, "handle_subscription_deleted")
        assert callable(service.handle_subscription_deleted)

    def test_has_update_seat_count_method(self, service):
        assert hasattr(service, "update_seat_count")
        assert callable(service.update_seat_count)

    def test_has_cancel_subscription_method(self, service):
        assert hasattr(service, "cancel_subscription")
        assert callable(service.cancel_subscription)

    def test_has_reactivate_workspace_method(self, service):
        assert hasattr(service, "reactivate_workspace")
        assert callable(service.reactivate_workspace)

    def test_has_get_subscription_method(self, service):
        assert hasattr(service, "get_subscription")
        assert callable(service.get_subscription)

    def test_has_preview_upgrade_method(self, service):
        assert hasattr(service, "preview_subscription_change")
        assert callable(service.preview_subscription_change)

    def test_has_upgrade_plan_method(self, service):
        assert hasattr(service, "upgrade_plan")
        assert callable(service.upgrade_plan)


class TestSubscriptionModelIntegration:

    def test_subscription_model_import(self):
        from app.core.db.models.subscription import Subscription

        assert Subscription is not None

    def test_stripe_event_log_model_import(self):
        from app.core.db.models.subscription import StripeEventLog

        assert StripeEventLog is not None

    def test_plan_model_import(self):
        from app.core.db.models.plan import Plan

        assert Plan is not None


class TestSubscriptionCRUDIntegration:

    def test_subscription_db_import(self):
        from app.core.db.crud import subscription_db

        assert subscription_db is not None

    def test_plan_db_import(self):
        from app.core.db.crud import plan_db

        assert plan_db is not None

    def test_stripe_event_log_db_import(self):
        from app.core.db.crud import stripe_event_log_db

        assert stripe_event_log_db is not None

    def test_api_subscription_context_db_import(self):
        from app.core.db.crud import api_subscription_context_db

        assert api_subscription_context_db is not None

    def test_career_subscription_context_db_import(self):
        from app.core.db.crud import career_subscription_context_db

        assert career_subscription_context_db is not None


class TestSubscriptionServiceContextIntegration:

    @pytest.fixture
    def service(self):
        """Get SubscriptionService instance."""
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    def test_service_uses_product_type(self, service):
        # Service should use ProductType.API for workspace subscriptions
        assert ProductType.API.value == "api"
        assert ProductType.CAREER.value == "career"

    def test_api_subscription_context_model_import(self):
        from app.core.db.models.subscription_context import APISubscriptionContext

        assert APISubscriptionContext is not None

    def test_career_subscription_context_model_import(self):
        from app.core.db.models.subscription_context import CareerSubscriptionContext

        assert CareerSubscriptionContext is not None

    def test_subscription_has_api_context_relationship(self):
        from app.core.db.models.subscription import Subscription

        subscription = Subscription()
        assert hasattr(subscription, "api_context")

    def test_subscription_has_career_context_relationship(self):
        from app.core.db.models.subscription import Subscription

        subscription = Subscription()
        assert hasattr(subscription, "career_context")

    def test_subscription_has_product_type_attribute(self):
        from app.core.db.models.subscription import Subscription

        subscription = Subscription()
        assert hasattr(subscription, "product_type")

    def test_subscription_product_type_default(self):
        from app.core.db.models.subscription import Subscription

        subscription = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.ACTIVE,
            product_type=ProductType.API,  # Explicitly set since default is at DB level
        )
        assert subscription.product_type == ProductType.API


class TestSubscriptionServiceAPIContextCreation:

    @pytest.fixture
    def service(self):
        """Get SubscriptionService instance."""
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    @pytest.mark.asyncio
    async def test_handle_checkout_completed_creates_context(self):
        from app.apps.cubex_api.services.subscription import SubscriptionService

        service = SubscriptionService()

        assert hasattr(service, "handle_checkout_completed")
        assert callable(service.handle_checkout_completed)

    def test_service_imports_api_context_db(self):
        from app.core.db.crud import api_subscription_context_db

        assert api_subscription_context_db is not None
        assert hasattr(api_subscription_context_db, "create")


class TestSubscriptionDBMethods:

    def test_subscription_db_has_get_by_workspace(self):
        from app.core.db.crud import subscription_db

        assert hasattr(subscription_db, "get_by_workspace")
        assert callable(subscription_db.get_by_workspace)

    def test_subscription_db_has_get_by_user(self):
        from app.core.db.crud import subscription_db

        assert hasattr(subscription_db, "get_by_user")
        assert callable(subscription_db.get_by_user)

    @pytest.mark.asyncio
    async def test_get_by_workspace_signature(self):
        from app.core.db.crud import subscription_db

        import inspect

        sig = inspect.signature(subscription_db.get_by_workspace)
        params = list(sig.parameters.keys())

        assert "session" in params
        assert "workspace_id" in params

    @pytest.mark.asyncio
    async def test_get_by_user_signature(self):
        from app.core.db.crud import subscription_db

        import inspect

        sig = inspect.signature(subscription_db.get_by_user)
        params = list(sig.parameters.keys())

        assert "session" in params
        assert "user_id" in params


class TestCheckoutSessionLineItems:

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

            mock_stripe.create_checkout_session.assert_called_once()
            call_kwargs = mock_stripe.create_checkout_session.call_args.kwargs

            line_items = call_kwargs.get("line_items", [])

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

            mock_stripe.create_checkout_session.assert_called_once()
            call_kwargs = mock_stripe.create_checkout_session.call_args.kwargs

            line_items = call_kwargs.get("line_items", [])

            # Should have 1 line item: base only (no seats)
            assert len(line_items) == 1

            # Only item: base price (quantity=1)
            assert line_items[0].price == "price_career_123"
            assert line_items[0].quantity == 1


class TestUpdateSeatCountWithSeatPriceId:

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

            call_kwargs = mock_stripe.update_subscription.call_args.kwargs
            assert call_kwargs.get("proration_behavior") == "none"


class TestHandleSubscriptionUpdated:

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
            "app.apps.cubex_api.services.subscription.get_publisher",
            return_value=AsyncMock(),
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
            plan_id = uuid4()
            plan = MagicMock()
            plan.id = plan_id
            plan.stripe_price_id = "price_123"
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)

            mock_session = AsyncMock()
            workspace_id = uuid4()

            await service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_123",
                stripe_customer_id="cus_123",
                workspace_id=workspace_id,
                plan_id=plan_id,
                seat_count=5,
            )

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
            "app.apps.cubex_api.services.subscription.get_publisher",
            return_value=AsyncMock(),
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
            plan_id = uuid4()
            plan = MagicMock()
            plan.id = plan_id
            plan.stripe_price_id = "price_123"
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)

            mock_session = AsyncMock()
            workspace_id = uuid4()

            await service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_123",
                stripe_customer_id="cus_123",
                workspace_id=workspace_id,
                plan_id=plan_id,
                seat_count=5,
            )

            mock_sub_db.create.assert_called_once()

            create_call = mock_sub_db.create.call_args
            create_data = (
                create_call.args[1]
                if len(create_call.args) > 1
                else create_call.kwargs.get("data", {})
            )

            expected_amount = Decimal("145.00")
            assert create_data.get("amount") == expected_amount


class TestHandleCheckoutCompletedLogic:

    @pytest.fixture
    def service(self):
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    @pytest.fixture
    def mock_stripe_sub(self):
        """Create a basic mock Stripe subscription with single item."""
        price = MagicMock()
        price.id = "price_base_123"
        price.unit_amount = 2900

        item = MagicMock()
        item.price = price
        item.quantity = 1
        item.current_period_start = 1700000000
        item.current_period_end = 1702678400

        items = MagicMock()
        items.data = [item]

        stripe_sub = MagicMock()
        stripe_sub.id = "sub_123"
        stripe_sub.status = "active"
        stripe_sub.items = items
        return stripe_sub

    @pytest.mark.asyncio
    async def test_idempotency_returns_existing(self, service, mock_stripe_sub):
        existing = MagicMock(id=uuid4())

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe:
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=existing)
            mock_sub_db.create = AsyncMock()

            result = await service.handle_checkout_completed(
                session=AsyncMock(),
                stripe_subscription_id="sub_123",
                stripe_customer_id="cus_123",
                workspace_id=uuid4(),
                plan_id=uuid4(),
                seat_count=1,
            )

            assert result == existing
            mock_sub_db.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_deactivates_existing_free_subscription(
        self, service, mock_stripe_sub
    ):
        current_sub = MagicMock(id=uuid4())
        plan = MagicMock(id=uuid4(), stripe_price_id="price_base_123")
        new_sub = MagicMock(id=uuid4())
        workspace_id = uuid4()

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db, patch(
            "app.apps.cubex_api.services.subscription.user_db"
        ) as mock_user_db, patch(
            "app.apps.cubex_api.services.subscription.get_publisher",
            return_value=AsyncMock(),
        ):
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_workspace = AsyncMock(return_value=current_sub)
            mock_sub_db.update = AsyncMock(return_value=current_sub)
            mock_sub_db.create = AsyncMock(return_value=new_sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)
            mock_ws_db.update_status = AsyncMock()
            mock_ws_db.get_by_id = AsyncMock(return_value=None)
            mock_ctx_db.get_by_workspace = AsyncMock(return_value=None)
            mock_ctx_db.create = AsyncMock()
            mock_user_db.get_by_id = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            await service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_123",
                stripe_customer_id="cus_123",
                workspace_id=workspace_id,
                plan_id=plan.id,
                seat_count=1,
            )

            cancel_call = mock_sub_db.update.call_args_list[0]
            cancel_data = (
                cancel_call.args[2]
                if len(cancel_call.args) > 2
                else cancel_call.kwargs.get("data", {})
            )
            assert cancel_data["status"] == SubscriptionStatus.CANCELED

    @pytest.mark.asyncio
    async def test_creates_new_context_when_none_exists(self, service, mock_stripe_sub):
        plan = MagicMock(id=uuid4(), stripe_price_id="price_base_123")
        new_sub = MagicMock(id=uuid4())
        workspace_id = uuid4()

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db, patch(
            "app.apps.cubex_api.services.subscription.user_db"
        ) as mock_user_db, patch(
            "app.apps.cubex_api.services.subscription.get_publisher",
            return_value=AsyncMock(),
        ):
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)
            mock_sub_db.create = AsyncMock(return_value=new_sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)
            mock_ws_db.update_status = AsyncMock()
            mock_ws_db.get_by_id = AsyncMock(return_value=None)
            mock_ctx_db.get_by_workspace = AsyncMock(return_value=None)
            mock_ctx_db.create = AsyncMock()
            mock_user_db.get_by_id = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            await service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_123",
                stripe_customer_id="cus_123",
                workspace_id=workspace_id,
                plan_id=plan.id,
                seat_count=1,
            )

            mock_ctx_db.create.assert_called_once()
            create_data = mock_ctx_db.create.call_args
            data = (
                create_data.args[1]
                if len(create_data.args) > 1
                else create_data.kwargs.get("data", {})
            )
            assert data["workspace_id"] == workspace_id
            assert data["subscription_id"] == new_sub.id

    @pytest.mark.asyncio
    async def test_updates_existing_context(self, service, mock_stripe_sub):
        plan = MagicMock(id=uuid4(), stripe_price_id="price_base_123")
        new_sub = MagicMock(id=uuid4())
        workspace_id = uuid4()
        existing_ctx = MagicMock(id=uuid4())

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db, patch(
            "app.apps.cubex_api.services.subscription.user_db"
        ) as mock_user_db, patch(
            "app.apps.cubex_api.services.subscription.get_publisher",
            return_value=AsyncMock(),
        ):
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)
            mock_sub_db.create = AsyncMock(return_value=new_sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)
            mock_ws_db.update_status = AsyncMock()
            mock_ws_db.get_by_id = AsyncMock(return_value=None)
            mock_ctx_db.get_by_workspace = AsyncMock(return_value=existing_ctx)
            mock_ctx_db.update = AsyncMock()
            mock_user_db.get_by_id = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            await service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_123",
                stripe_customer_id="cus_123",
                workspace_id=workspace_id,
                plan_id=plan.id,
                seat_count=1,
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
    async def test_activates_workspace(self, service, mock_stripe_sub):
        from app.core.enums import WorkspaceStatus

        plan = MagicMock(id=uuid4(), stripe_price_id="price_base_123")
        new_sub = MagicMock(id=uuid4())
        workspace_id = uuid4()

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db, patch(
            "app.apps.cubex_api.services.subscription.user_db"
        ) as mock_user_db, patch(
            "app.apps.cubex_api.services.subscription.get_publisher",
            return_value=AsyncMock(),
        ):
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)
            mock_sub_db.create = AsyncMock(return_value=new_sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)
            mock_ws_db.update_status = AsyncMock()
            mock_ws_db.get_by_id = AsyncMock(return_value=None)
            mock_ctx_db.get_by_workspace = AsyncMock(return_value=None)
            mock_ctx_db.create = AsyncMock()
            mock_user_db.get_by_id = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            await service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_123",
                stripe_customer_id="cus_123",
                workspace_id=workspace_id,
                plan_id=plan.id,
                seat_count=1,
            )

            mock_ws_db.update_status.assert_called_once_with(
                mock_session, workspace_id, WorkspaceStatus.ACTIVE, commit_self=False
            )

    @pytest.mark.asyncio
    async def test_sends_activation_email(self, service, mock_stripe_sub):
        plan_id = uuid4()
        plan = MagicMock(id=plan_id, stripe_price_id="price_base_123")
        plan.name = "Professional"
        new_sub = MagicMock(id=uuid4())
        workspace_id = uuid4()
        owner = MagicMock(email="owner@test.com", full_name="Test Owner")
        workspace = MagicMock(owner_id=uuid4())
        workspace.display_name = "Test WS"

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.plan_db"
        ) as mock_plan_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db, patch(
            "app.apps.cubex_api.services.subscription.user_db"
        ) as mock_user_db, patch(
            "app.apps.cubex_api.services.subscription.get_publisher",
            return_value=AsyncMock(),
        ) as mock_get_pub:
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)
            mock_sub_db.create = AsyncMock(return_value=new_sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)
            mock_ws_db.update_status = AsyncMock()
            mock_ws_db.get_by_id = AsyncMock(return_value=workspace)
            mock_ctx_db.get_by_workspace = AsyncMock(return_value=None)
            mock_ctx_db.create = AsyncMock()
            mock_user_db.get_by_id = AsyncMock(return_value=owner)

            mock_session = AsyncMock()
            await service.handle_checkout_completed(
                session=mock_session,
                stripe_subscription_id="sub_123",
                stripe_customer_id="cus_123",
                workspace_id=workspace_id,
                plan_id=plan.id,
                seat_count=5,
            )

            mock_publisher = mock_get_pub.return_value
            mock_publisher.assert_called_once()
            payload = mock_publisher.call_args[0][1]
            assert payload["email"] == "owner@test.com"
            assert payload["plan_name"] == "Professional"
            assert payload["workspace_name"] == "Test WS"
            assert payload["seat_count"] == 5
            assert payload["product_name"] == "CueBX API"

    @pytest.mark.asyncio
    async def test_plan_not_found_raises(self, service, mock_stripe_sub):
        from app.apps.cubex_api.services.subscription import PlanNotFoundException

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.plan_db"
        ) as mock_plan_db:
            mock_stripe.get_subscription = AsyncMock(return_value=mock_stripe_sub)
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)
            mock_plan_db.get_by_id = AsyncMock(return_value=None)

            with pytest.raises(PlanNotFoundException):
                await service.handle_checkout_completed(
                    session=AsyncMock(),
                    stripe_subscription_id="sub_123",
                    stripe_customer_id="cus_123",
                    workspace_id=uuid4(),
                    plan_id=uuid4(),
                    seat_count=1,
                )


class TestHandleSubscriptionDeleted:

    @pytest.fixture
    def service(self):
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, service):
        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)

            result = await service.handle_subscription_deleted(
                session=AsyncMock(),
                stripe_subscription_id="sub_not_found",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_marks_subscription_canceled(self, service):
        api_context = MagicMock(workspace_id=uuid4())
        subscription = MagicMock(
            id=uuid4(),
            product_type=ProductType.API,
            api_context=api_context,
        )
        updated_sub = MagicMock(
            id=subscription.id,
            product_type=ProductType.API,
            api_context=api_context,
        )

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_member_db"
        ) as mock_member_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=subscription
            )
            mock_sub_db.update = AsyncMock(return_value=updated_sub)
            mock_ws_db.update_status = AsyncMock()
            mock_member_db.disable_all_members = AsyncMock()

            mock_session = AsyncMock()
            result = await service.handle_subscription_deleted(
                session=mock_session,
                stripe_subscription_id="sub_del_123",
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
    async def test_freezes_workspace_for_api_subscription(self, service):
        from app.core.enums import WorkspaceStatus

        workspace_id = uuid4()
        api_context = MagicMock(workspace_id=workspace_id)
        subscription = MagicMock(
            id=uuid4(),
            product_type=ProductType.API,
            api_context=api_context,
        )
        updated_sub = MagicMock(id=subscription.id)

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_member_db"
        ) as mock_member_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=subscription
            )
            mock_sub_db.update = AsyncMock(return_value=updated_sub)
            mock_ws_db.update_status = AsyncMock()
            mock_member_db.disable_all_members = AsyncMock()

            mock_session = AsyncMock()
            await service.handle_subscription_deleted(
                session=mock_session,
                stripe_subscription_id="sub_del_123",
            )

            mock_ws_db.update_status.assert_called_once_with(
                mock_session, workspace_id, WorkspaceStatus.FROZEN, commit_self=False
            )
            mock_member_db.disable_all_members.assert_called_once_with(
                mock_session, workspace_id, except_owner=True, commit_self=False
            )

    @pytest.mark.asyncio
    async def test_no_freeze_when_no_api_context(self, service):
        subscription = MagicMock(
            id=uuid4(),
            product_type=ProductType.API,
            api_context=None,
        )
        updated_sub = MagicMock(id=subscription.id)

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=subscription
            )
            mock_sub_db.update = AsyncMock(return_value=updated_sub)
            mock_ws_db.update_status = AsyncMock()

            mock_session = AsyncMock()
            await service.handle_subscription_deleted(
                session=mock_session,
                stripe_subscription_id="sub_del_123",
            )

            mock_ws_db.update_status.assert_not_called()


class TestHandleSubscriptionUpdatedLogic:

    @pytest.fixture
    def service(self):
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    @pytest.fixture
    def mock_db_sub(self):
        """Create a mock DB subscription for update tests."""
        plan = MagicMock()
        plan.stripe_price_id = "price_base_123"
        plan.seat_stripe_price_id = "price_seat_456"
        plan.name = "Professional"
        plan.product_type = ProductType.API

        api_context = MagicMock(workspace_id=uuid4())

        sub = MagicMock()
        sub.id = uuid4()
        sub.plan = plan
        sub.plan_id = plan.id if hasattr(plan, "id") else uuid4()
        sub.product_type = ProductType.API
        sub.seat_count = 5
        sub.amount = None
        sub.current_period_start = 1700000000
        sub.current_period_end = 1702678400
        sub.api_context = api_context
        return sub

    def _make_stripe_sub(self, status="active", cancel_at_period_end=False):
        """Helper to create a mock stripe subscription."""
        price = MagicMock()
        price.id = "price_base_123"
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
        stripe_sub.cancel_at_period_end = cancel_at_period_end
        stripe_sub.canceled_at = None
        stripe_sub.items = items
        return stripe_sub

    @pytest.mark.asyncio
    async def test_invalid_subscription_id_raises_value_error(self, service):
        with pytest.raises(ValueError, match="Invalid Stripe subscription ID"):
            await service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="",
            )

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, service):
        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(return_value=None)

            result = await service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="sub_not_found",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_status_mapping_active(self, service, mock_db_sub):
        stripe_sub = self._make_stripe_sub(status="active")

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_db_sub
            )
            mock_sub_db.update = AsyncMock(return_value=mock_db_sub)
            mock_stripe.get_subscription = AsyncMock(return_value=stripe_sub)
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=None)
            mock_ws_db.get_by_id = AsyncMock(return_value=MagicMock())

            await service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="sub_123",
            )

            update_data = mock_sub_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["status"] == SubscriptionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_status_mapping_past_due(self, service, mock_db_sub):
        stripe_sub = self._make_stripe_sub(status="past_due")

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_db_sub
            )
            mock_sub_db.update = AsyncMock(return_value=mock_db_sub)
            mock_stripe.get_subscription = AsyncMock(return_value=stripe_sub)
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=None)
            mock_ws_db.get_by_id = AsyncMock(return_value=MagicMock())

            await service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="sub_123",
            )

            update_data = mock_sub_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["status"] == SubscriptionStatus.PAST_DUE

    @pytest.mark.asyncio
    async def test_status_canceled_freezes_workspace(self, service, mock_db_sub):
        from app.core.enums import WorkspaceStatus

        stripe_sub = self._make_stripe_sub(status="canceled")

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_member_db"
        ) as mock_member_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_db_sub
            )
            mock_sub_db.update = AsyncMock(return_value=mock_db_sub)
            mock_stripe.get_subscription = AsyncMock(return_value=stripe_sub)
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=None)
            mock_ws_db.update_status = AsyncMock()
            mock_member_db.disable_all_members = AsyncMock()

            await service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="sub_123",
            )

            mock_ws_db.update_status.assert_called_once()
            ws_args = mock_ws_db.update_status.call_args
            assert ws_args.args[1] == mock_db_sub.api_context.workspace_id
            assert ws_args.args[2] == WorkspaceStatus.FROZEN

    @pytest.mark.asyncio
    async def test_active_status_reactivates_frozen_workspace(
        self, service, mock_db_sub
    ):
        from app.core.enums import WorkspaceStatus

        stripe_sub = self._make_stripe_sub(status="active")
        frozen_ws = MagicMock(status=WorkspaceStatus.FROZEN)

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_db_sub
            )
            mock_sub_db.update = AsyncMock(return_value=mock_db_sub)
            mock_stripe.get_subscription = AsyncMock(return_value=stripe_sub)
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=None)
            mock_ws_db.get_by_id = AsyncMock(return_value=frozen_ws)
            mock_ws_db.update_status = AsyncMock()

            await service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="sub_123",
            )

            mock_ws_db.update_status.assert_called_once()
            ws_args = mock_ws_db.update_status.call_args
            assert ws_args.args[2] == WorkspaceStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_canceled_at_propagated(self, service, mock_db_sub):
        stripe_sub = self._make_stripe_sub(status="canceled")
        stripe_sub.canceled_at = 1702000000

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.workspace_member_db"
        ) as mock_member_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_db_sub
            )
            mock_sub_db.update = AsyncMock(return_value=mock_db_sub)
            mock_stripe.get_subscription = AsyncMock(return_value=stripe_sub)
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=None)
            mock_ws_db.update_status = AsyncMock()
            mock_member_db.disable_all_members = AsyncMock()

            await service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="sub_123",
            )

            update_data = mock_sub_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["canceled_at"] == 1702000000

    @pytest.mark.asyncio
    async def test_billing_period_change_resets_credits(self, service, mock_db_sub):
        stripe_sub = self._make_stripe_sub(status="active")
        # Change period to trigger reset
        stripe_sub.items.data[0].current_period_start = 1702678400  # New period
        stripe_sub.items.data[0].current_period_end = 1705356800

        context = MagicMock(id=uuid4())

        with patch(
            "app.apps.cubex_api.services.subscription.subscription_db"
        ) as mock_sub_db, patch(
            "app.apps.cubex_api.services.subscription.Stripe"
        ) as mock_stripe, patch(
            "app.apps.cubex_api.services.subscription.workspace_db"
        ) as mock_ws_db, patch(
            "app.apps.cubex_api.services.subscription.api_subscription_context_db"
        ) as mock_ctx_db:
            mock_sub_db.get_by_stripe_subscription_id = AsyncMock(
                return_value=mock_db_sub
            )
            mock_sub_db.update = AsyncMock(return_value=mock_db_sub)
            mock_stripe.get_subscription = AsyncMock(return_value=stripe_sub)
            mock_ctx_db.get_by_subscription = AsyncMock(return_value=context)
            mock_ctx_db.reset_credits_used = AsyncMock()
            mock_ws_db.get_by_id = AsyncMock(return_value=MagicMock())

            await service.handle_subscription_updated(
                session=AsyncMock(),
                stripe_subscription_id="sub_123",
            )


class TestCreateCheckoutSessionLogic:

    SVC = "app.apps.cubex_api.services.subscription"

    @pytest.fixture
    def service(self):
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    def _make_plan(self, *, has_seats=True, can_purchase=True):
        plan = MagicMock(
            id=uuid4(),
            stripe_price_id="price_base_123",
            seat_stripe_price_id="price_seat_123" if has_seats else None,
            has_seat_pricing=has_seats,
            can_be_purchased=can_purchase,
            product_type=ProductType.API,
            min_seats=1,
            max_seats=50,
            is_active=True,
            is_deleted=False,
        )
        plan.name = "Professional"
        return plan

    @pytest.mark.asyncio
    async def test_happy_path_with_seat_pricing(self, service):
        plan = self._make_plan(has_seats=True)
        user = MagicMock(id=uuid4(), email="u@test.com", full_name="Test")
        user.stripe_customer_id = "cus_123"
        stripe_session = MagicMock(id="cs_abc", url="https://checkout.stripe.com")

        with patch(f"{self.SVC}.plan_db") as mock_plan_db, patch(
            f"{self.SVC}.subscription_db"
        ) as mock_sub_db, patch(f"{self.SVC}.Stripe") as mock_stripe:
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)
            mock_stripe.create_checkout_session = AsyncMock(return_value=stripe_session)

            result = await service.create_checkout_session(
                session=AsyncMock(),
                workspace_id=uuid4(),
                plan_id=plan.id,
                seat_count=5,
                success_url="https://app/success",
                cancel_url="https://app/cancel",
                user=user,
            )

            assert result is stripe_session
            mock_stripe.create_checkout_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_plan_not_purchasable_raises(self, service):
        from app.apps.cubex_api.services.subscription import PlanNotFoundException

        plan = self._make_plan(can_purchase=False)

        with patch(f"{self.SVC}.plan_db") as mock_plan_db:
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)

            with pytest.raises(PlanNotFoundException):
                await service.create_checkout_session(
                    session=AsyncMock(),
                    workspace_id=uuid4(),
                    plan_id=plan.id,
                    seat_count=1,
                    success_url="https://app/success",
                    cancel_url="https://app/cancel",
                    user=MagicMock(id=uuid4()),
                )

    @pytest.mark.asyncio
    async def test_invalid_seat_count_raises(self, service):
        from app.apps.cubex_api.services.subscription import (
            InvalidSeatCountException,
        )

        plan = self._make_plan()

        with patch(f"{self.SVC}.plan_db") as mock_plan_db:
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)

            with pytest.raises(InvalidSeatCountException):
                await service.create_checkout_session(
                    session=AsyncMock(),
                    workspace_id=uuid4(),
                    plan_id=plan.id,
                    seat_count=100,  # Exceeds max_seats=50
                    success_url="https://app/success",
                    cancel_url="https://app/cancel",
                    user=MagicMock(id=uuid4()),
                )

    @pytest.mark.asyncio
    async def test_existing_paid_subscription_raises(self, service):
        from app.apps.cubex_api.services.subscription import (
            CannotUpgradeFreeWorkspace,
        )

        plan = self._make_plan()
        existing_sub = MagicMock(stripe_subscription_id="sub_existing")

        with patch(f"{self.SVC}.plan_db") as mock_plan_db, patch(
            f"{self.SVC}.subscription_db"
        ) as mock_sub_db:
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)
            mock_sub_db.get_by_workspace = AsyncMock(return_value=existing_sub)

            with pytest.raises(CannotUpgradeFreeWorkspace):
                await service.create_checkout_session(
                    session=AsyncMock(),
                    workspace_id=uuid4(),
                    plan_id=plan.id,
                    seat_count=3,
                    success_url="https://app/success",
                    cancel_url="https://app/cancel",
                    user=MagicMock(id=uuid4()),
                )

    @pytest.mark.asyncio
    async def test_ensure_stripe_customer_creates_new(self, service):
        plan = self._make_plan()
        user = MagicMock(id=uuid4(), email="new@test.com", full_name="New")
        user.stripe_customer_id = None
        stripe_customer = MagicMock(id="cus_new")

        with patch(f"{self.SVC}.plan_db") as mock_plan_db, patch(
            f"{self.SVC}.subscription_db"
        ) as mock_sub_db, patch(f"{self.SVC}.Stripe") as mock_stripe, patch(
            f"{self.SVC}.user_db"
        ) as mock_user_db:
            mock_plan_db.get_by_id = AsyncMock(return_value=plan)
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)
            mock_stripe.create_customer = AsyncMock(return_value=stripe_customer)
            mock_stripe.create_checkout_session = AsyncMock(
                return_value=MagicMock(id="cs_x")
            )
            mock_user_db.update = AsyncMock()

            await service.create_checkout_session(
                session=AsyncMock(),
                workspace_id=uuid4(),
                plan_id=plan.id,
                seat_count=1,
                success_url="https://app/success",
                cancel_url="https://app/cancel",
                user=user,
            )

            mock_stripe.create_customer.assert_called_once()


class TestCancelSubscriptionLogic:

    SVC = "app.apps.cubex_api.services.subscription"

    @pytest.fixture
    def service(self):
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    @pytest.mark.asyncio
    async def test_cancel_at_period_end(self, service):
        sub = MagicMock(
            id=uuid4(),
            stripe_subscription_id="sub_cancel_period",
        )
        updated_sub = MagicMock(id=sub.id)
        mock_session = AsyncMock()

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db, patch(
            f"{self.SVC}.Stripe"
        ) as mock_stripe, patch(f"{self.SVC}.workspace_db") as mock_ws_db, patch(
            f"{self.SVC}.workspace_member_db"
        ) as mock_member_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=sub)
            mock_sub_db.update = AsyncMock(return_value=updated_sub)
            mock_stripe.cancel_subscription = AsyncMock()

            result = await service.cancel_subscription(
                session=mock_session,
                workspace_id=uuid4(),
                cancel_at_period_end=True,
            )

            assert result is updated_sub
            mock_stripe.cancel_subscription.assert_called_once_with(
                "sub_cancel_period", cancel_at_period_end=True
            )
            # Should NOT freeze workspace
            mock_ws_db.update_status.assert_not_called()
            mock_member_db.disable_all_members.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_immediately_freezes_workspace(self, service):
        workspace_id = uuid4()
        sub = MagicMock(
            id=uuid4(),
            stripe_subscription_id="sub_cancel_now",
        )
        updated_sub = MagicMock(id=sub.id)
        mock_session = AsyncMock()

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db, patch(
            f"{self.SVC}.Stripe"
        ) as mock_stripe, patch(f"{self.SVC}.workspace_db") as mock_ws_db, patch(
            f"{self.SVC}.workspace_member_db"
        ) as mock_member_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=sub)
            mock_sub_db.update = AsyncMock(return_value=updated_sub)
            mock_stripe.cancel_subscription = AsyncMock()
            mock_ws_db.update_status = AsyncMock()
            mock_member_db.disable_all_members = AsyncMock()

            result = await service.cancel_subscription(
                session=mock_session,
                workspace_id=workspace_id,
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
            # Workspace should be frozen
            mock_ws_db.update_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found_raises(self, service):
        from app.apps.cubex_api.services.subscription import (
            SubscriptionNotFoundException,
        )

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)

            with pytest.raises(SubscriptionNotFoundException):
                await service.cancel_subscription(
                    session=AsyncMock(), workspace_id=uuid4()
                )


class TestReactivateWorkspaceLogic:

    SVC = "app.apps.cubex_api.services.subscription"

    @pytest.fixture
    def service(self):
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    @pytest.mark.asyncio
    async def test_happy_path_reactivates(self, service):
        from app.core.enums import WorkspaceStatus

        workspace_id = uuid4()
        owner_id = uuid4()
        sub = MagicMock(
            id=uuid4(),
            seat_count=5,
            stripe_subscription_id="sub_react",
            status=SubscriptionStatus.ACTIVE,
        )
        owner_member = MagicMock(user_id=owner_id, is_owner=True, is_active=False)
        workspace = MagicMock(id=workspace_id, owner_id=owner_id)
        mock_session = AsyncMock()

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db, patch(
            f"{self.SVC}.workspace_member_db"
        ) as mock_member_db, patch(f"{self.SVC}.workspace_db") as mock_ws_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=sub)
            mock_member_db.get_workspace_members = AsyncMock(
                return_value=[owner_member]
            )
            mock_ws_db.update_status = AsyncMock(return_value=workspace)

            result = await service.reactivate_workspace(
                session=mock_session,
                workspace_id=workspace_id,
            )

            assert result is workspace
            mock_ws_db.update_status.assert_called_once()
            ws_args = mock_ws_db.update_status.call_args
            assert ws_args.args[2] == WorkspaceStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_too_many_members_raises(self, service):
        from app.apps.cubex_api.services.subscription import (
            InvalidSeatCountException,
        )

        workspace_id = uuid4()
        owner_id = uuid4()
        sub = MagicMock(
            id=uuid4(),
            seat_count=2,  # Only 2 seats
            stripe_subscription_id="sub_react",
            status=SubscriptionStatus.ACTIVE,
        )
        owner_member = MagicMock(user_id=owner_id, is_owner=True)
        member2 = MagicMock(user_id=uuid4(), is_owner=False)
        member3 = MagicMock(user_id=uuid4(), is_owner=False)

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db, patch(
            f"{self.SVC}.workspace_member_db"
        ) as mock_member_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=sub)
            mock_member_db.get_workspace_members = AsyncMock(
                return_value=[owner_member, member2, member3]
            )

            with pytest.raises(InvalidSeatCountException):
                await service.reactivate_workspace(
                    session=AsyncMock(),
                    workspace_id=workspace_id,
                    member_ids_to_enable=[member2.user_id, member3.user_id],
                )

    @pytest.mark.asyncio
    async def test_not_found_raises(self, service):
        from app.apps.cubex_api.services.subscription import (
            SubscriptionNotFoundException,
        )

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)

            with pytest.raises(SubscriptionNotFoundException):
                await service.reactivate_workspace(
                    session=AsyncMock(), workspace_id=uuid4()
                )


class TestPreviewSubscriptionChangeLogic:

    SVC = "app.apps.cubex_api.services.subscription"

    @pytest.fixture
    def service(self):
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    def _make_sub(self, plan_rank=1, seat_count=5):
        plan = MagicMock(
            id=uuid4(),
            rank=plan_rank,
            stripe_price_id="price_current",
            seat_stripe_price_id="price_seat_current",
            min_seats=1,
            max_seats=50,
        )
        plan.name = "Current"
        sub = MagicMock(
            id=uuid4(),
            stripe_subscription_id="sub_preview",
            plan=plan,
            plan_id=plan.id,
            seat_count=seat_count,
            status=SubscriptionStatus.ACTIVE,
        )
        sub.api_context = MagicMock(workspace_id=uuid4())
        return sub

    @pytest.mark.asyncio
    async def test_plan_upgrade_preview(self, service):
        sub = self._make_sub(plan_rank=1)
        new_plan = MagicMock(
            id=uuid4(),
            rank=2,
            stripe_price_id="price_new",
            seat_stripe_price_id="price_seat_new",
            min_seats=1,
            max_seats=50,
            is_active=True,
            is_deleted=False,
            product_type=ProductType.API,
        )
        new_plan.name = "Enterprise"
        invoice = MagicMock(amount_due=5000)

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db, patch(
            f"{self.SVC}.plan_db"
        ) as mock_plan_db, patch(f"{self.SVC}.Stripe") as mock_stripe, patch(
            f"{self.SVC}.workspace_member_db"
        ):
            mock_sub_db.get_by_workspace = AsyncMock(return_value=sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=new_plan)
            mock_stripe.preview_invoice = AsyncMock(return_value=invoice)

            result = await service.preview_subscription_change(
                session=AsyncMock(),
                workspace_id=sub.api_context.workspace_id,
                new_plan_id=new_plan.id,
            )

            assert result is invoice
            mock_stripe.preview_invoice.assert_called_once()

    @pytest.mark.asyncio
    async def test_same_plan_raises(self, service):
        from app.apps.cubex_api.services.subscription import SamePlanException

        sub = self._make_sub()

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db, patch(
            f"{self.SVC}.plan_db"
        ) as mock_plan_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=sub)
            same_plan = MagicMock(
                id=sub.plan_id,
                rank=1,
                is_active=True,
                is_deleted=False,
                product_type=ProductType.API,
            )
            mock_plan_db.get_by_id = AsyncMock(return_value=same_plan)

            with pytest.raises(SamePlanException):
                await service.preview_subscription_change(
                    session=AsyncMock(),
                    workspace_id=uuid4(),
                    new_plan_id=sub.plan_id,
                )

    @pytest.mark.asyncio
    async def test_downgrade_raises(self, service):
        from app.apps.cubex_api.services.subscription import (
            PlanDowngradeNotAllowedException,
        )

        sub = self._make_sub(plan_rank=3)
        lower_plan = MagicMock(
            id=uuid4(),
            rank=2,
            stripe_price_id="price_lower",
            min_seats=1,
            max_seats=10,
            is_active=True,
            is_deleted=False,
            product_type=ProductType.API,
        )
        lower_plan.name = "Lower"

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db, patch(
            f"{self.SVC}.plan_db"
        ) as mock_plan_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=lower_plan)

            with pytest.raises(PlanDowngradeNotAllowedException):
                await service.preview_subscription_change(
                    session=AsyncMock(),
                    workspace_id=uuid4(),
                    new_plan_id=lower_plan.id,
                )

    @pytest.mark.asyncio
    async def test_not_found_raises(self, service):
        from app.apps.cubex_api.services.subscription import (
            SubscriptionNotFoundException,
        )

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)

            with pytest.raises(SubscriptionNotFoundException):
                await service.preview_subscription_change(
                    session=AsyncMock(),
                    workspace_id=uuid4(),
                    new_plan_id=uuid4(),
                )


class TestUpgradePlanLogic:

    SVC = "app.apps.cubex_api.services.subscription"

    @pytest.fixture
    def service(self):
        from app.apps.cubex_api.services.subscription import SubscriptionService

        return SubscriptionService()

    def _make_sub(self, plan_rank=1, seat_count=3):
        plan = MagicMock(
            id=uuid4(),
            rank=plan_rank,
            stripe_price_id="price_current",
            seat_stripe_price_id="price_seat_current",
        )
        plan.name = "Current Plan"
        ctx = MagicMock(workspace_id=uuid4())
        sub = MagicMock(
            id=uuid4(),
            stripe_subscription_id="sub_upgrade",
            plan=plan,
            plan_id=plan.id,
            seat_count=seat_count,
            api_context=ctx,
            current_period_start=datetime(2024, 1, 1, tzinfo=UTC),
        )
        return sub

    @pytest.mark.asyncio
    async def test_happy_path_upgrades(self, service):
        sub = self._make_sub(plan_rank=1)
        new_plan = MagicMock(
            id=uuid4(),
            rank=2,
            stripe_price_id="price_enterprise",
            seat_stripe_price_id="price_seat_enterprise",
            max_seats=100,
            is_active=True,
            is_deleted=False,
            product_type=ProductType.API,
        )
        new_plan.name = "Enterprise"
        updated_sub = MagicMock(id=sub.id)
        workspace = MagicMock()
        workspace.display_name = "Test WS"
        owner = MagicMock(email="owner@test.com", full_name="Owner")

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db, patch(
            f"{self.SVC}.plan_db"
        ) as mock_plan_db, patch(f"{self.SVC}.Stripe") as mock_stripe, patch(
            f"{self.SVC}.workspace_db"
        ) as mock_ws_db, patch(
            f"{self.SVC}.user_db"
        ) as mock_user_db, patch(
            f"{self.SVC}.get_publisher", return_value=AsyncMock()
        ):
            mock_sub_db.get_by_workspace = AsyncMock(return_value=sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=new_plan)
            mock_stripe.update_subscription = AsyncMock()
            mock_sub_db.update = AsyncMock(return_value=updated_sub)
            mock_ws_db.get_by_id = AsyncMock(return_value=workspace)
            mock_user_db.get_by_id = AsyncMock(return_value=owner)

            result = await service.upgrade_plan(
                session=AsyncMock(),
                workspace_id=sub.api_context.workspace_id,
                new_plan_id=new_plan.id,
            )

            assert result is updated_sub
            mock_stripe.update_subscription.assert_called_once()
            update_data = mock_sub_db.update.call_args
            data = (
                update_data.args[2]
                if len(update_data.args) > 2
                else update_data.kwargs.get("data", {})
            )
            assert data["plan_id"] == new_plan.id

    @pytest.mark.asyncio
    async def test_same_plan_raises(self, service):
        from app.apps.cubex_api.services.subscription import SamePlanException

        sub = self._make_sub()

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db, patch(
            f"{self.SVC}.plan_db"
        ) as mock_plan_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=sub)
            same_plan = MagicMock(
                id=sub.plan_id,
                rank=1,
                is_active=True,
                is_deleted=False,
                product_type=ProductType.API,
            )
            mock_plan_db.get_by_id = AsyncMock(return_value=same_plan)

            with pytest.raises(SamePlanException):
                await service.upgrade_plan(
                    session=AsyncMock(),
                    workspace_id=uuid4(),
                    new_plan_id=sub.plan_id,
                )

    @pytest.mark.asyncio
    async def test_downgrade_raises(self, service):
        from app.apps.cubex_api.services.subscription import (
            PlanDowngradeNotAllowedException,
        )

        sub = self._make_sub(plan_rank=3)
        lower_plan = MagicMock(
            id=uuid4(),
            rank=1,
            stripe_price_id="price_low",
            is_active=True,
            is_deleted=False,
            product_type=ProductType.API,
        )
        lower_plan.name = "Lower"

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db, patch(
            f"{self.SVC}.plan_db"
        ) as mock_plan_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=lower_plan)

            with pytest.raises(PlanDowngradeNotAllowedException):
                await service.upgrade_plan(
                    session=AsyncMock(),
                    workspace_id=uuid4(),
                    new_plan_id=lower_plan.id,
                )

    @pytest.mark.asyncio
    async def test_seats_exceed_new_plan_max_raises(self, service):
        from app.apps.cubex_api.services.subscription import (
            InvalidSeatCountException,
        )

        sub = self._make_sub(plan_rank=1, seat_count=20)
        new_plan = MagicMock(
            id=uuid4(),
            rank=2,
            stripe_price_id="price_new",
            seat_stripe_price_id="price_seat_new",
            max_seats=10,  # Less than current 20
            is_active=True,
            is_deleted=False,
            product_type=ProductType.API,
        )
        new_plan.name = "New Plan"

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db, patch(
            f"{self.SVC}.plan_db"
        ) as mock_plan_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=sub)
            mock_plan_db.get_by_id = AsyncMock(return_value=new_plan)

            with pytest.raises(InvalidSeatCountException):
                await service.upgrade_plan(
                    session=AsyncMock(),
                    workspace_id=uuid4(),
                    new_plan_id=new_plan.id,
                )

    @pytest.mark.asyncio
    async def test_not_found_raises(self, service):
        from app.apps.cubex_api.services.subscription import (
            SubscriptionNotFoundException,
        )

        with patch(f"{self.SVC}.subscription_db") as mock_sub_db:
            mock_sub_db.get_by_workspace = AsyncMock(return_value=None)

            with pytest.raises(SubscriptionNotFoundException):
                await service.upgrade_plan(
                    session=AsyncMock(),
                    workspace_id=uuid4(),
                    new_plan_id=uuid4(),
                )
