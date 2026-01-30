"""
Test suite for GoogleOAuthService.

This module contains comprehensive tests for the Google OAuth provider including:
- Authorization URL generation with correct scopes and parameters
- Token exchange flow
- User info retrieval
- Error handling for API failures
- Configuration validation

Run all tests:
    pytest app/tests/services/oauth/test_google.py -v

Run with coverage:
    pytest app/tests/services/oauth/test_google.py --cov=app.shared.services.oauth.google --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.shared.exceptions.types import OAuthException


class TestGoogleOAuthServiceInit:
    """Test suite for GoogleOAuthService initialization."""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        """Cleanup fixture to close client after each test."""
        from app.shared.services.oauth.google import GoogleOAuthService

        yield
        await GoogleOAuthService.aclose()

    def test_provider_name(self):
        """Test that provider_name is 'google'."""
        from app.shared.services.oauth.google import GoogleOAuthService

        assert GoogleOAuthService.provider_name == "google"

    @pytest.mark.asyncio
    async def test_init_creates_client(self):
        """Test that init creates HTTP client."""
        from app.shared.services.oauth.google import GoogleOAuthService

        await GoogleOAuthService.init()

        assert GoogleOAuthService._client is not None
        assert isinstance(GoogleOAuthService._client, httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_init_with_custom_credentials(self):
        """Test that init accepts custom credentials."""
        from app.shared.services.oauth.google import GoogleOAuthService

        await GoogleOAuthService.init(
            client_id="custom_client_id",
            client_secret="custom_client_secret",
        )

        assert GoogleOAuthService._client_id == "custom_client_id"
        assert GoogleOAuthService._client_secret == "custom_client_secret"

    @pytest.mark.asyncio
    async def test_aclose_closes_client(self):
        """Test that aclose closes the HTTP client."""
        from app.shared.services.oauth.google import GoogleOAuthService

        await GoogleOAuthService.init()
        assert GoogleOAuthService._client is not None

        await GoogleOAuthService.aclose()

        assert GoogleOAuthService._client is None

    @pytest.mark.asyncio
    async def test_aclose_when_client_is_none(self):
        """Test that aclose handles None client gracefully."""
        from app.shared.services.oauth.google import GoogleOAuthService

        GoogleOAuthService._client = None

        # Should not raise any exception
        await GoogleOAuthService.aclose()

        assert GoogleOAuthService._client is None


class TestGoogleAuthorizationUrl:
    """Test suite for Google authorization URL generation."""

    def test_get_authorization_url_structure(self):
        """Test that authorization URL has correct structure."""
        from app.shared.services.oauth.google import GoogleOAuthService

        url = GoogleOAuthService.get_authorization_url(
            redirect_uri="https://app.com/callback",
            state="test_state_123",
        )

        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "accounts.google.com"
        assert parsed.path == "/o/oauth2/v2/auth"

    def test_get_authorization_url_contains_client_id(self):
        """Test that authorization URL contains client_id."""
        from app.shared.services.oauth.google import GoogleOAuthService

        url = GoogleOAuthService.get_authorization_url(
            redirect_uri="https://app.com/callback",
            state="test_state",
        )

        params = parse_qs(urlparse(url).query)
        assert "client_id" in params

    def test_get_authorization_url_contains_redirect_uri(self):
        """Test that authorization URL contains redirect_uri."""
        from app.shared.services.oauth.google import GoogleOAuthService

        redirect_uri = "https://app.com/callback"
        url = GoogleOAuthService.get_authorization_url(
            redirect_uri=redirect_uri,
            state="test_state",
        )

        params = parse_qs(urlparse(url).query)
        assert params["redirect_uri"][0] == redirect_uri

    def test_get_authorization_url_contains_state(self):
        """Test that authorization URL contains state parameter."""
        from app.shared.services.oauth.google import GoogleOAuthService

        state = "unique_state_token"
        url = GoogleOAuthService.get_authorization_url(
            redirect_uri="https://app.com/callback",
            state=state,
        )

        params = parse_qs(urlparse(url).query)
        assert params["state"][0] == state

    def test_get_authorization_url_has_correct_scopes(self):
        """Test that authorization URL requests correct scopes."""
        from app.shared.services.oauth.google import GoogleOAuthService

        url = GoogleOAuthService.get_authorization_url(
            redirect_uri="https://app.com/callback",
            state="test_state",
        )

        params = parse_qs(urlparse(url).query)
        scopes = params["scope"][0].split()

        assert "openid" in scopes
        assert "email" in scopes
        assert "profile" in scopes

    def test_get_authorization_url_response_type_code(self):
        """Test that authorization URL uses code response type."""
        from app.shared.services.oauth.google import GoogleOAuthService

        url = GoogleOAuthService.get_authorization_url(
            redirect_uri="https://app.com/callback",
            state="test_state",
        )

        params = parse_qs(urlparse(url).query)
        assert params["response_type"][0] == "code"

    def test_get_authorization_url_access_type_offline(self):
        """Test that authorization URL requests offline access."""
        from app.shared.services.oauth.google import GoogleOAuthService

        url = GoogleOAuthService.get_authorization_url(
            redirect_uri="https://app.com/callback",
            state="test_state",
        )

        params = parse_qs(urlparse(url).query)
        assert params["access_type"][0] == "offline"


class TestGoogleTokenExchange:
    """Test suite for Google token exchange."""

    @pytest.fixture(autouse=True)
    async def setup_client(self):
        """Setup HTTP client for each test."""
        from app.shared.services.oauth.google import GoogleOAuthService

        await GoogleOAuthService.init()
        yield
        await GoogleOAuthService.aclose()

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_success(self):
        """Test successful token exchange."""
        from app.shared.services.oauth.google import GoogleOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "ya29.access_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "1//refresh_token",
            "scope": "openid email profile",
            "id_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
        }

        with patch.object(
            GoogleOAuthService._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            tokens = await GoogleOAuthService.exchange_code_for_tokens(
                code="4/0auth_code",
                redirect_uri="https://app.com/callback",
            )

            assert tokens.access_token == "ya29.access_token"
            assert tokens.token_type == "Bearer"
            assert tokens.expires_in == 3600
            assert tokens.refresh_token == "1//refresh_token"

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_posts_to_correct_url(self):
        """Test that token exchange posts to correct Google endpoint."""
        from app.shared.services.oauth.google import GoogleOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test",
            "token_type": "Bearer",
        }

        with patch.object(
            GoogleOAuthService._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            await GoogleOAuthService.exchange_code_for_tokens(
                code="auth_code",
                redirect_uri="https://app.com/callback",
            )

            call_args = mock_post.call_args
            assert call_args[0][0] == "https://oauth2.googleapis.com/token"

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_sends_correct_data(self):
        """Test that token exchange sends correct form data."""
        from app.shared.services.oauth.google import GoogleOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test",
            "token_type": "Bearer",
        }

        with patch.object(
            GoogleOAuthService._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            await GoogleOAuthService.exchange_code_for_tokens(
                code="auth_code_123",
                redirect_uri="https://app.com/callback",
            )

            call_kwargs = mock_post.call_args[1]
            data = call_kwargs["data"]

            assert data["code"] == "auth_code_123"
            assert data["redirect_uri"] == "https://app.com/callback"
            assert data["grant_type"] == "authorization_code"

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_failure(self):
        """Test token exchange failure handling."""
        from app.shared.services.oauth.google import GoogleOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant"
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Code expired",
        }

        with patch.object(
            GoogleOAuthService._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(OAuthException) as exc_info:
                await GoogleOAuthService.exchange_code_for_tokens(
                    code="expired_code",
                    redirect_uri="https://app.com/callback",
                )

            assert "token exchange" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_network_error(self):
        """Test token exchange network error handling."""
        from app.shared.services.oauth.google import GoogleOAuthService

        with patch.object(
            GoogleOAuthService._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.side_effect = httpx.RequestError("Connection failed")

            with pytest.raises(OAuthException):
                await GoogleOAuthService.exchange_code_for_tokens(
                    code="auth_code",
                    redirect_uri="https://app.com/callback",
                )


class TestGoogleUserInfo:
    """Test suite for Google user info retrieval."""

    @pytest.fixture(autouse=True)
    async def setup_client(self):
        """Setup HTTP client for each test."""
        from app.shared.services.oauth.google import GoogleOAuthService

        await GoogleOAuthService.init()
        yield
        await GoogleOAuthService.aclose()

    @pytest.mark.asyncio
    async def test_get_user_info_success(self):
        """Test successful user info retrieval."""
        from app.shared.services.oauth.google import GoogleOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sub": "123456789",
            "email": "user@gmail.com",
            "email_verified": True,
            "name": "John Doe",
            "given_name": "John",
            "family_name": "Doe",
            "picture": "https://lh3.googleusercontent.com/photo.jpg",
        }

        with patch.object(
            GoogleOAuthService._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            user_info = await GoogleOAuthService.get_user_info(
                access_token="ya29.access_token"
            )

            assert user_info.provider == "google"
            assert user_info.provider_user_id == "123456789"
            assert user_info.email == "user@gmail.com"
            assert user_info.email_verified is True
            assert user_info.name == "John Doe"
            assert user_info.given_name == "John"
            assert user_info.family_name == "Doe"
            assert "googleusercontent.com" in user_info.picture

    @pytest.mark.asyncio
    async def test_get_user_info_calls_correct_endpoint(self):
        """Test that user info is fetched from correct endpoint."""
        from app.shared.services.oauth.google import GoogleOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sub": "123",
            "email": "user@gmail.com",
        }

        with patch.object(
            GoogleOAuthService._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            await GoogleOAuthService.get_user_info(access_token="token")

            call_args = mock_get.call_args
            assert "googleapis.com/oauth2" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_user_info_sends_authorization_header(self):
        """Test that user info request includes authorization header."""
        from app.shared.services.oauth.google import GoogleOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sub": "123",
            "email": "user@gmail.com",
        }

        with patch.object(
            GoogleOAuthService._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            await GoogleOAuthService.get_user_info(access_token="my_token")

            call_kwargs = mock_get.call_args[1]
            assert "Authorization" in call_kwargs["headers"]
            assert call_kwargs["headers"]["Authorization"] == "Bearer my_token"

    @pytest.mark.asyncio
    async def test_get_user_info_failure(self):
        """Test user info retrieval failure handling."""
        from app.shared.services.oauth.google import GoogleOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid token"

        with patch.object(
            GoogleOAuthService._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(OAuthException) as exc_info:
                await GoogleOAuthService.get_user_info(access_token="invalid_token")

            assert "user info" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_get_user_info_stores_raw_data(self):
        """Test that raw response data is stored."""
        from app.shared.services.oauth.google import GoogleOAuthService

        raw_data = {
            "sub": "123",
            "email": "user@gmail.com",
            "custom_field": "custom_value",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = raw_data

        with patch.object(
            GoogleOAuthService._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            user_info = await GoogleOAuthService.get_user_info(access_token="token")

            assert user_info.raw_data == raw_data


class TestGoogleModuleExports:
    """Test suite for module exports."""

    def test_all_exports(self):
        """Test that __all__ contains expected exports."""
        from app.shared.services.oauth import google

        assert hasattr(google, "__all__")
        assert "GoogleOAuthService" in google.__all__
