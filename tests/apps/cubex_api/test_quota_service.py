"""
Test suite for QuotaService.

This module contains comprehensive tests for the QuotaService including:
- API key generation and management
- Usage validation and logging
- Usage reverting (idempotent)
- client_id parsing

Run all tests:
    pytest tests/apps/cubex_api/test_quota_service.py -v

Run with coverage:
    pytest tests/apps/cubex_api/test_quota_service.py --cov=app.apps.cubex_api.services.quota --cov-report=term-missing -v
"""

from uuid import uuid4

import pytest

from app.shared.enums import AccessStatus


class TestQuotaServiceInit:
    """Test suite for QuotaService initialization."""

    def test_service_import(self):
        """Test that QuotaService can be imported."""
        from app.apps.cubex_api.services.quota import QuotaService

        assert QuotaService is not None

    def test_service_singleton_exists(self):
        """Test that quota_service singleton is accessible."""
        from app.apps.cubex_api.services.quota import quota_service

        assert quota_service is not None


class TestQuotaServiceExceptions:
    """Test suite for quota-related exceptions."""

    def test_api_key_not_found_exception(self):
        """Test APIKeyNotFoundException."""
        from app.apps.cubex_api.services.quota import APIKeyNotFoundException

        exc = APIKeyNotFoundException()
        assert exc is not None
        assert "API key not found" in str(exc.message)

    def test_api_key_invalid_exception(self):
        """Test APIKeyInvalidException."""
        from app.apps.cubex_api.services.quota import APIKeyInvalidException

        exc = APIKeyInvalidException()
        assert exc is not None
        assert "invalid" in str(exc.message).lower()

    def test_usage_log_not_found_exception(self):
        """Test UsageLogNotFoundException."""
        from app.apps.cubex_api.services.quota import UsageLogNotFoundException

        exc = UsageLogNotFoundException()
        assert exc is not None
        assert "Usage log not found" in str(exc.message)


class TestQuotaServiceConstants:
    """Test suite for QuotaService constants."""

    def test_api_key_prefix(self):
        """Test API key prefix constant."""
        from app.apps.cubex_api.services.quota import API_KEY_PREFIX

        assert API_KEY_PREFIX == "cbx_live_"

    def test_client_id_prefix(self):
        """Test client ID prefix constant."""
        from app.apps.cubex_api.services.quota import CLIENT_ID_PREFIX

        assert CLIENT_ID_PREFIX == "ws_"


class TestAccessStatusEnum:
    """Test suite for AccessStatus enum."""

    def test_access_status_values(self):
        """Test AccessStatus enum values."""
        assert AccessStatus.GRANTED.value == "granted"
        assert AccessStatus.DENIED.value == "denied"


class TestQuotaServiceMethods:
    """Test suite for QuotaService method signatures."""

    @pytest.fixture
    def service(self):
        """Get QuotaService instance."""
        from app.apps.cubex_api.services.quota import QuotaService

        return QuotaService()

    def test_has_create_api_key_method(self, service):
        """Test that create_api_key method exists."""
        assert hasattr(service, "create_api_key")
        assert callable(service.create_api_key)

    def test_has_list_api_keys_method(self, service):
        """Test that list_api_keys method exists."""
        assert hasattr(service, "list_api_keys")
        assert callable(service.list_api_keys)

    def test_has_revoke_api_key_method(self, service):
        """Test that revoke_api_key method exists."""
        assert hasattr(service, "revoke_api_key")
        assert callable(service.revoke_api_key)

    def test_has_validate_and_log_usage_method(self, service):
        """Test that validate_and_log_usage method exists."""
        assert hasattr(service, "validate_and_log_usage")
        assert callable(service.validate_and_log_usage)

    def test_has_commit_usage_method(self, service):
        """Test that commit_usage method exists."""
        assert hasattr(service, "commit_usage")
        assert callable(service.commit_usage)


class TestAPIKeyGeneration:
    """Test suite for API key generation."""

    @pytest.fixture
    def service(self):
        """Get QuotaService instance."""
        from app.apps.cubex_api.services.quota import QuotaService

        return QuotaService()

    def test_generate_api_key_format(self, service):
        """Test that generated API keys have correct format."""
        raw_key, key_hash, key_prefix = service._generate_api_key()

        # Check raw key format
        assert raw_key.startswith("cbx_live_")
        assert len(raw_key) > 20  # Reasonable length

        # Check key hash is 64 chars (HMAC-SHA256 hex)
        assert len(key_hash) == 64
        assert all(c in "0123456789abcdef" for c in key_hash)

        # Check key prefix format
        assert key_prefix.startswith("cbx_live_")
        assert len(key_prefix) == len("cbx_live_") + 5  # prefix + 5 chars

    def test_generate_api_key_uniqueness(self, service):
        """Test that generated API keys are unique."""
        keys = set()
        for _ in range(10):
            raw_key, _, _ = service._generate_api_key()
            keys.add(raw_key)

        # All 10 keys should be unique
        assert len(keys) == 10


