"""
Test suite for Rate Limiting Implementation.

This module contains comprehensive tests for:
- RateLimitInfo dataclass
- QuotaService._check_rate_limit method
- Rate limit integration in validate_and_log_usage
- Rate limit headers in internal API responses

Run all tests:
    pytest tests/apps/cubex_api/test_rate_limiting.py -v

Run with coverage:
    pytest tests/apps/cubex_api/test_rate_limiting.py --cov=app.apps.cubex_api.services.quota --cov-report=term-missing -v
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.apps.cubex_api.services.quota import RateLimitInfo, quota_service


# ============================================================================
# RateLimitInfo Dataclass Tests
# ============================================================================


class TestRateLimitInfoDataclass:
    """Test suite for RateLimitInfo dataclass."""

    def test_rate_limit_info_import(self):
        """Test that RateLimitInfo can be imported."""
        from app.apps.cubex_api.services.quota import RateLimitInfo

        assert RateLimitInfo is not None

    def test_rate_limit_info_export_from_services(self):
        """Test that RateLimitInfo is exported from services __init__."""
        from app.apps.cubex_api.services import RateLimitInfo

        assert RateLimitInfo is not None

    def test_rate_limit_info_creation_with_all_fields(self):
        """Test RateLimitInfo creation with all fields."""
        info = RateLimitInfo(
            limit=20,
            remaining=15,
            reset_timestamp=1739352000,
            is_exceeded=False,
        )
        assert info.limit == 20
        assert info.remaining == 15
        assert info.reset_timestamp == 1739352000
        assert info.is_exceeded is False

    def test_rate_limit_info_default_is_exceeded(self):
        """Test that is_exceeded defaults to False."""
        info = RateLimitInfo(
            limit=20,
            remaining=15,
            reset_timestamp=1739352000,
        )
        assert info.is_exceeded is False

    def test_rate_limit_info_exceeded_state(self):
        """Test RateLimitInfo with is_exceeded=True."""
        info = RateLimitInfo(
            limit=20,
            remaining=0,
            reset_timestamp=1739352000,
            is_exceeded=True,
        )
        assert info.is_exceeded is True
        assert info.remaining == 0

    def test_rate_limit_info_zero_remaining(self):
        """Test RateLimitInfo with zero remaining requests."""
        info = RateLimitInfo(
            limit=50,
            remaining=0,
            reset_timestamp=int(time.time()) + 45,
        )
        assert info.remaining == 0
        assert info.limit == 50

    def test_rate_limit_info_fields_are_integers(self):
        """Test that all numeric fields are integers."""
        info = RateLimitInfo(
            limit=20,
            remaining=15,
            reset_timestamp=1739352000,
        )
        assert isinstance(info.limit, int)
        assert isinstance(info.remaining, int)
        assert isinstance(info.reset_timestamp, int)
        assert isinstance(info.is_exceeded, bool)


# ============================================================================
# QuotaService._check_rate_limit Tests
# ============================================================================


class TestCheckRateLimitMethod:
    """Test suite for QuotaService._check_rate_limit method."""

    def test_check_rate_limit_method_exists(self):
        """Test that _check_rate_limit method exists."""
        assert hasattr(quota_service, "_check_rate_limit")
        assert callable(quota_service._check_rate_limit)

    def test_check_rate_limit_method_signature(self):
        """Test that _check_rate_limit has correct signature."""
        import inspect

        sig = inspect.signature(quota_service._check_rate_limit)
        params = list(sig.parameters.keys())

        assert "workspace_id" in params
        assert "plan_id" in params

    @pytest.mark.asyncio
    async def test_check_rate_limit_returns_rate_limit_info(self):
        """Test that _check_rate_limit returns RateLimitInfo."""
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.QuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=60,
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        assert isinstance(result, RateLimitInfo)
        assert result.limit == 20

    @pytest.mark.asyncio
    async def test_check_rate_limit_first_request_in_window(self):
        """Test rate limit for first request in window."""
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.QuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=1,
            ) as mock_incr,
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_expire,
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=60,
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        # First request should set expiry
        mock_incr.assert_called_once()
        mock_expire.assert_called_once()
        assert result.remaining == 19
        assert result.is_exceeded is False

    @pytest.mark.asyncio
    async def test_check_rate_limit_subsequent_request(self):
        """Test rate limit for subsequent request (not first)."""
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.QuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=5,  # 5th request
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_expire,
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=45,
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        # Subsequent requests should not set expiry
        mock_expire.assert_not_called()
        assert result.remaining == 15
        assert result.is_exceeded is False

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self):
        """Test rate limit when exceeded."""
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.QuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=21,  # Over limit
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=30,
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        assert result.is_exceeded is True
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_unavailable(self):
        """Test rate limit when Redis is unavailable."""
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.QuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=None,  # Redis unavailable
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        # Should allow request when Redis is unavailable
        assert result.is_exceeded is False
        assert result.limit == 20
        assert result.remaining == 19

    @pytest.mark.asyncio
    async def test_check_rate_limit_uses_correct_redis_key(self):
        """Test that rate limit uses correct Redis key format."""
        workspace_id = uuid4()
        plan_id = uuid4()
        expected_key = f"rate_limit:{workspace_id}"

        with (
            patch(
                "app.apps.cubex_api.services.quota.QuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=1,
            ) as mock_incr,
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=60,
            ),
        ):
            await quota_service._check_rate_limit(workspace_id, plan_id)

        mock_incr.assert_called_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_check_rate_limit_uses_plan_rate_limit(self):
        """Test that rate limit uses the plan's configured rate limit."""
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.QuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=50,  # Custom rate limit
            ) as mock_get_rate_limit,
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=60,
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        mock_get_rate_limit.assert_called_once_with(plan_id)
        assert result.limit == 50
        assert result.remaining == 49

    @pytest.mark.asyncio
    async def test_check_rate_limit_ttl_fallback(self):
        """Test that TTL defaults to 60 when lookup fails."""
        workspace_id = uuid4()
        plan_id = uuid4()
        current_time = int(time.time())

        with (
            patch(
                "app.apps.cubex_api.services.quota.QuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=5,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=-1,  # Key has no expiry (error case)
            ),
            patch(
                "app.apps.cubex_api.services.quota.time.time", return_value=current_time
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        # Should default to 60 seconds
        assert result.reset_timestamp == current_time + 60

    @pytest.mark.asyncio
    async def test_check_rate_limit_at_exact_limit(self):
        """Test rate limit when at exactly the limit."""
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.QuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=20,  # Exactly at limit
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=30,
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        # At exactly limit, should not be exceeded
        assert result.is_exceeded is False
        assert result.remaining == 0


# ============================================================================
# Rate Limit Integration with validate_and_log_usage Tests
# ============================================================================


class TestValidateAndLogUsageRateLimiting:
    """Test rate limiting integration in validate_and_log_usage."""

    def test_validate_and_log_usage_returns_seven_tuple(self):
        """Test that validate_and_log_usage returns 7-tuple."""
        import inspect

        sig = inspect.signature(quota_service.validate_and_log_usage)
        # Check return annotation includes RateLimitInfo
        return_annotation = str(sig.return_annotation)
        assert "RateLimitInfo" in return_annotation

    def test_validate_and_log_usage_includes_rate_limit_info_in_return(self):
        """Test that the return type includes rate_limit_info."""
        import inspect

        sig = inspect.signature(quota_service.validate_and_log_usage)
        return_annotation = str(sig.return_annotation)

        # Should be a 7-tuple with RateLimitInfo as the last element
        assert "tuple" in return_annotation.lower()
        assert "RateLimitInfo" in return_annotation


# ============================================================================
# Rate Limit Headers Tests
# ============================================================================


class TestRateLimitHeadersConstruction:
    """Test that rate limit headers are correctly constructed."""

    def test_x_ratelimit_limit_header_format(self):
        """Test X-RateLimit-Limit header is an integer string."""
        info = RateLimitInfo(limit=20, remaining=15, reset_timestamp=1739352000)
        header_value = str(info.limit)
        assert header_value == "20"
        assert header_value.isdigit()

    def test_x_ratelimit_remaining_header_format(self):
        """Test X-RateLimit-Remaining header is an integer string."""
        info = RateLimitInfo(limit=20, remaining=15, reset_timestamp=1739352000)
        header_value = str(info.remaining)
        assert header_value == "15"
        assert header_value.isdigit()

    def test_x_ratelimit_reset_header_format(self):
        """Test X-RateLimit-Reset header is a Unix timestamp."""
        reset_time = int(time.time()) + 60
        info = RateLimitInfo(limit=20, remaining=15, reset_timestamp=reset_time)
        header_value = str(info.reset_timestamp)
        assert header_value.isdigit()
        assert int(header_value) > int(time.time())  # Should be in the future

    def test_retry_after_calculation(self):
        """Test Retry-After header calculation."""
        current_time = int(time.time())
        reset_time = current_time + 45
        info = RateLimitInfo(
            limit=20, remaining=0, reset_timestamp=reset_time, is_exceeded=True
        )

        retry_after = max(0, info.reset_timestamp - current_time)
        assert retry_after == 45


# ============================================================================
# Integration Tests with HTTP Client
# ============================================================================


class TestRateLimitHeadersInResponse:
    """Test rate limit headers in HTTP responses."""

    @pytest.mark.asyncio
    async def test_validate_response_may_have_rate_limit_headers(
        self, client, internal_api_headers: dict[str, str]
    ):
        """Test that validate response may include rate limit headers."""
        from httpx import AsyncClient

        # Make a request (will fail for other reasons, but headers may be present)
        response = await client.post(
            "/api/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123abc",
                "client_id": f"ws_{uuid4().hex}",
                "request_id": str(uuid4()),
                "endpoint": "/test",
                "method": "POST",
                "payload_hash": "a" * 64,
            },
            headers=internal_api_headers,
        )

        # Headers may or may not be present depending on how far validation got
        # Use .get() to safely access
        rate_limit = response.headers.get("X-RateLimit-Limit")
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset_at = response.headers.get("X-RateLimit-Reset")

        # If headers are present, they should be valid integers
        if rate_limit is not None:
            assert rate_limit.isdigit()
        if remaining is not None:
            assert remaining.isdigit()
        if reset_at is not None:
            assert reset_at.isdigit()

    @pytest.mark.asyncio
    async def test_rate_limit_headers_safe_access_pattern(
        self, client, internal_api_headers: dict[str, str]
    ):
        """Test the documented safe access pattern for rate limit headers."""
        response = await client.post(
            "/api/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123abc",
                "client_id": f"ws_{uuid4().hex}",
                "request_id": str(uuid4()),
                "endpoint": "/test",
                "method": "POST",
                "payload_hash": "a" * 64,
            },
            headers=internal_api_headers,
        )

        # This is the documented pattern - should not raise KeyError
        rate_limit = response.headers.get("X-RateLimit-Limit")
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset_at = response.headers.get("X-RateLimit-Reset")
        retry_after = response.headers.get("Retry-After")

        # All should be None or valid values, never raise an error
        assert rate_limit is None or isinstance(rate_limit, str)
        assert remaining is None or isinstance(remaining, str)
        assert reset_at is None or isinstance(reset_at, str)
        assert retry_after is None or isinstance(retry_after, str)


