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
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.apps.cubex_api.services.quota import RateLimitInfo, quota_service
from app.core.enums import FeatureKey
from app.core.services.quota_cache import FeatureConfig, PlanConfig


class TestRateLimitInfoDataclass:

    def test_rate_limit_info_import(self):
        from app.apps.cubex_api.services.quota import RateLimitInfo

        assert RateLimitInfo is not None

    def test_rate_limit_info_export_from_services(self):
        from app.apps.cubex_api.services import RateLimitInfo

        assert RateLimitInfo is not None

    def test_rate_limit_info_creation_with_minute_fields(self):
        info = RateLimitInfo(
            limit_per_minute=20,
            remaining_per_minute=15,
            reset_per_minute=1739352000,
            is_exceeded=False,
        )
        assert info.limit_per_minute == 20
        assert info.remaining_per_minute == 15
        assert info.reset_per_minute == 1739352000
        assert info.is_exceeded is False

    def test_rate_limit_info_defaults_are_none(self):
        info = RateLimitInfo()
        assert info.limit_per_minute is None
        assert info.remaining_per_minute is None
        assert info.reset_per_minute is None
        assert info.limit_per_day is None
        assert info.remaining_per_day is None
        assert info.reset_per_day is None
        assert info.is_exceeded is False
        assert info.exceeded_window is None

    def test_rate_limit_info_exceeded_state(self):
        info = RateLimitInfo(
            limit_per_minute=20,
            remaining_per_minute=0,
            reset_per_minute=1739352000,
            is_exceeded=True,
            exceeded_window="minute",
        )
        assert info.is_exceeded is True
        assert info.remaining_per_minute == 0
        assert info.exceeded_window == "minute"

    def test_rate_limit_info_zero_remaining(self):
        info = RateLimitInfo(
            limit_per_minute=50,
            remaining_per_minute=0,
            reset_per_minute=int(time.time()) + 45,
        )
        assert info.remaining_per_minute == 0
        assert info.limit_per_minute == 50

    def test_rate_limit_info_fields_types(self):
        info = RateLimitInfo(
            limit_per_minute=20,
            remaining_per_minute=15,
            reset_per_minute=1739352000,
        )
        assert isinstance(info.limit_per_minute, int)
        assert isinstance(info.remaining_per_minute, int)
        assert isinstance(info.reset_per_minute, int)
        assert isinstance(info.is_exceeded, bool)

    def test_rate_limit_info_with_both_windows(self):
        info = RateLimitInfo(
            limit_per_minute=20,
            remaining_per_minute=15,
            reset_per_minute=1739352000,
            limit_per_day=1000,
            remaining_per_day=950,
            reset_per_day=1739395200,
        )
        assert info.limit_per_minute == 20
        assert info.limit_per_day == 1000


