"""
Test suite for CareerQuotaService.

- RateLimitInfo dataclass
- CareerQuotaService initialization and methods
- Billing period calculation
- Rate limiting (per-minute and per-day)
- Idempotency checking
- Quota checking
- Usage validation and logging
- Usage committing
- Schema validation (UsageValidateRequest, UsageCommitRequest, etc.)
- Model and CRUD integration

Run all tests:
    pytest tests/apps/cubex_career/test_quota_service.py -v

Run with coverage:
    pytest tests/apps/cubex_career/test_quota_service.py \
        --cov=app.apps.cubex_career.services.quota \
        --cov-report=term-missing -v
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.enums import AccessStatus, FailureType, FeatureKey


class TestRateLimitInfoDataclass:

    def test_rate_limit_info_import(self):
        from app.apps.cubex_career.services.quota import RateLimitInfo

        assert RateLimitInfo is not None

    def test_rate_limit_info_creation_with_all_fields(self):
        from app.apps.cubex_career.services.quota import RateLimitInfo

        info = RateLimitInfo(
            limit_per_minute=20,
            remaining_per_minute=15,
            reset_per_minute=1739352000,
            limit_per_day=500,
            remaining_per_day=450,
            reset_per_day=1739400000,
            is_exceeded=False,
            exceeded_window=None,
        )
        assert info.limit_per_minute == 20
        assert info.remaining_per_minute == 15
        assert info.reset_per_minute == 1739352000
        assert info.limit_per_day == 500
        assert info.remaining_per_day == 450
        assert info.reset_per_day == 1739400000
        assert info.is_exceeded is False
        assert info.exceeded_window is None

    def test_rate_limit_info_defaults(self):
        from app.apps.cubex_career.services.quota import RateLimitInfo

        info = RateLimitInfo(
            limit_per_minute=20,
            remaining_per_minute=15,
            reset_per_minute=1739352000,
            limit_per_day=500,
            remaining_per_day=450,
            reset_per_day=1739400000,
        )
        assert info.is_exceeded is False
        assert info.exceeded_window is None

    def test_rate_limit_info_all_fields_optional(self):
        from app.apps.cubex_career.services.quota import RateLimitInfo

        info = RateLimitInfo()
        assert info.limit_per_minute is None
        assert info.remaining_per_minute is None
        assert info.reset_per_minute is None
        assert info.limit_per_day is None
        assert info.remaining_per_day is None
        assert info.reset_per_day is None
        assert info.is_exceeded is False
        assert info.exceeded_window is None

    def test_rate_limit_info_exceeded_minute(self):
        from app.apps.cubex_career.services.quota import RateLimitInfo

        info = RateLimitInfo(
            limit_per_minute=20,
            remaining_per_minute=0,
            reset_per_minute=1739352000,
            limit_per_day=500,
            remaining_per_day=400,
            reset_per_day=1739400000,
            is_exceeded=True,
            exceeded_window="minute",
        )
        assert info.is_exceeded is True
        assert info.exceeded_window == "minute"
        assert info.remaining_per_minute == 0

    def test_rate_limit_info_exceeded_day(self):
        from app.apps.cubex_career.services.quota import RateLimitInfo

        info = RateLimitInfo(
            limit_per_minute=20,
            remaining_per_minute=10,
            reset_per_minute=1739352000,
            limit_per_day=500,
            remaining_per_day=0,
            reset_per_day=1739400000,
            is_exceeded=True,
            exceeded_window="day",
        )
        assert info.is_exceeded is True
        assert info.exceeded_window == "day"
        assert info.remaining_per_day == 0


class TestCareerQuotaServiceInit:

    def test_service_import(self):
        from app.apps.cubex_career.services.quota import CareerQuotaService

        assert CareerQuotaService is not None

    def test_service_singleton_exists(self):
        from app.apps.cubex_career.services.quota import career_quota_service

        assert career_quota_service is not None

    def test_service_exports_from_init(self):
        from app.apps.cubex_career.services import (
            CareerQuotaService,
            career_quota_service,
        )

        assert CareerQuotaService is not None
        assert career_quota_service is not None


class TestCareerQuotaServiceMethods:

    @pytest.fixture
    def service(self):
        """Get CareerQuotaService instance."""
        from app.apps.cubex_career.services.quota import CareerQuotaService

        return CareerQuotaService()

    def test_has_validate_and_log_usage_method(self, service):
        assert hasattr(service, "validate_and_log_usage")
        assert callable(service.validate_and_log_usage)

    def test_has_commit_usage_method(self, service):
        assert hasattr(service, "commit_usage")
        assert callable(service.commit_usage)

    def test_has_check_rate_limit_method(self, service):
        assert hasattr(service, "_check_rate_limit")
        assert callable(service._check_rate_limit)

    def test_has_check_idempotency_method(self, service):
        assert hasattr(service, "_check_idempotency")
        assert callable(service._check_idempotency)

    def test_has_check_quota_method(self, service):
        assert hasattr(service, "_check_quota")
        assert callable(service._check_quota)

    def test_has_calculate_billing_period_method(self, service):
        assert hasattr(service, "_calculate_billing_period")
        assert callable(service._calculate_billing_period)

    def test_validate_and_log_usage_signature(self, service):
        import inspect

        sig = inspect.signature(service.validate_and_log_usage)
        params = list(sig.parameters.keys())

        assert "session" in params
        assert "user_id" in params
        assert "plan_id" in params
        assert "subscription_id" in params
        assert "request_id" in params
        assert "feature_key" in params
        assert "endpoint" in params
        assert "method" in params
        assert "payload_hash" in params

    def test_commit_usage_signature(self, service):
        import inspect

        sig = inspect.signature(service.commit_usage)
        params = list(sig.parameters.keys())

        assert "session" in params
        assert "user_id" in params
        assert "usage_id" in params
        assert "success" in params
        assert "metrics" in params
        assert "failure" in params


class TestBillingPeriodCalculation:

    @pytest.fixture
    def service(self):
        from app.apps.cubex_career.services.quota import CareerQuotaService

        return CareerQuotaService()

    def test_uses_subscription_period_when_available(self, service):
        sub_start = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        sub_end = datetime(2026, 2, 15, 0, 0, 0, tzinfo=timezone.utc)
        user_created = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc)

        period_start, period_end = service._calculate_billing_period(
            subscription_period_start=sub_start,
            subscription_period_end=sub_end,
            user_created_at=user_created,
            now=now,
        )

        assert period_start == sub_start
        assert period_end == sub_end

    def test_falls_back_to_user_created_when_no_subscription(self, service):
        user_created = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        # 45 days after creation = period 1 (days 30-60)
        now = datetime(2026, 2, 15, 0, 0, 0, tzinfo=timezone.utc)

        period_start, period_end = service._calculate_billing_period(
            subscription_period_start=None,
            subscription_period_end=None,
            user_created_at=user_created,
            now=now,
        )

        expected_start = user_created + timedelta(days=30)
        expected_end = expected_start + timedelta(days=30)

        assert period_start == expected_start
        assert period_end == expected_end

    def test_first_period_is_user_creation_date(self, service):
        user_created = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        now = datetime(2026, 1, 25, 0, 0, 0, tzinfo=timezone.utc)

        period_start, period_end = service._calculate_billing_period(
            subscription_period_start=None,
            subscription_period_end=None,
            user_created_at=user_created,
            now=now,
        )

        assert period_start == user_created
        assert period_end == user_created + timedelta(days=30)

    def test_handles_naive_datetime(self, service):
        user_created = datetime(2026, 1, 1, 0, 0, 0)  # naive
        now = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)

        period_start, period_end = service._calculate_billing_period(
            subscription_period_start=None,
            subscription_period_end=None,
            user_created_at=user_created,
            now=now,
        )

        assert period_start.tzinfo == timezone.utc
        assert period_end.tzinfo == timezone.utc

    def test_partial_subscription_period_falls_back(self, service):
        user_created = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)

        period_start, period_end = service._calculate_billing_period(
            subscription_period_start=datetime(
                2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc
            ),
            subscription_period_end=None,
            user_created_at=user_created,
            now=now,
        )

        assert period_start == user_created
        assert period_end == user_created + timedelta(days=30)

    def test_multiple_periods_elapsed(self, service):
        user_created = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)  # ~365 days

        period_start, period_end = service._calculate_billing_period(
            subscription_period_start=None,
            subscription_period_end=None,
            user_created_at=user_created,
            now=now,
        )

        # 365 / 30 = 12 complete periods
        expected_start = user_created + timedelta(days=360)  # 12 * 30
        expected_end = expected_start + timedelta(days=30)

        assert period_start == expected_start
        assert period_end == expected_end


class TestCheckRateLimit:

    @pytest.fixture
    def service(self):
        from app.apps.cubex_career.services.quota import CareerQuotaService

        return CareerQuotaService()

    @pytest.mark.asyncio
    async def test_returns_rate_limit_info(self, service):
        from app.apps.cubex_career.services.quota import RateLimitInfo

        user_id = uuid4()

        with patch(
            "app.apps.cubex_career.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            side_effect=[(1, 60), (1, 86400)],
        ):
            result = await service._check_rate_limit(user_id, 20, 500)

        assert isinstance(result, RateLimitInfo)
        assert result.limit_per_minute == 20
        assert result.limit_per_day == 500
        assert result.is_exceeded is False

    @pytest.mark.asyncio
    async def test_remaining_decrements_correctly(self, service):
        user_id = uuid4()

        with patch(
            "app.apps.cubex_career.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            side_effect=[(5, 45), (100, 50000)],
        ):
            result = await service._check_rate_limit(user_id, 20, 500)

        assert result.remaining_per_minute == 15  # 20 - 5
        assert result.remaining_per_day == 400  # 500 - 100

    @pytest.mark.asyncio
    async def test_minute_limit_exceeded(self, service):
        user_id = uuid4()

        with patch(
            "app.apps.cubex_career.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            side_effect=[(21, 45), (100, 50000)],  # 21 > 20, minute exceeded
        ):
            result = await service._check_rate_limit(user_id, 20, 500)

        assert result.is_exceeded is True
        assert result.exceeded_window == "minute"
        assert result.remaining_per_minute == 0

    @pytest.mark.asyncio
    async def test_day_limit_exceeded(self, service):
        user_id = uuid4()

        with patch(
            "app.apps.cubex_career.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            side_effect=[(5, 45), (501, 50000)],  # 501 > 500, day exceeded
        ):
            result = await service._check_rate_limit(user_id, 20, 500)

        assert result.is_exceeded is True
        assert result.exceeded_window == "day"

    @pytest.mark.asyncio
    async def test_redis_unavailable_allows_request(self, service):
        user_id = uuid4()

        with patch(
            "app.apps.cubex_career.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            return_value=None,  # Redis unavailable
        ):
            result = await service._check_rate_limit(user_id, 20, 500)

        assert result.is_exceeded is False
        assert result.limit_per_minute == 20
        assert result.limit_per_day == 500

    @pytest.mark.asyncio
    async def test_minute_exceeded_takes_priority_over_day(self, service):
        user_id = uuid4()

        with patch(
            "app.apps.cubex_career.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            side_effect=[(21, 45), (501, 50000)],  # both exceeded
        ):
            result = await service._check_rate_limit(user_id, 20, 500)

        assert result.is_exceeded is True
        assert result.exceeded_window == "minute"

    @pytest.mark.asyncio
    async def test_negative_ttl_defaults_to_window_size(self, service):
        user_id = uuid4()

        with patch(
            "app.apps.cubex_career.services.quota.RedisService.rate_limit_incr",
            new_callable=AsyncMock,
            side_effect=[(1, -1), (1, -1)],  # negative TTLs
        ):
            result = await service._check_rate_limit(user_id, 20, 500)

        # Should not crash, values should use default window sizes
        assert result.is_exceeded is False
        assert result.limit_per_minute == 20

    @pytest.mark.asyncio
    async def test_returns_none_when_both_limits_none(self, service):
        user_id = uuid4()
        result = await service._check_rate_limit(user_id, None, None)
        assert result is None


class TestUsageEstimateValidation:

    def test_valid_usage_estimate_with_all_fields(self):
        from app.apps.cubex_career.schemas.internal import UsageEstimate

        estimate = UsageEstimate(
            input_chars=1000,
            max_output_tokens=500,
            model="gpt-4o",
        )
        assert estimate.input_chars == 1000
        assert estimate.max_output_tokens == 500
        assert estimate.model == "gpt-4o"

    def test_valid_usage_estimate_with_only_model(self):
        from app.apps.cubex_career.schemas.internal import UsageEstimate

        estimate = UsageEstimate(model="gpt-4o-mini")
        assert estimate.model == "gpt-4o-mini"
        assert estimate.input_chars is None

    def test_invalid_usage_estimate_no_fields(self):
        from app.apps.cubex_career.schemas.internal import UsageEstimate

        with pytest.raises(ValidationError) as exc_info:
            UsageEstimate()
        assert "At least one field must be provided" in str(exc_info.value)

    def test_input_chars_bounds(self):
        from app.apps.cubex_career.schemas.internal import UsageEstimate

        UsageEstimate(input_chars=10_000_000)  # valid at max
        with pytest.raises(ValidationError):
            UsageEstimate(input_chars=10_000_001)

    def test_max_output_tokens_bounds(self):
        from app.apps.cubex_career.schemas.internal import UsageEstimate

        UsageEstimate(max_output_tokens=2_000_000)  # valid at max
        with pytest.raises(ValidationError):
            UsageEstimate(max_output_tokens=2_000_001)


class TestUsageValidateRequestSchema:

    def test_valid_request(self):
        from app.apps.cubex_career.schemas.internal import UsageValidateRequest

        request = UsageValidateRequest(
            request_id="req_123",
            feature_key=FeatureKey.CAREER_CAREER_PATH,
            endpoint="/v1/career-path",
            method="POST",
            payload_hash="a" * 64,
        )
        assert request.feature_key == FeatureKey.CAREER_CAREER_PATH

    def test_endpoint_normalized_to_lowercase(self):
        from app.apps.cubex_career.schemas.internal import UsageValidateRequest

        request = UsageValidateRequest(
            request_id="req_123",
            feature_key=FeatureKey.CAREER_CAREER_PATH,
            endpoint="/V1/CAREER-PATH",
            method="POST",
            payload_hash="a" * 64,
        )
        assert request.endpoint == "/v1/career-path"

    def test_method_normalized_to_uppercase(self):
        from app.apps.cubex_career.schemas.internal import UsageValidateRequest

        request = UsageValidateRequest(
            request_id="req_123",
            feature_key=FeatureKey.CAREER_CAREER_PATH,
            endpoint="/v1/career-path",
            method="post",
            payload_hash="a" * 64,
        )
        assert request.method == "POST"

    def test_invalid_payload_hash_length(self):
        from app.apps.cubex_career.schemas.internal import UsageValidateRequest

        with pytest.raises(ValidationError):
            UsageValidateRequest(
                request_id="req_123",
                feature_key=FeatureKey.CAREER_CAREER_PATH,
                endpoint="/v1/career-path",
                method="POST",
                payload_hash="a" * 63,  # too short
            )

    def test_invalid_payload_hash_pattern(self):
        from app.apps.cubex_career.schemas.internal import UsageValidateRequest

        with pytest.raises(ValidationError):
            UsageValidateRequest(
                request_id="req_123",
                feature_key=FeatureKey.CAREER_CAREER_PATH,
                endpoint="/v1/career-path",
                method="POST",
                payload_hash="g" * 64,  # invalid hex chars
            )

    def test_with_client_info(self):
        from app.apps.cubex_career.schemas.internal import UsageValidateRequest

        request = UsageValidateRequest(
            request_id="req_123",
            feature_key=FeatureKey.CAREER_CAREER_PATH,
            endpoint="/v1/career-path",
            method="POST",
            payload_hash="a" * 64,
            client={"ip": "192.168.1.1", "user_agent": "TestAgent/1.0"},
        )
        assert request.client is not None
        assert request.client.ip == "192.168.1.1"

    def test_with_usage_estimate(self):
        from app.apps.cubex_career.schemas.internal import UsageValidateRequest

        request = UsageValidateRequest(
            request_id="req_123",
            feature_key=FeatureKey.CAREER_CAREER_PATH,
            endpoint="/v1/career-path",
            method="POST",
            payload_hash="a" * 64,
            usage_estimate={"input_chars": 5000, "model": "gpt-4o"},
        )
        assert request.usage_estimate is not None
        assert request.usage_estimate.input_chars == 5000


class TestUsageCommitRequestSchema:

    def test_success_without_metrics(self):
        from app.apps.cubex_career.schemas.internal import UsageCommitRequest

        request = UsageCommitRequest(
            user_id=uuid4(),
            usage_id=uuid4(),
            success=True,
        )
        assert request.success is True
        assert request.metrics is None
        assert request.failure is None

    def test_success_with_metrics(self):
        from app.apps.cubex_career.schemas.internal import (
            UsageCommitRequest,
            UsageMetrics,
        )

        request = UsageCommitRequest(
            user_id=uuid4(),
            usage_id=uuid4(),
            success=True,
            metrics=UsageMetrics(
                model_used="gpt-4o",
                input_tokens=1000,
                output_tokens=200,
                latency_ms=800,
            ),
        )
        assert request.metrics.model_used == "gpt-4o"

    def test_failure_requires_failure_details(self):
        from app.apps.cubex_career.schemas.internal import UsageCommitRequest

        with pytest.raises(ValidationError) as exc_info:
            UsageCommitRequest(
                user_id=uuid4(),
                usage_id=uuid4(),
                success=False,
            )
        assert "failure details are required" in str(exc_info.value)

    def test_failure_with_details(self):
        from app.apps.cubex_career.schemas.internal import (
            FailureDetails,
            UsageCommitRequest,
        )

        request = UsageCommitRequest(
            user_id=uuid4(),
            usage_id=uuid4(),
            success=False,
            failure=FailureDetails(
                failure_type=FailureType.TIMEOUT,
                reason="Request timed out after 30 seconds",
            ),
        )
        assert request.failure.failure_type == FailureType.TIMEOUT

    def test_has_user_id_not_api_key(self):
        from app.apps.cubex_career.schemas.internal import UsageCommitRequest

        request = UsageCommitRequest(
            user_id=uuid4(),
            usage_id=uuid4(),
            success=True,
        )
        assert hasattr(request, "user_id")
        assert not hasattr(request, "api_key")


class TestUsageValidateResponseSchema:

    def test_granted_response(self):
        from app.apps.cubex_career.schemas.internal import UsageValidateResponse

        response = UsageValidateResponse(
            access=AccessStatus.GRANTED,
            user_id=uuid4(),
            usage_id=uuid4(),
            message="Access granted.",
            credits_reserved=Decimal("1.50"),
        )
        assert response.access == AccessStatus.GRANTED

    def test_denied_response(self):
        from app.apps.cubex_career.schemas.internal import UsageValidateResponse

        response = UsageValidateResponse(
            access=AccessStatus.DENIED,
            user_id=uuid4(),
            usage_id=None,
            message="Quota exceeded.",
        )
        assert response.access == AccessStatus.DENIED
        assert response.usage_id is None

    def test_has_user_id_not_is_test_key(self):
        from app.apps.cubex_career.schemas.internal import UsageValidateResponse

        response = UsageValidateResponse(
            access=AccessStatus.GRANTED,
            user_id=uuid4(),
            usage_id=uuid4(),
            message="OK",
        )
        assert hasattr(response, "user_id")
        assert not hasattr(response, "is_test_key")


class TestUsageMetricsSchema:

    def test_all_fields(self):
        from app.apps.cubex_career.schemas.internal import UsageMetrics

        metrics = UsageMetrics(
            model_used="gpt-4o",
            input_tokens=1500,
            output_tokens=500,
            latency_ms=1200,
        )
        assert metrics.model_used == "gpt-4o"

    def test_all_optional(self):
        from app.apps.cubex_career.schemas.internal import UsageMetrics

        metrics = UsageMetrics()
        assert metrics.model_used is None

    def test_token_bounds(self):
        from app.apps.cubex_career.schemas.internal import UsageMetrics

        UsageMetrics(input_tokens=2_000_000)  # valid at max
        with pytest.raises(ValidationError):
            UsageMetrics(input_tokens=2_000_001)

    def test_latency_ms_bounds(self):
        from app.apps.cubex_career.schemas.internal import UsageMetrics

        UsageMetrics(latency_ms=3_600_000)  # valid at max
        with pytest.raises(ValidationError):
            UsageMetrics(latency_ms=3_600_001)


class TestFailureDetailsSchema:

    def test_valid_failure_details(self):
        from app.apps.cubex_career.schemas.internal import FailureDetails

        failure = FailureDetails(
            failure_type=FailureType.INTERNAL_ERROR,
            reason="Model API returned 500",
        )
        assert failure.failure_type == FailureType.INTERNAL_ERROR

    def test_failure_type_required(self):
        from app.apps.cubex_career.schemas.internal import FailureDetails

        with pytest.raises(ValidationError):
            FailureDetails(reason="Some error")  # type: ignore

    def test_reason_required(self):
        from app.apps.cubex_career.schemas.internal import FailureDetails

        with pytest.raises(ValidationError):
            FailureDetails(failure_type=FailureType.TIMEOUT)  # type: ignore

    def test_reason_min_length(self):
        from app.apps.cubex_career.schemas.internal import FailureDetails

        with pytest.raises(ValidationError):
            FailureDetails(failure_type=FailureType.TIMEOUT, reason="")

    def test_reason_max_length(self):
        from app.apps.cubex_career.schemas.internal import FailureDetails

        FailureDetails(failure_type=FailureType.TIMEOUT, reason="a" * 1000)
        with pytest.raises(ValidationError):
            FailureDetails(failure_type=FailureType.TIMEOUT, reason="a" * 1001)


class TestCareerUsageLogModel:

    def test_model_import(self):
        from app.apps.cubex_career.db.models.usage_log import CareerUsageLog

        assert CareerUsageLog is not None

    def test_model_tablename(self):
        from app.apps.cubex_career.db.models.usage_log import CareerUsageLog

        assert CareerUsageLog.__tablename__ == "career_usage_logs"

    def test_model_in_init(self):
        from app.apps.cubex_career.db.models import CareerUsageLog

        assert CareerUsageLog is not None

    def test_model_in_core_init(self):
        from app.apps.cubex_career.db.models.usage_log import CareerUsageLog

        assert CareerUsageLog is not None


class TestCareerUsageLogCRUD:

    def test_crud_import(self):
        from app.apps.cubex_career.db.crud.usage_log import career_usage_log_db

        assert career_usage_log_db is not None

    def test_crud_in_init(self):
        from app.apps.cubex_career.db.crud import career_usage_log_db

        assert career_usage_log_db is not None

    def test_has_get_by_request_id(self):
        from app.apps.cubex_career.db.crud.usage_log import career_usage_log_db

        assert hasattr(career_usage_log_db, "get_by_request_id")
        assert callable(career_usage_log_db.get_by_request_id)

    def test_has_get_by_request_id_and_fingerprint(self):
        from app.apps.cubex_career.db.crud.usage_log import career_usage_log_db

        assert hasattr(career_usage_log_db, "get_by_request_id_and_fingerprint")
        assert callable(career_usage_log_db.get_by_request_id_and_fingerprint)

    def test_has_get_by_user(self):
        from app.apps.cubex_career.db.crud.usage_log import career_usage_log_db

        assert hasattr(career_usage_log_db, "get_by_user")
        assert callable(career_usage_log_db.get_by_user)

    def test_has_commit(self):
        from app.apps.cubex_career.db.crud.usage_log import career_usage_log_db

        assert hasattr(career_usage_log_db, "commit")
        assert callable(career_usage_log_db.commit)

    def test_has_expire_pending(self):
        from app.apps.cubex_career.db.crud.usage_log import career_usage_log_db

        assert hasattr(career_usage_log_db, "expire_pending")
        assert callable(career_usage_log_db.expire_pending)

    def test_has_sum_credits_for_period(self):
        from app.apps.cubex_career.db.crud.usage_log import career_usage_log_db

        assert hasattr(career_usage_log_db, "sum_credits_for_period")
        assert callable(career_usage_log_db.sum_credits_for_period)

    def test_sum_credits_method_signature(self):
        import inspect

        from app.apps.cubex_career.db.crud.usage_log import career_usage_log_db

        sig = inspect.signature(career_usage_log_db.sum_credits_for_period)
        params = list(sig.parameters.keys())

        assert "user_id" in params
        assert "workspace_id" not in params


class TestCareerSubscriptionContextCRUD:

    def test_crud_import(self):
        from app.core.db.crud import career_subscription_context_db

        assert career_subscription_context_db is not None

    def test_has_increment_credits_used(self):
        from app.core.db.crud import career_subscription_context_db

        assert hasattr(career_subscription_context_db, "increment_credits_used")
        assert callable(career_subscription_context_db.increment_credits_used)

    def test_has_reset_credits_used(self):
        from app.core.db.crud import career_subscription_context_db

        assert hasattr(career_subscription_context_db, "reset_credits_used")
        assert callable(career_subscription_context_db.reset_credits_used)

    def test_has_get_by_user(self):
        from app.core.db.crud import career_subscription_context_db

        assert hasattr(career_subscription_context_db, "get_by_user")
        assert callable(career_subscription_context_db.get_by_user)

    def test_reset_credits_no_billing_period_param(self):
        import inspect

        from app.core.db.crud import career_subscription_context_db

        sig = inspect.signature(career_subscription_context_db.reset_credits_used)
        params = list(sig.parameters.keys())

        assert "new_billing_period_start" not in params
        assert "session" in params
        assert "context_id" in params


class TestCheckQuota:

    @pytest.fixture
    def service(self):
        from app.apps.cubex_career.services.quota import CareerQuotaService

        return CareerQuotaService()

    @pytest.mark.asyncio
    async def test_quota_granted_within_limits(self, service):
        mock_session = AsyncMock()
        mock_context = AsyncMock()
        mock_context.credits_used = Decimal("50.00")

        with patch(
            "app.apps.cubex_career.services.quota.career_subscription_context_db.get_by_user",
            new_callable=AsyncMock,
            return_value=mock_context,
        ):
            access, message, status_code = await service._check_quota(
                mock_session, uuid4(), Decimal("100.00"), Decimal("1.50")
            )

        assert access == AccessStatus.GRANTED
        assert status_code == 200

    @pytest.mark.asyncio
    async def test_quota_denied_when_exceeded(self, service):
        mock_session = AsyncMock()
        mock_context = AsyncMock()
        mock_context.credits_used = Decimal("99.00")

        with patch(
            "app.apps.cubex_career.services.quota.career_subscription_context_db.get_by_user",
            new_callable=AsyncMock,
            return_value=mock_context,
        ):
            access, message, status_code = await service._check_quota(
                mock_session, uuid4(), Decimal("100.00"), Decimal("2.00")
            )

        assert access == AccessStatus.DENIED
        assert status_code == 429
        assert "Quota exceeded" in message

    @pytest.mark.asyncio
    async def test_quota_granted_at_exact_boundary(self, service):
        mock_session = AsyncMock()
        mock_context = AsyncMock()
        mock_context.credits_used = Decimal("98.50")

        with patch(
            "app.apps.cubex_career.services.quota.career_subscription_context_db.get_by_user",
            new_callable=AsyncMock,
            return_value=mock_context,
        ):
            access, _, status_code = await service._check_quota(
                mock_session, uuid4(), Decimal("100.00"), Decimal("1.50")
            )

        assert access == AccessStatus.GRANTED
        assert status_code == 200

    @pytest.mark.asyncio
    async def test_quota_check_no_context_defaults_to_zero(self, service):
        mock_session = AsyncMock()

        with patch(
            "app.apps.cubex_career.services.quota.career_subscription_context_db.get_by_user",
            new_callable=AsyncMock,
            return_value=None,  # No context
        ):
            access, _, status_code = await service._check_quota(
                mock_session, uuid4(), Decimal("100.00"), Decimal("1.50")
            )

        assert access == AccessStatus.GRANTED
        assert status_code == 200


class TestValidateAndLogUsage:

    @pytest.fixture
    def service(self):
        from app.apps.cubex_career.services.quota import CareerQuotaService

        return CareerQuotaService()

    @pytest.mark.asyncio
    async def test_returns_six_tuple(self, service):
        from app.apps.cubex_career.services.quota import RateLimitInfo
        from app.core.services.quota_cache import PlanConfig

        mock_session = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_log = AsyncMock()
        mock_log.id = uuid4()

        mock_plan_config = PlanConfig(
            multiplier=Decimal("1.0"),
            credits_allocation=Decimal("100.00"),
            rate_limit_per_minute=20,
            rate_limit_per_day=500,
        )

        rate_info = RateLimitInfo(
            limit_per_minute=20,
            remaining_per_minute=19,
            reset_per_minute=1700000060,
            limit_per_day=500,
            remaining_per_day=499,
            reset_per_day=1700086400,
        )

        with (
            patch.object(service, "_check_idempotency", return_value=None),
            patch(
                "app.apps.cubex_career.services.quota.QuotaCacheService.get_plan_config",
                new_callable=AsyncMock,
                return_value=mock_plan_config,
            ),
            patch.object(service, "_check_rate_limit", return_value=rate_info),
            patch(
                "app.apps.cubex_career.services.quota.QuotaCacheService.calculate_billable_cost",
                new_callable=AsyncMock,
                return_value=Decimal("1.50"),
            ),
            patch.object(
                service,
                "_check_quota",
                return_value=(AccessStatus.GRANTED, "OK", 200),
            ),
            patch(
                "app.apps.cubex_career.services.quota.career_usage_log_db.create",
                new_callable=AsyncMock,
                return_value=mock_log,
            ),
        ):
            result = await service.validate_and_log_usage(
                session=mock_session,
                user_id=uuid4(),
                plan_id=uuid4(),
                subscription_id=uuid4(),
                request_id="req_test_123",
                feature_key=FeatureKey.CAREER_CAREER_PATH,
                endpoint="/v1/career-path",
                method="POST",
                payload_hash="a" * 64,
                commit_self=False,
            )

        assert len(result) == 6
        access, usage_id, message, credits, status_code, rl_info = result
        assert access == AccessStatus.GRANTED
        assert usage_id == mock_log.id
        assert credits == Decimal("1.50")
        assert isinstance(rl_info, RateLimitInfo)

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_denied(self, service):
        from app.apps.cubex_career.services.quota import RateLimitInfo
        from app.core.services.quota_cache import PlanConfig

        mock_session = AsyncMock()

        mock_plan_config = PlanConfig(
            multiplier=Decimal("1.0"),
            credits_allocation=Decimal("100.00"),
            rate_limit_per_minute=20,
            rate_limit_per_day=500,
        )

        rate_info = RateLimitInfo(
            limit_per_minute=20,
            remaining_per_minute=0,
            reset_per_minute=1700000060,
            limit_per_day=500,
            remaining_per_day=400,
            reset_per_day=1700086400,
            is_exceeded=True,
            exceeded_window="minute",
        )

        with (
            patch.object(service, "_check_idempotency", return_value=None),
            patch(
                "app.apps.cubex_career.services.quota.QuotaCacheService.get_plan_config",
                new_callable=AsyncMock,
                return_value=mock_plan_config,
            ),
            patch.object(service, "_check_rate_limit", return_value=rate_info),
        ):
            result = await service.validate_and_log_usage(
                session=mock_session,
                user_id=uuid4(),
                plan_id=uuid4(),
                subscription_id=uuid4(),
                request_id="req_test_123",
                feature_key=FeatureKey.CAREER_CAREER_PATH,
                endpoint="/v1/career-path",
                method="POST",
                payload_hash="a" * 64,
                commit_self=False,
            )

        access, usage_id, message, credits, status_code, rl_info = result
        assert access == AccessStatus.DENIED
        assert usage_id is None
        assert status_code == 429
        assert "Rate limit exceeded" in message

    @pytest.mark.asyncio
    async def test_idempotent_request_returns_cached_result(self, service):
        mock_session = AsyncMock()
        cached_usage_id = uuid4()

        idempotent_result = (
            AccessStatus.GRANTED,
            cached_usage_id,
            "Request already processed (idempotent). Access: granted",
            Decimal("1.50"),
            200,
            None,
        )

        with patch.object(
            service, "_check_idempotency", return_value=idempotent_result
        ):
            result = await service.validate_and_log_usage(
                session=mock_session,
                user_id=uuid4(),
                plan_id=uuid4(),
                subscription_id=uuid4(),
                request_id="req_duplicate",
                feature_key=FeatureKey.CAREER_CAREER_PATH,
                endpoint="/v1/career-path",
                method="POST",
                payload_hash="a" * 64,
                commit_self=False,
            )

        access, usage_id, message, _, _, _ = result
        assert access == AccessStatus.GRANTED
        assert usage_id == cached_usage_id
        assert "idempotent" in message


class TestCommitUsage:

    @pytest.fixture
    def service(self):
        from app.apps.cubex_career.services.quota import CareerQuotaService

        return CareerQuotaService()

    @pytest.mark.asyncio
    async def test_successful_commit_increments_credits(self, service):
        user_id = uuid4()
        usage_id = uuid4()
        context_id = uuid4()

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_log = AsyncMock()
        mock_log.user_id = user_id
        mock_log.is_deleted = False

        mock_committed = AsyncMock()
        mock_committed.credits_charged = Decimal("1.50")
        mock_committed.user_id = user_id

        mock_context = AsyncMock()
        mock_context.id = context_id

        with (
            patch(
                "app.apps.cubex_career.services.quota.career_usage_log_db.get_by_id",
                new_callable=AsyncMock,
                return_value=mock_log,
            ),
            patch(
                "app.apps.cubex_career.services.quota.career_usage_log_db.commit",
                new_callable=AsyncMock,
                return_value=mock_committed,
            ),
            patch(
                "app.apps.cubex_career.services.quota.career_subscription_context_db.get_by_user",
                new_callable=AsyncMock,
                return_value=mock_context,
            ),
            patch(
                "app.apps.cubex_career.services.quota.career_subscription_context_db.increment_credits_used",
                new_callable=AsyncMock,
            ) as mock_increment,
        ):
            ok, msg = await service.commit_usage(
                mock_session, user_id, usage_id, success=True, commit_self=False
            )

        assert ok is True
        assert "SUCCESS" in msg
        mock_increment.assert_called_once_with(
            mock_session, context_id, Decimal("1.50")
        )

    @pytest.mark.asyncio
    async def test_failed_commit_does_not_increment_credits(self, service):
        user_id = uuid4()
        usage_id = uuid4()

        mock_session = AsyncMock()
        mock_log = AsyncMock()
        mock_log.user_id = user_id
        mock_log.is_deleted = False

        mock_committed = AsyncMock()
        mock_committed.credits_charged = None
        mock_committed.user_id = user_id

        with (
            patch(
                "app.apps.cubex_career.services.quota.career_usage_log_db.get_by_id",
                new_callable=AsyncMock,
                return_value=mock_log,
            ),
            patch(
                "app.apps.cubex_career.services.quota.career_usage_log_db.commit",
                new_callable=AsyncMock,
                return_value=mock_committed,
            ),
            patch(
                "app.apps.cubex_career.services.quota.career_subscription_context_db.get_by_user",
                new_callable=AsyncMock,
            ) as mock_get_ctx,
            patch(
                "app.apps.cubex_career.services.quota.career_subscription_context_db.increment_credits_used",
                new_callable=AsyncMock,
            ) as mock_increment,
        ):
            ok, msg = await service.commit_usage(
                mock_session,
                user_id,
                usage_id,
                success=False,
                failure={"failure_type": "timeout", "reason": "timed out"},
                commit_self=False,
            )

        assert ok is True
        assert "FAILED" in msg
        mock_increment.assert_not_called()
        mock_get_ctx.assert_not_called()

    @pytest.mark.asyncio
    async def test_commit_not_found_is_idempotent(self, service):
        mock_session = AsyncMock()

        with patch(
            "app.apps.cubex_career.services.quota.career_usage_log_db.get_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            ok, msg = await service.commit_usage(
                mock_session, uuid4(), uuid4(), success=True, commit_self=False
            )

        assert ok is True
        assert "idempotent" in msg

    @pytest.mark.asyncio
    async def test_commit_ownership_mismatch_fails(self, service):
        owner_id = uuid4()
        attacker_id = uuid4()
        usage_id = uuid4()

        mock_session = AsyncMock()
        mock_log = AsyncMock()
        mock_log.user_id = owner_id
        mock_log.is_deleted = False

        with patch(
            "app.apps.cubex_career.services.quota.career_usage_log_db.get_by_id",
            new_callable=AsyncMock,
            return_value=mock_log,
        ):
            ok, msg = await service.commit_usage(
                mock_session, attacker_id, usage_id, success=True, commit_self=False
            )

        assert ok is False
        assert "does not own" in msg

    @pytest.mark.asyncio
    async def test_commit_deleted_log_is_idempotent(self, service):
        mock_session = AsyncMock()
        mock_log = AsyncMock()
        mock_log.is_deleted = True

        with patch(
            "app.apps.cubex_career.services.quota.career_usage_log_db.get_by_id",
            new_callable=AsyncMock,
            return_value=mock_log,
        ):
            ok, msg = await service.commit_usage(
                mock_session, uuid4(), uuid4(), success=True, commit_self=False
            )

        assert ok is True
        assert "idempotent" in msg


class TestCareerInternalRouterRegistration:

    def test_internal_router_import(self):
        from app.apps.cubex_career.routers.internal import router

        assert router is not None

    def test_internal_router_prefix(self):
        from app.apps.cubex_career.routers.internal import router

        assert router.prefix == "/internal"

    def test_internal_router_tags(self):
        from app.apps.cubex_career.routers.internal import router

        assert "Career - Internal API" in router.tags

    def test_internal_router_in_app(self):
        from app.main import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        # Career internal endpoints should be at /career/internal/...
        assert any("/career/internal" in r for r in routes)


class TestCareerInternalRouterEndpoints:

    def test_has_validate_endpoint(self):
        from app.apps.cubex_career.routers.internal import router

        paths = [r.path for r in router.routes if hasattr(r, "path")]
        assert "/internal/usage/validate" in paths

    def test_has_commit_endpoint(self):
        from app.apps.cubex_career.routers.internal import router

        paths = [r.path for r in router.routes if hasattr(r, "path")]
        assert "/internal/usage/commit" in paths


class TestCareerSchedulerJob:

    def test_expire_job_function_exists(self):
        from app.infrastructure.scheduler.jobs import (
            expire_pending_career_usage_logs,
        )

        assert expire_pending_career_usage_logs is not None
        assert callable(expire_pending_career_usage_logs)

    def test_schedule_job_function_exists(self):
        from app.infrastructure.scheduler.main import (
            schedule_expire_pending_career_usage_logs_job,
        )

        assert schedule_expire_pending_career_usage_logs_job is not None
        assert callable(schedule_expire_pending_career_usage_logs_job)


class TestCareerFeatureKeys:

    def test_career_career_path(self):
        assert FeatureKey.CAREER_CAREER_PATH.value == "career.career_path"

    def test_career_extract_keywords(self):
        assert FeatureKey.CAREER_EXTRACT_KEYWORDS.value == "career.extract_keywords"

    def test_career_feedback_analyzer(self):
        assert FeatureKey.CAREER_FEEDBACK_ANALYZER.value == "career.feedback_analyzer"

    def test_career_job_match(self):
        assert FeatureKey.CAREER_JOB_MATCH.value == "career.job_match"

    def test_career_extract_cues_resume(self):
        assert (
            FeatureKey.CAREER_EXTRACT_CUES_RESUME.value == "career.extract_cues.resume"
        )

    def test_career_reframe_feedback(self):
        assert FeatureKey.CAREER_REFRAME_FEEDBACK.value == "career.reframe_feedback"

    def test_career_keys_are_distinct_from_api_keys(self):
        career_keys = [k for k in FeatureKey if k.value.startswith("career.")]
        api_keys = [k for k in FeatureKey if k.value.startswith("api.")]

        assert len(career_keys) > 0
        assert len(api_keys) > 0
        assert set(career_keys).isdisjoint(set(api_keys))
