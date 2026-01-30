"""
OAuth provider services.

This package contains OAuth provider implementations for authentication:
- BaseOAuthProvider: Abstract base class for OAuth providers
- GoogleOAuthService: Google OAuth 2.0 implementation
- GitHubOAuthService: GitHub OAuth implementation
- OAuthStateManager: Manager for encoding/decoding OAuth state parameters

Example usage:
    from app.shared.services.oauth import GoogleOAuthService, GitHubOAuthService

    # Initialize providers
    await GoogleOAuthService.init()
    await GitHubOAuthService.init()

    # Get authorization URL
    url = GoogleOAuthService.get_authorization_url(
        redirect_uri="https://app.com/callback",
        state="random_state",
    )

    # Exchange code for tokens
    tokens = await GoogleOAuthService.exchange_code_for_tokens(
        code="auth_code",
        redirect_uri="https://app.com/callback",
    )

    # Get user info
    user_info = await GoogleOAuthService.get_user_info(tokens.access_token)
"""

from app.shared.services.oauth.base import (
    BaseOAuthProvider,
    OAuthStateData,
    OAuthStateManager,
    OAuthTokens,
    OAuthUserInfo,
    generate_state,
)
from app.shared.services.oauth.github import GitHubOAuthService
from app.shared.services.oauth.google import GoogleOAuthService


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
