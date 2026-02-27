"""
Integration tests for Career subscription router.

Tests all Career subscription endpoints with real database and per-test rollback.
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4
from unittest.mock import patch, AsyncMock

from app.core.enums import SubscriptionStatus


class TestListCareerPlans:

    @pytest.mark.asyncio
    async def test_list_career_plans_success(
        self, client: AsyncClient, free_career_plan
    ):
        response = await client.get("/career/subscriptions/plans")

        assert response.status_code == 200
        data = response.json()
        assert "plans" in data
        assert len(data["plans"]) >= 1

        plan = data["plans"][0]
        assert "id" in plan
        assert "name" in plan
        assert "price" in plan
        assert "features" in plan

    @pytest.mark.asyncio
    async def test_list_career_plans_includes_features(
        self, client: AsyncClient, free_career_plan
    ):
        response = await client.get("/career/subscriptions/plans")

        assert response.status_code == 200
        data = response.json()

        for plan in data["plans"]:
            assert "features" in plan
            assert isinstance(plan["features"], list)

    @pytest.mark.asyncio
    async def test_list_career_plans_unauthenticated(self, client: AsyncClient):
        response = await client.get("/career/subscriptions/plans")

        # Plans should be publicly accessible
        assert response.status_code == 200


class TestGetCareerPlan:

    @pytest.mark.asyncio
    async def test_get_career_plan_success(self, client: AsyncClient, plus_career_plan):
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
        fake_plan_id = uuid4()
        response = await client.get(f"/career/subscriptions/plans/{fake_plan_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_career_plan_free_tier(
        self, client: AsyncClient, free_career_plan
    ):
        response = await client.get(
            f"/career/subscriptions/plans/{free_career_plan.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Free"


class TestGetMyCareerSubscription:

    @pytest.mark.asyncio
    async def test_get_career_subscription_success(
        self, authenticated_client: AsyncClient, career_subscription
    ):
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
        response = await authenticated_client.get("/career/subscriptions")

        assert response.status_code == 200
        data = response.json()
        # No subscription returns null
        assert data is None

    @pytest.mark.asyncio
    async def test_get_career_subscription_unauthenticated(self, client: AsyncClient):
        response = await client.get("/career/subscriptions")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_career_subscription_includes_plan(
        self, authenticated_client: AsyncClient, career_subscription
    ):
        response = await authenticated_client.get("/career/subscriptions")

        assert response.status_code == 200
        data = response.json()
        assert "plan" in data
        assert data["plan"] is not None
        assert "name" in data["plan"]
        assert "features" in data["plan"]


class TestCreateCareerCheckout:

    @pytest.mark.asyncio
    async def test_create_career_checkout_unauthenticated(
        self, client: AsyncClient, plus_career_plan
    ):
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
        payload = {
            "plan_id": str(plus_career_plan.id),
            # Missing required URLs
        }
        response = await authenticated_client.post(
            "/career/subscriptions/checkout", json=payload
        )

        assert response.status_code == 422


class TestPreviewCareerUpgrade:

    @pytest.mark.asyncio
    async def test_preview_career_upgrade_unauthenticated(
        self, client: AsyncClient, pro_career_plan
    ):
        payload = {"new_plan_id": str(pro_career_plan.id)}
        response = await client.post(
            "/career/subscriptions/preview-upgrade", json=payload
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_preview_career_upgrade_no_subscription(
        self, authenticated_client: AsyncClient, pro_career_plan
    ):
        payload = {"new_plan_id": str(pro_career_plan.id)}
        response = await authenticated_client.post(
            "/career/subscriptions/preview-upgrade", json=payload
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_career_upgrade_invalid_plan(
        self, authenticated_client: AsyncClient, career_subscription
    ):
        fake_plan_id = uuid4()
        payload = {"new_plan_id": str(fake_plan_id)}
        response = await authenticated_client.post(
            "/career/subscriptions/preview-upgrade", json=payload
        )

        assert response.status_code == 404


class TestUpgradeCareerPlan:

    @pytest.mark.asyncio
    async def test_upgrade_career_plan_unauthenticated(
        self, client: AsyncClient, pro_career_plan
    ):
        payload = {"new_plan_id": str(pro_career_plan.id)}
        response = await client.post("/career/subscriptions/upgrade", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upgrade_career_plan_no_subscription(
        self, authenticated_client: AsyncClient, pro_career_plan
    ):
        payload = {"new_plan_id": str(pro_career_plan.id)}
        response = await authenticated_client.post(
            "/career/subscriptions/upgrade", json=payload
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upgrade_career_plan_invalid_plan(
        self, authenticated_client: AsyncClient, career_subscription
    ):
        fake_plan_id = uuid4()
        payload = {"new_plan_id": str(fake_plan_id)}
        response = await authenticated_client.post(
            "/career/subscriptions/upgrade", json=payload
        )

        assert response.status_code == 404


class TestCancelCareerSubscription:

    @pytest.mark.asyncio
    async def test_cancel_career_subscription_unauthenticated(
        self, client: AsyncClient
    ):
        payload = {"cancel_at_period_end": True}
        response = await client.post("/career/subscriptions/cancel", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_cancel_career_subscription_no_subscription(
        self, authenticated_client: AsyncClient
    ):
        payload = {"cancel_at_period_end": True}
        response = await authenticated_client.post(
            "/career/subscriptions/cancel", json=payload
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_career_subscription_at_period_end(
        self, authenticated_client: AsyncClient, paid_career_subscription
    ):
        payload = {"cancel_at_period_end": True}

        with patch(
            "app.apps.cubex_career.services.subscription.Stripe.cancel_subscription",
            new_callable=AsyncMock,
        ) as mock_cancel:
            response = await authenticated_client.post(
                "/career/subscriptions/cancel", json=payload
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "period" in data["message"].lower()
        mock_cancel.assert_called_once_with(
            paid_career_subscription.stripe_subscription_id,
            cancel_at_period_end=True,
        )

    @pytest.mark.asyncio
    async def test_cancel_career_subscription_immediately(
        self, authenticated_client: AsyncClient, paid_career_subscription
    ):
        payload = {"cancel_at_period_end": False}
        original_stripe_id = paid_career_subscription.stripe_subscription_id

        with patch(
            "app.apps.cubex_career.services.subscription.Stripe.cancel_subscription",
            new_callable=AsyncMock,
        ) as mock_cancel:
            response = await authenticated_client.post(
                "/career/subscriptions/cancel", json=payload
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "immediately" in data["message"].lower()
        mock_cancel.assert_called_once_with(
            original_stripe_id,
            cancel_at_period_end=False,
        )


class TestActivateCareerSubscription:

    @pytest.mark.asyncio
    async def test_activate_career_subscription_success(
        self, authenticated_client: AsyncClient
    ):
        response = await authenticated_client.post("/career/subscriptions/activate")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == SubscriptionStatus.ACTIVE.value
        assert "plan" in data

    @pytest.mark.asyncio
    async def test_activate_career_subscription_idempotent(
        self, authenticated_client: AsyncClient, career_subscription
    ):
        response = await authenticated_client.post("/career/subscriptions/activate")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(career_subscription.id)

    @pytest.mark.asyncio
    async def test_activate_career_subscription_unauthenticated(
        self, client: AsyncClient
    ):
        response = await client.post("/career/subscriptions/activate")

        assert response.status_code == 401


class TestCareerSubscriptionEdgeCases:

    @pytest.mark.asyncio
    async def test_invalid_uuid_format(self, client: AsyncClient):
        response = await client.get("/career/subscriptions/plans/not-a-uuid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_request_body(self, authenticated_client: AsyncClient):
        response = await authenticated_client.post(
            "/career/subscriptions/checkout", json={}
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_subscription_response_includes_period_info(
        self, authenticated_client: AsyncClient, career_subscription
    ):
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
        response = await client.get(
            f"/career/subscriptions/plans/{plus_career_plan.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert float(data["price"]) > 0
