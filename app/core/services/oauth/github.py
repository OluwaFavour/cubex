"""
GitHub OAuth provider implementation.

This module provides OAuth authentication with GitHub, supporting
the standard authorization code flow.

Example usage:
    from app.core.services.oauth.github import GitHubOAuthService

    # Initialize the service
    await GitHubOAuthService.init()

    # Generate authorization URL
    url = GitHubOAuthService.get_authorization_url(
        redirect_uri="https://app.com/callback",
        state="random_state_token",
    )

    # After user authorization, exchange code for tokens
    tokens = await GitHubOAuthService.exchange_code_for_tokens(
        code="auth_code_from_callback",
        redirect_uri="https://app.com/callback",
    )

    # Get user information
    user_info = await GitHubOAuthService.get_user_info(tokens.access_token)
    print(f"User email: {user_info.email}")

    # Cleanup
    await GitHubOAuthService.aclose()
"""

import asyncio
from urllib.parse import urlencode

import httpx

from app.core.config import auth_logger, settings
from app.core.exceptions.types import OAuthException
from app.core.services.oauth.base import (
    BaseOAuthProvider,
    OAuthTokens,
    OAuthUserInfo,
)


__all__ = ["GitHubOAuthService"]


class GitHubOAuthService(BaseOAuthProvider):
    """
    GitHub OAuth service implementation.

    This class provides methods for authenticating users via GitHub OAuth.
    It follows the singleton pattern with class methods and manages an HTTP
    client for API requests.

    Attributes:
        provider_name: The provider identifier ("github").
        _client_id: GitHub OAuth client ID.
        _client_secret: GitHub OAuth client secret.
        _client: HTTP client for API requests.

    GitHub API Endpoints:
        - Authorization: https://github.com/login/oauth/authorize
        - Token: https://github.com/login/oauth/access_token
        - User: https://api.github.com/user
        - Emails: https://api.github.com/user/emails

    Scopes requested:
        - read:user: Read user profile data
        - user:email: Access user email addresses

    Example:
        >>> await GitHubOAuthService.init()
        >>> url = GitHubOAuthService.get_authorization_url(
        ...     redirect_uri="https://app.com/callback",
        ...     state="random_state",
        ... )
        >>> # User authorizes, callback receives code
        >>> tokens = await GitHubOAuthService.exchange_code_for_tokens(
        ...     code="xxx",
        ...     redirect_uri="https://app.com/callback",
        ... )
        >>> user_info = await GitHubOAuthService.get_user_info(tokens.access_token)
        >>> print(user_info.email)
    """

    provider_name: str = "github"

    _client_id: str = settings.GITHUB_CLIENT_ID
    _client_secret: str = settings.GITHUB_CLIENT_SECRET
    _client: httpx.AsyncClient | None = None

    # GitHub OAuth endpoints
    _AUTHORIZATION_URL: str = "https://github.com/login/oauth/authorize"
    _TOKEN_URL: str = "https://github.com/login/oauth/access_token"
    _USER_URL: str = "https://api.github.com/user"
    _EMAILS_URL: str = "https://api.github.com/user/emails"

    # OAuth scopes
    _SCOPES: list[str] = ["read:user", "user:email"]

    @classmethod
    async def init(
        cls,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        """
        Initialize the GitHub OAuth service.

        Sets up the HTTP client and optionally overrides credentials.
        Should be called during application startup.

        Args:
            client_id: Optional custom GitHub client ID.
            client_secret: Optional custom GitHub client secret.

        Returns:
            None
        """
        if client_id is not None:
            cls._client_id = client_id
        if client_secret is not None:
            cls._client_secret = client_secret

        await cls.aclose()
        cls._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        auth_logger.info("GitHubOAuthService initialized")

    @classmethod
    async def aclose(cls) -> None:
        """
        Close the HTTP client and cleanup resources.

        Should be called during application shutdown.

        Returns:
            None
        """
        if cls._client is not None:
            try:
                await cls._client.aclose()
            finally:
                cls._client = None
                auth_logger.info("GitHubOAuthService closed")

    @classmethod
    def get_authorization_url(cls, redirect_uri: str, state: str) -> str:
        """
        Generate GitHub OAuth authorization URL.

        Creates a URL for redirecting users to GitHub's authorization page.
        The URL includes all necessary parameters for the OAuth flow.

        Args:
            redirect_uri: The URI to redirect to after authorization.
                         Must be registered in GitHub OAuth App settings.
            state: A random state token for CSRF protection.
                   Should be stored in session and verified on callback.

        Returns:
            str: The full authorization URL with query parameters.

        Example:
            >>> url = GitHubOAuthService.get_authorization_url(
            ...     redirect_uri="https://app.com/auth/github/callback",
            ...     state="abc123",
            ... )
            >>> # Redirect user to this URL
        """
        params = {
            "client_id": cls._client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(cls._SCOPES),
            "state": state,
        }
        return f"{cls._AUTHORIZATION_URL}?{urlencode(params)}"

    @classmethod
    async def exchange_code_for_tokens(
        cls, code: str, redirect_uri: str
    ) -> OAuthTokens:
        """
        Exchange authorization code for access tokens.

        Sends a POST request to GitHub's token endpoint to exchange
        the authorization code received from the callback for an
        access token.

        Args:
            code: The authorization code from the OAuth callback.
            redirect_uri: The same redirect URI used in authorization.

        Returns:
            OAuthTokens: Container with access_token, token_type, and scope.
                        Note: GitHub does not return refresh tokens by default.

        Raises:
            OAuthException: If token exchange fails due to invalid code,
                           network error, or other issues.

        Example:
            >>> tokens = await GitHubOAuthService.exchange_code_for_tokens(
            ...     code="auth_code_xxx",
            ...     redirect_uri="https://app.com/callback",
            ... )
            >>> print(tokens.access_token)
        """
        if cls._client is None:
            await cls.init()
            assert cls._client is not None, "Client initialization failed"

        data = {
            "code": code,
            "client_id": cls._client_id,
            "client_secret": cls._client_secret,
            "redirect_uri": redirect_uri,
        }

        headers = {"Accept": "application/json"}

        try:
            response = await cls._client.post(
                cls._TOKEN_URL, data=data, headers=headers
            )

            if response.status_code != 200:
                auth_logger.error(
                    f"GitHub token exchange failed: status={response.status_code}, "
                    f"response={response.text}"
                )
                raise OAuthException(
                    message=f"GitHub token exchange failed: {response.text}"
                )

            token_data = response.json()

            # GitHub returns error in response body with 200 status
            if "error" in token_data:
                error_msg = token_data.get("error_description", token_data.get("error"))
                auth_logger.error(f"GitHub token exchange error: {error_msg}")
                raise OAuthException(
                    message=f"GitHub token exchange failed: {error_msg}"
                )

            auth_logger.info("GitHub token exchange successful")

            return OAuthTokens(
                access_token=token_data["access_token"],
                token_type=token_data.get("token_type", "bearer"),
                scope=token_data.get("scope"),
            )

        except httpx.RequestError as e:
            auth_logger.error(f"GitHub token exchange network error: {e}")
            raise OAuthException(
                message="GitHub token exchange failed: network error"
            ) from e

    @classmethod
    async def _get_primary_email(cls, access_token: str) -> tuple[str | None, bool]:
        """
        Fetch the user's primary verified email from GitHub.

        GitHub users may have multiple email addresses. This method
        fetches all emails and returns the primary verified one.

        Note: This is an internal method that assumes the client is already
        initialized. It should only be called from methods that have already
        called init().

        Args:
            access_token: A valid access token.

        Returns:
            tuple: (email, email_verified) - The primary email and verification status.
                   Returns (None, False) if no suitable email is found.
        """
        # Client should already be initialized by caller (get_user_info)
        if cls._client is None:
            auth_logger.warning("_get_primary_email called without initialized client")
            return None, False

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            response = await cls._client.get(cls._EMAILS_URL, headers=headers)

            if response.status_code != 200:
                auth_logger.warning(
                    f"Failed to fetch GitHub emails: status={response.status_code}"
                )
                return None, False

            emails = response.json()

            # Find primary verified email
            for email_data in emails:
                if email_data.get("primary") and email_data.get("verified"):
                    return email_data["email"], True

            # Fallback to first verified email
            for email_data in emails:
                if email_data.get("verified"):
                    return email_data["email"], True

            # Last resort: first email
            if emails:
                return emails[0]["email"], emails[0].get("verified", False)

            return None, False

        except Exception as e:
            auth_logger.warning(f"Error fetching GitHub emails: {e}")
            return None, False

    @classmethod
    async def get_user_info(cls, access_token: str) -> OAuthUserInfo:
        """
        Retrieve user information from GitHub.

        Fetches the authenticated user's profile information and
        primary email address using the provided access token.

        Args:
            access_token: A valid access token from token exchange.

        Returns:
            OAuthUserInfo: Normalized user information including:
                - provider: "github"
                - provider_user_id: GitHub's unique user ID
                - email: User's primary email address
                - email_verified: Whether email is verified
                - name: Display name
                - picture: Avatar URL
                - raw_data: Complete API response

        Raises:
            OAuthException: If user info retrieval fails.

        Example:
            >>> user_info = await GitHubOAuthService.get_user_info(
            ...     access_token="gho_xxxxx"
            ... )
            >>> print(f"Email: {user_info.email}, Name: {user_info.name}")
        """
        if cls._client is None:
            await cls.init()
            assert cls._client is not None, "Client initialization failed"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        # Retry logic for transient network errors
        max_retries = 2
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                response = await cls._client.get(cls._USER_URL, headers=headers)

                if response.status_code != 200:
                    auth_logger.error(
                        f"GitHub user info retrieval failed: status={response.status_code}"
                    )
                    raise OAuthException(
                        message=f"Failed to retrieve GitHub user info: {response.text}"
                    )

                user_data = response.json()

                # Get email - may need to fetch from /user/emails endpoint
                email = user_data.get("email")
                email_verified = False

                if not email:
                    # Fetch primary email from emails endpoint
                    email, email_verified = await cls._get_primary_email(access_token)
                else:
                    # If email is in profile, check verification via emails endpoint
                    _, email_verified = await cls._get_primary_email(access_token)

                auth_logger.info(
                    f"GitHub user info retrieved: user_id={user_data.get('id')}"
                )

                return OAuthUserInfo(
                    provider=cls.provider_name,
                    provider_user_id=str(user_data["id"]),
                    email=email or "",
                    email_verified=email_verified,
                    name=user_data.get("name"),
                    picture=user_data.get("avatar_url"),
                    raw_data=user_data,
                )

            except httpx.RequestError as e:
                last_error = e
                auth_logger.warning(
                    f"GitHub user info network error (attempt {attempt + 1}/{max_retries + 1}): {type(e).__name__}: {e}"
                )
                if attempt < max_retries:
                    # Small delay before retry
                    await asyncio.sleep(0.5)
                    continue

        auth_logger.error(f"GitHub user info network error after retries: {last_error}")
        raise OAuthException(
            message="Failed to retrieve GitHub user info: network error"
        ) from last_error
