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
    """Test that admin module imports correctly."""

    def test_admin_module_imports(self):
        """Test that admin module can be imported."""
        from app.admin import init_admin

        # admin is None until init_admin is called
        assert init_admin is not None
        assert callable(init_admin)

    def test_admin_views_import(self):
        """Test that all admin views can be imported."""
        from app.admin.views import (
            EndpointCostConfigAdmin,
            PlanAdmin,
            PlanPricingRuleAdmin,
            SubscriptionAdmin,
            UserAdmin,
            WorkspaceAdmin,
            WorkspaceMemberAdmin,
        )

        assert PlanAdmin is not None
        assert EndpointCostConfigAdmin is not None
        assert PlanPricingRuleAdmin is not None
        assert UserAdmin is not None
        assert WorkspaceAdmin is not None
        assert WorkspaceMemberAdmin is not None
        assert SubscriptionAdmin is not None

    def test_admin_auth_import(self):
        """Test that auth backend can be imported."""
        from app.admin.auth import AdminAuth, admin_auth

        assert AdminAuth is not None
        assert admin_auth is not None

    def test_admin_setup_import(self):
        """Test that setup module can be imported."""
        from app.admin.setup import init_admin

        # admin is None until init_admin is called
        assert init_admin is not None
        assert callable(init_admin)


class TestAdminAuthBackend:
    """Test suite for AdminAuth authentication backend."""

    @pytest.fixture
    def auth_backend(self):
        """Create a fresh AdminAuth instance for testing."""
        from app.admin.auth import AdminAuth
        from app.shared.config import settings

        return AdminAuth(secret_key=settings.SESSION_SECRET_KEY)

    @pytest.fixture
    def mock_request(self):
        """Create a mock request object."""
        request = MagicMock()
        request.session = {}
        return request

    @pytest.mark.asyncio
    async def test_login_success(self, auth_backend, mock_request):
        """Test successful login with correct credentials."""
        from app.admin.auth import AdminAuth
        from app.shared.config import settings

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
        """Test login failure with wrong username."""
        from app.shared.config import settings

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
        """Test login failure with wrong password."""
        from app.shared.config import settings

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
        """Test login failure with empty credentials."""
        mock_request.form = AsyncMock(return_value={"username": "", "password": ""})

        result = await auth_backend.login(mock_request)

        assert result is False
        assert "admin_token" not in mock_request.session

    @pytest.mark.asyncio
    async def test_login_failure_none_credentials(self, auth_backend, mock_request):
        """Test login failure with None credentials."""
        mock_request.form = AsyncMock(return_value={})

        result = await auth_backend.login(mock_request)

        assert result is False
        assert "admin_token" not in mock_request.session

    @pytest.mark.asyncio
    async def test_logout_clears_session(self, auth_backend, mock_request):
        """Test that logout clears the session."""
        # Setup: add a token to the session
        mock_request.session["admin_token"] = "some_token"
        mock_request.session["other_data"] = "should_be_cleared"

        result = await auth_backend.logout(mock_request)

        assert result is True
        assert len(mock_request.session) == 0

    @pytest.mark.asyncio
    async def test_authenticate_with_valid_token(self, auth_backend, mock_request):
        """Test authentication succeeds with valid HMAC token in session."""
        from app.admin.auth import AdminAuth
        from app.shared.config import settings

        # Generate a valid HMAC token
        token = AdminAuth._create_token(settings.SESSION_SECRET_KEY)
        mock_request.session["admin_token"] = token

        result = await auth_backend.authenticate(mock_request)

        assert result is True

    @pytest.mark.asyncio
    async def test_authenticate_without_token_redirects(
        self, auth_backend, mock_request
    ):
        """Test authentication redirects when no token in session."""
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
        """Test authentication redirects when token has invalid signature."""
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
        """Test authentication redirects when token is expired."""
        import base64
        import hashlib
        import hmac

        from starlette.responses import RedirectResponse

        from app.shared.config import settings

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
        """Test authentication redirects when token signature is tampered."""
        import base64

        from starlette.responses import RedirectResponse

        from app.admin.auth import AdminAuth

        # Create a token with wrong signature
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
    """Test suite for admin view configurations."""

    def test_plan_admin_configuration(self):
        """Test PlanAdmin view configuration."""
        from app.admin.views import PlanAdmin

        assert PlanAdmin.name == "Plan"
        assert PlanAdmin.name_plural == "Plans"
        assert PlanAdmin.can_create is True
        assert PlanAdmin.can_edit is True
        assert PlanAdmin.can_delete is True
        assert PlanAdmin.can_view_details is True
        assert PlanAdmin.can_export is True

    def test_endpoint_cost_config_admin_configuration(self):
        """Test EndpointCostConfigAdmin view configuration."""
        from app.admin.views import EndpointCostConfigAdmin

        assert EndpointCostConfigAdmin.name == "Endpoint Cost"
        assert EndpointCostConfigAdmin.name_plural == "Endpoint Costs"
        assert EndpointCostConfigAdmin.can_create is True
        assert EndpointCostConfigAdmin.can_edit is True
        assert EndpointCostConfigAdmin.can_delete is True

    def test_plan_pricing_rule_admin_configuration(self):
        """Test PlanPricingRuleAdmin view configuration."""
        from app.admin.views import PlanPricingRuleAdmin

        assert PlanPricingRuleAdmin.name == "Plan Pricing Rule"
        assert PlanPricingRuleAdmin.name_plural == "Plan Pricing Rules"
        assert PlanPricingRuleAdmin.can_create is True
        assert PlanPricingRuleAdmin.can_edit is True
        assert PlanPricingRuleAdmin.can_delete is True

    def test_user_admin_is_read_only(self):
        """Test UserAdmin view is read-only."""
        from app.admin.views import UserAdmin

        assert UserAdmin.name == "User"
        assert UserAdmin.name_plural == "Users"
        assert UserAdmin.can_create is False
        assert UserAdmin.can_edit is False
        assert UserAdmin.can_delete is False
        assert UserAdmin.can_view_details is True
        assert UserAdmin.can_export is True

    def test_workspace_admin_is_read_only(self):
        """Test WorkspaceAdmin view is read-only."""
        from app.admin.views import WorkspaceAdmin

        assert WorkspaceAdmin.name == "Workspace"
        assert WorkspaceAdmin.name_plural == "Workspaces"
        assert WorkspaceAdmin.can_create is False
        assert WorkspaceAdmin.can_edit is False
        assert WorkspaceAdmin.can_delete is False
        assert WorkspaceAdmin.can_view_details is True

    def test_workspace_member_admin_is_read_only(self):
        """Test WorkspaceMemberAdmin view is read-only."""
        from app.admin.views import WorkspaceMemberAdmin

        assert WorkspaceMemberAdmin.name == "Workspace Member"
        assert WorkspaceMemberAdmin.name_plural == "Workspace Members"
        assert WorkspaceMemberAdmin.can_create is False
        assert WorkspaceMemberAdmin.can_edit is False
        assert WorkspaceMemberAdmin.can_delete is False

    def test_subscription_admin_limited_edit(self):
        """Test SubscriptionAdmin allows limited editing."""
        from app.admin.views import SubscriptionAdmin

        assert SubscriptionAdmin.name == "Subscription"
        assert SubscriptionAdmin.name_plural == "Subscriptions"
        assert SubscriptionAdmin.can_create is False  # No manual creation
        assert SubscriptionAdmin.can_edit is True  # Can edit status
        assert SubscriptionAdmin.can_delete is False  # No deletion
        assert SubscriptionAdmin.can_view_details is True


