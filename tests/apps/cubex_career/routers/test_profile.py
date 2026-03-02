"""
Integration tests for Career profile router.

Tests the GET /career/profile endpoint with real database and per-test rollback.
"""

import pytest
from httpx import AsyncClient

from app.core.enums import SubscriptionStatus


class TestGetCareerProfile:

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        response = await client.get("/career/profile")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_no_subscription_returns_profile_with_null_career_fields(
        self, authenticated_client: AsyncClient
    ):
        response = await authenticated_client.get("/career/profile")

        assert response.status_code == 200
        data = response.json()

        # User fields should be populated
        assert "id" in data
        assert "email" in data
        assert "email_verified" in data
        assert "full_name" in data
        assert "is_active" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert "has_password" in data
        assert "oauth_providers" in data

        # Career fields should be null
        assert data["subscription_status"] is None
        assert data["plan"] is None
        assert data["credits_used"] is None
        assert data["credits_limit"] is None
        assert data["credits_remaining"] is None

    @pytest.mark.asyncio
    async def test_with_free_subscription_returns_career_details(
        self,
        authenticated_client: AsyncClient,
        career_subscription,
    ):
        response = await authenticated_client.get("/career/profile")

        assert response.status_code == 200
        data = response.json()

        # User fields
        assert data["id"] is not None
        assert data["email"] is not None
        assert isinstance(data["has_password"], bool)
        assert isinstance(data["oauth_providers"], list)

        # Career fields populated
        assert data["subscription_status"] == SubscriptionStatus.ACTIVE.value
        assert data["plan"] is not None
        assert data["plan"]["name"] == "Free"
        assert data["credits_used"] is not None
        assert data["credits_limit"] is not None
        assert data["credits_remaining"] is not None

    @pytest.mark.asyncio
    async def test_with_paid_subscription_returns_career_details(
        self,
        authenticated_client: AsyncClient,
        paid_career_subscription,
    ):
        response = await authenticated_client.get("/career/profile")

        assert response.status_code == 200
        data = response.json()

        assert data["subscription_status"] == SubscriptionStatus.ACTIVE.value
        assert data["plan"] is not None
        assert data["plan"]["name"] == "Plus Plan"
        assert data["credits_used"] is not None
        assert data["credits_limit"] is not None
        assert data["credits_remaining"] is not None

    @pytest.mark.asyncio
    async def test_credits_remaining_is_calculated_correctly(
        self,
        authenticated_client: AsyncClient,
        career_subscription,
    ):
        response = await authenticated_client.get("/career/profile")

        assert response.status_code == 200
        data = response.json()

        credits_used = float(data["credits_used"])
        credits_limit = float(data["credits_limit"])
        credits_remaining = float(data["credits_remaining"])

        assert credits_remaining == pytest.approx(credits_limit - credits_used)

    @pytest.mark.asyncio
    async def test_response_includes_user_email(
        self, authenticated_client: AsyncClient, test_user
    ):
        response = await authenticated_client.get("/career/profile")

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["id"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_has_password_field(
        self, authenticated_client: AsyncClient, test_user
    ):
        """has_password should reflect whether user has a password_hash."""
        response = await authenticated_client.get("/career/profile")

        assert response.status_code == 200
        data = response.json()
        expected = test_user.password_hash is not None
        assert data["has_password"] == expected
