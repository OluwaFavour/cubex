from enum import Enum


class OAuthProviders(str, Enum):
    """Supported OAuth providers for authentication."""

    GOOGLE = "google"
    GITHUB = "github"


class OTPPurpose(str, Enum):
    """Purpose of the OTP token."""

    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


__all__ = ["OAuthProviders", "OTPPurpose"]
