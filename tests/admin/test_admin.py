"""
Test suite for SQLAdmin configuration and authentication.

Tests cover:
- Admin module imports and structure
- Authentication backend behavior (HMAC tokens)
- Admin view configurations
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestAdminModuleImports:

    def test_admin_module_imports(self):
        from app.admin import init_admin

        # admin is None until init_admin is called
        assert init_admin is not None
        assert callable(init_admin)

    def test_admin_views_import(self):
        from app.admin.views import (
            FeatureCostConfigAdmin,
            PlanAdmin,
            PlanPricingRuleAdmin,
            SubscriptionAdmin,
            UserAdmin,
            WorkspaceAdmin,
            WorkspaceMemberAdmin,
        )

        assert PlanAdmin is not None
        assert FeatureCostConfigAdmin is not None
        assert PlanPricingRuleAdmin is not None
        assert UserAdmin is not None
        assert WorkspaceAdmin is not None
        assert WorkspaceMemberAdmin is not None
        assert SubscriptionAdmin is not None

    def test_admin_auth_import(self):
        from app.admin.auth import AdminAuth, admin_auth

        assert AdminAuth is not None
        assert admin_auth is not None

    def test_admin_setup_import(self):
        from app.admin.setup import init_admin

        # admin is None until init_admin is called
        assert init_admin is not None
        assert callable(init_admin)


class TestAdminAuthBackend:

    @pytest.fixture
    def auth_backend(self):
        """Create a fresh AdminAuth instance for testing."""
        from app.admin.auth import AdminAuth
        from app.core.config import settings

        return AdminAuth(secret_key=settings.SESSION_SECRET_KEY)

    @pytest.fixture
    def mock_request(self):
        """Create a mock request object."""
        request = MagicMock()
        request.session = {}
        return request

    @pytest.mark.asyncio
    async def test_login_success(self, auth_backend, mock_request):
        from app.admin.auth import AdminAuth
        from app.core.config import settings

        # Mock form data with correct credentials
        mock_request.form = AsyncMock(
            return_value={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
            }
        )

        result = await auth_backend.login(mock_request)

        assert result is True
        assert "admin_token" in mock_request.session
        token = mock_request.session["admin_token"]
        assert len(token) > 0
        # Verify token is valid (can be validated)
        assert AdminAuth._validate_token(token, settings.SESSION_SECRET_KEY) is True

    @pytest.mark.asyncio
    async def test_login_failure_wrong_username(self, auth_backend, mock_request):
        from app.core.config import settings

        mock_request.form = AsyncMock(
            return_value={
                "username": "wrong_username",
                "password": settings.ADMIN_PASSWORD,
            }
        )

        result = await auth_backend.login(mock_request)

        assert result is False
        assert "admin_token" not in mock_request.session

    @pytest.mark.asyncio
    async def test_login_failure_wrong_password(self, auth_backend, mock_request):
        from app.core.config import settings

        mock_request.form = AsyncMock(
            return_value={
                "username": settings.ADMIN_USERNAME,
                "password": "wrong_password",
            }
        )

        result = await auth_backend.login(mock_request)

        assert result is False
        assert "admin_token" not in mock_request.session

    @pytest.mark.asyncio
    async def test_login_failure_empty_credentials(self, auth_backend, mock_request):
        mock_request.form = AsyncMock(return_value={"username": "", "password": ""})

        result = await auth_backend.login(mock_request)

        assert result is False
        assert "admin_token" not in mock_request.session

    @pytest.mark.asyncio
    async def test_login_failure_none_credentials(self, auth_backend, mock_request):
        mock_request.form = AsyncMock(return_value={})

        result = await auth_backend.login(mock_request)

        assert result is False
        assert "admin_token" not in mock_request.session

    @pytest.mark.asyncio
    async def test_logout_clears_session(self, auth_backend, mock_request):
        # Setup: add a token to the session
        mock_request.session["admin_token"] = "some_token"
        mock_request.session["other_data"] = "should_be_cleared"

        result = await auth_backend.logout(mock_request)

        assert result is True
        assert len(mock_request.session) == 0

    @pytest.mark.asyncio
    async def test_authenticate_with_valid_token(self, auth_backend, mock_request):
        from app.admin.auth import AdminAuth
        from app.core.config import settings

        token = AdminAuth._create_token(settings.SESSION_SECRET_KEY)
        mock_request.session["admin_token"] = token

        result = await auth_backend.authenticate(mock_request)

        assert result is True

    @pytest.mark.asyncio
    async def test_authenticate_without_token_redirects(
        self, auth_backend, mock_request
    ):
        from starlette.responses import RedirectResponse

        mock_request.session = {}
        mock_request.url_for = MagicMock(return_value="/admin/login")

        result = await auth_backend.authenticate(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302

    @pytest.mark.asyncio
    async def test_authenticate_with_invalid_token_redirects(
        self, auth_backend, mock_request
    ):
        from starlette.responses import RedirectResponse

        # Token exists in session but is not a valid HMAC token
        mock_request.session = {"admin_token": "invalid_token"}
        mock_request.url_for = MagicMock(return_value="/admin/login")

        result = await auth_backend.authenticate(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        # Session should be cleared
        assert len(mock_request.session) == 0

    @pytest.mark.asyncio
    async def test_authenticate_with_expired_token_redirects(
        self, auth_backend, mock_request
    ):
        import base64
        import hashlib
        import hmac

        from starlette.responses import RedirectResponse

        from app.core.config import settings

        # Create an expired token (timestamp from 2 days ago)
        expired_timestamp = int(time.time()) - 172800  # 48 hours ago
        credentials = f"{settings.ADMIN_USERNAME}:{settings.ADMIN_PASSWORD}"
        credentials_hash = hashlib.sha256(credentials.encode()).hexdigest()[:16]
        message = f"{credentials_hash}:{expired_timestamp}"
        signature = hmac.new(
            settings.SESSION_SECRET_KEY.encode(), message.encode(), hashlib.sha256
        ).hexdigest()[:32]
        expired_token = base64.urlsafe_b64encode(
            f"{message}:{signature}".encode()
        ).decode()

        mock_request.session = {"admin_token": expired_token}
        mock_request.url_for = MagicMock(return_value="/admin/login")

        result = await auth_backend.authenticate(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302

    @pytest.mark.asyncio
    async def test_authenticate_with_tampered_token_redirects(
        self, auth_backend, mock_request
    ):
        import base64

        from starlette.responses import RedirectResponse

        from app.admin.auth import AdminAuth

        timestamp = int(time.time())
        credentials_hash = AdminAuth._get_credentials_hash()
        message = f"{credentials_hash}:{timestamp}"
        tampered_signature = "tampered_signature_here_12345678"
        tampered_token = base64.urlsafe_b64encode(
            f"{message}:{tampered_signature}".encode()
        ).decode()

        mock_request.session = {"admin_token": tampered_token}
        mock_request.url_for = MagicMock(return_value="/admin/login")

        result = await auth_backend.authenticate(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302


class TestAdminViewConfigurations:

    def test_plan_admin_configuration(self):
        from app.admin.views import PlanAdmin

        assert PlanAdmin.name == "Plan"
        assert PlanAdmin.name_plural == "Plans"
        assert PlanAdmin.can_create is True
        assert PlanAdmin.can_edit is True
        assert PlanAdmin.can_delete is True
        assert PlanAdmin.can_view_details is True
        assert PlanAdmin.can_export is True

    def test_endpoint_cost_config_admin_configuration(self):
        from app.admin.views import FeatureCostConfigAdmin

        assert FeatureCostConfigAdmin.name == "Feature Cost"
        assert FeatureCostConfigAdmin.name_plural == "Feature Costs"
        assert FeatureCostConfigAdmin.can_create is True
        assert FeatureCostConfigAdmin.can_edit is True
        assert FeatureCostConfigAdmin.can_delete is True

    def test_plan_pricing_rule_admin_configuration(self):
        from app.admin.views import PlanPricingRuleAdmin

        assert PlanPricingRuleAdmin.name == "Plan Pricing Rule"
        assert PlanPricingRuleAdmin.name_plural == "Plan Pricing Rules"
        assert PlanPricingRuleAdmin.can_create is True
        assert PlanPricingRuleAdmin.can_edit is True
        assert PlanPricingRuleAdmin.can_delete is True

    def test_user_admin_is_read_only(self):
        from app.admin.views import UserAdmin

        assert UserAdmin.name == "User"
        assert UserAdmin.name_plural == "Users"
        assert UserAdmin.can_create is False
        assert UserAdmin.can_edit is False
        assert UserAdmin.can_delete is False
        assert UserAdmin.can_view_details is True
        assert UserAdmin.can_export is True

    def test_workspace_admin_is_read_only(self):
        from app.admin.views import WorkspaceAdmin

        assert WorkspaceAdmin.name == "Workspace"
        assert WorkspaceAdmin.name_plural == "Workspaces"
        assert WorkspaceAdmin.can_create is False
        assert WorkspaceAdmin.can_edit is False
        assert WorkspaceAdmin.can_delete is False
        assert WorkspaceAdmin.can_view_details is True

    def test_workspace_member_admin_is_read_only(self):
        from app.admin.views import WorkspaceMemberAdmin

        assert WorkspaceMemberAdmin.name == "Workspace Member"
        assert WorkspaceMemberAdmin.name_plural == "Workspace Members"
        assert WorkspaceMemberAdmin.can_create is False
        assert WorkspaceMemberAdmin.can_edit is False
        assert WorkspaceMemberAdmin.can_delete is False

    def test_subscription_admin_limited_edit(self):
        from app.admin.views import SubscriptionAdmin

        assert SubscriptionAdmin.name == "Subscription"
        assert SubscriptionAdmin.name_plural == "Subscriptions"
        assert SubscriptionAdmin.can_create is False  # No manual creation
        assert SubscriptionAdmin.can_edit is True  # Can edit status
        assert SubscriptionAdmin.can_delete is False  # No deletion
        assert SubscriptionAdmin.can_view_details is True


class TestAdminSetup:

    def test_init_admin_creates_instance(self):
        from unittest.mock import MagicMock

        from app.admin.setup import init_admin

        mock_app = MagicMock()
        init_admin(mock_app)

        from app.admin.setup import admin

        assert admin is not None
        assert admin.base_url == "/admin"
        assert admin.title == "CueBX Admin"

    def test_admin_has_authentication(self):
        from unittest.mock import MagicMock

        from app.admin.auth import admin_auth
        from app.admin.setup import admin, init_admin

        if admin is None:
            mock_app = MagicMock()
            init_admin(mock_app)

        from app.admin.setup import admin as current_admin

        assert current_admin is not None
        assert current_admin.authentication_backend is admin_auth


class TestAdminSettingsConfiguration:

    def test_admin_settings_exist(self):
        from app.core.config import settings

        assert hasattr(settings, "ADMIN_USERNAME")
        assert hasattr(settings, "ADMIN_PASSWORD")

    def test_admin_settings_have_defaults(self):
        from app.core.config import settings

        # These should have defaults (for development)
        assert settings.ADMIN_USERNAME is not None
        assert settings.ADMIN_PASSWORD is not None
        assert len(settings.ADMIN_USERNAME) > 0
        assert len(settings.ADMIN_PASSWORD) > 0

