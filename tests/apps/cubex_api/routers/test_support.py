"""
Test suite for Support Router.

This module contains comprehensive tests for the support router endpoints:
- POST /api/support/contact-sales - submit a sales inquiry

Run all tests:
    pytest tests/apps/cubex_api/routers/test_support.py -v

Run with coverage:
    pytest tests/apps/cubex_api/routers/test_support.py --cov=app.apps.cubex_api.routers.support --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.enums import SalesRequestStatus


class TestSupportRouterSetup:
    """Test support router setup and configuration."""

    def test_support_router_import(self):
        """Test that support router can be imported."""
        from app.apps.cubex_api.routers.support import router

        assert router is not None

    def test_support_router_export(self):
        """Test that support_router is exported from __init__."""
        from app.apps.cubex_api.routers import support_router

        assert support_router is not None

    def test_support_router_prefix(self):
        """Test that support router has correct prefix."""
        from app.apps.cubex_api.routers.support import router

        assert router.prefix == "/support"


class TestContactSalesEndpoint:
    """Test POST /support/contact-sales endpoint."""

    @pytest.mark.asyncio
    async def test_contact_sales_success(self, client: AsyncClient):
        """Test successful sales inquiry submission."""
        response = await client.post(
            "/api/support/contact-sales",
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "message": "I'm interested in enterprise pricing.",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert (
            data["message"]
            == "Thank you for your inquiry. Our sales team will contact you shortly."
        )
        assert data["status"] == SalesRequestStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_contact_sales_without_message(self, client: AsyncClient):
        """Test sales inquiry submission without optional message."""
        response = await client.post(
            "/api/support/contact-sales",
            json={
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane.smith@example.com",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == SalesRequestStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_contact_sales_missing_first_name(self, client: AsyncClient):
        """Test that missing first_name returns 422."""
        response = await client.post(
            "/api/support/contact-sales",
            json={
                "last_name": "Doe",
                "email": "john.doe@example.com",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_contact_sales_missing_last_name(self, client: AsyncClient):
        """Test that missing last_name returns 422."""
        response = await client.post(
            "/api/support/contact-sales",
            json={
                "first_name": "John",
                "email": "john.doe@example.com",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_contact_sales_missing_email(self, client: AsyncClient):
        """Test that missing email returns 422."""
        response = await client.post(
            "/api/support/contact-sales",
            json={
                "first_name": "John",
                "last_name": "Doe",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_contact_sales_invalid_email(self, client: AsyncClient):
        """Test that invalid email format returns 422."""
        response = await client.post(
            "/api/support/contact-sales",
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": "not-an-email",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_contact_sales_empty_first_name(self, client: AsyncClient):
        """Test that empty first_name returns 422."""
        response = await client.post(
            "/api/support/contact-sales",
            json={
                "first_name": "",
                "last_name": "Doe",
                "email": "john.doe@example.com",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_contact_sales_whitespace_only_first_name(self, client: AsyncClient):
        """Test that whitespace-only first_name returns 422."""
        response = await client.post(
            "/api/support/contact-sales",
            json={
                "first_name": "   ",
                "last_name": "Doe",
                "email": "john.doe@example.com",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_contact_sales_message_too_long(self, client: AsyncClient):
        """Test that message exceeding 5000 chars returns 422."""
        response = await client.post(
            "/api/support/contact-sales",
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "message": "x" * 5001,
            },
        )

        assert response.status_code == 422


class TestContactSalesRateLimiting:
    """Test rate limiting for contact-sales endpoint."""

    @pytest.mark.asyncio
    async def test_rate_limit_by_email_called(self, client: AsyncClient):
        """Test that rate limiting function is called with correct email."""
        with patch(
            "app.apps.cubex_api.routers.support._check_email_rate_limit",
            new_callable=AsyncMock,
        ) as mock_rate_limit:
            response = await client.post(
                "/api/support/contact-sales",
                json={
                    "first_name": "Test",
                    "last_name": "User",
                    "email": "test@example.com",
                },
            )

            assert response.status_code == 201
            # Verify rate limit was called with lowercase email
            mock_rate_limit.assert_called_once()
            call_args = mock_rate_limit.call_args
            assert call_args[0][0] == "test@example.com"
            assert "/api/support/contact-sales" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_429(self, client: AsyncClient):
        """Test that rate limit exceeded returns 429."""
        from app.core.exceptions.types import RateLimitExceededException

        with patch(
            "app.apps.cubex_api.routers.support._check_email_rate_limit",
            new_callable=AsyncMock,
            side_effect=RateLimitExceededException(
                message="Rate limit exceeded. Try again in 3600 seconds.",
                retry_after=3600,
            ),
        ):
            response = await client.post(
                "/api/support/contact-sales",
                json={
                    "first_name": "Test",
                    "last_name": "User",
                    "email": "test@example.com",
                },
            )

            assert response.status_code == 429
            assert "Rate limit exceeded" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_email_normalized_by_pydantic(self, client: AsyncClient):
        """Test that Pydantic normalizes email domain to lowercase."""
        with patch(
            "app.apps.cubex_api.routers.support._check_email_rate_limit",
            new_callable=AsyncMock,
        ) as mock_rate_limit:
            response = await client.post(
                "/api/support/contact-sales",
                json={
                    "first_name": "Test",
                    "last_name": "User",
                    "email": "Test@EXAMPLE.COM",
                },
            )

            assert response.status_code == 201
            # Pydantic EmailStr normalizes domain to lowercase
            call_args = mock_rate_limit.call_args
            assert call_args[0][0] == "Test@example.com"


class TestSalesRequestModel:
    """Test SalesRequest model."""

    def test_sales_request_model_import(self):
        """Test that SalesRequest model can be imported."""
        from app.apps.cubex_api.db.models.support import SalesRequest

        assert SalesRequest is not None

    def test_sales_request_model_export(self):
        """Test that SalesRequest is exported from __init__."""
        from app.apps.cubex_api.db.models import SalesRequest

        assert SalesRequest is not None

    def test_sales_request_status_enum(self):
        """Test that SalesRequestStatus enum has expected values."""
        assert SalesRequestStatus.PENDING.value == "pending"
        assert SalesRequestStatus.CONTACTED.value == "contacted"
        assert SalesRequestStatus.CLOSED.value == "closed"


class TestSalesRequestCRUD:
    """Test SalesRequest CRUD operations."""

    def test_sales_request_db_import(self):
        """Test that sales_request_db can be imported."""
        from app.apps.cubex_api.db.crud.support import sales_request_db

        assert sales_request_db is not None

    def test_sales_request_db_export(self):
        """Test that sales_request_db is exported from __init__."""
        from app.apps.cubex_api.db.crud import sales_request_db

        assert sales_request_db is not None


class TestSupportSchemas:
    """Test support schemas."""

    def test_contact_sales_request_schema(self):
        """Test ContactSalesRequest schema validation."""
        from app.apps.cubex_api.schemas.support import ContactSalesRequest

        # Valid request
        request = ContactSalesRequest(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            message="Test message",
        )
        assert request.first_name == "John"
        assert request.last_name == "Doe"
        assert request.email == "john@example.com"
        assert request.message == "Test message"

    def test_contact_sales_request_without_message(self):
        """Test ContactSalesRequest schema without optional message."""
        from app.apps.cubex_api.schemas.support import ContactSalesRequest

        request = ContactSalesRequest(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
        )
        assert request.message is None

    def test_contact_sales_request_strips_whitespace(self):
        """Test that ContactSalesRequest strips whitespace."""
        from app.apps.cubex_api.schemas.support import ContactSalesRequest

        request = ContactSalesRequest(
            first_name="  John  ",
            last_name="  Doe  ",
            email="john@example.com",
            message="  Test message  ",
        )
        assert request.first_name == "John"
        assert request.last_name == "Doe"
        assert request.message == "Test message"

    def test_contact_sales_response_schema(self):
        """Test ContactSalesResponse schema."""
        from uuid import uuid4

        from app.apps.cubex_api.schemas.support import ContactSalesResponse

        response = ContactSalesResponse(
            id=uuid4(),
            message="Thank you",
            status=SalesRequestStatus.PENDING,
        )
        assert response.message == "Thank you"
        assert response.status == SalesRequestStatus.PENDING

    def test_schemas_exported(self):
        """Test that schemas are exported from __init__."""
        from app.apps.cubex_api.schemas import (
            ContactSalesRequest,
            ContactSalesResponse,
        )

        assert ContactSalesRequest is not None
        assert ContactSalesResponse is not None
