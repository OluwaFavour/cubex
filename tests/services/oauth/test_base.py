"""
Test suite for BaseOAuthProvider abstract class.

This module contains comprehensive tests for the BaseOAuthProvider including:
- Abstract method definitions
- Shared utility methods
- State token generation and verification
- Error handling patterns

Run all tests:
    pytest app/tests/services/oauth/test_base.py -v

Run with coverage:
    pytest app/tests/services/oauth/test_base.py --cov=app.shared.services.oauth.base --cov-report=term-missing -v
"""


import pytest


class TestBaseOAuthProviderAbstract:
    """Test suite for BaseOAuthProvider abstract class."""

    def test_base_provider_is_abstract(self):
        """Test that BaseOAuthProvider cannot be instantiated directly."""
        from app.shared.services.oauth.base import BaseOAuthProvider

        with pytest.raises(TypeError):
            BaseOAuthProvider()

    def test_base_provider_requires_get_authorization_url(self):
        """Test that subclasses must implement get_authorization_url."""
        from app.shared.services.oauth.base import BaseOAuthProvider

        class IncompleteProvider(BaseOAuthProvider):
            provider_name = "incomplete"

            async def exchange_code_for_tokens(self, code, redirect_uri):
                pass

            async def get_user_info(self, access_token):
                pass

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_base_provider_requires_exchange_code_for_tokens(self):
        """Test that subclasses must implement exchange_code_for_tokens."""
        from app.shared.services.oauth.base import BaseOAuthProvider

        class IncompleteProvider(BaseOAuthProvider):
            provider_name = "incomplete"

            def get_authorization_url(self, redirect_uri, state):
                pass

            async def get_user_info(self, access_token):
                pass

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_base_provider_requires_get_user_info(self):
        """Test that subclasses must implement get_user_info."""
        from app.shared.services.oauth.base import BaseOAuthProvider

        class IncompleteProvider(BaseOAuthProvider):
            provider_name = "incomplete"

            def get_authorization_url(self, redirect_uri, state):
                pass

            async def exchange_code_for_tokens(self, code, redirect_uri):
                pass

        with pytest.raises(TypeError):
            IncompleteProvider()


class TestGenerateState:
    """Test suite for state token generation."""

    def test_generate_state_returns_string(self):
        """Test that generate_state returns a string."""
        from app.shared.services.oauth.base import generate_state

        state = generate_state()
        assert isinstance(state, str)

    def test_generate_state_default_length(self):
        """Test that generate_state uses default length of 32 bytes (64 hex chars)."""
        from app.shared.services.oauth.base import generate_state

        state = generate_state()
        # 32 bytes = 64 hex characters
        assert len(state) == 64

    def test_generate_state_custom_length(self):
        """Test that generate_state respects custom length."""
        from app.shared.services.oauth.base import generate_state

        state = generate_state(length=16)
        # 16 bytes = 32 hex characters
        assert len(state) == 32

    def test_generate_state_is_unique(self):
        """Test that generate_state produces unique values."""
        from app.shared.services.oauth.base import generate_state

        states = [generate_state() for _ in range(100)]
        assert len(set(states)) == 100


class TestOAuthUserInfo:
    """Test suite for OAuthUserInfo dataclass."""

    def test_oauth_user_info_creation(self):
        """Test creating OAuthUserInfo with all fields."""
        from app.shared.services.oauth.base import OAuthUserInfo

        user_info = OAuthUserInfo(
            provider="google",
            provider_user_id="12345",
            email="user@example.com",
            email_verified=True,
            name="John Doe",
            given_name="John",
            family_name="Doe",
            picture="https://example.com/photo.jpg",
            raw_data={"custom": "data"},
        )

        assert user_info.provider == "google"
        assert user_info.provider_user_id == "12345"
        assert user_info.email == "user@example.com"
        assert user_info.email_verified is True
        assert user_info.name == "John Doe"
        assert user_info.given_name == "John"
        assert user_info.family_name == "Doe"
        assert user_info.picture == "https://example.com/photo.jpg"
        assert user_info.raw_data == {"custom": "data"}

    def test_oauth_user_info_minimal(self):
        """Test creating OAuthUserInfo with minimal fields."""
        from app.shared.services.oauth.base import OAuthUserInfo

        user_info = OAuthUserInfo(
            provider="github",
            provider_user_id="67890",
            email="user@example.com",
        )

        assert user_info.provider == "github"
        assert user_info.provider_user_id == "67890"
        assert user_info.email == "user@example.com"
        assert user_info.email_verified is False
        assert user_info.name is None
        assert user_info.given_name is None
        assert user_info.family_name is None
        assert user_info.picture is None
        assert user_info.raw_data == {}

    def test_oauth_user_info_to_dict(self):
        """Test converting OAuthUserInfo to dictionary."""
        from app.shared.services.oauth.base import OAuthUserInfo

        user_info = OAuthUserInfo(
            provider="google",
            provider_user_id="12345",
            email="user@example.com",
            name="John Doe",
        )

        data = user_info.to_dict()

        assert isinstance(data, dict)
        assert data["provider"] == "google"
        assert data["provider_user_id"] == "12345"
        assert data["email"] == "user@example.com"
        assert data["name"] == "John Doe"