class TestAdminSetup:
    """Test suite for admin setup and initialization."""

    def test_init_admin_creates_instance(self):
        """Test that init_admin creates and registers admin views."""
        from unittest.mock import MagicMock

        from app.admin.setup import init_admin

        mock_app = MagicMock()
        init_admin(mock_app)

        # Verify admin was created
        from app.admin.setup import admin

        assert admin is not None
        assert admin.base_url == "/admin"
        assert admin.title == "CueBX Admin"

    def test_admin_has_authentication(self):
        """Test that admin has authentication backend configured."""
        from unittest.mock import MagicMock

        from app.admin.auth import admin_auth
        from app.admin.setup import admin, init_admin

        # Initialize if not already done
        if admin is None:
            mock_app = MagicMock()
            init_admin(mock_app)

        from app.admin.setup import admin as current_admin

        assert current_admin is not None
        assert current_admin.authentication_backend is admin_auth


class TestAdminSettingsConfiguration:
    """Test suite for admin settings in config."""

    def test_admin_settings_exist(self):
        """Test that admin settings are defined in config."""
        from app.shared.config import settings

        assert hasattr(settings, "ADMIN_USERNAME")
        assert hasattr(settings, "ADMIN_PASSWORD")

    def test_admin_settings_have_defaults(self):
        """Test that admin settings have default values."""
        from app.shared.config import settings

        # These should have defaults (for development)
        assert settings.ADMIN_USERNAME is not None
        assert settings.ADMIN_PASSWORD is not None
        assert len(settings.ADMIN_USERNAME) > 0
        assert len(settings.ADMIN_PASSWORD) > 0