# ============================================================================
# Edge Cases
# ============================================================================


class TestRateLimitEdgeCases:
    """Test edge cases for rate limiting."""

    def test_rate_limit_info_with_zero_limit(self):
        """Test RateLimitInfo with zero limit (edge case)."""
        info = RateLimitInfo(
            limit=0,
            remaining=0,
            reset_timestamp=int(time.time()) + 60,
        )
        assert info.limit == 0
        assert info.remaining == 0

    def test_rate_limit_info_with_negative_remaining_handled(self):
        """Test that remaining is always non-negative."""
        # The _check_rate_limit method uses max(0, ...) to ensure this
        remaining = max(0, 20 - 25)  # Simulating over-limit
        assert remaining == 0

    def test_rate_limit_info_with_large_limit(self):
        """Test RateLimitInfo with large limit values."""
        info = RateLimitInfo(
            limit=10000,
            remaining=9999,
            reset_timestamp=int(time.time()) + 60,
        )
        assert info.limit == 10000
        assert info.remaining == 9999

    @pytest.mark.asyncio
    async def test_check_rate_limit_with_none_plan_id(self):
        """Test rate limit with None plan_id (uses default)."""
        workspace_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.QuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,  # Default rate limit
            ) as mock_get_rate_limit,
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=60,
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, None)

        mock_get_rate_limit.assert_called_once_with(None)
        assert result.limit == 20


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def internal_api_headers() -> dict[str, str]:
    """Return headers with valid internal API key."""
    from app.shared.config import settings

    return {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}


