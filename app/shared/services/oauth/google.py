"""
Google OAuth 2.0 provider implementation.

This module provides OAuth 2.0 authentication with Google, supporting
the standard authorization code flow with OpenID Connect.

Example usage:
    from app.shared.services.oauth.google import GoogleOAuthService

    # Initialize the service
    await GoogleOAuthService.init()

    # Generate authorization URL
    url = GoogleOAuthService.get_authorization_url(
        redirect_uri="https://app.com/callback",
        state="random_state_token",
    )

    # After user authorization, exchange code for tokens
    tokens = await GoogleOAuthService.exchange_code_for_tokens(
        code="4/0auth_code_from_callback",
        redirect_uri="https://app.com/callback",
    )

    # Get user information
    user_info = await GoogleOAuthService.get_user_info(tokens.access_token)
    print(f"User email: {user_info.email}")

    # Cleanup
    await GoogleOAuthService.aclose()
"""

from urllib.parse import urlencode

import httpx

from app.shared.config import auth_logger, settings
from app.shared.exceptions.types import OAuthException
from app.shared.services.oauth.base import (
    BaseOAuthProvider,
    OAuthTokens,
    OAuthUserInfo,
)


__all__ = ["GoogleOAuthService"]


class GoogleOAuthService(BaseOAuthProvider):
    """
    Google OAuth 2.0 service implementation.

    This class provides methods for authenticating users via Google OAuth 2.0.
    It follows the singleton pattern with class methods and manages an HTTP
    client for API requests.

    Attributes:
        provider_name: The provider identifier ("google").
        _client_id: Google OAuth client ID.
        _client_secret: Google OAuth client secret.
        _client: HTTP client for API requests.

    Google API Endpoints:
        - Authorization: https://accounts.google.com/o/oauth2/v2/auth
        - Token: https://oauth2.googleapis.com/token
        - User Info: https://www.googleapis.com/oauth2/v3/userinfo

    Scopes requested:
        - openid: OpenID Connect authentication
        - email: User's email address
        - profile: User's basic profile information

    Example:
        >>> await GoogleOAuthService.init()
        >>> url = GoogleOAuthService.get_authorization_url(
        ...     redirect_uri="https://app.com/callback",
        ...     state="random_state",
        ... )
        >>> # User authorizes, callback receives code
        >>> tokens = await GoogleOAuthService.exchange_code_for_tokens(
        ...     code="4/0xxx",
        ...     redirect_uri="https://app.com/callback",
        ... )
        >>> user_info = await GoogleOAuthService.get_user_info(tokens.access_token)
        >>> print(user_info.email)
    """

    provider_name: str = "google"

    _client_id: str = settings.GOOGLE_CLIENT_ID
    _client_secret: str = settings.GOOGLE_CLIENT_SECRET
    _client: httpx.AsyncClient | None = None

    # Google OAuth endpoints
    _AUTHORIZATION_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL: str = "https://oauth2.googleapis.com/token"
    _USERINFO_URL: str = "https://www.googleapis.com/oauth2/v3/userinfo"

    # OAuth scopes
    _SCOPES: list[str] = ["openid", "email", "profile"]

    @classmethod
    async def init(
        cls,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        """
        Initialize the Google OAuth service.

        Sets up the HTTP client and optionally overrides credentials.
        Should be called during application startup.

        Args:
            client_id: Optional custom Google client ID.
            client_secret: Optional custom Google client secret.

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
        auth_logger.info("GoogleOAuthService initialized")

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
                auth_logger.info("GoogleOAuthService closed")

    @classmethod
    def get_authorization_url(cls, redirect_uri: str, state: str) -> str:
        """
        Generate Google OAuth authorization URL.

        Creates a URL for redirecting users to Google's authorization page.
        The URL includes all necessary parameters for the OAuth flow.

        Args:
            redirect_uri: The URI to redirect to after authorization.
                         Must be registered in Google Cloud Console.
            state: A random state token for CSRF protection.
                   Should be stored in session and verified on callback.

        Returns:
            str: The full authorization URL with query parameters.

        Example:
            >>> url = GoogleOAuthService.get_authorization_url(
            ...     redirect_uri="https://app.com/auth/google/callback",
            ...     state="abc123",
            ... )
            >>> # Redirect user to this URL
        """
        params = {
            "client_id": cls._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(cls._SCOPES),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{cls._AUTHORIZATION_URL}?{urlencode(params)}"

    @classmethod
    async def exchange_code_for_tokens(
        cls, code: str, redirect_uri: str
    ) -> OAuthTokens:
        """
        Exchange authorization code for access tokens.

        Sends a POST request to Google's token endpoint to exchange
        the authorization code received from the callback for access
        and refresh tokens.

        Args:
            code: The authorization code from the OAuth callback.
            redirect_uri: The same redirect URI used in authorization.

        Returns:
            OAuthTokens: Container with access_token, token_type,
                        expires_in, refresh_token, scope, and id_token.

        Raises:
            OAuthException: If token exchange fails due to invalid code,
                           network error, or other issues.

        Example:
            >>> tokens = await GoogleOAuthService.exchange_code_for_tokens(
            ...     code="4/0AcvDMrBxxxxxx",
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
            "grant_type": "authorization_code",
        }

        try:
            response = await cls._client.post(cls._TOKEN_URL, data=data)

            if response.status_code != 200:
                auth_logger.error(
                    f"Google token exchange failed: status={response.status_code}, "
                    f"response={response.text}"
                )
                raise OAuthException(
                    message=f"Google token exchange failed: {response.text}"
                )

            token_data = response.json()

            auth_logger.info("Google token exchange successful")

            return OAuthTokens(
                access_token=token_data["access_token"],
                token_type=token_data["token_type"],
                expires_in=token_data.get("expires_in"),
                refresh_token=token_data.get("refresh_token"),
                scope=token_data.get("scope"),
                id_token=token_data.get("id_token"),
            )

        except httpx.RequestError as e:
            auth_logger.error(f"Google token exchange network error: {e}")
            raise OAuthException(
                message="Google token exchange failed: network error"
            ) from e

    @classmethod
    async def get_user_info(cls, access_token: str) -> OAuthUserInfo:
        """
        Retrieve user information from Google.

        Fetches the authenticated user's profile information using
        the provided access token.

        Args:
            access_token: A valid access token from token exchange.

        Returns:
            OAuthUserInfo: Normalized user information including:
                - provider: "google"
                - provider_user_id: Google's unique user ID (sub)
                - email: User's email address
                - email_verified: Whether email is verified
                - name: Full display name
                - given_name: First name
                - family_name: Last name
                - picture: Profile picture URL
                - raw_data: Complete API response

        Raises:
            OAuthException: If user info retrieval fails.

        Example:
            >>> user_info = await GoogleOAuthService.get_user_info(
            ...     access_token="ya29.xxxxx"
            ... )
            >>> print(f"Email: {user_info.email}, Verified: {user_info.email_verified}")
        """
        if cls._client is None:
            await cls.init()
            assert cls._client is not None, "Client initialization failed"

        headers = {"Authorization": f"Bearer {access_token}"}

        # Retry logic for transient network errors
        max_retries = 2
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                response = await cls._client.get(cls._USERINFO_URL, headers=headers)

                if response.status_code != 200:
                    auth_logger.error(
                        f"Google user info retrieval failed: status={response.status_code}"
                    )
                    raise OAuthException(
                        message=f"Failed to retrieve Google user info: {response.text}"
                    )

                user_data = response.json()

                auth_logger.info(
                    f"Google user info retrieved: user_id={user_data.get('sub')}"
                )

                return OAuthUserInfo(
                    provider=cls.provider_name,
                    provider_user_id=user_data["sub"],
                    email=user_data.get("email", ""),
                    email_verified=user_data.get("email_verified", False),
                    name=user_data.get("name"),
                    given_name=user_data.get("given_name"),
                    family_name=user_data.get("family_name"),
                    picture=user_data.get("picture"),
                    raw_data=user_data,
                )

            except httpx.RequestError as e:
                last_error = e
                auth_logger.warning(
                    f"Google user info network error (attempt {attempt + 1}/{max_retries + 1}): {type(e).__name__}: {e}"
                )
                if attempt < max_retries:
                    # Small delay before retry
                    await asyncio.sleep(0.5)
                    continue

        auth_logger.error(f"Google user info network error after retries: {last_error}")
        raise OAuthException(
            message="Failed to retrieve Google user info: network error"
        ) from last_error
