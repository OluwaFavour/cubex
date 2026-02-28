"""
Shared schemas for API request validation and response serialization.

"""

from app.core.schemas.auth import (
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
from app.core.schemas.plan import (
    FeatureResponse,
    PlanResponse,
    PlanListResponse,
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
    # Plan
    "FeatureResponse",
    "PlanResponse",
    "PlanListResponse",
]
