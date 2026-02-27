"""
Services for cubex_api.
"""

from app.apps.cubex_api.services.subscription import (
    SubscriptionService,
    subscription_service,
    SubscriptionNotFoundException,
    PlanNotFoundException,
    InvalidSeatCountException,
    SeatDowngradeBlockedException,
    CannotUpgradeFreeWorkspace,
    StripeWebhookException,
    WorkspaceAccessDeniedException,
    AdminPermissionRequiredException,
    OwnerPermissionRequiredException,
    PlanDowngradeNotAllowedException,
    SamePlanException,
)
from app.apps.cubex_api.services.workspace import (
    WorkspaceService,
    workspace_service,
    WorkspaceNotFoundException,
    WorkspaceFrozenException,
    InsufficientSeatsException,
    MemberNotFoundException,
    InvitationNotFoundException,
    InvitationAlreadyExistsException,
    MemberAlreadyExistsException,
    CannotInviteOwnerException,
    PermissionDeniedException,
    FreeWorkspaceNoInvitesException,
)
from app.apps.cubex_api.services.quota import (
    QuotaService,
    quota_service,
    RateLimitInfo,
    APIKeyNotFoundException,
    APIKeyInvalidException,
    UsageLogNotFoundException,
    API_KEY_PREFIX,
    TEST_API_KEY_PREFIX,
    CLIENT_ID_PREFIX,
)
from app.apps.cubex_api.services.quota_cache import (
    APIQuotaCacheService,
)

__all__ = [
    # Subscription service
    "SubscriptionService",
    "subscription_service",
    "SubscriptionNotFoundException",
    "PlanNotFoundException",
    "InvalidSeatCountException",
    "SeatDowngradeBlockedException",
    "CannotUpgradeFreeWorkspace",
    "StripeWebhookException",
    "WorkspaceAccessDeniedException",
    "AdminPermissionRequiredException",
    "OwnerPermissionRequiredException",
    "PlanDowngradeNotAllowedException",
    "SamePlanException",
    # Workspace service
    "WorkspaceService",
    "workspace_service",
    "WorkspaceNotFoundException",
    "WorkspaceFrozenException",
    "InsufficientSeatsException",
    "MemberNotFoundException",
    "InvitationNotFoundException",
    "InvitationAlreadyExistsException",
    "MemberAlreadyExistsException",
    "CannotInviteOwnerException",
    "PermissionDeniedException",
    "FreeWorkspaceNoInvitesException",
    # Quota service
    "QuotaService",
    "quota_service",
    "RateLimitInfo",
    "APIKeyNotFoundException",
    "APIKeyInvalidException",
    "UsageLogNotFoundException",
    "API_KEY_PREFIX",
    "TEST_API_KEY_PREFIX",
    "CLIENT_ID_PREFIX",
    # Quota cache service
    "APIQuotaCacheService",
]

