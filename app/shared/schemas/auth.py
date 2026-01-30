"""
Authentication schemas for request validation and response serialization.

This module provides Pydantic models for all authentication-related
API endpoints including:
- Email signup and verification
- Email signin with remember me
- OAuth authentication flows
- Token refresh and revocation
- Password reset
- Profile management
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

from app.shared.enums import OAuthProviders


# =============================================================================
# Type Aliases for Reusable Annotated Types
# =============================================================================

# Password with validation constraints
PasswordStr = Annotated[
    str,
    StringConstraints(min_length=8, max_length=128),
    Field(description="Password (min 8 characters)"),
]

# OTP code with pattern validation
OTPCodeStr = Annotated[
    str,
    StringConstraints(min_length=6, max_length=6, pattern=r"^\d{6}$"),
    Field(description="6-digit verification code"),
]


# =============================================================================
# Base Schemas
# =============================================================================


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str
    success: bool = True


# =============================================================================
# Signup Schemas
# =============================================================================


class SignupRequest(BaseModel):
    """Request schema for email signup."""

    email: Annotated[EmailStr, Field(description="User's email address")]
    password: PasswordStr
    full_name: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=255),
        Field(description="User's full name"),
    ] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password complexity."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class SignupResponse(BaseModel):
    """Response schema for successful signup (pending verification)."""

    message: str = "Verification code sent to your email"
    email: EmailStr
    requires_verification: bool = True


# =============================================================================
# OTP Verification Schemas
# =============================================================================


class OTPVerifyRequest(BaseModel):
    """Request schema for OTP verification."""

    email: Annotated[EmailStr, Field(description="Email the OTP was sent to")]
    otp_code: OTPCodeStr


class ResendOTPRequest(BaseModel):
    """Request schema for resending OTP."""

    email: Annotated[EmailStr, Field(description="Email to resend OTP to")]


# =============================================================================
# Login Schemas
# =============================================================================


class LoginRequest(BaseModel):
    """Request schema for email signin."""

    email: Annotated[EmailStr, Field(description="User's email address")]
    password: Annotated[str, Field(description="User's password")]
    remember_me: Annotated[
        bool,
        Field(description="If true, extends refresh token duration to 30 days"),
    ] = False


# =============================================================================
# Token Schemas
# =============================================================================


class TokenResponse(BaseModel):
    """Response schema for successful authentication."""

    access_token: Annotated[str, Field(description="Short-lived JWT access token")]
    refresh_token: Annotated[str, Field(description="Long-lived refresh token")]
    token_type: Literal["bearer"] = "bearer"
    expires_in: Annotated[
        int, Field(description="Access token expiration time in seconds")
    ]


class RefreshTokenRequest(BaseModel):
    """Request schema for token refresh."""

    refresh_token: Annotated[str, Field(description="The refresh token to use")]


class AccessTokenResponse(BaseModel):
    """Response schema for refreshed access token."""

    access_token: Annotated[str, Field(description="New short-lived JWT access token")]
    token_type: Literal["bearer"] = "bearer"
    expires_in: Annotated[
        int, Field(description="Access token expiration time in seconds")
    ]


# =============================================================================
# OAuth Schemas
# =============================================================================


class OAuthInitRequest(BaseModel):
    """Request schema for initiating OAuth flow."""

    provider: Annotated[
        OAuthProviders, Field(description="OAuth provider (google, github)")
    ]
    remember_me: Annotated[
        bool,
        Field(description="If true, extends refresh token duration to 30 days"),
    ] = False


class OAuthInitResponse(BaseModel):
    """Response schema for OAuth initialization."""

    authorization_url: Annotated[
        str, Field(description="URL to redirect user for OAuth consent")
    ]
    state: Annotated[str, Field(description="CSRF protection state parameter")]


class OAuthCallbackRequest(BaseModel):
    """Query parameters for OAuth callback."""

    code: Annotated[str, Field(description="Authorization code from provider")]
    state: Annotated[str, Field(description="State parameter for CSRF validation")]


# =============================================================================
# Password Reset Schemas
# =============================================================================


class PasswordResetRequest(BaseModel):
    """Request schema for initiating password reset."""

    email: Annotated[EmailStr, Field(description="Email address for password reset")]


class PasswordResetConfirmRequest(BaseModel):
    """Request schema for confirming password reset with OTP."""

    email: Annotated[EmailStr, Field(description="Email address")]
    otp_code: OTPCodeStr
    new_password: PasswordStr

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password complexity."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class ChangePasswordRequest(BaseModel):
    """Request schema for changing password (authenticated user)."""

    current_password: Annotated[str, Field(description="Current password")]
    new_password: PasswordStr

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password complexity."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# =============================================================================
# Profile Schemas
# =============================================================================


class ProfileResponse(BaseModel):
    """Response schema for user profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    email_verified: bool
    full_name: str | None
    avatar_url: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Computed fields
    has_password: Annotated[
        bool,
        Field(description="Whether user has a password set (false for OAuth-only)"),
    ]
    oauth_providers: Annotated[
        list[OAuthProviders],
        Field(default_factory=list, description="List of linked OAuth providers"),
    ]


class ProfileUpdateRequest(BaseModel):
    """Request schema for updating user profile."""

    full_name: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=255),
        Field(description="User's full name"),
    ] = None
    avatar_url: Annotated[
        str | None,
        StringConstraints(max_length=512),
        Field(description="URL to user's avatar image"),
    ] = None


# =============================================================================
# Session Management Schemas
# =============================================================================


class ActiveSessionResponse(BaseModel):
    """Response schema for an active session."""

    id: UUID
    device_info: str | None
    created_at: datetime
    expires_at: datetime
    is_current: Annotated[
        bool, Field(description="Whether this is the current session")
    ]


class ActiveSessionsResponse(BaseModel):
    """Response schema for listing active sessions."""

    sessions: list[ActiveSessionResponse]
    total: int


# =============================================================================
# Export all schemas
# =============================================================================

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
