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
]
