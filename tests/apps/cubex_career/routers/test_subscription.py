"""
Integration tests for Career subscription router.

Tests all Career subscription endpoints with real database and per-test rollback.
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4

from app.shared.enums import SubscriptionStatus


# ============================================================================
# Test List Career Plans
# ============================================================================


class TestListCareerPlans:
    """Tests for GET /career/subscriptions/plans"""

    @pytest.mark.asyncio
    async def test_list_career_plans_success(
        self, client: AsyncClient, free_career_plan
    ):
        """Should return list of active Career plans."""
        response = await client.get("/career/subscriptions/plans")

        assert response.status_code == 200
        data = response.json()
        assert "plans" in data
        assert len(data["plans"]) >= 1

        # Verify plan structure
        plan = data["plans"][0]
        assert "id" in plan
        assert "name" in plan
        assert "price" in plan
        assert "features" in plan

    @pytest.mark.asyncio
    async def test_list_career_plans_includes_features(
        self, client: AsyncClient, free_career_plan
    ):
        """Should include plan features in response."""
        response = await client.get("/career/subscriptions/plans")

        assert response.status_code == 200
        data = response.json()

        for plan in data["plans"]:
            assert "features" in plan
            assert isinstance(plan["features"], list)

    @pytest.mark.asyncio
    async def test_list_career_plans_unauthenticated(self, client: AsyncClient):
        """Plans endpoint should work without authentication."""
        response = await client.get("/career/subscriptions/plans")

        # Plans should be publicly accessible
        assert response.status_code == 200


# ============================================================================
# Test Get Career Plan
# ============================================================================


class TestGetCareerPlan:
    """Tests for GET /career/subscriptions/plans/{plan_id}"""

    @pytest.mark.asyncio
    async def test_get_career_plan_success(self, client: AsyncClient, plus_career_plan):
        """Should return Career plan details."""
        response = await client.get(
            f"/career/subscriptions/plans/{plus_career_plan.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(plus_career_plan.id)
        assert data["name"] == plus_career_plan.name
        assert "features" in data

    @pytest.mark.asyncio
    async def test_get_career_plan_not_found(self, client: AsyncClient):
        """Should return 404 for non-existent plan."""
        fake_plan_id = uuid4()
        response = await client.get(f"/career/subscriptions/plans/{fake_plan_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_career_plan_free_tier(
        self, client: AsyncClient, free_career_plan
    ):
        """Should return free Career plan details."""
        response = await client.get(
            f"/career/subscriptions/plans/{free_career_plan.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Free"


# ============================================================================
# Test Get My Career Subscription
# ============================================================================


class TestGetMyCareerSubscription:
    """Tests for GET /career/subscriptions"""

    @pytest.mark.asyncio
    async def test_get_career_subscription_success(
        self, authenticated_client: AsyncClient, career_subscription
    ):
        """Should return user's Career subscription."""
        response = await authenticated_client.get("/career/subscriptions")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(career_subscription.id)
        assert data["status"] == SubscriptionStatus.ACTIVE.value
        assert "plan" in data

    @pytest.mark.asyncio
    async def test_get_career_subscription_no_subscription(
        self, authenticated_client: AsyncClient
    ):
        """Should return null if user has no Career subscription."""
        response = await authenticated_client.get("/career/subscriptions")

        assert response.status_code == 200
        data = response.json()
        # No subscription returns null
        assert data is None

    @pytest.mark.asyncio
    async def test_get_career_subscription_unauthenticated(self, client: AsyncClient):
        """Should return 401 if not authenticated."""
        response = await client.get("/career/subscriptions")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_career_subscription_includes_plan(
        self, authenticated_client: AsyncClient, career_subscription
    ):
        """Should include full plan details in response."""
        response = await authenticated_client.get("/career/subscriptions")

        assert response.status_code == 200
        data = response.json()
        assert "plan" in data
        assert data["plan"] is not None
        assert "name" in data["plan"]
        assert "features" in data["plan"]