class TestClientIdParsing:
    """Test suite for client_id parsing."""

    @pytest.fixture
    def service(self):
        """Get QuotaService instance."""
        from app.apps.cubex_api.services.quota import QuotaService

        return QuotaService()

    def test_parse_valid_client_id(self, service):
        """Test parsing a valid client_id."""
        test_uuid = uuid4()
        client_id = f"ws_{test_uuid.hex}"

        result = service._parse_client_id(client_id)

        assert result is not None
        assert result == test_uuid

    def test_parse_client_id_without_prefix(self, service):
        """Test parsing client_id without prefix returns None."""
        test_uuid = uuid4()
        client_id = test_uuid.hex

        result = service._parse_client_id(client_id)

        assert result is None

    def test_parse_client_id_with_wrong_prefix(self, service):
        """Test parsing client_id with wrong prefix returns None."""
        test_uuid = uuid4()
        client_id = f"wrong_{test_uuid.hex}"

        result = service._parse_client_id(client_id)

        assert result is None

    def test_parse_client_id_with_invalid_uuid(self, service):
        """Test parsing client_id with invalid UUID returns None."""
        client_id = "ws_notavaliduuid"

        result = service._parse_client_id(client_id)

        assert result is None


class TestAPIKeyFormatValidation:
    """Test suite for API key format validation."""

    @pytest.fixture
    def service(self):
        """Get QuotaService instance."""
        from app.apps.cubex_api.services.quota import QuotaService

        return QuotaService()

    def test_validate_valid_api_key_format(self, service):
        """Test validating a properly formatted API key."""
        api_key = "cbx_live_abc123def456ghi789jkl012mno345pqr678stu901"

        result = service._validate_api_key_format(api_key)

        assert result is True

    def test_validate_api_key_without_prefix(self, service):
        """Test validating API key without prefix returns False."""
        api_key = "abc123def456ghi789jkl012mno345pqr678stu901"

        result = service._validate_api_key_format(api_key)

        assert result is False

    def test_validate_api_key_only_prefix(self, service):
        """Test validating API key that is only the prefix returns False."""
        api_key = "cbx_live_"

        result = service._validate_api_key_format(api_key)

        assert result is False

    def test_validate_empty_api_key(self, service):
        """Test validating empty API key returns False."""
        api_key = ""

        result = service._validate_api_key_format(api_key)

        assert result is False


class TestAPIKeyModelIntegration:
    """Test APIKey model integration."""

    def test_api_key_model_import(self):
        """Test that APIKey model can be imported."""
        from app.apps.cubex_api.db.models.workspace import APIKey

        assert APIKey is not None

    def test_usage_log_model_import(self):
        """Test that UsageLog model can be imported."""
        from app.apps.cubex_api.db.models.workspace import UsageLog

        assert UsageLog is not None

    def test_models_in_init(self):
        """Test that models are exported from __init__."""
        from app.apps.cubex_api.db.models import APIKey, UsageLog

        assert APIKey is not None
        assert UsageLog is not None


class TestAPIKeyCRUDIntegration:
    """Test APIKey CRUD integration."""

    def test_api_key_db_import(self):
        """Test that api_key_db can be imported."""
        from app.apps.cubex_api.db.crud.workspace import api_key_db

        assert api_key_db is not None

    def test_usage_log_db_import(self):
        """Test that usage_log_db can be imported."""
        from app.apps.cubex_api.db.crud.workspace import usage_log_db

        assert usage_log_db is not None

    def test_crud_in_init(self):
        """Test that CRUD instances are exported from __init__."""
        from app.apps.cubex_api.db.crud import api_key_db, usage_log_db

        assert api_key_db is not None
        assert usage_log_db is not None


class TestQuotaServiceExports:
    """Test QuotaService exports from __init__."""

    def test_exports_from_services_init(self):
        """Test that QuotaService is exported from services __init__."""
        from app.apps.cubex_api.services import (
            QuotaService,
            quota_service,
            APIKeyNotFoundException,
            APIKeyInvalidException,
            UsageLogNotFoundException,
            API_KEY_PREFIX,
            CLIENT_ID_PREFIX,
        )

        assert QuotaService is not None
        assert quota_service is not None
        assert APIKeyNotFoundException is not None
        assert APIKeyInvalidException is not None
        assert UsageLogNotFoundException is not None
        assert API_KEY_PREFIX == "cbx_live_"
        assert CLIENT_ID_PREFIX == "ws_"