class TestOAuthTokens:
    """Test suite for OAuthTokens dataclass."""

    def test_oauth_tokens_creation(self):
        """Test creating OAuthTokens with all fields."""
        from app.shared.services.oauth.base import OAuthTokens

        tokens = OAuthTokens(
            access_token="access_123",
            token_type="Bearer",
            expires_in=3600,
            refresh_token="refresh_456",
            scope="openid email profile",
            id_token="id_token_789",
        )

        assert tokens.access_token == "access_123"
        assert tokens.token_type == "Bearer"
        assert tokens.expires_in == 3600
        assert tokens.refresh_token == "refresh_456"
        assert tokens.scope == "openid email profile"
        assert tokens.id_token == "id_token_789"

    def test_oauth_tokens_minimal(self):
        """Test creating OAuthTokens with minimal fields."""
        from app.shared.services.oauth.base import OAuthTokens

        tokens = OAuthTokens(
            access_token="access_123",
            token_type="Bearer",
        )

        assert tokens.access_token == "access_123"
        assert tokens.token_type == "Bearer"
        assert tokens.expires_in is None
        assert tokens.refresh_token is None
        assert tokens.scope is None
        assert tokens.id_token is None


class TestConcreteProvider:
    """Test suite using a concrete implementation of BaseOAuthProvider."""

    @pytest.fixture
    def concrete_provider(self):
        """Create a concrete implementation for testing."""
        from app.shared.services.oauth.base import (
            BaseOAuthProvider,
            OAuthTokens,
            OAuthUserInfo,
        )

        class TestProvider(BaseOAuthProvider):
            provider_name = "test"

            def get_authorization_url(self, redirect_uri: str, state: str) -> str:
                return f"https://test.com/auth?redirect_uri={redirect_uri}&state={state}"

            async def exchange_code_for_tokens(
                self, code: str, redirect_uri: str
            ) -> OAuthTokens:
                return OAuthTokens(
                    access_token="test_access_token",
                    token_type="Bearer",
                )

            async def get_user_info(self, access_token: str) -> OAuthUserInfo:
                return OAuthUserInfo(
                    provider="test",
                    provider_user_id="test_123",
                    email="test@example.com",
                )

        return TestProvider()

    def test_provider_name(self, concrete_provider):
        """Test that provider_name is accessible."""
        assert concrete_provider.provider_name == "test"

    def test_get_authorization_url(self, concrete_provider):
        """Test get_authorization_url method."""
        url = concrete_provider.get_authorization_url(
            redirect_uri="https://app.com/callback",
            state="random_state_123",
        )

        assert "https://test.com/auth" in url
        assert "redirect_uri=https://app.com/callback" in url
        assert "state=random_state_123" in url

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens(self, concrete_provider):
        """Test exchange_code_for_tokens method."""
        tokens = await concrete_provider.exchange_code_for_tokens(
            code="auth_code_123",
            redirect_uri="https://app.com/callback",
        )

        assert tokens.access_token == "test_access_token"
        assert tokens.token_type == "Bearer"

    @pytest.mark.asyncio
    async def test_get_user_info(self, concrete_provider):
        """Test get_user_info method."""
        user_info = await concrete_provider.get_user_info(
            access_token="test_access_token"
        )

        assert user_info.provider == "test"
        assert user_info.provider_user_id == "test_123"
        assert user_info.email == "test@example.com"


class TestModuleExports:
    """Test suite for module exports."""

    def test_all_exports(self):
        """Test that __all__ contains expected exports."""
        from app.shared.services.oauth import base

        assert hasattr(base, "__all__")
        assert "BaseOAuthProvider" in base.__all__
        assert "OAuthUserInfo" in base.__all__
        assert "OAuthTokens" in base.__all__
        assert "generate_state" in base.__all__
