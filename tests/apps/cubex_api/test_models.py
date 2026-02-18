"""
Test suite for Plan and Subscription models.

This module tests the Plan and Subscription SQLAlchemy models.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

# Import from core models which handles the import order correctly
from app.core.db.models import Workspace  # noqa: F401
from app.core.enums import PlanType, ProductType, SubscriptionStatus
from app.core.db.models.plan import Plan, FeatureSchema


class TestFeatureSchema:
    """Test suite for FeatureSchema Pydantic model."""

    def test_feature_schema_with_required_fields(self):
        """Test FeatureSchema with required title field."""
        features = FeatureSchema(title="API Access")

        assert features.title == "API Access"
        assert features.description is None
        assert features.value is None
        assert features.category is None

    def test_feature_schema_with_all_fields(self):
        """Test FeatureSchema with all fields."""
        features = FeatureSchema(
            title="Premium Support",
            description="24/7 support access",
            value=True,
            category="support",
        )

        assert features.title == "Premium Support"
        assert features.description == "24/7 support access"
        assert features.value is True
        assert features.category == "support"

    def test_feature_schema_to_dict(self):
        """Test FeatureSchema model_dump method."""
        features = FeatureSchema(title="API Access", value="unlimited")
        data = features.model_dump()

        assert isinstance(data, dict)
        assert data["title"] == "API Access"
        assert data["value"] == "unlimited"

    def test_feature_schema_from_dict(self):
        """Test creating FeatureSchema from dict."""
        data = {
            "title": "Storage",
            "description": "Cloud storage",
            "value": "10GB",
        }
        features = FeatureSchema(**data)

        assert features.title == "Storage"
        assert features.description == "Cloud storage"
        assert features.value == "10GB"

    def test_feature_schema_forbids_extra_fields(self):
        """Test that FeatureSchema forbids extra fields."""
        with pytest.raises(ValidationError):
            FeatureSchema(title="Test", unknown_field="value")


class TestPlanModel:
    """Test suite for Plan SQLAlchemy model."""

    def test_plan_attributes(self):
        """Test Plan model has expected attributes."""
        plan = Plan(
            name="Pro Plan",
            type=PlanType.PAID,
            product_type=ProductType.API,
            max_seats=50,
            min_seats=1,
            price=1999,  # $19.99
            stripe_price_id="price_test123",
            features=[{"title": "API access", "value": True}],
            is_active=True,
        )

        assert plan.name == "Pro Plan"
        assert plan.type == PlanType.PAID
        assert plan.product_type == ProductType.API
        assert plan.max_seats == 50
        assert plan.min_seats == 1
        assert plan.price == 1999
        assert plan.stripe_price_id == "price_test123"
        assert plan.is_active is True

    def test_plan_seat_pricing_attributes(self):
        """Test Plan model has seat pricing attributes."""
        plan = Plan(
            name="Professional",
            type=PlanType.PAID,
            product_type=ProductType.API,
            price=4900,  # $49.00 base price
            stripe_price_id="price_base_123",
            seat_price=500,  # $5.00 per seat
            seat_display_price="$5/seat/month",
            seat_stripe_price_id="price_seat_123",
            features=[{"title": "Unlimited seats"}],
            is_active=True,
        )

        assert plan.seat_price == 500
        assert plan.seat_display_price == "$5/seat/month"
        assert plan.seat_stripe_price_id == "price_seat_123"

    def test_plan_has_seat_pricing_property(self):
        """Test Plan has_seat_pricing property."""
        # Plan with seat pricing
        plan_with_seats = Plan(
            name="Professional",
            type=PlanType.PAID,
            product_type=ProductType.API,
            price=4900,
            stripe_price_id="price_base_123",
            seat_stripe_price_id="price_seat_123",
        )
        assert plan_with_seats.has_seat_pricing is True

        # Plan without seat pricing
        plan_without_seats = Plan(
            name="Basic",
            type=PlanType.PAID,
            product_type=ProductType.API,
            price=1900,
            stripe_price_id="price_base_456",
            seat_stripe_price_id=None,
        )
        assert plan_without_seats.has_seat_pricing is False

    def test_plan_can_be_purchased_with_seat_pricing_only(self):
        """Test Plan can_be_purchased works with seat pricing only."""
        # Plan with only seat stripe ID (no base stripe ID)
        plan = Plan(
            name="Seat Only",
            type=PlanType.PAID,
            product_type=ProductType.API,
            price=0,  # No base price
            stripe_price_id=None,
            seat_price=500,
            seat_stripe_price_id="price_seat_only",
            is_active=True,
        )
        assert plan.can_be_purchased is True

    def test_plan_free_tier_defaults(self):
        """Test Plan model for free tier has appropriate defaults."""
        plan = Plan(
            name="Free Plan",
            type=PlanType.FREE,
            max_seats=1,
            min_seats=1,
            price=0,
            is_active=True,
        )

        assert plan.name == "Free Plan"
        assert plan.type == PlanType.FREE
        assert plan.max_seats == 1
        assert plan.price == 0
        assert plan.stripe_price_id is None

    def test_plan_product_type_default(self):
        """Test Plan model product_type field.

        Note: Default values are applied by the database on INSERT,
        so we just verify the attribute exists and can be explicitly set.
        """
        plan = Plan(
            name="Default Plan",
            type=PlanType.FREE,
            price=0,
            product_type=ProductType.API,  # Explicitly set since default is at DB level
        )

        assert plan.product_type == ProductType.API

    def test_plan_product_type_career(self):
        """Test Plan model can be set to CAREER product type."""
        plan = Plan(
            name="Career Pro",
            type=PlanType.PAID,
            product_type=ProductType.CAREER,
            price=999,
        )

        assert plan.product_type == ProductType.CAREER

    def test_plan_has_product_type_attribute(self):
        """Test Plan model has product_type attribute."""
        plan = Plan()
        assert hasattr(plan, "product_type")


class TestSubscriptionModel:
    """Test suite for Subscription SQLAlchemy model."""

    def test_subscription_attributes(self):
        """Test Subscription model has expected attributes."""
        from app.core.db.models.subscription import Subscription

        plan_id = uuid4()

        subscription = Subscription(
            plan_id=plan_id,
            product_type=ProductType.API,
            status=SubscriptionStatus.ACTIVE,
            seat_count=5,
            stripe_subscription_id="sub_test123",
            stripe_customer_id="cus_test456",
        )

        assert subscription.plan_id == plan_id
        assert subscription.product_type == ProductType.API
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.seat_count == 5
        assert subscription.stripe_subscription_id == "sub_test123"
        assert subscription.stripe_customer_id == "cus_test456"

    def test_subscription_status_enum(self):
        """Test Subscription model uses correct status enum."""
        from app.core.db.models.subscription import Subscription

        subscription = Subscription(
            plan_id=uuid4(),
            product_type=ProductType.API,
            status=SubscriptionStatus.PAST_DUE,
        )

        assert subscription.status == SubscriptionStatus.PAST_DUE

    def test_subscription_product_type_default(self):
        """Test Subscription model product_type field.

        Note: Default values are applied by the database on INSERT,
        so we just verify the attribute exists and can be explicitly set.
        """
        from app.core.db.models.subscription import Subscription

        subscription = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.ACTIVE,
            product_type=ProductType.API,  # Explicitly set since default is at DB level
        )

        assert subscription.product_type == ProductType.API

    def test_subscription_product_type_career(self):
        """Test Subscription model can be set to CAREER product type."""
        from app.core.db.models.subscription import Subscription

        subscription = Subscription(
            plan_id=uuid4(),
            product_type=ProductType.CAREER,
            status=SubscriptionStatus.ACTIVE,
        )

        assert subscription.product_type == ProductType.CAREER

    def test_subscription_context_relationships(self):
        """Test Subscription model has context relationships."""
        from app.core.db.models.subscription import Subscription

        subscription = Subscription()

        assert hasattr(subscription, "api_context")
        assert hasattr(subscription, "career_context")

    def test_subscription_is_active_property(self):
        """Test Subscription is_active property."""
        from app.core.db.models.subscription import Subscription

        # Active subscription
        active_sub = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.ACTIVE,
        )
        assert active_sub.is_active is True

        # Trialing subscription
        trialing_sub = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.TRIALING,
        )
        assert trialing_sub.is_active is True

        # Canceled subscription
        canceled_sub = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.CANCELED,
        )
        assert canceled_sub.is_active is False

    def test_subscription_is_canceled_property(self):
        """Test Subscription is_canceled property."""
        from app.core.db.models.subscription import Subscription

        # Canceled subscription
        canceled_sub = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.CANCELED,
        )
        assert canceled_sub.is_canceled is True

        # Active subscription
        active_sub = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.ACTIVE,
        )
        assert active_sub.is_canceled is False

    def test_subscription_is_past_due_property(self):
        """Test Subscription is_past_due property."""
        from app.core.db.models.subscription import Subscription

        # Past due subscription
        past_due_sub = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.PAST_DUE,
        )
        assert past_due_sub.is_past_due is True

        # Unpaid subscription
        unpaid_sub = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.UNPAID,
        )
        assert unpaid_sub.is_past_due is True

        # Active subscription
        active_sub = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.ACTIVE,
        )
        assert active_sub.is_past_due is False

    def test_subscription_requires_action_property(self):
        """Test Subscription requires_action property."""
        from app.core.db.models.subscription import Subscription

        # Incomplete subscription
        incomplete_sub = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.INCOMPLETE,
        )
        assert incomplete_sub.requires_action is True

        # Past due subscription
        past_due_sub = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.PAST_DUE,
        )
        assert past_due_sub.requires_action is True

        # Active subscription
        active_sub = Subscription(
            plan_id=uuid4(),
            status=SubscriptionStatus.ACTIVE,
        )
        assert active_sub.requires_action is False


class TestStripeEventLogModel:
    """Test suite for StripeEventLog model."""

    def test_stripe_event_log_attributes(self):
        """Test StripeEventLog model has expected attributes."""
        from app.core.db.models.subscription import StripeEventLog

        event = StripeEventLog(
            event_id="evt_test123",
            event_type="checkout.session.completed",
            processed_at=datetime.now(timezone.utc),
        )

        assert event.event_id == "evt_test123"
        assert event.event_type == "checkout.session.completed"
        assert event.processed_at is not None
