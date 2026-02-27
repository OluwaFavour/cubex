from enum import Enum


class OAuthProviders(str, Enum):
    """Supported OAuth providers for authentication."""

    GOOGLE = "google"
    GITHUB = "github"


class OTPPurpose(str, Enum):
    """Purpose of the OTP token."""

    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


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


class SalesRequestStatus(str, Enum):
    """Status of a sales request."""

    PENDING = "pending"  # Not yet contacted
    CONTACTED = "contacted"  # Sales team has reached out
    CLOSED = "closed"  # Request resolved/closed


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


class FeatureKey(str, Enum):
    API_CAREER_PATH = "api.career_path"
    API_EXTRACT_KEYWORDS = "api.extract_keywords"
    API_FEEDBACK_ANALYZER = "api.feedback_analyzer"
    API_GENERATE_FEEDBACK = "api.generate_feedback"
    API_JOB_MATCH = "api.job_match"
    API_EXTRACT_CUES_RESUME = "api.extract_cues.resume"
    API_EXTRACT_CUES_FEEDBACK = "api.extract_cues.feedback"
    API_EXTRACT_CUES_INTERVIEW = "api.extract_cues.interview"
    API_EXTRACT_CUES_ASSESSMENT = "api.extract_cues.assessment"
    API_REFRAME_FEEDBACK = "api.reframe_feedback"

    CAREER_CAREER_PATH = "career.career_path"
    CAREER_EXTRACT_KEYWORDS = "career.extract_keywords"
    CAREER_FEEDBACK_ANALYZER = "career.feedback_analyzer"
    CAREER_GENERATE_FEEDBACK = "career.generate_feedback"
    CAREER_JOB_MATCH = "career.job_match"
    CAREER_EXTRACT_CUES_RESUME = "career.extract_cues.resume"
    CAREER_EXTRACT_CUES_FEEDBACK = "career.extract_cues.feedback"
    CAREER_EXTRACT_CUES_INTERVIEW = "career.extract_cues.interview"
    CAREER_EXTRACT_CUES_ASSESSMENT = "career.extract_cues.assessment"
    CAREER_REFRAME_FEEDBACK = "career.reframe_feedback"


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
    "FeatureKey",
]

