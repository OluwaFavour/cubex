"""
Base OAuth provider abstract class and core utilities.

Example usage:
    from app.core.services.oauth.base import BaseOAuthProvider, OAuthUserInfo

    class MyOAuthProvider(BaseOAuthProvider):
        provider_name = "my_provider"

        def get_authorization_url(self, redirect_uri: str, state: str) -> str:
            ...

        async def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> OAuthTokens:
            ...

        async def get_user_info(self, access_token: str) -> OAuthUserInfo:
            ...
"""

import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings


__all__ = [
    "BaseOAuthProvider",
    "OAuthTokens",
    "OAuthUserInfo",
    "OAuthStateData",
    "OAuthStateManager",
    "generate_state",
]


def generate_state(length: int = 32) -> str:
    """
    Generate a cryptographically secure random state token.

    The state token is used to prevent CSRF attacks in OAuth flows.
    It should be stored in the user's session and verified when the
    OAuth callback is received.

    Args:
        length: Number of random bytes to generate. Default is 32 bytes
                which produces a 64-character hex string.

    Returns:
        str: A hex-encoded random string of length * 2 characters.

    Example:
        >>> state = generate_state()
        >>> len(state)
        64
        >>> state = generate_state(length=16)
        >>> len(state)
        32
    """
    return secrets.token_hex(length)


@dataclass
class OAuthTokens:
    """
    Container for OAuth tokens returned from token exchange.

    Attributes:
        access_token: The access token for API calls.
        token_type: The type of token (usually "Bearer").
        expires_in: Optional token expiration time in seconds.
        refresh_token: Optional refresh token for obtaining new access tokens.
        scope: Optional space-separated list of granted scopes.
        id_token: Optional OpenID Connect ID token (JWT).

    Example:
        >>> tokens = OAuthTokens(
        ...     access_token="ya29.xxx",
        ...     token_type="Bearer",
        ...     expires_in=3600,
        ... )
        >>> tokens.access_token
        'ya29.xxx'
    """

    access_token: str
    token_type: str
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None
    id_token: str | None = None


