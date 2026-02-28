"""
OAuth provider services.

This package contains OAuth provider implementations for authentication:
- BaseOAuthProvider: Abstract base class for OAuth providers
- GoogleOAuthService: Google OAuth 2.0 implementation
- GitHubOAuthService: GitHub OAuth implementation
- OAuthStateManager: Manager for encoding/decoding OAuth state parameters

Example usage:
    from app.core.services.oauth import GoogleOAuthService, GitHubOAuthService

    await GoogleOAuthService.init()
    await GitHubOAuthService.init()

    url = GoogleOAuthService.get_authorization_url(
        redirect_uri="https://app.com/callback",
        state="random_state",
    )

    # Exchange code for tokens
    tokens = await GoogleOAuthService.exchange_code_for_tokens(
        code="auth_code",
        redirect_uri="https://app.com/callback",
    )

    user_info = await GoogleOAuthService.get_user_info(tokens.access_token)
"""

from app.core.services.oauth.base import (
    BaseOAuthProvider,
    OAuthStateData,
    OAuthStateManager,
    OAuthTokens,
    OAuthUserInfo,
    generate_state,
)
from app.core.services.oauth.github import GitHubOAuthService
from app.core.services.oauth.google import GoogleOAuthService

__all__ = [
    "BaseOAuthProvider",
    "OAuthTokens",
    "OAuthUserInfo",
    "OAuthStateData",
    "OAuthStateManager",
    "generate_state",
    "GoogleOAuthService",
    "GitHubOAuthService",
]
