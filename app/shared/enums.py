from enum import Enum


class OAuthProviders(str, Enum):
    """Supported OAuth providers for authentication."""

    GOOGLE = "google"
    GITHUB = "github"


class OTPPurpose(str, Enum):
    """Purpose of the OTP token."""

    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


# ============================================================================
# Subscription & Plan Enums
# ============================================================================


class ProductType(str, Enum):
    """Type of product for subscriptions."""

    API = "api"  # Workspace/team subscriptions (cubex_api)
    CAREER = "career"  # Individual user subscriptions (cubex_career)


class APIPlanName(str, Enum):
    """Plan names for API product (workspace subscriptions)."""

    FREE = "Free"
    BASIC = "Basic"
    PROFESSIONAL = "Professional"


class CareerPlanName(str, Enum):
    """Plan names for Career product (individual subscriptions)."""

    FREE = "Free"
    PLUS = "Plus Plan"
    PRO = "Pro Plan"


class PlanType(str, Enum):
    """Type of subscription plan."""

    FREE = "free"
    PAID = "paid"


class SubscriptionStatus(str, Enum):
    """Status of a subscription."""

    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    TRIALING = "trialing"
    UNPAID = "unpaid"
    PAUSED = "paused"


# ============================================================================
# Workspace Enums
# ============================================================================


class WorkspaceStatus(str, Enum):
    """Status of a workspace."""

    ACTIVE = "active"
    FROZEN = "frozen"  # Subscription expired, read-only
    SUSPENDED = "suspended"  # Admin action or violation


class MemberStatus(str, Enum):
    """Status of a workspace member."""

    ENABLED = "enabled"  # Has access, consumes a seat
    DISABLED = "disabled"  # No access, does not consume a seat


class MemberRole(str, Enum):
    """Role of a workspace member."""

    OWNER = "owner"  # Full control, billing access
    ADMIN = "admin"  # Manage members, settings
    MEMBER = "member"  # Regular access


class InvitationStatus(str, Enum):
    """Status of a workspace invitation."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


# ============================================================================
# Support Enums
# ============================================================================


class SalesRequestStatus(str, Enum):
    """Status of a sales request."""

    PENDING = "pending"  # Not yet contacted
    CONTACTED = "contacted"  # Sales team has reached out
    CLOSED = "closed"  # Request resolved/closed


# ============================================================================
# API Usage Enums
# ============================================================================


class AccessStatus(str, Enum):
    """Status of API usage access validation."""

    GRANTED = "granted"
    DENIED = "denied"


class UsageLogStatus(str, Enum):
    """Status of a usage log entry."""

    PENDING = "pending"  # Request in progress, awaiting commit
    SUCCESS = "success"  # Request completed successfully, counts toward quota
    FAILED = "failed"  # Request failed, does not count toward quota
    EXPIRED = "expired"  # Pending too long, expired by scheduler


class FailureType(str, Enum):
    """Type of failure for API usage tracking.

    Used to categorize failures when committing usage logs with success=False.
    Helps identify patterns and issues we may be responsible for.
    """

    INTERNAL_ERROR = "internal_error"  # Our server error (5xx)
    TIMEOUT = "timeout"  # Request timed out
    RATE_LIMITED = "rate_limited"  # Upstream rate limit hit
    INVALID_RESPONSE = "invalid_response"  # Malformed response from upstream
    UPSTREAM_ERROR = "upstream_error"  # Upstream service error
    CLIENT_ERROR = "client_error"  # Client-side error (4xx)
    VALIDATION_ERROR = "validation_error"  # Request/response validation failed


__all__ = [
    "AccessStatus",
    "APIPlanName",
    "CareerPlanName",
    "FailureType",
    "InvitationStatus",
    "MemberRole",
    "MemberStatus",
    "OAuthProviders",
    "OTPPurpose",
    "PlanType",
    "ProductType",
    "SalesRequestStatus",
    "SubscriptionStatus",
    "UsageLogStatus",
    "WorkspaceStatus",
]
