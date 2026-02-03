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


__all__ = [
    "APIPlanName",
    "CareerPlanName",
    "InvitationStatus",
    "MemberRole",
    "MemberStatus",
    "OAuthProviders",
    "OTPPurpose",
    "PlanType",
    "ProductType",
    "SubscriptionStatus",
    "WorkspaceStatus",
]
