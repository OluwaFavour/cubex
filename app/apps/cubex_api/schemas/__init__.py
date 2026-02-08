"""
Schemas for cubex_api.
"""

from app.apps.cubex_api.schemas.subscription import (
    FeatureResponse,
    PlanResponse,
    PlanListResponse,
    SubscriptionResponse,
    CheckoutRequest,
    CheckoutResponse,
    SeatUpdateRequest,
    CancelSubscriptionRequest,
    ReactivateRequest,
    UpgradePreviewRequest,
    UpgradePreviewResponse,
    UpgradeRequest,
)
from app.apps.cubex_api.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceMemberResponse,
    WorkspaceResponse,
    WorkspaceDetailResponse,
    WorkspaceListResponse,
    MemberStatusUpdate,
    MemberRoleUpdate,
    InvitationCreate,
    InvitationResponse,
    InvitationListResponse,
    InvitationAccept,
    InvitationCreatedResponse,
    MessageResponse,
    APIKeyCreate,
    APIKeyResponse,
    APIKeyCreatedResponse,
    APIKeyListResponse,
)

__all__ = [
    # Subscription schemas
    "FeatureResponse",
    "PlanResponse",
    "PlanListResponse",
    "SubscriptionResponse",
    "CheckoutRequest",
    "CheckoutResponse",
    "SeatUpdateRequest",
    "CancelSubscriptionRequest",
    "ReactivateRequest",
    "UpgradePreviewRequest",
    "UpgradePreviewResponse",
    "UpgradeRequest",
    # Workspace schemas
    "WorkspaceCreate",
    "WorkspaceUpdate",
    "WorkspaceMemberResponse",
    "WorkspaceResponse",
    "WorkspaceDetailResponse",
    "WorkspaceListResponse",
    "MemberStatusUpdate",
    "MemberRoleUpdate",
    "InvitationCreate",
    "InvitationResponse",
    "InvitationListResponse",
    "InvitationAccept",
    "InvitationCreatedResponse",
    "MessageResponse",
    # API Key schemas
    "APIKeyCreate",
    "APIKeyResponse",
    "APIKeyCreatedResponse",
    "APIKeyListResponse",
]
