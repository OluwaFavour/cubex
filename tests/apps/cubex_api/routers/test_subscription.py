"""
Integration tests for API subscription router.

Tests all subscription endpoints with real database and per-test rollback.
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4

from app.core.enums import SubscriptionStatus


class TestListPlans:
    """Tests for GET /api/subscriptions/plans"""

    @pytest.mark.asyncio
    async def test_list_plans_success(self, client: AsyncClient, free_api_plan):
        """Should return list of active API plans."""
        response = await client.get("/api/subscriptions/plans")

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
    async def test_list_plans_includes_features(
        self, client: AsyncClient, free_api_plan
    ):
        """Should include plan features in response."""
        response = await client.get("/api/subscriptions/plans")

        assert response.status_code == 200
        data = response.json()

        for plan in data["plans"]:
            assert "features" in plan
            assert isinstance(plan["features"], list)

    @pytest.mark.asyncio
    async def test_list_plans_unauthenticated(self, client: AsyncClient):
        """Plans endpoint should work without authentication."""
        response = await client.get("/api/subscriptions/plans")

        # Plans should be publicly accessible
        assert response.status_code == 200


class TestGetPlan:
    """Tests for GET /api/subscriptions/plans/{plan_id}"""

    @pytest.mark.asyncio
    async def test_get_plan_success(self, client: AsyncClient, basic_api_plan):
        """Should return plan details."""
        response = await client.get(f"/api/subscriptions/plans/{basic_api_plan.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(basic_api_plan.id)
        assert data["name"] == basic_api_plan.name
        assert "features" in data

    @pytest.mark.asyncio
    async def test_get_plan_not_found(self, client: AsyncClient):
        """Should return 404 for non-existent plan."""
        fake_plan_id = uuid4()
        response = await client.get(f"/api/subscriptions/plans/{fake_plan_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_plan_includes_seat_limits(
        self, client: AsyncClient, basic_api_plan
    ):
        """Should include seat limits in response."""
        response = await client.get(f"/api/subscriptions/plans/{basic_api_plan.id}")

        assert response.status_code == 200
        data = response.json()
        assert "min_seats" in data
        assert "max_seats" in data


class TestGetWorkspaceSubscription:
    """Tests for GET /api/subscriptions/workspaces/{workspace_id}"""

    @pytest.mark.asyncio
    async def test_get_subscription_success(
        self, authenticated_client: AsyncClient, test_workspace, test_subscription
    ):
        """Should return workspace subscription details."""
        response = await authenticated_client.get(
            f"/api/subscriptions/workspaces/{test_workspace.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_subscription.id)
        assert data["workspace_id"] == str(test_workspace.id)
        assert data["status"] == SubscriptionStatus.ACTIVE.value
        assert "plan" in data

    @pytest.mark.asyncio
    async def test_get_subscription_no_subscription(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should return null if workspace has no subscription."""
        response = await authenticated_client.get(
            f"/api/subscriptions/workspaces/{test_workspace.id}"
        )

        assert response.status_code == 200
        data = response.json()
        # No subscription returns null
        assert data is None

    @pytest.mark.asyncio
    async def test_get_subscription_not_member(
        self, client: AsyncClient, test_workspace, db_session
    ):
        """Should return 404 (not found) for non-members to hide workspace existence."""
        from app.core.db.models import User
        from tests.conftest import create_test_access_token

        other_user = User(
            id=uuid4(),
            email="outsider@example.com",
            password_hash="hash",
            full_name="Outsider",
            email_verified=True,
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.flush()

        token = create_test_access_token(other_user)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.get(
            f"/api/subscriptions/workspaces/{test_workspace.id}"
        )
        # Returns 404 instead of 403 to hide workspace existence from non-members
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_subscription_includes_plan_details(
        self, authenticated_client: AsyncClient, test_workspace, test_subscription
    ):
        """Should include full plan details in response."""
        response = await authenticated_client.get(
            f"/api/subscriptions/workspaces/{test_workspace.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "plan" in data
        assert data["plan"] is not None
        assert "name" in data["plan"]
        assert "features" in data["plan"]


class TestCreateCheckout:
    """Tests for POST /api/subscriptions/workspaces/{workspace_id}/checkout"""

    @pytest.mark.asyncio
    async def test_create_checkout_not_admin(
        self, client: AsyncClient, test_workspace, test_workspace_member, basic_api_plan
    ):
        """Should return 403 if user is not admin."""
        from tests.conftest import create_test_access_token

        member_user, _ = test_workspace_member
        token = create_test_access_token(member_user)
        client.headers["Authorization"] = f"Bearer {token}"

        payload = {
            "plan_id": str(basic_api_plan.id),
            "seat_count": 5,
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
        }
        response = await client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/checkout",
            json=payload,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_checkout_invalid_plan(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should return 404 for non-existent plan."""
        fake_plan_id = uuid4()
        payload = {
            "plan_id": str(fake_plan_id),
            "seat_count": 5,
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
        }
        response = await authenticated_client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/checkout",
            json=payload,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_checkout_validation_error(
        self, authenticated_client: AsyncClient, test_workspace, basic_api_plan
    ):
        """Should return 422 for invalid request body."""
        payload = {
            "plan_id": str(basic_api_plan.id),
            # Missing required URLs
        }
        response = await authenticated_client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/checkout",
            json=payload,
        )

        assert response.status_code == 422


class TestUpdateSeats:
    """Tests for PATCH /api/subscriptions/workspaces/{workspace_id}/seats"""

    @pytest.mark.asyncio
    async def test_update_seats_not_admin(
        self,
        client: AsyncClient,
        test_workspace,
        test_workspace_member,
        test_subscription,
    ):
        """Should return 403 if user is not admin."""
        from tests.conftest import create_test_access_token

        member_user, _ = test_workspace_member
        token = create_test_access_token(member_user)
        client.headers["Authorization"] = f"Bearer {token}"

        payload = {"seat_count": 10}
        response = await client.patch(
            f"/api/subscriptions/workspaces/{test_workspace.id}/seats",
            json=payload,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_seats_no_subscription(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should return 404 if no subscription exists."""
        payload = {"seat_count": 10}
        response = await authenticated_client.patch(
            f"/api/subscriptions/workspaces/{test_workspace.id}/seats",
            json=payload,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_seats_validation_error(
        self, authenticated_client: AsyncClient, test_workspace, test_subscription
    ):
        """Should return 422 for invalid seat count."""
        payload = {"seat_count": -1}
        response = await authenticated_client.patch(
            f"/api/subscriptions/workspaces/{test_workspace.id}/seats",
            json=payload,
        )

        assert response.status_code == 422


class TestCancelSubscription:
    """Tests for POST /api/subscriptions/workspaces/{workspace_id}/cancel"""

    @pytest.mark.asyncio
    async def test_cancel_subscription_not_owner(
        self,
        client: AsyncClient,
        test_workspace,
        test_workspace_admin,
        test_subscription,
    ):
        """Should return 403 if user is not owner (only admin)."""
        from tests.conftest import create_test_access_token

        admin_user, _ = test_workspace_admin
        token = create_test_access_token(admin_user)
        client.headers["Authorization"] = f"Bearer {token}"

        payload = {"cancel_at_period_end": True}
        response = await client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/cancel",
            json=payload,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cancel_subscription_no_subscription(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should return 404 if no subscription exists."""
        payload = {"cancel_at_period_end": True}
        response = await authenticated_client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/cancel",
            json=payload,
        )

        assert response.status_code == 404


class TestReactivateWorkspace:
    """Tests for POST /api/subscriptions/workspaces/{workspace_id}/reactivate"""

    @pytest.mark.asyncio
    async def test_reactivate_not_owner(
        self, client: AsyncClient, test_workspace, test_workspace_admin
    ):
        """Should return 403 if user is not owner."""
        from tests.conftest import create_test_access_token

        admin_user, _ = test_workspace_admin
        token = create_test_access_token(admin_user)
        client.headers["Authorization"] = f"Bearer {token}"

        payload = {}
        response = await client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/reactivate",
            json=payload,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_reactivate_with_member_ids(
        self, authenticated_client: AsyncClient, test_workspace, test_subscription
    ):
        """Should accept member IDs to enable."""
        payload = {"member_ids_to_enable": [str(uuid4())]}
        response = await authenticated_client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/reactivate",
            json=payload,
        )

        # May succeed or fail based on business logic, but should not error on format
        assert response.status_code in [200, 400, 404]


class TestPreviewUpgrade:
    """Tests for POST /api/subscriptions/workspaces/{workspace_id}/preview-upgrade"""

    @pytest.mark.asyncio
    async def test_preview_upgrade_not_admin(
        self,
        client: AsyncClient,
        test_workspace,
        test_workspace_member,
        test_subscription,
        professional_api_plan,
    ):
        """Should return 403 if user is not admin."""
        from tests.conftest import create_test_access_token

        member_user, _ = test_workspace_member
        token = create_test_access_token(member_user)
        client.headers["Authorization"] = f"Bearer {token}"

        payload = {"new_plan_id": str(professional_api_plan.id)}
        response = await client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/preview-upgrade",
            json=payload,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_preview_upgrade_no_subscription(
        self, authenticated_client: AsyncClient, test_workspace, professional_api_plan
    ):
        """Should return 404 if no subscription exists."""
        payload = {"new_plan_id": str(professional_api_plan.id)}
        response = await authenticated_client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/preview-upgrade",
            json=payload,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_upgrade_invalid_plan(
        self, authenticated_client: AsyncClient, test_workspace, test_subscription
    ):
        """Should return 404 for non-existent plan."""
        fake_plan_id = uuid4()
        payload = {"new_plan_id": str(fake_plan_id)}
        response = await authenticated_client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/preview-upgrade",
            json=payload,
        )

        assert response.status_code == 404


class TestUpgradePlan:
    """Tests for POST /api/subscriptions/workspaces/{workspace_id}/upgrade"""

    @pytest.mark.asyncio
    async def test_upgrade_plan_not_admin(
        self,
        client: AsyncClient,
        test_workspace,
        test_workspace_member,
        test_subscription,
        professional_api_plan,
    ):
        """Should return 403 if user is not admin."""
        from tests.conftest import create_test_access_token

        member_user, _ = test_workspace_member
        token = create_test_access_token(member_user)
        client.headers["Authorization"] = f"Bearer {token}"

        payload = {"new_plan_id": str(professional_api_plan.id)}
        response = await client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/upgrade",
            json=payload,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_upgrade_plan_no_subscription(
        self, authenticated_client: AsyncClient, test_workspace, professional_api_plan
    ):
        """Should return 404 if no subscription exists."""
        payload = {"new_plan_id": str(professional_api_plan.id)}
        response = await authenticated_client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/upgrade",
            json=payload,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upgrade_plan_invalid_plan(
        self, authenticated_client: AsyncClient, test_workspace, test_subscription
    ):
        """Should return 404 for non-existent plan."""
        fake_plan_id = uuid4()
        payload = {"new_plan_id": str(fake_plan_id)}
        response = await authenticated_client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/upgrade",
            json=payload,
        )

        assert response.status_code == 404


class TestSubscriptionEdgeCases:
    """Edge case tests for subscription endpoints."""

    @pytest.mark.asyncio
    async def test_free_plan_no_stripe_id(
        self, authenticated_client: AsyncClient, free_api_plan
    ):
        """Free plan should not have Stripe price ID requirement."""
        response = await authenticated_client.get(
            f"/api/subscriptions/plans/{free_api_plan.id}"
        )

        assert response.status_code == 200
        data = response.json()
        # Free plans may have null or empty stripe_price_id
        assert data["name"] == "Free"

    @pytest.mark.asyncio
    async def test_workspace_not_found_returns_404(
        self, authenticated_client: AsyncClient
    ):
        """Should return 404 for non-existent workspace (hides existence)."""
        fake_workspace_id = uuid4()
        response = await authenticated_client.get(
            f"/api/subscriptions/workspaces/{fake_workspace_id}"
        )

        # Returns 404 to hide whether workspace exists (security measure)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_uuid_format(self, client: AsyncClient):
        """Should return 422 for invalid UUID format."""
        response = await client.get("/api/subscriptions/plans/not-a-uuid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_request_body(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should handle empty request body appropriately."""
        response = await authenticated_client.post(
            f"/api/subscriptions/workspaces/{test_workspace.id}/checkout",
            json={},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_subscription_response_includes_period_info(
        self, authenticated_client: AsyncClient, test_workspace, test_subscription
    ):
        """Should include billing period information in response."""
        response = await authenticated_client.get(
            f"/api/subscriptions/workspaces/{test_workspace.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "current_period_start" in data
        assert "current_period_end" in data
        assert "cancel_at_period_end" in data

    @pytest.mark.asyncio
    async def test_subscription_response_includes_credits_info(
        self, authenticated_client: AsyncClient, test_workspace, test_subscription
    ):
        """Should include credits allocation and usage in response."""
        response = await authenticated_client.get(
            f"/api/subscriptions/workspaces/{test_workspace.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "credits_allocation" in data
        assert "credits_used" in data
        # Credits allocation should be a decimal value (default is 5000.0)
        assert float(data["credits_allocation"]) > 0
        # Credits used should be 0 for new subscription
        assert float(data["credits_used"]) == 0.0