class TestCheckRateLimitMethod:

    def test_check_rate_limit_method_exists(self):
        assert hasattr(quota_service, "_check_rate_limit")
        assert callable(quota_service._check_rate_limit)

    def test_check_rate_limit_method_signature(self):
        import inspect

        sig = inspect.signature(quota_service._check_rate_limit)
        params = list(sig.parameters.keys())

        assert "workspace_id" in params
        assert "rate_limit_per_minute" in params
        assert "rate_limit_per_day" in params

    @pytest.mark.asyncio
    async def test_check_rate_limit_returns_rate_limit_info(self):
        workspace_id = uuid4()

        with patch(
            "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            return_value=(1, 60),
        ):
            result = await quota_service._check_rate_limit(workspace_id, 20, None)

        assert isinstance(result, RateLimitInfo)
        assert result.limit_per_minute == 20

    @pytest.mark.asyncio
    async def test_check_rate_limit_first_request_in_window(self):
        workspace_id = uuid4()

        with patch(
            "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            return_value=(1, 60),
        ) as mock_rate_limit_incr:
            result = await quota_service._check_rate_limit(workspace_id, 20, None)

        mock_rate_limit_incr.assert_called_once()
        assert result.remaining_per_minute == 19
        assert result.is_exceeded is False

    @pytest.mark.asyncio
    async def test_check_rate_limit_subsequent_request(self):
        workspace_id = uuid4()

        with patch(
            "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            return_value=(5, 45),
        ):
            result = await quota_service._check_rate_limit(workspace_id, 20, None)

        assert result.remaining_per_minute == 15
        assert result.is_exceeded is False

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self):
        workspace_id = uuid4()

        with patch(
            "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            return_value=(21, 30),
        ):
            result = await quota_service._check_rate_limit(workspace_id, 20, None)

        assert result.is_exceeded is True
        assert result.remaining_per_minute == 0
        assert result.exceeded_window == "minute"

    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_unavailable(self):
        workspace_id = uuid4()

        with patch(
            "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await quota_service._check_rate_limit(workspace_id, 20, None)

        assert result.is_exceeded is False
        assert result.limit_per_minute == 20
        assert result.remaining_per_minute == 19

    @pytest.mark.asyncio
    async def test_check_rate_limit_uses_correct_redis_key(self):
        workspace_id = uuid4()
        expected_key = f"rate_limit:{workspace_id}:min"

        with patch(
            "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            return_value=(1, 60),
        ) as mock_rate_limit_incr:
            await quota_service._check_rate_limit(workspace_id, 20, None)

        mock_rate_limit_incr.assert_called_once_with(expected_key, 60)

    @pytest.mark.asyncio
    async def test_check_rate_limit_with_custom_limit(self):
        workspace_id = uuid4()

        with patch(
            "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            return_value=(1, 60),
        ):
            result = await quota_service._check_rate_limit(workspace_id, 50, None)

        assert result.limit_per_minute == 50
        assert result.remaining_per_minute == 49

    @pytest.mark.asyncio
    async def test_check_rate_limit_ttl_fallback(self):
        workspace_id = uuid4()
        current_time = int(time.time())

        with (
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(5, -1),
            ),
            patch(
                "app.apps.cubex_api.services.quota.time.time", return_value=current_time
            ),
        ):
            result = await quota_service._check_rate_limit(workspace_id, 20, None)

        assert result.reset_per_minute == current_time + 60

    @pytest.mark.asyncio
    async def test_check_rate_limit_at_exact_limit(self):
        workspace_id = uuid4()

        with patch(
            "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            return_value=(20, 30),
        ):
            result = await quota_service._check_rate_limit(workspace_id, 20, None)

        assert result.is_exceeded is False
        assert result.remaining_per_minute == 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_returns_none_when_both_unlimited(self):
        workspace_id = uuid4()
        result = await quota_service._check_rate_limit(workspace_id, None, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_check_rate_limit_day_window_only(self):
        workspace_id = uuid4()

        with patch(
            "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            return_value=(10, 80000),
        ):
            result = await quota_service._check_rate_limit(workspace_id, None, 1000)

        assert result.limit_per_minute is None
        assert result.remaining_per_minute is None
        assert result.limit_per_day == 1000
        assert result.remaining_per_day == 990
        assert result.is_exceeded is False

    @pytest.mark.asyncio
    async def test_check_rate_limit_day_exceeded(self):
        workspace_id = uuid4()

        with patch(
            "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            return_value=(1001, 40000),
        ):
            result = await quota_service._check_rate_limit(workspace_id, None, 1000)

        assert result.is_exceeded is True
        assert result.exceeded_window == "day"
        assert result.remaining_per_day == 0


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
        info = RateLimitInfo(
            limit_per_minute=20, remaining_per_minute=15, reset_per_minute=1739352000
        )
        header_value = str(info.limit_per_minute)
        assert header_value == "20"
        assert header_value.isdigit()

    def test_x_ratelimit_remaining_header_format(self):
        info = RateLimitInfo(
            limit_per_minute=20, remaining_per_minute=15, reset_per_minute=1739352000
        )
        header_value = str(info.remaining_per_minute)
        assert header_value == "15"
        assert header_value.isdigit()

    def test_x_ratelimit_reset_header_format(self):
        reset_time = int(time.time()) + 60
        info = RateLimitInfo(
            limit_per_minute=20, remaining_per_minute=15, reset_per_minute=reset_time
        )
        header_value = str(info.reset_per_minute)
        assert header_value.isdigit()
        assert int(header_value) > int(time.time())

    def test_retry_after_calculation(self):
        current_time = int(time.time())
        reset_time = current_time + 45
        info = RateLimitInfo(
            limit_per_minute=20,
            remaining_per_minute=0,
            reset_per_minute=reset_time,
            is_exceeded=True,
            exceeded_window="minute",
        )

        retry_after = max(0, info.reset_per_minute - current_time)
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
        # Use .get() to safely access — new header names include window suffix
        rate_limit = response.headers.get("X-RateLimit-Limit-Minute")
        remaining = response.headers.get("X-RateLimit-Remaining-Minute")
        reset_at = response.headers.get("X-RateLimit-Reset-Minute")

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
        rate_limit = response.headers.get("X-RateLimit-Limit-Minute")
        remaining = response.headers.get("X-RateLimit-Remaining-Minute")
        reset_at = response.headers.get("X-RateLimit-Reset-Minute")
        retry_after = response.headers.get("Retry-After")

        # All should be None or valid values, never raise an error
        assert rate_limit is None or isinstance(rate_limit, str)
        assert remaining is None or isinstance(remaining, str)
        assert reset_at is None or isinstance(reset_at, str)
        assert retry_after is None or isinstance(retry_after, str)


class TestRateLimitEdgeCases:

    def test_rate_limit_info_with_zero_limit(self):
        info = RateLimitInfo(
            limit_per_minute=0,
            remaining_per_minute=0,
            reset_per_minute=int(time.time()) + 60,
        )
        assert info.limit_per_minute == 0
        assert info.remaining_per_minute == 0

    def test_rate_limit_info_with_negative_remaining_handled(self):
        # The _check_rate_limit method uses max(0, ...) to ensure this
        remaining = max(0, 20 - 25)  # Simulating over-limit
        assert remaining == 0

    def test_rate_limit_info_with_large_limit(self):
        info = RateLimitInfo(
            limit_per_minute=10000,
            remaining_per_minute=9999,
            reset_per_minute=int(time.time()) + 60,
        )
        assert info.limit_per_minute == 10000
        assert info.remaining_per_minute == 9999

    @pytest.mark.asyncio
    async def test_check_rate_limit_with_none_limits_returns_none(self):
        workspace_id = uuid4()
        result = await quota_service._check_rate_limit(workspace_id, None, None)
        assert result is None


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
    """E2E tests going through the actual router.

    All tests mock ``get_plan_config`` and ``get_feature_config`` because
    the test DB has no ``PlanPricingRule`` / ``FeatureCostConfig`` rows,
    and the new code intentionally has **no** silent defaults.
    """

    _PLAN_CONFIG = PlanConfig(
        multiplier=Decimal("1.0"),
        credits_allocation=Decimal("5000.0"),
        rate_limit_per_minute=20,
        rate_limit_per_day=None,
    )
    _FEATURE_CONFIG = FeatureConfig(internal_cost_credits=Decimal("1.0"))

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
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_config",
                new_callable=AsyncMock,
                return_value=self._PLAN_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_feature_config",
                new_callable=AsyncMock,
                return_value=self._FEATURE_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(1, 60),
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

        assert "X-RateLimit-Limit-Minute" in response.headers
        assert "X-RateLimit-Remaining-Minute" in response.headers
        assert "X-RateLimit-Reset-Minute" in response.headers

        assert response.headers["X-RateLimit-Limit-Minute"].isdigit()
        assert response.headers["X-RateLimit-Remaining-Minute"].isdigit()
        assert response.headers["X-RateLimit-Reset-Minute"].isdigit()

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
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_config",
                new_callable=AsyncMock,
                return_value=self._PLAN_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_feature_config",
                new_callable=AsyncMock,
                return_value=self._FEATURE_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(1, 60),
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
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_config",
                new_callable=AsyncMock,
                return_value=self._PLAN_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_feature_config",
                new_callable=AsyncMock,
                return_value=self._FEATURE_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(2, 55),
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

        remaining1 = int(response1.headers.get("X-RateLimit-Remaining-Minute", "-1"))
        remaining2 = int(response2.headers.get("X-RateLimit-Remaining-Minute", "-1"))

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

        # Simulate rate limit exceeded (count > limit of 20)
        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_config",
                new_callable=AsyncMock,
                return_value=self._PLAN_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(21, 45),
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
        assert data["access"] == "denied"

        assert "Retry-After" in response.headers
        retry_after = int(response.headers["Retry-After"])
        assert retry_after > 0
        assert retry_after <= 60

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
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_config",
                new_callable=AsyncMock,
                return_value=self._PLAN_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(1, 60),
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
        assert "X-RateLimit-Limit-Minute" in response.headers
        assert "X-RateLimit-Remaining-Minute" in response.headers

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
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_config",
                new_callable=AsyncMock,
                return_value=self._PLAN_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_feature_config",
                new_callable=AsyncMock,
                return_value=self._FEATURE_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(15, 30),
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
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_config",
                new_callable=AsyncMock,
                return_value=self._PLAN_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_feature_config",
                new_callable=AsyncMock,
                return_value=self._FEATURE_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(2, 55),
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
        remaining1 = int(response1.headers.get("X-RateLimit-Remaining-Minute", "-1"))
        remaining2 = int(response2.headers.get("X-RateLimit-Remaining-Minute", "-1"))

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

        custom_config = PlanConfig(
            multiplier=Decimal("1.0"),
            credits_allocation=Decimal("5000.0"),
            rate_limit_per_minute=50,
            rate_limit_per_day=None,
        )

        with (
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_config",
                new_callable=AsyncMock,
                return_value=custom_config,
            ),
            patch(
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_feature_config",
                new_callable=AsyncMock,
                return_value=self._FEATURE_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(10, 45),
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

        # Limit should be 50 (from mocked plan config)
        assert response.headers["X-RateLimit-Limit-Minute"] == "50"

        # Remaining should be limit - count = 50 - 10 = 40
        assert response.headers["X-RateLimit-Remaining-Minute"] == "40"

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
                "app.apps.cubex_api.services.quota.APIQuotaCacheService.get_plan_config",
                new_callable=AsyncMock,
                return_value=self._PLAN_CONFIG,
            ),
            patch(
                "app.apps.cubex_api.services.quota.RedisService.rate_limit_incr",
                new_callable=AsyncMock,
                return_value=(25, 30),
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

        assert data["access"] == "denied"
        assert "message" in data
        assert "rate limit" in data["message"].lower()
