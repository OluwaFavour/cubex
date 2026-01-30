"""
Shared schemas for API request validation and response serialization.

This module exports all shared Pydantic schemas used across
multiple application modules.
"""

from app.shared.schemas.auth import (
    # Base
    MessageResponse,
    # Signup
    SignupRequest,
    SignupResponse,
    # OTP
    OTPVerifyRequest,
    ResendOTPRequest,
    # Login
    LoginRequest,
    # Tokens
    TokenResponse,
    RefreshTokenRequest,
    AccessTokenResponse,
    # OAuth
    OAuthInitRequest,
    OAuthInitResponse,
    OAuthCallbackRequest,
    # Password
    PasswordResetRequest,
    PasswordResetConfirmRequest,
    ChangePasswordRequest,
    # Profile
    ProfileResponse,
    ProfileUpdateRequest,
    # Sessions
    ActiveSessionResponse,
    ActiveSessionsResponse,
)

__all__ = [
    # Base
    "MessageResponse",
    # Signup
    "SignupRequest",
    "SignupResponse",
    # OTP
    "OTPVerifyRequest",
    "ResendOTPRequest",
    # Login
    "LoginRequest",
    # Tokens
    "TokenResponse",
    "RefreshTokenRequest",
    "AccessTokenResponse",
    # OAuth
    "OAuthInitRequest",
    "OAuthInitResponse",
    "OAuthCallbackRequest",
    # Password
    "PasswordResetRequest",
    "PasswordResetConfirmRequest",
    "ChangePasswordRequest",
    # Profile
    "ProfileResponse",
    "ProfileUpdateRequest",
    # Sessions
    "ActiveSessionResponse",
    "ActiveSessionsResponse",
]
