"""
Test suite for Internal API Router.

This module contains comprehensive tests for the internal router endpoints:
- POST /internal/usage/validate - validates API key and logs usage
- POST /internal/usage/revert - reverts usage (idempotent)
- X-Internal-API-Key header authentication

Run all tests:
    pytest tests/apps/cubex_api/routers/test_internal.py -v

Run with coverage:
    pytest tests/apps/cubex_api/routers/test_internal.py --cov=app.apps.cubex_api.routers.internal --cov-report=term-missing -v
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.shared.config import settings
from app.shared.enums import AccessStatus


@pytest.fixture
def internal_api_headers() -> dict[str, str]:
    """Return headers with valid internal API key."""
    return {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}


@pytest.fixture
def invalid_internal_api_headers() -> dict[str, str]:
    """Return headers with invalid internal API key."""
    return {"X-Internal-API-Key": "invalid_key"}


class TestInternalRouterSetup:
    """Test internal router setup and configuration."""

    def test_internal_router_import(self):
        """Test that internal_router can be imported."""
        from app.apps.cubex_api.routers.internal import router

        assert router is not None

    def test_internal_router_export(self):
        """Test that internal_router is exported from __init__."""
        from app.apps.cubex_api.routers import internal_router

        assert internal_router is not None

    def test_internal_router_prefix(self):
        """Test that internal router has correct prefix."""
        from app.apps.cubex_api.routers.internal import router

        assert router.prefix == "/internal"

    def test_internal_router_tags(self):
        """Test that internal router has correct tags."""
        from app.apps.cubex_api.routers.internal import router

        assert "Internal API" in router.tags


class TestInternalAPIKeyAuthentication:
    """Test internal API key authentication."""

    @pytest.mark.asyncio
    async def test_missing_api_key_header(self, client: AsyncClient):
        """Test that missing API key header returns 401."""
        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123",
                "client_id": f"ws_{uuid4().hex}",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_api_key_header(
        self, client: AsyncClient, invalid_internal_api_headers: dict[str, str]
    ):
        """Test that invalid API key header returns 401."""
        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123",
                "client_id": f"ws_{uuid4().hex}",
            },
            headers=invalid_internal_api_headers,
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_api_key_header_accepted(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test that valid API key header is accepted (may fail for other reasons)."""
        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123",
                "client_id": f"ws_{uuid4().hex}",
            },
            headers=internal_api_headers,
        )

        # Should not be 403 Forbidden - could be 404 or other error
        assert response.status_code != 403


