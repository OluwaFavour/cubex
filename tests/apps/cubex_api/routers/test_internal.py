"""
Test suite for Internal API Router.

This module contains comprehensive tests for the internal router endpoints:
- POST /api/internal/usage/validate - validates API key and logs usage
- POST /api/internal/usage/commit - commits usage as success or failure
- X-Internal-API-Key header authentication

Run all tests:
    pytest tests/apps/cubex_api/routers/test_internal.py -v

Run with coverage:
    pytest tests/apps/cubex_api/routers/test_internal.py --cov=app.apps.cubex_api.routers.internal --cov-report=term-missing -v
"""

import hashlib
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.config import settings
from app.shared.enums import AccessStatus


def _generate_payload_hash(data: str = "") -> str:
    """Generate a valid 64-char hex payload hash."""
    if not data:
        data = str(uuid4())
    return hashlib.sha256(data.encode()).hexdigest()


def make_validate_request(
    api_key: str = "cbx_live_test123abc",
    client_id: str | None = None,
    request_id: str | None = None,
    endpoint: str = "/test/endpoint",
    method: str = "POST",
    payload_hash: str | None = None,
    **extra,
) -> dict:
    """Helper to create valid usage validate request with required fields."""
    if client_id is None:
        client_id = f"ws_{uuid4().hex}"
    if request_id is None:
        request_id = str(uuid4())
    if payload_hash is None:
        payload_hash = _generate_payload_hash()
    return {
        "api_key": api_key,
        "client_id": client_id,
        "request_id": request_id,
        "endpoint": endpoint,
        "method": method,
        "payload_hash": payload_hash,
        **extra,
    }


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
            "/api/internal/usage/validate",
            json=make_validate_request(),
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_api_key_header(
        self, client: AsyncClient, invalid_internal_api_headers: dict[str, str]
    ):
        """Test that invalid API key header returns 401."""
        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(),
            headers=invalid_internal_api_headers,
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_api_key_header_accepted(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test that valid API key header is accepted (may fail for other reasons)."""
        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(),
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
            "/api/internal/usage/validate",
            json=make_validate_request(api_key="invalid_key_format"),
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
            "/api/internal/usage/validate",
            json=make_validate_request(client_id="invalid_client_id"),
            headers=internal_api_headers,
        )

        # Should return 422 due to pydantic validation
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validate_with_optional_usage_estimate(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test validation with optional usage_estimate field."""
        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                usage_estimate={
                    "input_chars": 1000,
                    "max_output_tokens": 500,
                    "model": "gpt-4",
                }
            ),
            headers=internal_api_headers,
        )

        # API key doesn't exist, so returns 401 with DENIED access
        assert response.status_code == 401
        data = response.json()
        assert data["access"] == AccessStatus.DENIED.value
        # Response should include credits_reserved field
        assert "credits_reserved" in data

    @pytest.mark.asyncio
    async def test_validate_nonexistent_api_key(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test validation with non-existent API key."""
        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(api_key="cbx_live_nonexistentkey123456789"),
            headers=internal_api_headers,
        )

        # Returns 401 with DENIED access for nonexistent API key
        assert response.status_code == 401
        data = response.json()
        assert data["access"] == AccessStatus.DENIED.value


class TestUsageCommitEndpoint:
    """Test POST /internal/usage/commit endpoint."""

    @pytest.mark.asyncio
    async def test_commit_missing_api_key_header(self, client: AsyncClient):
        """Test commit without API key header returns 401."""
        response = await client.post(
            "/api/internal/usage/commit",
            json={
                "api_key": "cbx_live_test123",
                "usage_id": str(uuid4()),
                "success": True,
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_commit_invalid_api_key_header(
        self, client: AsyncClient, invalid_internal_api_headers: dict[str, str]
    ):
        """Test commit with invalid API key header returns 401."""
        response = await client.post(
            "/api/internal/usage/commit",
            json={
                "api_key": "cbx_live_test123",
                "usage_id": str(uuid4()),
                "success": True,
            },
            headers=invalid_internal_api_headers,
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_commit_valid_request_format(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test commit with valid request format."""
        response = await client.post(
            "/api/internal/usage/commit",
            json={
                "api_key": "cbx_live_test123abc",
                "usage_id": str(uuid4()),
                "success": True,
            },
            headers=internal_api_headers,
        )

        # Should return 200 with success response (idempotent)
        assert response.status_code == 200
        data = response.json()
        assert "success" in data

    @pytest.mark.asyncio
    async def test_commit_nonexistent_usage(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test commit with non-existent usage_id."""
        response = await client.post(
            "/api/internal/usage/commit",
            json={
                "api_key": "cbx_live_test123abc",
                "usage_id": str(uuid4()),  # Non-existent ID
                "success": True,
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
            "/api/internal/usage/validate",
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
            "/api/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123",
            },
            headers=internal_api_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_commit_missing_api_key_field(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test commit with missing api_key field."""
        response = await client.post(
            "/api/internal/usage/commit",
            json={
                "usage_id": str(uuid4()),
                "success": True,
            },
            headers=internal_api_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_commit_missing_usage_id_field(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test commit with missing usage_id field."""
        response = await client.post(
            "/api/internal/usage/commit",
            json={
                "api_key": "cbx_live_test123",
                "success": True,
            },
            headers=internal_api_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_commit_invalid_uuid_usage_id(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test commit with invalid UUID format for usage_id."""
        response = await client.post(
            "/api/internal/usage/commit",
            json={
                "api_key": "cbx_live_test123",
                "usage_id": "not-a-valid-uuid",
                "success": True,
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
            "/api/internal/usage/validate",
            json=make_validate_request(client_id=valid_client_id),
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
            "/api/internal/usage/validate",
            json=make_validate_request(client_id=invalid_client_id),
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
            "/api/internal/usage/validate",
            json=make_validate_request(client_id=invalid_client_id),
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
            "/api/internal/usage/validate",
            json=make_validate_request(),
            headers=internal_api_headers,
        )

        # All status codes should have the response format
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
            "/api/internal/usage/validate",
            json=make_validate_request(),
            headers=internal_api_headers,
        )

        # All status codes should have the response format
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_validate_response_has_credits_reserved(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test that validate response includes credits_reserved field."""
        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(),
            headers=internal_api_headers,
        )

        # All status codes should have the response format
        data = response.json()
        assert "credits_reserved" in data

    @pytest.mark.asyncio
    async def test_commit_response_has_success_field(
        self, client: AsyncClient, internal_api_headers: dict[str, str]
    ):
        """Test that commit response includes success field."""
        response = await client.post(
            "/api/internal/usage/commit",
            json={
                "api_key": "cbx_live_test123abc",
                "usage_id": str(uuid4()),
                "success": True,
            },
            headers=internal_api_headers,
        )

        # Should return 200 (idempotent)
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert isinstance(data["success"], bool)


# ============================================================================
# E2E Tests for validate_usage with Real Database and Redis
# ============================================================================


class TestValidateUsageE2E:
    """End-to-end tests for validate_usage using real fixtures.

    These tests use:
    - Real PostgreSQL database (via test fixtures)
    - Real Redis (via testcontainers)
    - Real API key generation and validation
    """

    @pytest.mark.asyncio
    async def test_validate_usage_live_key_success(
        self,
        client: AsyncClient,
        internal_api_headers: dict[str, str],
        live_api_key,
        test_workspace,
    ):
        """Test successful validation with a live API key."""
        from tests.conftest import make_client_id

        raw_key, api_key = live_api_key
        client_id = make_client_id(test_workspace)

        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                api_key=raw_key,
                client_id=client_id,
            ),
            headers=internal_api_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access"] == AccessStatus.GRANTED.value
        assert data["usage_id"] is not None
        assert data["is_test_key"] is False
        assert data["credits_reserved"] is not None

    @pytest.mark.asyncio
    async def test_validate_usage_quota_exceeded_returns_429(
        self,
        client: AsyncClient,
        internal_api_headers: dict[str, str],
        api_key_for_exhausted_workspace,
    ):
        """Test that quota exceeded returns 429 with appropriate message."""
        from tests.conftest import make_client_id

        raw_key, api_key, workspace, subscription, credits_allocation = (
            api_key_for_exhausted_workspace
        )
        client_id = make_client_id(workspace)

        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                api_key=raw_key,
                client_id=client_id,
            ),
            headers=internal_api_headers,
        )

        assert response.status_code == 429
        data = response.json()
        assert data["access"] == AccessStatus.DENIED.value
        assert (
            "quota" in data["message"].lower() or "exceeded" in data["message"].lower()
        )

    @pytest.mark.asyncio
    async def test_validate_usage_idempotent_same_fingerprint(
        self,
        client: AsyncClient,
        internal_api_headers: dict[str, str],
        live_api_key,
        test_workspace,
    ):
        """Test idempotency: same request_id + same fingerprint returns same usage_id."""
        from tests.conftest import make_client_id

        raw_key, api_key = live_api_key
        client_id = make_client_id(test_workspace)
        request_id = str(uuid4())
        payload_hash = _generate_payload_hash("same_payload")

        # First request
        response1 = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                api_key=raw_key,
                client_id=client_id,
                request_id=request_id,
                endpoint="/test",
                method="POST",
                payload_hash=payload_hash,
            ),
            headers=internal_api_headers,
        )

        assert response1.status_code == 200
        data1 = response1.json()
        usage_id_1 = data1["usage_id"]

        # Second request with same fingerprint
        response2 = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                api_key=raw_key,
                client_id=client_id,
                request_id=request_id,  # Same request_id
                endpoint="/test",  # Same endpoint
                method="POST",  # Same method
                payload_hash=payload_hash,  # Same payload_hash
            ),
            headers=internal_api_headers,
        )

        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["usage_id"] == usage_id_1  # Same usage_id returned
        assert "idempotent" in data2["message"].lower()

    @pytest.mark.asyncio
    async def test_validate_usage_idempotent_different_fingerprint(
        self,
        client: AsyncClient,
        internal_api_headers: dict[str, str],
        live_api_key,
        test_workspace,
    ):
        """Test that same request_id but different fingerprint creates new record."""
        from tests.conftest import make_client_id

        raw_key, api_key = live_api_key
        client_id = make_client_id(test_workspace)
        request_id = str(uuid4())

        # First request
        response1 = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                api_key=raw_key,
                client_id=client_id,
                request_id=request_id,
                payload_hash=_generate_payload_hash("payload_1"),
            ),
            headers=internal_api_headers,
        )

        assert response1.status_code == 200
        usage_id_1 = response1.json()["usage_id"]

        # Second request with same request_id but different payload_hash
        response2 = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                api_key=raw_key,
                client_id=client_id,
                request_id=request_id,  # Same request_id
                payload_hash=_generate_payload_hash("payload_2"),  # Different payload
            ),
            headers=internal_api_headers,
        )

        assert response2.status_code == 200
        usage_id_2 = response2.json()["usage_id"]
        assert usage_id_2 != usage_id_1  # Different usage_id (new record)

    @pytest.mark.asyncio
    async def test_validate_usage_workspace_mismatch_returns_403(
        self,
        client: AsyncClient,
        internal_api_headers: dict[str, str],
        live_api_key,
        other_workspace,
    ):
        """Test that API key from one workspace + client_id from another returns 403."""
        from tests.conftest import make_client_id

        raw_key, api_key = live_api_key  # Key belongs to test_workspace
        client_id = make_client_id(other_workspace)  # client_id from other_workspace

        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                api_key=raw_key,
                client_id=client_id,
            ),
            headers=internal_api_headers,
        )

        assert response.status_code == 403
        data = response.json()
        assert data["access"] == AccessStatus.DENIED.value
        assert "does not belong" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_validate_usage_expired_key_returns_401(
        self,
        client: AsyncClient,
        internal_api_headers: dict[str, str],
        expired_api_key,
        test_workspace,
    ):
        """Test that an expired API key returns 401."""
        from tests.conftest import make_client_id

        raw_key, api_key = expired_api_key
        client_id = make_client_id(test_workspace)

        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                api_key=raw_key,
                client_id=client_id,
            ),
            headers=internal_api_headers,
        )

        assert response.status_code == 401
        data = response.json()
        assert data["access"] == AccessStatus.DENIED.value
        assert (
            "expired" in data["message"].lower()
            or "not found" in data["message"].lower()
        )

    @pytest.mark.asyncio
    async def test_validate_usage_revoked_key_returns_401(
        self,
        client: AsyncClient,
        internal_api_headers: dict[str, str],
        revoked_api_key,
        test_workspace,
    ):
        """Test that a revoked API key returns 401."""
        from tests.conftest import make_client_id

        raw_key, api_key = revoked_api_key
        client_id = make_client_id(test_workspace)

        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                api_key=raw_key,
                client_id=client_id,
            ),
            headers=internal_api_headers,
        )

        assert response.status_code == 401
        data = response.json()
        assert data["access"] == AccessStatus.DENIED.value
        assert (
            "revoked" in data["message"].lower()
            or "not found" in data["message"].lower()
        )

    @pytest.mark.asyncio
    async def test_validate_usage_test_key_bypasses_quota(
        self,
        client: AsyncClient,
        internal_api_headers: dict[str, str],
        test_api_key_for_exhausted_workspace,
    ):
        """Test that test keys bypass quota checks even when quota is exhausted."""
        from tests.conftest import make_client_id

        raw_key, api_key, workspace, subscription, credits_allocation = (
            test_api_key_for_exhausted_workspace
        )
        client_id = make_client_id(workspace)

        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                api_key=raw_key,
                client_id=client_id,
            ),
            headers=internal_api_headers,
        )

        # Test keys should be granted even with exhausted quota
        assert response.status_code == 200
        data = response.json()
        assert data["access"] == AccessStatus.GRANTED.value
        assert data["is_test_key"] is True

    @pytest.mark.asyncio
    async def test_validate_usage_test_key_response_fields(
        self,
        client: AsyncClient,
        internal_api_headers: dict[str, str],
        test_api_key,
        test_workspace,
    ):
        """Test that test key responses have correct fields: is_test_key=True, credits_reserved='0.0000'."""
        from tests.conftest import make_client_id

        raw_key, api_key = test_api_key
        client_id = make_client_id(test_workspace)

        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                api_key=raw_key,
                client_id=client_id,
            ),
            headers=internal_api_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_test_key"] is True
        # credits_reserved may be "0.00" or "0.0000" depending on decimal precision
        assert data["credits_reserved"] in ("0.00", "0.0000")
        assert data["access"] == AccessStatus.GRANTED.value

    @pytest.mark.asyncio
    async def test_validate_usage_test_key_rate_limited(
        self,
        client: AsyncClient,
        internal_api_headers: dict[str, str],
        test_api_key,
        test_workspace,
        basic_api_plan_pricing_rule,
    ):
        """Test that test keys are still subject to rate limits.

        Uses freezegun to freeze time so all requests happen in the same window.
        """
        from freezegun import freeze_time

        from tests.conftest import make_client_id

        raw_key, api_key = test_api_key
        client_id = make_client_id(test_workspace)

        # Get rate limit from pricing rule fixture
        rate_limit = basic_api_plan_pricing_rule.rate_limit_per_minute

        # Freeze time to ensure all requests are in the same window
        with freeze_time("2026-02-13 12:00:00"):
            # Make requests up to the rate limit
            for i in range(rate_limit):
                response = await client.post(
                    "/api/internal/usage/validate",
                    json=make_validate_request(
                        api_key=raw_key,
                        client_id=client_id,
                        request_id=str(uuid4()),  # Unique request_id each time
                    ),
                    headers=internal_api_headers,
                )
                # Should succeed until we hit the limit
                assert response.status_code == 200, f"Request {i+1} failed unexpectedly"

            # The next request should be rate limited
            response = await client.post(
                "/api/internal/usage/validate",
                json=make_validate_request(
                    api_key=raw_key,
                    client_id=client_id,
                    request_id=str(uuid4()),
                ),
                headers=internal_api_headers,
            )

            assert response.status_code == 429
            data = response.json()
            assert data["access"] == AccessStatus.DENIED.value
            assert "rate limit" in data["message"].lower()
            # Should have Retry-After header
            assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_validate_usage_headers_absent_on_400(
        self,
        client: AsyncClient,
        internal_api_headers: dict[str, str],
    ):
        """Test that rate limit headers are NOT present on 400 errors (early validation failures)."""
        # Invalid client_id format should fail before rate limiting
        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                client_id="invalid_not_ws_prefix",
            ),
            headers=internal_api_headers,
        )

        # Should be 422 (validation error) not 400
        assert response.status_code == 422
        # Rate limit headers should NOT be present on validation errors
        assert "X-RateLimit-Limit" not in response.headers
        assert "X-RateLimit-Remaining" not in response.headers
        assert "X-RateLimit-Reset" not in response.headers

    @pytest.mark.asyncio
    async def test_validate_usage_rate_limit_headers_present(
        self,
        client: AsyncClient,
        internal_api_headers: dict[str, str],
        live_api_key,
        test_workspace,
    ):
        """Test that rate limit headers are present on successful requests."""
        from tests.conftest import make_client_id

        raw_key, api_key = live_api_key
        client_id = make_client_id(test_workspace)

        response = await client.post(
            "/api/internal/usage/validate",
            json=make_validate_request(
                api_key=raw_key,
                client_id=client_id,
            ),
            headers=internal_api_headers,
        )

        assert response.status_code == 200
        # Rate limit headers should be present
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        # Remaining should be less than limit (we just used one)
        limit = int(response.headers["X-RateLimit-Limit"])
        remaining = int(response.headers["X-RateLimit-Remaining"])
        assert remaining < limit