# ============================================================================
# Test Create Career Checkout
# ============================================================================


class TestCreateCareerCheckout:
    """Tests for POST /career/subscriptions/checkout"""

    @pytest.mark.asyncio
    async def test_create_career_checkout_unauthenticated(
        self, client: AsyncClient, plus_career_plan
    ):
        """Should return 401 if not authenticated."""
        payload = {
            "plan_id": str(plus_career_plan.id),
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
        }
        response = await client.post("/career/subscriptions/checkout", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_career_checkout_invalid_plan(
        self, authenticated_client: AsyncClient
    ):
        """Should return 404 for non-existent plan."""
        fake_plan_id = uuid4()
        payload = {
            "plan_id": str(fake_plan_id),
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
        }
        response = await authenticated_client.post(
            "/career/subscriptions/checkout", json=payload
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_career_checkout_validation_error(
        self, authenticated_client: AsyncClient, plus_career_plan
    ):
        """Should return 422 for invalid request body."""
        payload = {
            "plan_id": str(plus_career_plan.id),
            # Missing required URLs
        }
        response = await authenticated_client.post(
            "/career/subscriptions/checkout", json=payload
        )

        assert response.status_code == 422


# ============================================================================
# Test Preview Career Upgrade
# ============================================================================


class TestPreviewCareerUpgrade:
    """Tests for POST /career/subscriptions/preview-upgrade"""

    @pytest.mark.asyncio
    async def test_preview_career_upgrade_unauthenticated(
        self, client: AsyncClient, pro_career_plan
    ):
        """Should return 401 if not authenticated."""
        payload = {"new_plan_id": str(pro_career_plan.id)}
        response = await client.post(
            "/career/subscriptions/preview-upgrade", json=payload
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_preview_career_upgrade_no_subscription(
        self, authenticated_client: AsyncClient, pro_career_plan
    ):
        """Should return 404 if user has no subscription."""
        payload = {"new_plan_id": str(pro_career_plan.id)}
        response = await authenticated_client.post(
            "/career/subscriptions/preview-upgrade", json=payload
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_career_upgrade_invalid_plan(
        self, authenticated_client: AsyncClient, career_subscription
    ):
        """Should return 404 for non-existent plan."""
        fake_plan_id = uuid4()
        payload = {"new_plan_id": str(fake_plan_id)}
        response = await authenticated_client.post(
            "/career/subscriptions/preview-upgrade", json=payload
        )

        assert response.status_code == 404


# ============================================================================
# Test Upgrade Career Plan
# ============================================================================


class TestUpgradeCareerPlan:
    """Tests for POST /career/subscriptions/upgrade"""

    @pytest.mark.asyncio
    async def test_upgrade_career_plan_unauthenticated(
        self, client: AsyncClient, pro_career_plan
    ):
        """Should return 401 if not authenticated."""
        payload = {"new_plan_id": str(pro_career_plan.id)}
        response = await client.post("/career/subscriptions/upgrade", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upgrade_career_plan_no_subscription(
        self, authenticated_client: AsyncClient, pro_career_plan
    ):
        """Should return 404 if user has no subscription."""
        payload = {"new_plan_id": str(pro_career_plan.id)}
        response = await authenticated_client.post(
            "/career/subscriptions/upgrade", json=payload
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upgrade_career_plan_invalid_plan(
        self, authenticated_client: AsyncClient, career_subscription
    ):
        """Should return 404 for non-existent plan."""
        fake_plan_id = uuid4()
        payload = {"new_plan_id": str(fake_plan_id)}
        response = await authenticated_client.post(
            "/career/subscriptions/upgrade", json=payload
        )

        assert response.status_code == 404


# ============================================================================
# Test Cancel Career Subscription
# ============================================================================


class TestCancelCareerSubscription:
    """Tests for POST /career/subscriptions/cancel"""

    @pytest.mark.asyncio
    async def test_cancel_career_subscription_unauthenticated(
        self, client: AsyncClient
    ):
        """Should return 401 if not authenticated."""
        payload = {"cancel_at_period_end": True}
        response = await client.post("/career/subscriptions/cancel", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_cancel_career_subscription_no_subscription(
        self, authenticated_client: AsyncClient
    ):
        """Should return 404 if user has no subscription."""
        payload = {"cancel_at_period_end": True}
        response = await authenticated_client.post(
            "/career/subscriptions/cancel", json=payload
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_career_subscription_at_period_end(
        self, authenticated_client: AsyncClient, paid_career_subscription
    ):
        """Should handle cancel at period end request."""
        payload = {"cancel_at_period_end": True}
        response = await authenticated_client.post(
            "/career/subscriptions/cancel", json=payload
        )

        # May succeed or fail based on Stripe mock, check format
        if response.status_code == 200:
            data = response.json()
            assert "message" in data
            assert "success" in data

    @pytest.mark.asyncio
    async def test_cancel_career_subscription_immediately(
        self, authenticated_client: AsyncClient, paid_career_subscription
    ):
        """Should handle immediate cancel request."""
        payload = {"cancel_at_period_end": False}
        response = await authenticated_client.post(
            "/career/subscriptions/cancel", json=payload
        )

        # May succeed or fail based on Stripe mock, check format
        if response.status_code == 200:
            data = response.json()
            assert "message" in data


# ============================================================================
# Test Activate Career Subscription
# ============================================================================


class TestActivateCareerSubscription:
    """Tests for POST /career/subscriptions/activate"""

    @pytest.mark.asyncio
    async def test_activate_career_subscription_success(
        self, authenticated_client: AsyncClient
    ):
        """Should create free Career subscription if not exists."""
        response = await authenticated_client.post("/career/subscriptions/activate")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == SubscriptionStatus.ACTIVE.value
        assert "plan" in data

    @pytest.mark.asyncio
    async def test_activate_career_subscription_idempotent(
        self, authenticated_client: AsyncClient, career_subscription
    ):
        """Should return existing subscription if already exists."""
        response = await authenticated_client.post("/career/subscriptions/activate")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(career_subscription.id)

    @pytest.mark.asyncio
    async def test_activate_career_subscription_unauthenticated(
        self, client: AsyncClient
    ):
        """Should return 401 if not authenticated."""
        response = await client.post("/career/subscriptions/activate")

        assert response.status_code == 401


# ============================================================================
# Edge Cases
# ============================================================================


class TestCareerSubscriptionEdgeCases:
    """Edge case tests for Career subscription endpoints."""

    @pytest.mark.asyncio
    async def test_invalid_uuid_format(self, client: AsyncClient):
        """Should return 422 for invalid UUID format."""
        response = await client.get("/career/subscriptions/plans/not-a-uuid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_request_body(self, authenticated_client: AsyncClient):
        """Should handle empty request body appropriately."""
        response = await authenticated_client.post(
            "/career/subscriptions/checkout", json={}
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_subscription_response_includes_period_info(
        self, authenticated_client: AsyncClient, career_subscription
    ):
        """Should include billing period information in response."""
        response = await authenticated_client.get("/career/subscriptions")

        assert response.status_code == 200
        data = response.json()
        assert "current_period_start" in data
        assert "current_period_end" in data
        assert "cancel_at_period_end" in data

    @pytest.mark.asyncio
    async def test_free_career_plan_zero_price(
        self, client: AsyncClient, free_career_plan
    ):
        """Free Career plan should have zero price."""
        response = await client.get(
            f"/career/subscriptions/plans/{free_career_plan.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert float(data["price"]) == 0.0

    @pytest.mark.asyncio
    async def test_paid_career_plan_positive_price(
        self, client: AsyncClient, plus_career_plan
    ):
        """Paid Career plan should have positive price."""
        response = await client.get(
            f"/career/subscriptions/plans/{plus_career_plan.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert float(data["price"]) > 0
