"""
Authentication schemas for request validation and response serialization.

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

from app.core.enums import OAuthProviders

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


class MessageResponse(BaseModel):
    """Generic message response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"message": "Operation completed successfully", "success": True}
        }
    )

    message: str
    success: bool = True


class SignupRequest(BaseModel):
    """Request schema for email signup."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123",
                "full_name": "John Doe",
            }
        }
    )

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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Verification code sent to your email",
                "email": "user@example.com",
                "requires_verification": True,
            }
        }
    )

    message: str = "Verification code sent to your email"
    email: EmailStr
    requires_verification: bool = True


class OTPVerifyRequest(BaseModel):
    """Request schema for OTP verification."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"email": "user@example.com", "otp_code": "123456"}
        }
    )

    email: Annotated[EmailStr, Field(description="Email the OTP was sent to")]
    otp_code: OTPCodeStr


class ResendOTPRequest(BaseModel):
    """Request schema for resending OTP."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "user@example.com"}}
    )

    email: Annotated[EmailStr, Field(description="Email to resend OTP to")]


class LoginRequest(BaseModel):
    """Request schema for email signin."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123",
                "remember_me": False,
            }
        }
    )

    email: Annotated[EmailStr, Field(description="User's email address")]
    password: Annotated[str, Field(description="User's password")]
    remember_me: Annotated[
        bool,
        Field(description="If true, extends refresh token duration to 30 days"),
    ] = False


class TokenResponse(BaseModel):
    """Response schema for successful authentication."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4...",
                "token_type": "bearer",
                "expires_in": 900,
            }
        }
    )

    access_token: Annotated[str, Field(description="Short-lived JWT access token")]
    refresh_token: Annotated[str, Field(description="Long-lived refresh token")]
    token_type: Literal["bearer"] = "bearer"
    expires_in: Annotated[
        int, Field(description="Access token expiration time in seconds")
    ]


class RefreshTokenRequest(BaseModel):
    """Request schema for token refresh."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4..."}
        }
    )

    refresh_token: Annotated[str, Field(description="The refresh token to use")]


class AccessTokenResponse(BaseModel):
    """Response schema for refreshed access token."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 900,
            }
        }
    )

    access_token: Annotated[str, Field(description="New short-lived JWT access token")]
    token_type: Literal["bearer"] = "bearer"
    expires_in: Annotated[
        int, Field(description="Access token expiration time in seconds")
    ]


class OAuthInitRequest(BaseModel):
    """Request schema for initiating OAuth flow."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"provider": "google", "remember_me": False}}
    )

    provider: Annotated[
        OAuthProviders, Field(description="OAuth provider (google, github)")
    ]
    remember_me: Annotated[
        bool,
        Field(description="If true, extends refresh token duration to 30 days"),
    ] = False


class OAuthInitResponse(BaseModel):
    """Response schema for OAuth initialization."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "authorization_url": "https://accounts.google.com/o/oauth2/auth?...",
                "state": "abc123xyz789",
            }
        }
    )

    authorization_url: Annotated[
        str, Field(description="URL to redirect user for OAuth consent")
    ]
    state: Annotated[str, Field(description="CSRF protection state parameter")]


class OAuthCallbackRequest(BaseModel):
    """Query parameters for OAuth callback."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"code": "4/0AX4XfWh...", "state": "abc123xyz789"}
        }
    )

    code: Annotated[str, Field(description="Authorization code from provider")]
    state: Annotated[str, Field(description="State parameter for CSRF validation")]


class PasswordResetRequest(BaseModel):
    """Request schema for initiating password reset."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "user@example.com"}}
    )

    email: Annotated[EmailStr, Field(description="Email address for password reset")]


class PasswordResetConfirmRequest(BaseModel):
    """Request schema for confirming password reset with OTP."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "otp_code": "123456",
                "new_password": "NewSecurePass123",
            }
        }
    )

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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_password": "OldSecurePass123",
                "new_password": "NewSecurePass456",
            }
        }
    )

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


class ProfileResponse(BaseModel):
    """Response schema for user profile."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "email_verified": True,
                "full_name": "John Doe",
                "avatar_url": "https://example.com/avatar.jpg",
                "is_active": True,
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-20T15:45:00Z",
                "has_password": True,
                "oauth_providers": ["google"],
            }
        },
    )

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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "Jane Doe",
                "avatar_url": "https://example.com/new-avatar.jpg",
            }
        }
    )

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


class ActiveSessionResponse(BaseModel):
    """Response schema for an active session."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "device_info": "Chrome on Windows",
                "created_at": "2024-01-15T10:30:00Z",
                "expires_at": "2024-01-22T10:30:00Z",
                "is_current": True,
            }
        }
    )

    id: UUID
    device_info: str | None
    created_at: datetime
    expires_at: datetime
    is_current: Annotated[
        bool, Field(description="Whether this is the current session")
    ]


class ActiveSessionsResponse(BaseModel):
    """Response schema for listing active sessions."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sessions": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "device_info": "Chrome on Windows",
                        "created_at": "2024-01-15T10:30:00Z",
                        "expires_at": "2024-01-22T10:30:00Z",
                        "is_current": True,
                    }
                ],
                "total": 1,
            }
        }
    )

    sessions: list[ActiveSessionResponse]
    total: int


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