@dataclass
class OAuthUserInfo:
    """
    Normalized user information from OAuth providers.

    This dataclass provides a consistent structure for user information
    across different OAuth providers (Google, GitHub, etc.).

    Attributes:
        provider: The OAuth provider name (e.g., "google", "github").
        provider_user_id: The user's unique ID from the provider.
        email: The user's email address.
        email_verified: Whether the email has been verified by the provider.
        name: Optional full display name.
        given_name: Optional first name.
        family_name: Optional last name.
        picture: Optional URL to profile picture.
        raw_data: The complete raw response from the provider API.

    Example:
        >>> user_info = OAuthUserInfo(
        ...     provider="google",
        ...     provider_user_id="123456",
        ...     email="user@example.com",
        ...     email_verified=True,
        ...     name="John Doe",
        ... )
        >>> user_info.to_dict()
        {'provider': 'google', 'provider_user_id': '123456', ...}
    """

    provider: str
    provider_user_id: str
    email: str
    email_verified: bool = False
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    picture: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert user info to a dictionary.

        Returns:
            dict: Dictionary representation of the user info.
        """
        return {
            "provider": self.provider,
            "provider_user_id": self.provider_user_id,
            "email": self.email,
            "email_verified": self.email_verified,
            "name": self.name,
            "given_name": self.given_name,
            "family_name": self.family_name,
            "picture": self.picture,
            "raw_data": self.raw_data,
        }


class BaseOAuthProvider(ABC):
    """
    Abstract base class for OAuth providers.

    This class defines the interface that all OAuth provider implementations
    must follow. It includes methods for generating authorization URLs,
    exchanging authorization codes for tokens, and retrieving user information.

    Subclasses must implement:
        - provider_name: Class attribute with the provider name
        - get_authorization_url: Generate OAuth authorization URL
        - exchange_code_for_tokens: Exchange auth code for access tokens
        - get_user_info: Retrieve user information using access token

    Example:
        >>> class MyProvider(BaseOAuthProvider):
        ...     provider_name = "my_provider"
        ...
        ...     def get_authorization_url(self, redirect_uri, state):
        ...         return f"https://auth.example.com?redirect_uri={redirect_uri}&state={state}"
        ...
        ...     async def exchange_code_for_tokens(self, code, redirect_uri):
        ...         # ... implementation
        ...         pass
        ...
        ...     async def get_user_info(self, access_token):
        ...         # ... implementation
        ...         pass
    """

    provider_name: str

    @classmethod
    @abstractmethod
    def get_authorization_url(cls, redirect_uri: str, state: str) -> str:
        """
        Generate the OAuth authorization URL.

        This URL is where the user should be redirected to begin the
        OAuth authentication flow.

        Args:
            redirect_uri: The URI to redirect to after authorization.
            state: A random state token for CSRF protection.

        Returns:
            str: The full authorization URL with query parameters.
        """
        pass

    @classmethod
    @abstractmethod
    async def exchange_code_for_tokens(
        cls, code: str, redirect_uri: str
    ) -> OAuthTokens:
        """
        Exchange an authorization code for access tokens.

        This is called after the user authorizes the application and
        is redirected back with an authorization code.

        Args:
            code: The authorization code from the OAuth callback.
            redirect_uri: The same redirect URI used in the authorization request.

        Returns:
            OAuthTokens: Container with access token and related data.

        Raises:
            OAuthException: If token exchange fails.
        """
        pass

    @classmethod
    @abstractmethod
    async def get_user_info(cls, access_token: str) -> OAuthUserInfo:
        """
        Retrieve user information using an access token.

        Args:
            access_token: A valid access token from token exchange.

        Returns:
            OAuthUserInfo: Normalized user information.

        Raises:
            OAuthException: If user info retrieval fails.
        """
        pass


# State serializer for encoding callback URL and other data
_state_serializer = URLSafeTimedSerializer(
    secret_key=settings.SESSION_SECRET_KEY,
    salt="oauth-state",
)


@dataclass
class OAuthStateData:
    """Data encoded in OAuth state parameter."""

    callback_url: str | None = None
    remember_me: bool = False
    nonce: str = field(default_factory=lambda: secrets.token_hex(16))


class OAuthStateManager:
    """
    Manager for encoding/decoding OAuth state parameters.

    Uses itsdangerous to sign and serialize state data, ensuring
    it hasn't been tampered with and hasn't expired.
    """

    # State expires after 10 minutes
    STATE_MAX_AGE_SECONDS: int = 600

    @classmethod
    def encode_state(
        cls,
        callback_url: str | None = None,
        remember_me: bool = False,
    ) -> str:
        """
        Encode OAuth state data into a signed, URL-safe string.

        Args:
            callback_url: Frontend callback URL to redirect after OAuth.
            remember_me: Whether to extend session duration.

        Returns:
            str: Signed, URL-safe state string.
        """
        data = {
            "callback_url": callback_url,
            "remember_me": remember_me,
            "nonce": secrets.token_hex(16),
        }
        return _state_serializer.dumps(data)

    @classmethod
    def decode_state(cls, state: str) -> OAuthStateData | None:
        """
        Decode and verify OAuth state parameter.

        Args:
            state: The signed state string from OAuth callback.

        Returns:
            OAuthStateData if valid, None if invalid or expired.
        """
        try:
            data = _state_serializer.loads(state, max_age=cls.STATE_MAX_AGE_SECONDS)
            return OAuthStateData(
                callback_url=data.get("callback_url"),
                remember_me=data.get("remember_me", False),
                nonce=data.get("nonce", ""),
            )
        except (BadSignature, SignatureExpired):
            return None

    @classmethod
    def validate_callback_url(cls, callback_url: str) -> bool:
        """
        Validate that callback URL is in allowed origins.

        In production, also requires HTTPS.

        Args:
            callback_url: The callback URL to validate.

        Returns:
            bool: True if valid, False otherwise.
        """
        if not callback_url:
            return False

        try:
            parsed = urlparse(callback_url)

            # Must have scheme and netloc
            if not parsed.scheme or not parsed.netloc:
                return False

            # In production, require HTTPS
            if settings.ENVIRONMENT == "production" and parsed.scheme != "https":
                return False

            callback_origin = f"{parsed.scheme}://{parsed.netloc}"

            for allowed_origin in settings.CORS_ALLOW_ORIGINS:
                # Handle wildcard
                if allowed_origin == "*":
                    return True

                # Exact match or match with/without trailing slash
                if callback_origin.rstrip("/") == allowed_origin.rstrip("/"):
                    return True

            return False

        except Exception:
            return False

