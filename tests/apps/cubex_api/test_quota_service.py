"""
Test suite for QuotaService.

- API key generation and management
- Usage validation and logging
- Usage reverting (idempotent)
- client_id parsing
- Schema validation (UsageEstimate, UsageCommitRequest, metrics, failure)

Run all tests:
    pytest tests/apps/cubex_api/test_quota_service.py -v

Run with coverage:
    pytest tests/apps/cubex_api/test_quota_service.py --cov=app.apps.cubex_api.services.quota --cov-report=term-missing -v
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.enums import AccessStatus, FailureType


class TestFailureTypeEnum:

    def test_failure_type_values(self):
        assert FailureType.INTERNAL_ERROR.value == "internal_error"
        assert FailureType.TIMEOUT.value == "timeout"
        assert FailureType.RATE_LIMITED.value == "rate_limited"
        assert FailureType.INVALID_RESPONSE.value == "invalid_response"
        assert FailureType.UPSTREAM_ERROR.value == "upstream_error"
        assert FailureType.CLIENT_ERROR.value == "client_error"
        assert FailureType.VALIDATION_ERROR.value == "validation_error"

    def test_failure_type_count(self):
        assert len(FailureType) == 7


class TestUsageEstimateValidation:

    def test_valid_usage_estimate_with_all_fields(self):
        from app.apps.cubex_api.schemas.workspace import UsageEstimate

        estimate = UsageEstimate(
            input_chars=1000,
            max_output_tokens=500,
            model="gpt-4o",
        )
        assert estimate.input_chars == 1000
        assert estimate.max_output_tokens == 500
        assert estimate.model == "gpt-4o"

    def test_valid_usage_estimate_with_only_input_chars(self):
        from app.apps.cubex_api.schemas.workspace import UsageEstimate

        estimate = UsageEstimate(input_chars=1000)
        assert estimate.input_chars == 1000
        assert estimate.max_output_tokens is None
        assert estimate.model is None

    def test_valid_usage_estimate_with_only_model(self):
        from app.apps.cubex_api.schemas.workspace import UsageEstimate

        estimate = UsageEstimate(model="gpt-4o-mini")
        assert estimate.model == "gpt-4o-mini"

    def test_invalid_usage_estimate_no_fields(self):
        from app.apps.cubex_api.schemas.workspace import UsageEstimate

        with pytest.raises(ValidationError) as exc_info:
            UsageEstimate()
        assert "At least one field must be provided" in str(exc_info.value)

    def test_input_chars_max_bound(self):
        from app.apps.cubex_api.schemas.workspace import UsageEstimate

        # Valid at max
        estimate = UsageEstimate(input_chars=10_000_000)
        assert estimate.input_chars == 10_000_000

        # Invalid above max
        with pytest.raises(ValidationError):
            UsageEstimate(input_chars=10_000_001)

    def test_max_output_tokens_max_bound(self):
        from app.apps.cubex_api.schemas.workspace import UsageEstimate

        # Valid at max
        estimate = UsageEstimate(max_output_tokens=2_000_000)
        assert estimate.max_output_tokens == 2_000_000

        # Invalid above max
        with pytest.raises(ValidationError):
            UsageEstimate(max_output_tokens=2_000_001)

    def test_model_max_length(self):
        from app.apps.cubex_api.schemas.workspace import UsageEstimate

        # Valid at max length
        estimate = UsageEstimate(model="a" * 100)
        assert len(estimate.model) == 100

        # Invalid above max
        with pytest.raises(ValidationError):
            UsageEstimate(model="a" * 101)


class TestUsageMetricsValidation:

    def test_valid_metrics_all_fields(self):
        from app.apps.cubex_api.schemas.workspace import UsageMetrics

        metrics = UsageMetrics(
            model_used="gpt-4o",
            input_tokens=1500,
            output_tokens=500,
            latency_ms=1200,
        )
        assert metrics.model_used == "gpt-4o"
        assert metrics.input_tokens == 1500
        assert metrics.output_tokens == 500
        assert metrics.latency_ms == 1200

    def test_valid_metrics_partial_fields(self):
        from app.apps.cubex_api.schemas.workspace import UsageMetrics

        metrics = UsageMetrics(latency_ms=500)
        assert metrics.latency_ms == 500
        assert metrics.model_used is None

    def test_valid_metrics_empty(self):
        from app.apps.cubex_api.schemas.workspace import UsageMetrics

        metrics = UsageMetrics()
        assert metrics.model_used is None
        assert metrics.input_tokens is None

    def test_tokens_max_bounds(self):
        from app.apps.cubex_api.schemas.workspace import UsageMetrics

        # Valid at max
        metrics = UsageMetrics(input_tokens=2_000_000, output_tokens=2_000_000)
        assert metrics.input_tokens == 2_000_000
        assert metrics.output_tokens == 2_000_000

        # Invalid above max
        with pytest.raises(ValidationError):
            UsageMetrics(input_tokens=2_000_001)
        with pytest.raises(ValidationError):
            UsageMetrics(output_tokens=2_000_001)

    def test_latency_ms_max_bound(self):
        from app.apps.cubex_api.schemas.workspace import UsageMetrics

        # Valid at max
        metrics = UsageMetrics(latency_ms=3_600_000)
        assert metrics.latency_ms == 3_600_000

        # Invalid above max
        with pytest.raises(ValidationError):
            UsageMetrics(latency_ms=3_600_001)


class TestFailureDetailsValidation:

    def test_valid_failure_details(self):
        from app.apps.cubex_api.schemas.workspace import FailureDetails

        failure = FailureDetails(
            failure_type=FailureType.INTERNAL_ERROR,
            reason="Model API returned 500 Internal Server Error",
        )
        assert failure.failure_type == FailureType.INTERNAL_ERROR
        assert "500" in failure.reason

    def test_failure_type_required(self):
        from app.apps.cubex_api.schemas.workspace import FailureDetails

        with pytest.raises(ValidationError):
            FailureDetails(reason="Some error")  # type: ignore

    def test_reason_required(self):
        from app.apps.cubex_api.schemas.workspace import FailureDetails

        with pytest.raises(ValidationError):
            FailureDetails(failure_type=FailureType.TIMEOUT)  # type: ignore

    def test_reason_min_length(self):
        from app.apps.cubex_api.schemas.workspace import FailureDetails

        with pytest.raises(ValidationError):
            FailureDetails(failure_type=FailureType.TIMEOUT, reason="")

    def test_reason_max_length(self):
        from app.apps.cubex_api.schemas.workspace import FailureDetails

        # Valid at max length
        failure = FailureDetails(
            failure_type=FailureType.TIMEOUT,
            reason="a" * 1000,
        )
        assert len(failure.reason) == 1000

        # Invalid above max
        with pytest.raises(ValidationError):
            FailureDetails(failure_type=FailureType.TIMEOUT, reason="a" * 1001)


class TestUsageCommitRequestValidation:

    def test_success_without_metrics(self):
        from app.apps.cubex_api.schemas.workspace import UsageCommitRequest

        request = UsageCommitRequest(
            api_key="cbx_live_abc123",
            usage_id=uuid4(),
            success=True,
        )
        assert request.success is True
        assert request.metrics is None
        assert request.failure is None


class TestUsageValidateRequestNormalization:

    def test_endpoint_normalized_to_lowercase(self):
        from app.apps.cubex_api.schemas.workspace import UsageValidateRequest
        from app.core.enums import FeatureKey

        request = UsageValidateRequest(
            request_id="req_123",
            client_id="ws_550e8400e29b41d4a716446655440000",
            api_key="cbx_live_abc123",
            endpoint="/V1/EXTRACT-CUES/RESUME",
            method="POST",
            payload_hash="a" * 64,
            feature_key=FeatureKey.API_EXTRACT_CUES_RESUME,
        )
        assert request.endpoint == "/v1/extract-cues/resume"

    def test_method_normalized_to_uppercase(self):
        from app.apps.cubex_api.schemas.workspace import UsageValidateRequest
        from app.core.enums import FeatureKey

        request = UsageValidateRequest(
            request_id="req_123",
            client_id="ws_550e8400e29b41d4a716446655440000",
            api_key="cbx_live_abc123",
            endpoint="/v1/analyze",
            method="post",
            payload_hash="a" * 64,
            feature_key=FeatureKey.API_EXTRACT_CUES_RESUME,
        )
        assert request.method == "POST"

    def test_mixed_case_normalization(self):
        from app.apps.cubex_api.schemas.workspace import UsageValidateRequest
        from app.core.enums import FeatureKey

        request = UsageValidateRequest(
            request_id="req_123",
            client_id="ws_550e8400e29b41d4a716446655440000",
            api_key="cbx_live_abc123",
            endpoint="/Api/V1/Analyze",
            method="Post",
            payload_hash="a" * 64,
            feature_key=FeatureKey.API_EXTRACT_CUES_RESUME,
        )
        assert request.endpoint == "/api/v1/analyze"
        assert request.method == "POST"


class TestUsageCommitRequestMetricsValidation:

    def test_success_with_metrics(self):
        from app.apps.cubex_api.schemas.workspace import (
            UsageCommitRequest,
            UsageMetrics,
        )

        request = UsageCommitRequest(
            api_key="cbx_live_abc123",
            usage_id=uuid4(),
            success=True,
            metrics=UsageMetrics(
                model_used="gpt-4o",
                input_tokens=1000,
                output_tokens=200,
                latency_ms=800,
            ),
        )
        assert request.success is True
        assert request.metrics is not None
        assert request.metrics.model_used == "gpt-4o"

    def test_failure_requires_failure_details(self):
        from app.apps.cubex_api.schemas.workspace import UsageCommitRequest

        with pytest.raises(ValidationError) as exc_info:
            UsageCommitRequest(
                api_key="cbx_live_abc123",
                usage_id=uuid4(),
                success=False,
            )
        assert "failure details are required" in str(exc_info.value)

    def test_failure_with_failure_details(self):
        from app.apps.cubex_api.schemas.workspace import (
            FailureDetails,
            UsageCommitRequest,
        )

        request = UsageCommitRequest(
            api_key="cbx_live_abc123",
            usage_id=uuid4(),
            success=False,
            failure=FailureDetails(
                failure_type=FailureType.TIMEOUT,
                reason="Request timed out after 30 seconds",
            ),
        )
        assert request.success is False
        assert request.failure is not None
        assert request.failure.failure_type == FailureType.TIMEOUT


class TestQuotaServiceInit:

    def test_service_import(self):
        from app.apps.cubex_api.services.quota import QuotaService

        assert QuotaService is not None

    def test_service_singleton_exists(self):
        from app.apps.cubex_api.services.quota import quota_service

        assert quota_service is not None


class TestQuotaServiceExceptions:

    def test_api_key_not_found_exception(self):
        from app.apps.cubex_api.services.quota import APIKeyNotFoundException

        exc = APIKeyNotFoundException()
        assert exc is not None
        assert "API key not found" in str(exc.message)

    def test_api_key_invalid_exception(self):
        from app.apps.cubex_api.services.quota import APIKeyInvalidException

        exc = APIKeyInvalidException()
        assert exc is not None
        assert "invalid" in str(exc.message).lower()

    def test_usage_log_not_found_exception(self):
        from app.apps.cubex_api.services.quota import UsageLogNotFoundException

        exc = UsageLogNotFoundException()
        assert exc is not None
        assert "Usage log not found" in str(exc.message)


class TestQuotaServiceConstants:

    def test_api_key_prefix(self):
        from app.apps.cubex_api.services.quota import API_KEY_PREFIX

        assert API_KEY_PREFIX == "cbx_live_"

    def test_test_api_key_prefix(self):
        from app.apps.cubex_api.services.quota import TEST_API_KEY_PREFIX

        assert TEST_API_KEY_PREFIX == "cbx_test_"

    def test_client_id_prefix(self):
        from app.apps.cubex_api.services.quota import CLIENT_ID_PREFIX

        assert CLIENT_ID_PREFIX == "ws_"


class TestAccessStatusEnum:

    def test_access_status_values(self):
        assert AccessStatus.GRANTED.value == "granted"
        assert AccessStatus.DENIED.value == "denied"


class TestQuotaServiceMethods:

    @pytest.fixture
    def service(self):
        """Get QuotaService instance."""
        from app.apps.cubex_api.services.quota import QuotaService

        return QuotaService()

    def test_has_create_api_key_method(self, service):
        assert hasattr(service, "create_api_key")
        assert callable(service.create_api_key)

    def test_has_list_api_keys_method(self, service):
        assert hasattr(service, "list_api_keys")
        assert callable(service.list_api_keys)

    def test_has_revoke_api_key_method(self, service):
        assert hasattr(service, "revoke_api_key")
        assert callable(service.revoke_api_key)

    def test_has_validate_and_log_usage_method(self, service):
        assert hasattr(service, "validate_and_log_usage")
        assert callable(service.validate_and_log_usage)

    def test_has_commit_usage_method(self, service):
        assert hasattr(service, "commit_usage")
        assert callable(service.commit_usage)


class TestAPIKeyGeneration:

    @pytest.fixture
    def service(self):
        """Get QuotaService instance."""
        from app.apps.cubex_api.services.quota import QuotaService

        return QuotaService()

    def test_generate_api_key_format(self, service):
        raw_key, key_hash, key_prefix = service._generate_api_key()

        assert raw_key.startswith("cbx_live_")
        assert len(raw_key) > 20  # Reasonable length

        # Check key hash is 64 chars (HMAC-SHA256 hex)
        assert len(key_hash) == 64
        assert all(c in "0123456789abcdef" for c in key_hash)

        assert key_prefix.startswith("cbx_live_")
        assert len(key_prefix) == len("cbx_live_") + 5  # prefix + 5 chars

    def test_generate_test_api_key_format(self, service):
        raw_key, key_hash, key_prefix = service._generate_api_key(is_test_key=True)

        assert raw_key.startswith("cbx_test_")
        assert len(raw_key) > 20  # Reasonable length

        # Check key hash is 64 chars (HMAC-SHA256 hex)
        assert len(key_hash) == 64
        assert all(c in "0123456789abcdef" for c in key_hash)

        assert key_prefix.startswith("cbx_test_")
        assert len(key_prefix) == len("cbx_test_") + 5  # prefix + 5 chars

    def test_generate_api_key_uniqueness(self, service):
        keys = set()
        for _ in range(10):
            raw_key, _, _ = service._generate_api_key()
            keys.add(raw_key)

        # All 10 keys should be unique
        assert len(keys) == 10


class TestClientIdParsing:

    @pytest.fixture
    def service(self):
        """Get QuotaService instance."""
        from app.apps.cubex_api.services.quota import QuotaService

        return QuotaService()

    def test_parse_valid_client_id(self, service):
        test_uuid = uuid4()
        client_id = f"ws_{test_uuid.hex}"

        result = service._parse_client_id(client_id)

        assert result is not None
        assert result == test_uuid

    def test_parse_client_id_without_prefix(self, service):
        test_uuid = uuid4()
        client_id = test_uuid.hex

        result = service._parse_client_id(client_id)

        assert result is None

    def test_parse_client_id_with_wrong_prefix(self, service):
        test_uuid = uuid4()
        client_id = f"wrong_{test_uuid.hex}"

        result = service._parse_client_id(client_id)

        assert result is None

    def test_parse_client_id_with_invalid_uuid(self, service):
        client_id = "ws_notavaliduuid"

        result = service._parse_client_id(client_id)

        assert result is None


class TestAPIKeyFormatValidation:

    @pytest.fixture
    def service(self):
        """Get QuotaService instance."""
        from app.apps.cubex_api.services.quota import QuotaService

        return QuotaService()

    def test_validate_valid_api_key_format(self, service):
        api_key = "cbx_live_abc123def456ghi789jkl012mno345pqr678stu901"

        result = service._validate_api_key_format(api_key)

        assert result is True

    def test_validate_valid_test_api_key_format(self, service):
        api_key = "cbx_test_abc123def456ghi789jkl012mno345pqr678stu901"

        result = service._validate_api_key_format(api_key)

        assert result is True

    def test_validate_api_key_without_prefix(self, service):
        api_key = "abc123def456ghi789jkl012mno345pqr678stu901"

        result = service._validate_api_key_format(api_key)

        assert result is False

    def test_validate_api_key_only_prefix(self, service):
        api_key = "cbx_live_"

        result = service._validate_api_key_format(api_key)

        assert result is False

    def test_validate_test_api_key_only_prefix(self, service):
        api_key = "cbx_test_"

        result = service._validate_api_key_format(api_key)

        assert result is False

    def test_validate_empty_api_key(self, service):
        api_key = ""

        result = service._validate_api_key_format(api_key)

        assert result is False


class TestAPIKeyModelIntegration:

    def test_api_key_model_import(self):
        from app.apps.cubex_api.db.models.workspace import APIKey

        assert APIKey is not None

    def test_usage_log_model_import(self):
        from app.apps.cubex_api.db.models.workspace import UsageLog

        assert UsageLog is not None

    def test_models_in_init(self):
        from app.apps.cubex_api.db.models import APIKey, UsageLog

        assert APIKey is not None
        assert UsageLog is not None


class TestAPIKeyCRUDIntegration:

    def test_api_key_db_import(self):
        from app.apps.cubex_api.db.crud.workspace import api_key_db

        assert api_key_db is not None

    def test_usage_log_db_import(self):
        from app.apps.cubex_api.db.crud.workspace import usage_log_db

        assert usage_log_db is not None

    def test_crud_in_init(self):
        from app.apps.cubex_api.db.crud import api_key_db, usage_log_db

        assert api_key_db is not None
        assert usage_log_db is not None


class TestQuotaServiceExports:

    def test_exports_from_services_init(self):
        from app.apps.cubex_api.services import (
            QuotaService,
            quota_service,
            APIKeyNotFoundException,
            APIKeyInvalidException,
            UsageLogNotFoundException,
            API_KEY_PREFIX,
            TEST_API_KEY_PREFIX,
            CLIENT_ID_PREFIX,
        )

        assert QuotaService is not None
        assert quota_service is not None
        assert APIKeyNotFoundException is not None
        assert APIKeyInvalidException is not None
        assert UsageLogNotFoundException is not None
        assert API_KEY_PREFIX == "cbx_live_"
        assert TEST_API_KEY_PREFIX == "cbx_test_"
        assert CLIENT_ID_PREFIX == "ws_"


class TestBillingPeriodCalculation:

    def test_uses_subscription_period_when_available(self):
        from datetime import datetime, timezone

        from app.apps.cubex_api.services.quota import quota_service

        sub_start = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        sub_end = datetime(2026, 2, 15, 0, 0, 0, tzinfo=timezone.utc)
        workspace_created = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc)

        period_start, period_end = quota_service._calculate_billing_period(
            subscription_period_start=sub_start,
            subscription_period_end=sub_end,
            workspace_created_at=workspace_created,
            now=now,
        )

        assert period_start == sub_start
        assert period_end == sub_end

    def test_falls_back_to_workspace_created_when_no_subscription(self):
        from datetime import datetime, timezone, timedelta

        from app.apps.cubex_api.services.quota import quota_service

        workspace_created = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        # 45 days after creation = period 1 (days 30-60)
        now = datetime(2026, 2, 15, 0, 0, 0, tzinfo=timezone.utc)

        period_start, period_end = quota_service._calculate_billing_period(
            subscription_period_start=None,
            subscription_period_end=None,
            workspace_created_at=workspace_created,
            now=now,
        )

        # Should be in period 1: Jan 31 - Mar 2 (30 days from Jan 1 + 30 days)
        expected_start = workspace_created + timedelta(days=30)
        expected_end = expected_start + timedelta(days=30)

        assert period_start == expected_start
        assert period_end == expected_end

    def test_first_period_is_workspace_creation_date(self):
        from datetime import datetime, timezone, timedelta

        from app.apps.cubex_api.services.quota import quota_service

        workspace_created = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        # 10 days after creation = still in period 0
        now = datetime(2026, 1, 25, 0, 0, 0, tzinfo=timezone.utc)

        period_start, period_end = quota_service._calculate_billing_period(
            subscription_period_start=None,
            subscription_period_end=None,
            workspace_created_at=workspace_created,
            now=now,
        )

        assert period_start == workspace_created
        assert period_end == workspace_created + timedelta(days=30)

    def test_handles_naive_datetime(self):
        from datetime import datetime, timezone

        from app.apps.cubex_api.services.quota import quota_service

        # Naive datetime (no timezone)
        workspace_created = datetime(2026, 1, 1, 0, 0, 0)
        now = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)

        period_start, period_end = quota_service._calculate_billing_period(
            subscription_period_start=None,
            subscription_period_end=None,
            workspace_created_at=workspace_created,
            now=now,
        )

        # Should add UTC timezone and work correctly
        assert period_start.tzinfo == timezone.utc
        assert period_end.tzinfo == timezone.utc

    def test_partial_subscription_period_falls_back(self):
        from datetime import datetime, timezone, timedelta

        from app.apps.cubex_api.services.quota import quota_service

        workspace_created = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)

        # Only start provided, no end
        period_start, period_end = quota_service._calculate_billing_period(
            subscription_period_start=datetime(
                2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc
            ),
            subscription_period_end=None,
            workspace_created_at=workspace_created,
            now=now,
        )

        # Should fall back to workspace-based calculation
        assert period_start == workspace_created
        assert period_end == workspace_created + timedelta(days=30)


class TestUsageLogSumCredits:

    def test_sum_credits_method_exists(self):
        from app.apps.cubex_api.db.crud.workspace import usage_log_db

        assert hasattr(usage_log_db, "sum_credits_for_period")
        assert callable(usage_log_db.sum_credits_for_period)

    def test_sum_credits_method_signature(self):
        import inspect

        from app.apps.cubex_api.db.crud.workspace import usage_log_db

        sig = inspect.signature(usage_log_db.sum_credits_for_period)
        params = list(sig.parameters.keys())

        assert "session" in params
        assert "workspace_id" in params
        assert "period_start" in params
        assert "period_end" in params


class TestQuotaCacheServicePlanConfig:

    def test_get_plan_config_method_exists(self):
        from app.core.services.quota_cache import QuotaCacheService

        assert hasattr(QuotaCacheService, "get_plan_config")
        assert callable(QuotaCacheService.get_plan_config)

    def test_get_plan_config_method_signature(self):
        import inspect

        from app.core.services.quota_cache import QuotaCacheService

        sig = inspect.signature(QuotaCacheService.get_plan_config)
        params = list(sig.parameters.keys())

        assert "session" in params
        assert "plan_id" in params

    @pytest.mark.asyncio
    async def test_returns_none_when_plan_id_is_none(self):
        from unittest.mock import AsyncMock

        from app.core.services.quota_cache import QuotaCacheService

        result = await QuotaCacheService.get_plan_config(
            session=AsyncMock(),
            plan_id=None,
        )

        assert result is None
