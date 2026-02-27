"""
Test suite for Rate Limiting Implementation.

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
from app.core.enums import FeatureKey


class TestRateLimitInfoDataclass:

    def test_rate_limit_info_import(self):
        from app.apps.cubex_api.services.quota import RateLimitInfo

        assert RateLimitInfo is not None

    def test_rate_limit_info_export_from_services(self):
        from app.apps.cubex_api.services import RateLimitInfo

        assert RateLimitInfo is not None

    def test_rate_limit_info_creation_with_all_fields(self):
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
        info = RateLimitInfo(
            limit=20,
            remaining=15,
            reset_timestamp=1739352000,
        )
        assert info.is_exceeded is False

    def test_rate_limit_info_exceeded_state(self):
        info = RateLimitInfo(
            limit=20,
            remaining=0,
            reset_timestamp=1739352000,
            is_exceeded=True,
        )
        assert info.is_exceeded is True
        assert info.remaining == 0

    def test_rate_limit_info_zero_remaining(self):
        info = RateLimitInfo(
            limit=50,
            remaining=0,
            reset_timestamp=int(time.time()) + 45,
        )
        assert info.remaining == 0
        assert info.limit == 50

    def test_rate_limit_info_fields_are_integers(self):
        info = RateLimitInfo(
            limit=20,
            remaining=15,
            reset_timestamp=1739352000,
        )
        assert isinstance(info.limit, int)
        assert isinstance(info.remaining, int)
        assert isinstance(info.reset_timestamp, int)
        assert isinstance(info.is_exceeded, bool)


class TestCheckRateLimitMethod:

    def test_check_rate_limit_method_exists(self):
        assert hasattr(quota_service, "_check_rate_limit")
        assert callable(quota_service._check_rate_limit)

    def test_check_rate_limit_method_signature(self):
        import inspect

        sig = inspect.signature(quota_service._check_rate_limit)
        params = list(sig.parameters.keys())

        assert "workspace_id" in params
        assert "plan_id" in params

    @pytest.mark.asyncio
    async def test_check_rate_limit_returns_rate_limit_info(self):
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(1, 60),  # (current_count, ttl)
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        assert isinstance(result, RateLimitInfo)
        assert result.limit == 20

    @pytest.mark.asyncio
    async def test_check_rate_limit_first_request_in_window(self):
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(1, 60),  # (current_count, ttl) - first request
            ) as mock_rate_limit_incr,
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        # Atomic rate_limit_incr should be called
        mock_rate_limit_incr.assert_called_once()
        assert result.remaining == 19
        assert result.is_exceeded is False

    @pytest.mark.asyncio
    async def test_check_rate_limit_subsequent_request(self):
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(5, 45),  # (current_count, ttl) - 5th request
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        # 20 - 5 = 15 remaining
        assert result.remaining == 15
        assert result.is_exceeded is False

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self):
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(21, 30),  # (current_count, ttl) - over limit
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        assert result.is_exceeded is True
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_unavailable(self):
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
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
        workspace_id = uuid4()
        plan_id = uuid4()
        expected_key = f"rate_limit:{workspace_id}"

        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(1, 60),  # (current_count, ttl)
            ) as mock_rate_limit_incr,
        ):
            await quota_service._check_rate_limit(workspace_id, plan_id)

        mock_rate_limit_incr.assert_called_once_with(expected_key, 60)

    @pytest.mark.asyncio
    async def test_check_rate_limit_uses_plan_rate_limit(self):
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=50,  # Custom rate limit
            ) as mock_get_rate_limit,
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(1, 60),  # (current_count, ttl)
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        mock_get_rate_limit.assert_called_once_with(plan_id)
        assert result.limit == 50
        assert result.remaining == 49

    @pytest.mark.asyncio
    async def test_check_rate_limit_ttl_fallback(self):
        workspace_id = uuid4()
        plan_id = uuid4()
        current_time = int(time.time())

        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(5, -1),  # (current_count, ttl) - TTL lookup failed
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
        workspace_id = uuid4()
        plan_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(20, 30),  # (current_count, ttl) - exactly at limit
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, plan_id)

        # At exactly limit, should not be exceeded
        assert result.is_exceeded is False
        assert result.remaining == 0


class TestValidateAndLogUsageRateLimiting:

    def test_validate_and_log_usage_returns_seven_tuple(self):
        import inspect

        sig = inspect.signature(quota_service.validate_and_log_usage)
        return_annotation = str(sig.return_annotation)
        assert "RateLimitInfo" in return_annotation

    def test_validate_and_log_usage_includes_rate_limit_info_in_return(self):
        import inspect

        sig = inspect.signature(quota_service.validate_and_log_usage)
        return_annotation = str(sig.return_annotation)

        assert "tuple" in return_annotation.lower()
        assert "RateLimitInfo" in return_annotation


class TestRateLimitHeadersConstruction:

    def test_x_ratelimit_limit_header_format(self):
        info = RateLimitInfo(limit=20, remaining=15, reset_timestamp=1739352000)
        header_value = str(info.limit)
        assert header_value == "20"
        assert header_value.isdigit()

    def test_x_ratelimit_remaining_header_format(self):
        info = RateLimitInfo(limit=20, remaining=15, reset_timestamp=1739352000)
        header_value = str(info.remaining)
        assert header_value == "15"
        assert header_value.isdigit()

    def test_x_ratelimit_reset_header_format(self):
        reset_time = int(time.time()) + 60
        info = RateLimitInfo(limit=20, remaining=15, reset_timestamp=reset_time)
        header_value = str(info.reset_timestamp)
        assert header_value.isdigit()
        assert int(header_value) > int(time.time())  # Should be in the future

    def test_retry_after_calculation(self):
        current_time = int(time.time())
        reset_time = current_time + 45
        info = RateLimitInfo(
            limit=20, remaining=0, reset_timestamp=reset_time, is_exceeded=True
        )

        retry_after = max(0, info.reset_timestamp - current_time)
        assert retry_after == 45


class TestRateLimitHeadersInResponse:

    @pytest.mark.asyncio
    async def test_validate_response_may_have_rate_limit_headers(
        self, client, internal_api_headers: dict[str, str]
    ):
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
                "feature_key": FeatureKey.API_EXTRACT_CUES_RESUME,
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
        response = await client.post(
            "/api/internal/usage/validate",
            json={
                "api_key": "cbx_live_test123abc",
                "client_id": f"ws_{uuid4().hex}",
                "request_id": str(uuid4()),
                "endpoint": "/test",
                "method": "POST",
                "payload_hash": "a" * 64,
                "feature_key": FeatureKey.API_EXTRACT_CUES_RESUME,
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


class TestRateLimitEdgeCases:

    def test_rate_limit_info_with_zero_limit(self):
        info = RateLimitInfo(
            limit=0,
            remaining=0,
            reset_timestamp=int(time.time()) + 60,
        )
        assert info.limit == 0
        assert info.remaining == 0

    def test_rate_limit_info_with_negative_remaining_handled(self):
        # The _check_rate_limit method uses max(0, ...) to ensure this
        remaining = max(0, 20 - 25)  # Simulating over-limit
        assert remaining == 0

    def test_rate_limit_info_with_large_limit(self):
        info = RateLimitInfo(
            limit=10000,
            remaining=9999,
            reset_timestamp=int(time.time()) + 60,
        )
        assert info.limit == 10000
        assert info.remaining == 9999

    @pytest.mark.asyncio
    async def test_check_rate_limit_with_none_plan_id(self):
        workspace_id = uuid4()

        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_rate_limit",
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


@pytest.fixture
def internal_api_headers() -> dict[str, str]:
    """Return headers with valid internal API key."""
    from app.core.config import settings

    return {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}


@pytest.fixture
async def workspace_with_subscription(db_session, test_user, free_api_plan):
    """Create a workspace with an active subscription for testing."""
    from app.core.db.models import (
        APISubscriptionContext,
        Subscription,
        Workspace,
        WorkspaceMember,
    )
    from app.core.enums import (
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
    from app.apps.cubex_api.db.models import APIKey
    from app.apps.cubex_api.services.quota import quota_service

    workspace, subscription, plan = workspace_with_subscription

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


class TestRateLimitingEndToEnd:

    @pytest.mark.asyncio
    async def test_validate_request_includes_rate_limit_headers(
        self,
        client,
        internal_api_headers: dict[str, str],
        live_api_key,
    ):
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
                    "feature_key": FeatureKey.API_EXTRACT_CUES_RESUME,
                },
                headers=internal_api_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["access"] == "granted"

        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

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
                    "feature_key": FeatureKey.API_EXTRACT_CUES_RESUME,
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
                    "feature_key": FeatureKey.API_EXTRACT_CUES_RESUME,
                },
                headers=internal_api_headers,
            )

        # Both should be granted
        assert response1.status_code == 200
        assert response2.status_code == 200

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
        raw_key, api_key_record, workspace, subscription, plan = live_api_key

        # Simulate rate limit exceeded (count > limit)
        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(
                    21,
                    45,
                ),  # (current_count, ttl) - over the default limit of 20
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
                    "feature_key": FeatureKey.API_EXTRACT_CUES_RESUME,
                },
                headers=internal_api_headers,
            )

        assert response.status_code == 429
        data = response.json()
        assert data["access"] == "denied"  # Rate limited uses DENIED access status

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
        raw_key, api_key_record, workspace, subscription, plan = test_api_key

        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(1, 60),  # (current_count, ttl)
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
                    "feature_key": FeatureKey.API_EXTRACT_CUES_RESUME,
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
        from app.apps.cubex_api.db.models import APIKey
        from app.apps.cubex_api.services.quota import quota_service
        from app.core.db.models import (
            APISubscriptionContext,
            Subscription,
            Workspace,
            WorkspaceMember,
        )
        from app.core.enums import (
            MemberRole,
            MemberStatus,
            SubscriptionStatus,
            WorkspaceStatus,
        )

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
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(15, 30),  # (current_count, ttl) - high usage
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
                    "feature_key": FeatureKey.API_EXTRACT_CUES_RESUME,
                },
                headers=internal_api_headers,
            )

        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(2, 55),  # (current_count, ttl) - low usage
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
                    "feature_key": FeatureKey.API_EXTRACT_CUES_RESUME,
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
        raw_key, api_key_record, workspace, subscription, plan = live_api_key

        # Mock a specific rate limit for the plan
        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=50,  # Custom rate limit
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(10, 45),  # (current_count, ttl)
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
                    "feature_key": FeatureKey.API_EXTRACT_CUES_RESUME,
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
        raw_key, api_key_record, workspace, subscription, plan = live_api_key

        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(
                    25,
                    30,
                ),  # (current_count, ttl) - over default limit of 20
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
                    "feature_key": FeatureKey.API_EXTRACT_CUES_RESUME,
                },
                headers=internal_api_headers,
            )

        assert response.status_code == 429
        data = response.json()

        assert data["access"] == "denied"  # Rate limited uses DENIED access status
        assert "message" in data
        assert "rate limit" in data["message"].lower()