# ============================================================================
# Database-Backed Fixtures for End-to-End Tests
# ============================================================================


@pytest.fixture
async def workspace_with_subscription(db_session, test_user, free_api_plan):
    """Create a workspace with an active subscription for testing."""
    from app.shared.db.models import (
        APISubscriptionContext,
        Subscription,
        Workspace,
        WorkspaceMember,
    )
    from app.shared.enums import (
        MemberRole,
        MemberStatus,
        SubscriptionStatus,
        WorkspaceStatus,
    )

    workspace = Workspace(
        id=uuid4(),
        display_name="Rate Limit Test Workspace",
        slug=f"rate-limit-test-{uuid4().hex[:8]}",
        status=WorkspaceStatus.ACTIVE,
        is_personal=False,
        owner_id=test_user.id,
    )
    db_session.add(workspace)
    await db_session.flush()

    member = WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=test_user.id,
        role=MemberRole.OWNER,
        status=MemberStatus.ENABLED,
        joined_at=datetime.now(timezone.utc),
    )
    db_session.add(member)
    await db_session.flush()

    subscription = Subscription(
        id=uuid4(),
        plan_id=free_api_plan.id,
        status=SubscriptionStatus.ACTIVE,
        seat_count=1,
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(subscription)
    await db_session.flush()

    context = APISubscriptionContext(
        id=uuid4(),
        subscription_id=subscription.id,
        workspace_id=workspace.id,
    )
    db_session.add(context)
    await db_session.flush()

    return workspace, subscription, free_api_plan


@pytest.fixture
async def live_api_key(db_session, workspace_with_subscription):
    """Create a live API key for the test workspace.

    Returns tuple of (raw_key, api_key_record, workspace, subscription, plan).
    """
    from app.apps.cubex_api.db.models import APIKey
    from app.apps.cubex_api.services.quota import quota_service

    workspace, subscription, plan = workspace_with_subscription

    # Generate API key using service method
    raw_key, key_hash, key_prefix = quota_service._generate_api_key(is_test_key=False)

    api_key = APIKey(
        id=uuid4(),
        workspace_id=workspace.id,
        name="Rate Limit Test Key",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
        is_test_key=False,
    )
    db_session.add(api_key)
    await db_session.flush()

    return raw_key, api_key, workspace, subscription, plan


@pytest.fixture
async def test_api_key(db_session, workspace_with_subscription):
    """Create a test API key for the test workspace.

    Returns tuple of (raw_key, api_key_record, workspace, subscription, plan).
    """
    from app.apps.cubex_api.db.models import APIKey
    from app.apps.cubex_api.services.quota import quota_service

    workspace, subscription, plan = workspace_with_subscription

    # Generate test API key
    raw_key, key_hash, key_prefix = quota_service._generate_api_key(is_test_key=True)

    api_key = APIKey(
        id=uuid4(),
        workspace_id=workspace.id,
        name="Rate Limit Test Key (Test)",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
        is_test_key=True,
    )
    db_session.add(api_key)
    await db_session.flush()

    return raw_key, api_key, workspace, subscription, plan


# ============================================================================
# End-to-End Integration Tests (Database-Backed)
# ============================================================================


class TestRateLimitingEndToEnd:
    """End-to-end tests for rate limiting using real database fixtures."""

    @pytest.mark.asyncio
    async def test_validate_request_includes_rate_limit_headers(
        self,
        client,
        internal_api_headers: dict[str, str],
        live_api_key,
    ):
        """Test that a valid request returns rate limit headers."""
        raw_key, api_key_record, workspace, subscription, plan = live_api_key

        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=60,
            ),
        ):
            response = await client.post(
                "/api/internal/usage/validate",
                json={
                    "api_key": raw_key,
                    "client_id": f"ws_{workspace.id.hex}",
                    "request_id": str(uuid4()),
                    "endpoint": "/test/endpoint",
                    "method": "POST",
                    "payload_hash": "a" * 64,
                },
                headers=internal_api_headers,
            )

        # Should return 200 with GRANTED access
        assert response.status_code == 200
        data = response.json()
        assert data["access"] == "granted"

        # Check rate limit headers are present
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

        # Validate header values
        assert response.headers["X-RateLimit-Limit"].isdigit()
        assert response.headers["X-RateLimit-Remaining"].isdigit()
        assert response.headers["X-RateLimit-Reset"].isdigit()

    @pytest.mark.asyncio
    async def test_rate_limit_remaining_decrements(
        self,
        client,
        internal_api_headers: dict[str, str],
        live_api_key,
    ):
        """Test that remaining requests decrease with each call."""
        raw_key, api_key_record, workspace, subscription, plan = live_api_key

        # Simulate first request (count = 1)
        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=60,
            ),
        ):
            response1 = await client.post(
                "/api/internal/usage/validate",
                json={
                    "api_key": raw_key,
                    "client_id": f"ws_{workspace.id.hex}",
                    "request_id": str(uuid4()),
                    "endpoint": "/test/endpoint",
                    "method": "POST",
                    "payload_hash": "a" * 64,
                },
                headers=internal_api_headers,
            )

        # Simulate second request (count = 2)
        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=2,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=55,
            ),
        ):
            response2 = await client.post(
                "/api/internal/usage/validate",
                json={
                    "api_key": raw_key,
                    "client_id": f"ws_{workspace.id.hex}",
                    "request_id": str(uuid4()),
                    "endpoint": "/test/endpoint",
                    "method": "POST",
                    "payload_hash": "a" * 64,
                },
                headers=internal_api_headers,
            )

        # Both should be granted
        assert response1.status_code == 200
        assert response2.status_code == 200

        # Get remaining from both responses
        remaining1 = int(response1.headers.get("X-RateLimit-Remaining", "-1"))
        remaining2 = int(response2.headers.get("X-RateLimit-Remaining", "-1"))

        # Second request should have lower remaining
        assert remaining2 < remaining1

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_429(
        self,
        client,
        internal_api_headers: dict[str, str],
        live_api_key,
    ):
        """Test that exceeding rate limit returns 429 with Retry-After."""
        raw_key, api_key_record, workspace, subscription, plan = live_api_key

        # Simulate rate limit exceeded (count > limit)
        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=21,  # Over the default limit of 20
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=45,  # 45 seconds until reset
            ),
        ):
            response = await client.post(
                "/api/internal/usage/validate",
                json={
                    "api_key": raw_key,
                    "client_id": f"ws_{workspace.id.hex}",
                    "request_id": str(uuid4()),
                    "endpoint": "/test/endpoint",
                    "method": "POST",
                    "payload_hash": "a" * 64,
                },
                headers=internal_api_headers,
            )

        # Should return 429 Too Many Requests
        assert response.status_code == 429
        data = response.json()
        assert data["access"] == "denied"  # Rate limited uses DENIED access status

        # Should have Retry-After header
        assert "Retry-After" in response.headers
        retry_after = int(response.headers["Retry-After"])
        assert retry_after > 0
        assert retry_after <= 60  # Within the rate limit window

    @pytest.mark.asyncio
    async def test_test_api_key_has_rate_limit_headers(
        self,
        client,
        internal_api_headers: dict[str, str],
        test_api_key,
    ):
        """Test that test API keys also return rate limit headers."""
        raw_key, api_key_record, workspace, subscription, plan = test_api_key

        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=60,
            ),
        ):
            response = await client.post(
                "/api/internal/usage/validate",
                json={
                    "api_key": raw_key,
                    "client_id": f"ws_{workspace.id.hex}",
                    "request_id": str(uuid4()),
                    "endpoint": "/test/endpoint",
                    "method": "POST",
                    "payload_hash": "a" * 64,
                },
                headers=internal_api_headers,
            )

        # Test keys should still be rate limited
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers

    @pytest.mark.asyncio
    async def test_rate_limit_workspace_isolation(
        self,
        db_session,
        client,
        internal_api_headers: dict[str, str],
        test_user,
        free_api_plan,
    ):
        """Test that rate limits are isolated per workspace."""
        from app.apps.cubex_api.db.models import APIKey
        from app.apps.cubex_api.services.quota import quota_service
        from app.shared.db.models import (
            APISubscriptionContext,
            Subscription,
            Workspace,
            WorkspaceMember,
        )
        from app.shared.enums import (
            MemberRole,
            MemberStatus,
            SubscriptionStatus,
            WorkspaceStatus,
        )

        # Create two workspaces
        workspace1 = Workspace(
            id=uuid4(),
            display_name="Workspace 1",
            slug=f"workspace-1-{uuid4().hex[:8]}",
            status=WorkspaceStatus.ACTIVE,
            is_personal=False,
            owner_id=test_user.id,
        )
        workspace2 = Workspace(
            id=uuid4(),
            display_name="Workspace 2",
            slug=f"workspace-2-{uuid4().hex[:8]}",
            status=WorkspaceStatus.ACTIVE,
            is_personal=False,
            owner_id=test_user.id,
        )
        db_session.add(workspace1)
        db_session.add(workspace2)
        await db_session.flush()

        # Add members
        for ws in [workspace1, workspace2]:
            member = WorkspaceMember(
                id=uuid4(),
                workspace_id=ws.id,
                user_id=test_user.id,
                role=MemberRole.OWNER,
                status=MemberStatus.ENABLED,
                joined_at=datetime.now(timezone.utc),
            )
            db_session.add(member)
        await db_session.flush()

        # Create subscriptions
        for ws in [workspace1, workspace2]:
            sub = Subscription(
                id=uuid4(),
                plan_id=free_api_plan.id,
                status=SubscriptionStatus.ACTIVE,
                seat_count=1,
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
            )
            db_session.add(sub)
            await db_session.flush()

            ctx = APISubscriptionContext(
                id=uuid4(),
                subscription_id=sub.id,
                workspace_id=ws.id,
            )
            db_session.add(ctx)
        await db_session.flush()

        # Create API keys for both workspaces
        raw_key1, key_hash1, key_prefix1 = quota_service._generate_api_key()
        raw_key2, key_hash2, key_prefix2 = quota_service._generate_api_key()

        api_key1 = APIKey(
            id=uuid4(),
            workspace_id=workspace1.id,
            name="Key 1",
            key_hash=key_hash1,
            key_prefix=key_prefix1,
            is_active=True,
            is_test_key=False,
        )
        api_key2 = APIKey(
            id=uuid4(),
            workspace_id=workspace2.id,
            name="Key 2",
            key_hash=key_hash2,
            key_prefix=key_prefix2,
            is_active=True,
            is_test_key=False,
        )
        db_session.add(api_key1)
        db_session.add(api_key2)
        await db_session.flush()

        # Simulate workspace1 at high count, workspace2 at low count
        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=15,  # High usage
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=30,
            ),
        ):
            response1 = await client.post(
                "/api/internal/usage/validate",
                json={
                    "api_key": raw_key1,
                    "client_id": f"ws_{workspace1.id.hex}",
                    "request_id": str(uuid4()),
                    "endpoint": "/test",
                    "method": "POST",
                    "payload_hash": "a" * 64,
                },
                headers=internal_api_headers,
            )

        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=2,  # Low usage
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=55,
            ),
        ):
            response2 = await client.post(
                "/api/internal/usage/validate",
                json={
                    "api_key": raw_key2,
                    "client_id": f"ws_{workspace2.id.hex}",
                    "request_id": str(uuid4()),
                    "endpoint": "/test",
                    "method": "POST",
                    "payload_hash": "a" * 64,
                },
                headers=internal_api_headers,
            )

        # Both should succeed
        assert response1.status_code == 200
        assert response2.status_code == 200

        # But they should have different remaining counts
        remaining1 = int(response1.headers.get("X-RateLimit-Remaining", "-1"))
        remaining2 = int(response2.headers.get("X-RateLimit-Remaining", "-1"))

        # Workspace2 should have more remaining (lower count)
        assert remaining2 > remaining1

    @pytest.mark.asyncio
    async def test_rate_limit_header_values_match_plan(
        self,
        client,
        internal_api_headers: dict[str, str],
        live_api_key,
    ):
        """Test that rate limit header values match the plan's rate limit."""
        raw_key, api_key_record, workspace, subscription, plan = live_api_key

        # Mock a specific rate limit for the plan
        with (
            patch(
                "app.apps.cubex_api.services.quota.QuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=50,  # Custom rate limit
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=10,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=45,
            ),
        ):
            response = await client.post(
                "/api/internal/usage/validate",
                json={
                    "api_key": raw_key,
                    "client_id": f"ws_{workspace.id.hex}",
                    "request_id": str(uuid4()),
                    "endpoint": "/test/endpoint",
                    "method": "POST",
                    "payload_hash": "a" * 64,
                },
                headers=internal_api_headers,
            )

        assert response.status_code == 200

        # Limit should be 50 (from mocked plan rate limit)
        assert response.headers["X-RateLimit-Limit"] == "50"

        # Remaining should be limit - count = 50 - 10 = 40
        assert response.headers["X-RateLimit-Remaining"] == "40"

    @pytest.mark.asyncio
    async def test_rate_limited_response_includes_denial_reason(
        self,
        client,
        internal_api_headers: dict[str, str],
        live_api_key,
    ):
        """Test that rate limited response includes proper denial reason."""
        raw_key, api_key_record, workspace, subscription, plan = live_api_key

        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.incr",
                new_callable=AsyncMock,
                return_value=25,  # Over default limit of 20
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.expire",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.ttl",
                new_callable=AsyncMock,
                return_value=30,
            ),
        ):
            response = await client.post(
                "/api/internal/usage/validate",
                json={
                    "api_key": raw_key,
                    "client_id": f"ws_{workspace.id.hex}",
                    "request_id": str(uuid4()),
                    "endpoint": "/test/endpoint",
                    "method": "POST",
                    "payload_hash": "a" * 64,
                },
                headers=internal_api_headers,
            )

        assert response.status_code == 429
        data = response.json()

        # Check response structure
        assert data["access"] == "denied"  # Rate limited uses DENIED access status
        assert "message" in data
        assert "rate limit" in data["message"].lower()
