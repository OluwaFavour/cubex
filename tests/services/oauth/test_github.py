"""
Test suite for GitHubOAuthService.

This module contains comprehensive tests for the GitHub OAuth provider including:
- Authorization URL generation with correct scopes and parameters
- Token exchange flow
- User info retrieval (including primary email fetch)
- Error handling for API failures
- Configuration validation

Run all tests:
    pytest app/tests/services/oauth/test_github.py -v

Run with coverage:
    pytest app/tests/services/oauth/test_github.py --cov=app.core.services.oauth.github --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.core.exceptions.types import OAuthException


class TestGitHubOAuthServiceInit:
    """Test suite for GitHubOAuthService initialization."""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        """Cleanup fixture to close client after each test."""
        from app.core.services.oauth.github import GitHubOAuthService

        yield
        await GitHubOAuthService.aclose()

    def test_provider_name(self):
        """Test that provider_name is 'github'."""
        from app.core.services.oauth.github import GitHubOAuthService

        assert GitHubOAuthService.provider_name == "github"

    @pytest.mark.asyncio
    async def test_init_creates_client(self):
        """Test that init creates HTTP client."""
        from app.core.services.oauth.github import GitHubOAuthService

        await GitHubOAuthService.init()

        assert GitHubOAuthService._client is not None
        assert isinstance(GitHubOAuthService._client, httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_init_with_custom_credentials(self):
        """Test that init accepts custom credentials."""
        from app.core.services.oauth.github import GitHubOAuthService

        await GitHubOAuthService.init(
            client_id="custom_github_id",
            client_secret="custom_github_secret",
        )

        assert GitHubOAuthService._client_id == "custom_github_id"
        assert GitHubOAuthService._client_secret == "custom_github_secret"

    @pytest.mark.asyncio
    async def test_aclose_closes_client(self):
        """Test that aclose closes the HTTP client."""
        from app.core.services.oauth.github import GitHubOAuthService

        await GitHubOAuthService.init()
        assert GitHubOAuthService._client is not None

        await GitHubOAuthService.aclose()

        assert GitHubOAuthService._client is None

    @pytest.mark.asyncio
    async def test_aclose_when_client_is_none(self):
        """Test that aclose handles None client gracefully."""
        from app.core.services.oauth.github import GitHubOAuthService

        GitHubOAuthService._client = None

        # Should not raise any exception
        await GitHubOAuthService.aclose()

        assert GitHubOAuthService._client is None


class TestGitHubAuthorizationUrl:
    """Test suite for GitHub authorization URL generation."""

    def test_get_authorization_url_structure(self):
        """Test that authorization URL has correct structure."""
        from app.core.services.oauth.github import GitHubOAuthService

        url = GitHubOAuthService.get_authorization_url(
            redirect_uri="https://app.com/callback",
            state="test_state_123",
        )

        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "github.com"
        assert parsed.path == "/login/oauth/authorize"

    def test_get_authorization_url_contains_client_id(self):
        """Test that authorization URL contains client_id."""
        from app.core.services.oauth.github import GitHubOAuthService

        url = GitHubOAuthService.get_authorization_url(
            redirect_uri="https://app.com/callback",
            state="test_state",
        )

        params = parse_qs(urlparse(url).query)
        assert "client_id" in params

    def test_get_authorization_url_contains_redirect_uri(self):
        """Test that authorization URL contains redirect_uri."""
        from app.core.services.oauth.github import GitHubOAuthService

        redirect_uri = "https://app.com/callback"
        url = GitHubOAuthService.get_authorization_url(
            redirect_uri=redirect_uri,
            state="test_state",
        )

        params = parse_qs(urlparse(url).query)
        assert params["redirect_uri"][0] == redirect_uri

    def test_get_authorization_url_contains_state(self):
        """Test that authorization URL contains state parameter."""
        from app.core.services.oauth.github import GitHubOAuthService

        state = "unique_state_token"
        url = GitHubOAuthService.get_authorization_url(
            redirect_uri="https://app.com/callback",
            state=state,
        )

        params = parse_qs(urlparse(url).query)
        assert params["state"][0] == state

    def test_get_authorization_url_has_correct_scopes(self):
        """Test that authorization URL requests correct scopes."""
        from app.core.services.oauth.github import GitHubOAuthService

        url = GitHubOAuthService.get_authorization_url(
            redirect_uri="https://app.com/callback",
            state="test_state",
        )

        params = parse_qs(urlparse(url).query)
        scopes = params["scope"][0].split()

        # GitHub requires user:email scope for email access
        assert "user:email" in scopes or "read:user" in scopes


class TestGitHubTokenExchange:
    """Test suite for GitHub token exchange."""

    @pytest.fixture(autouse=True)
    async def setup_client(self):
        """Setup HTTP client for each test."""
        from app.core.services.oauth.github import GitHubOAuthService

        await GitHubOAuthService.init()
        yield
        await GitHubOAuthService.aclose()

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_success(self):
        """Test successful token exchange."""
        from app.core.services.oauth.github import GitHubOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "gho_access_token_123",
            "token_type": "bearer",
            "scope": "read:user,user:email",
        }

        with patch.object(
            GitHubOAuthService._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            tokens = await GitHubOAuthService.exchange_code_for_tokens(
                code="github_auth_code",
                redirect_uri="https://app.com/callback",
            )

            assert tokens.access_token == "gho_access_token_123"
            assert tokens.token_type == "bearer"
            assert tokens.scope == "read:user,user:email"

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_posts_to_correct_url(self):
        """Test that token exchange posts to correct GitHub endpoint."""
        from app.core.services.oauth.github import GitHubOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test",
            "token_type": "bearer",
        }

        with patch.object(
            GitHubOAuthService._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            await GitHubOAuthService.exchange_code_for_tokens(
                code="auth_code",
                redirect_uri="https://app.com/callback",
            )

            call_args = mock_post.call_args
            assert call_args[0][0] == "https://github.com/login/oauth/access_token"

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_sends_correct_headers(self):
        """Test that token exchange sends Accept: application/json header."""
        from app.core.services.oauth.github import GitHubOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test",
            "token_type": "bearer",
        }

        with patch.object(
            GitHubOAuthService._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            await GitHubOAuthService.exchange_code_for_tokens(
                code="auth_code",
                redirect_uri="https://app.com/callback",
            )

            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["headers"]["Accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_failure(self):
        """Test token exchange failure handling."""
        from app.core.services.oauth.github import GitHubOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": "bad_verification_code",
            "error_description": "The code passed is incorrect or expired.",
        }

        with patch.object(
            GitHubOAuthService._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(OAuthException) as exc_info:
                await GitHubOAuthService.exchange_code_for_tokens(
                    code="expired_code",
                    redirect_uri="https://app.com/callback",
                )

            assert "token exchange" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_http_error(self):
        """Test token exchange HTTP error handling."""
        from app.core.services.oauth.github import GitHubOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch.object(
            GitHubOAuthService._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(OAuthException):
                await GitHubOAuthService.exchange_code_for_tokens(
                    code="auth_code",
                    redirect_uri="https://app.com/callback",
                )

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_network_error(self):
        """Test token exchange network error handling."""
        from app.core.services.oauth.github import GitHubOAuthService

        with patch.object(
            GitHubOAuthService._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.side_effect = httpx.RequestError("Connection failed")

            with pytest.raises(OAuthException):
                await GitHubOAuthService.exchange_code_for_tokens(
                    code="auth_code",
                    redirect_uri="https://app.com/callback",
                )


class TestGitHubUserInfo:
    """Test suite for GitHub user info retrieval."""

    @pytest.fixture(autouse=True)
    async def setup_client(self):
        """Setup HTTP client for each test."""
        from app.core.services.oauth.github import GitHubOAuthService

        await GitHubOAuthService.init()
        yield
        await GitHubOAuthService.aclose()

    @pytest.mark.asyncio
    async def test_get_user_info_success(self):
        """Test successful user info retrieval."""
        from app.core.services.oauth.github import GitHubOAuthService

        user_response = MagicMock()
        user_response.status_code = 200
        user_response.json.return_value = {
            "id": 12345678,
            "login": "octocat",
            "name": "The Octocat",
            "email": "octocat@github.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/12345678",
        }

        emails_response = MagicMock()
        emails_response.status_code = 200
        emails_response.json.return_value = [
            {"email": "octocat@github.com", "primary": True, "verified": True},
            {"email": "secondary@example.com", "primary": False, "verified": True},
        ]

        with patch.object(
            GitHubOAuthService._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = [user_response, emails_response]

            user_info = await GitHubOAuthService.get_user_info(access_token="gho_token")

            assert user_info.provider == "github"
            assert user_info.provider_user_id == "12345678"
            assert user_info.email == "octocat@github.com"
            assert user_info.email_verified is True
            assert user_info.name == "The Octocat"
            assert "avatars.githubusercontent.com" in user_info.picture

    @pytest.mark.asyncio
    async def test_get_user_info_uses_primary_email(self):
        """Test that primary email is used when available."""
        from app.core.services.oauth.github import GitHubOAuthService

        user_response = MagicMock()
        user_response.status_code = 200
        user_response.json.return_value = {
            "id": 123,
            "login": "testuser",
            "email": None,  # No public email
        }

        emails_response = MagicMock()
        emails_response.status_code = 200
        emails_response.json.return_value = [
            {"email": "secondary@example.com", "primary": False, "verified": True},
            {"email": "primary@example.com", "primary": True, "verified": True},
        ]

        with patch.object(
            GitHubOAuthService._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = [user_response, emails_response]

            user_info = await GitHubOAuthService.get_user_info(access_token="token")

            assert user_info.email == "primary@example.com"
            assert user_info.email_verified is True

    @pytest.mark.asyncio
    async def test_get_user_info_fallback_to_verified_email(self):
        """Test fallback to first verified email when no primary."""
        from app.core.services.oauth.github import GitHubOAuthService

        user_response = MagicMock()
        user_response.status_code = 200
        user_response.json.return_value = {
            "id": 123,
            "login": "testuser",
            "email": None,
        }

        emails_response = MagicMock()
        emails_response.status_code = 200
        emails_response.json.return_value = [
            {"email": "unverified@example.com", "primary": False, "verified": False},
            {"email": "verified@example.com", "primary": False, "verified": True},
        ]

        with patch.object(
            GitHubOAuthService._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = [user_response, emails_response]

            user_info = await GitHubOAuthService.get_user_info(access_token="token")

            assert user_info.email == "verified@example.com"
            assert user_info.email_verified is True

    @pytest.mark.asyncio
    async def test_get_user_info_calls_correct_endpoints(self):
        """Test that correct GitHub API endpoints are called."""
        from app.core.services.oauth.github import GitHubOAuthService

        user_response = MagicMock()
        user_response.status_code = 200
        user_response.json.return_value = {"id": 123, "email": "test@example.com"}

        emails_response = MagicMock()
        emails_response.status_code = 200
        emails_response.json.return_value = []

        with patch.object(
            GitHubOAuthService._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = [user_response, emails_response]

            await GitHubOAuthService.get_user_info(access_token="token")

            calls = mock_get.call_args_list
            assert "api.github.com/user" in calls[0][0][0]
            assert "api.github.com/user/emails" in calls[1][0][0]

    @pytest.mark.asyncio
    async def test_get_user_info_sends_authorization_header(self):
        """Test that authorization header is sent correctly."""
        from app.core.services.oauth.github import GitHubOAuthService

        user_response = MagicMock()
        user_response.status_code = 200
        user_response.json.return_value = {"id": 123, "email": "test@example.com"}

        emails_response = MagicMock()
        emails_response.status_code = 200
        emails_response.json.return_value = []

        with patch.object(
            GitHubOAuthService._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = [user_response, emails_response]

            await GitHubOAuthService.get_user_info(access_token="my_token")

            # Check both calls have authorization header
            for call in mock_get.call_args_list:
                headers = call[1]["headers"]
                assert headers["Authorization"] == "Bearer my_token"

    @pytest.mark.asyncio
    async def test_get_user_info_failure(self):
        """Test user info retrieval failure handling."""
        from app.core.services.oauth.github import GitHubOAuthService

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Bad credentials"

        with patch.object(
            GitHubOAuthService._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(OAuthException) as exc_info:
                await GitHubOAuthService.get_user_info(access_token="invalid_token")

            assert "user info" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_get_user_info_stores_raw_data(self):
        """Test that raw response data is stored."""
        from app.core.services.oauth.github import GitHubOAuthService

        raw_data = {
            "id": 123,
            "login": "testuser",
            "email": "test@example.com",
            "custom_field": "custom_value",
        }

        user_response = MagicMock()
        user_response.status_code = 200
        user_response.json.return_value = raw_data

        emails_response = MagicMock()
        emails_response.status_code = 200
        emails_response.json.return_value = []

        with patch.object(
            GitHubOAuthService._client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = [user_response, emails_response]

            user_info = await GitHubOAuthService.get_user_info(access_token="token")

            assert user_info.raw_data == raw_data


class TestGitHubModuleExports:
    """Test suite for module exports."""

    def test_all_exports(self):
        """Test that __all__ contains expected exports."""
        from app.core.services.oauth import github

        assert hasattr(github, "__all__")
        assert "GitHubOAuthService" in github.__all__