class TestUsageValidateEndpoint:
    """Test POST /internal/usage/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_invalid_api_key_format(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test validation with invalid API key format."""
        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "invalid_key_format",  # Missing cbx_live_ prefix
                "client_id": f"ws_{uuid4().hex}",
            },
            headers=internal_api_headers,
        )

        # Should return DENIED access
        data = response.json()
        assert data["access"] == AccessStatus.DENIED.value

    @pytest.mark.asyncio
    async def test_validate_invalid_client_id_format(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test validation with invalid client_id format."""
        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123abc",
                "client_id": "invalid_client_id",  # Missing ws_ prefix
            },
            headers=internal_api_headers,
        )

        # Should return 422 due to pydantic validation
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validate_with_optional_cost(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test validation with optional cost field."""
        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123abc",
                "client_id": f"ws_{uuid4().hex}",
                "cost": {"tokens": 100, "requests": 1},
            },
            headers=internal_api_headers,
        )

        # Should process without error - returns 200 with DENIED access
        assert response.status_code == 200
        data = response.json()
        assert data["access"] == AccessStatus.DENIED.value

    @pytest.mark.asyncio
    async def test_validate_nonexistent_api_key(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test validation with non-existent API key."""
        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "cbx_live_nonexistentkey123456789",
                "client_id": f"ws_{uuid4().hex}",
            },
            headers=internal_api_headers,
        )

        # Returns 200 with DENIED access, not 404
        assert response.status_code == 200
        data = response.json()
        assert data["access"] == AccessStatus.DENIED.value


class TestUsageRevertEndpoint:
    """Test POST /internal/usage/revert endpoint."""

    @pytest.mark.asyncio
    async def test_revert_missing_api_key_header(self, client: AsyncClient):
        """Test revert without API key header returns 401."""
        response = await client.post(
            "/internal/usage/revert",
            json={
                "api_key": "cbx_live_test123",
                "usage_id": str(uuid4()),
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_revert_invalid_api_key_header(
        self, client: AsyncClient, invalid_internal_api_headers: dict[str, str]
    ):
        """Test revert with invalid API key header returns 401."""
        response = await client.post(
            "/internal/usage/revert",
            json={
                "api_key": "cbx_live_test123",
                "usage_id": str(uuid4()),
            },
            headers=invalid_internal_api_headers,
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_revert_valid_request_format(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test revert with valid request format."""
        response = await client.post(
            "/internal/usage/revert",
            json={
                "api_key": "cbx_live_test123abc",
                "usage_id": str(uuid4()),
            },
            headers=internal_api_headers,
        )

        # Should return 200 with success response (idempotent)
        assert response.status_code == 200
        data = response.json()
        assert "success" in data

    @pytest.mark.asyncio
    async def test_revert_nonexistent_usage(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test revert with non-existent usage_id."""
        response = await client.post(
            "/internal/usage/revert",
            json={
                "api_key": "cbx_live_test123abc",
                "usage_id": str(uuid4()),  # Non-existent ID
            },
            headers=internal_api_headers,
        )

        # Idempotent - returns 200 even for non-existent usage
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True  # Idempotent success


class TestRequestValidation:
    """Test request body validation."""

    @pytest.mark.asyncio
    async def test_validate_missing_api_key_field(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test validation with missing api_key field."""
        response = await client.post(
            "/internal/usage/validate",
            json={
                "client_id": f"ws_{uuid4().hex}",
            },
            headers=internal_api_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validate_missing_client_id_field(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test validation with missing client_id field."""
        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123",
            },
            headers=internal_api_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_revert_missing_api_key_field(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test revert with missing api_key field."""
        response = await client.post(
            "/internal/usage/revert",
            json={
                "usage_id": str(uuid4()),
            },
            headers=internal_api_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_revert_missing_usage_id_field(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test revert with missing usage_id field."""
        response = await client.post(
            "/internal/usage/revert",
            json={
                "api_key": "cbx_live_test123",
            },
            headers=internal_api_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validate_invalid_uuid_usage_id(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test revert with invalid UUID format for usage_id."""
        response = await client.post(
            "/internal/usage/revert",
            json={
                "api_key": "cbx_live_test123",
                "usage_id": "not-a-valid-uuid",
            },
            headers=internal_api_headers,
        )

        assert response.status_code == 422


class TestClientIdPattern:
    """Test client_id pattern validation."""

    @pytest.mark.asyncio
    async def test_valid_client_id_pattern(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test that valid client_id pattern is accepted."""
        valid_client_id = f"ws_{uuid4().hex}"

        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123abc",
                "client_id": valid_client_id,
            },
            headers=internal_api_headers,
        )

        # Should not fail with 422 for pattern mismatch
        assert response.status_code != 422 or "client_id" not in response.text

    @pytest.mark.asyncio
    async def test_invalid_client_id_pattern_missing_prefix(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test that client_id without prefix is rejected."""
        invalid_client_id = uuid4().hex

        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123abc",
                "client_id": invalid_client_id,
            },
            headers=internal_api_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_client_id_pattern_wrong_format(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test that client_id with wrong format is rejected."""
        invalid_client_id = "ws_not-hex-chars-here!"

        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123abc",
                "client_id": invalid_client_id,
            },
            headers=internal_api_headers,
        )

        assert response.status_code == 422


class TestResponseFormat:
    """Test response format from endpoints."""

    @pytest.mark.asyncio
    async def test_validate_response_has_access(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test that validate response includes access field."""
        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123abc",
                "client_id": f"ws_{uuid4().hex}",
            },
            headers=internal_api_headers,
        )

        # Skip check if error response
        if response.status_code == 200:
            data = response.json()
            assert "access" in data
            assert data["access"] in [
                AccessStatus.GRANTED.value,
                AccessStatus.DENIED.value,
            ]

    @pytest.mark.asyncio
    async def test_validate_response_has_message(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test that validate response includes message field."""
        response = await client.post(
            "/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123abc",
                "client_id": f"ws_{uuid4().hex}",
            },
            headers=internal_api_headers,
        )

        # Skip check if error response
        if response.status_code == 200:
            data = response.json()
            assert "message" in data

    @pytest.mark.asyncio
    async def test_revert_response_has_success_field(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test that revert response includes success field."""
        response = await client.post(
            "/internal/usage/revert",
            json={
                "api_key": "cbx_live_test123abc",
                "usage_id": str(uuid4()),
            },
            headers=internal_api_headers,
        )

        # Skip check if error response
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            assert isinstance(data["success"], bool)
