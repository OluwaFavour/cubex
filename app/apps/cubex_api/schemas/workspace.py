"""
Pydantic schemas for workspace endpoints.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.shared.enums import InvitationStatus, MemberRole, MemberStatus, WorkspaceStatus


# ============================================================================
# Workspace Schemas
# ============================================================================


class WorkspaceCreate(BaseModel):
    """Schema for creating a new workspace."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "display_name": "My Startup",
                "description": "Workspace for our startup team",
            }
        }
    )

    display_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128),
        Field(description="Workspace display name"),
    ]
    description: Annotated[
        str | None,
        StringConstraints(max_length=500),
        Field(description="Workspace description"),
    ] = None


class WorkspaceUpdate(BaseModel):
    """Schema for updating a workspace."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "display_name": "My Startup Renamed",
                "slug": "my-startup-renamed",
                "description": "Updated workspace description",
            }
        }
    )

    display_name: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=128),
        Field(description="Workspace display name"),
    ] = None
    slug: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=128, pattern=r"^[a-z0-9-]+$"),
        Field(description="URL-friendly workspace identifier"),
    ] = None
    description: Annotated[
        str | None,
        StringConstraints(max_length=500),
        Field(description="Workspace description"),
    ] = None


class WorkspaceMemberResponse(BaseModel):
    """Schema for workspace member response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "550e8400-e29b-41d4-a716-446655440001",
                "role": "admin",
                "status": "enabled",
                "joined_at": "2024-01-15T10:30:00Z",
                "user_email": "john@example.com",
                "user_name": "John Doe",
            }
        },
    )

    id: UUID
    user_id: UUID
    role: MemberRole
    status: MemberStatus
    joined_at: datetime
    user_email: str | None = None
    user_name: str | None = None


class WorkspaceResponse(BaseModel):
    """Schema for workspace response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "display_name": "My Startup",
                "slug": "my-startup",
                "status": "active",
                "is_personal": False,
                "description": "Workspace for our startup team",
                "created_at": "2024-01-15T10:30:00Z",
                "owner_id": "550e8400-e29b-41d4-a716-446655440001",
                "enabled_member_count": 5,
                "total_member_count": 7,
            }
        },
    )

    id: UUID
    display_name: str
    slug: str
    status: WorkspaceStatus
    is_personal: bool
    description: str | None
    created_at: datetime
    owner_id: UUID
    enabled_member_count: int = 0
    total_member_count: int = 0


class WorkspaceDetailResponse(WorkspaceResponse):
    """Schema for detailed workspace response with members."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "display_name": "My Startup",
                "slug": "my-startup",
                "status": "active",
                "is_personal": False,
                "description": "Workspace for our startup team",
                "created_at": "2024-01-15T10:30:00Z",
                "owner_id": "550e8400-e29b-41d4-a716-446655440001",
                "enabled_member_count": 5,
                "total_member_count": 7,
                "members": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440002",
                        "user_id": "550e8400-e29b-41d4-a716-446655440001",
                        "role": "owner",
                        "status": "enabled",
                        "joined_at": "2024-01-15T10:30:00Z",
                        "user_email": "owner@example.com",
                        "user_name": "Owner Name",
                    }
                ],
                "seat_count": 10,
                "available_seats": 3,
            }
        },
    )

    members: list[WorkspaceMemberResponse] = []
    seat_count: int = 0
    available_seats: int = 0


class WorkspaceListResponse(BaseModel):
    """Schema for list of workspaces."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "workspaces": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "display_name": "My Startup",
                        "slug": "my-startup",
                        "status": "active",
                        "is_personal": False,
                        "description": "Workspace for our startup team",
                        "created_at": "2024-01-15T10:30:00Z",
                        "owner_id": "550e8400-e29b-41d4-a716-446655440001",
                        "enabled_member_count": 5,
                        "total_member_count": 7,
                    }
                ]
            }
        }
    )

    workspaces: list[WorkspaceResponse]


# ============================================================================
# Member Schemas
# ============================================================================


class MemberStatusUpdate(BaseModel):
    """Schema for updating member status."""

    model_config = ConfigDict(json_schema_extra={"example": {"status": "disabled"}})

    status: Annotated[
        MemberStatus,
        Field(description="New member status: enabled or disabled"),
    ]


class MemberRoleUpdate(BaseModel):
    """Schema for updating member role."""

    model_config = ConfigDict(json_schema_extra={"example": {"role": "admin"}})

    role: Annotated[
        MemberRole,
        Field(description="New member role: admin or member"),
    ]


# ============================================================================
# Invitation Schemas
# ============================================================================


class InvitationCreate(BaseModel):
    """Schema for creating an invitation."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"email": "newmember@example.com", "role": "member"}
        }
    )

    email: Annotated[EmailStr, Field(description="Email address to invite")]
    role: Annotated[
        MemberRole,
        Field(description="Role to assign: admin or member"),
    ] = MemberRole.MEMBER


class InvitationResponse(BaseModel):
    """Schema for invitation response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "newmember@example.com",
                "role": "member",
                "status": "pending",
                "expires_at": "2024-01-22T10:30:00Z",
                "created_at": "2024-01-15T10:30:00Z",
                "inviter_email": "admin@example.com",
            }
        },
    )

    id: UUID
    email: str
    role: MemberRole
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime
    inviter_email: str | None = None


class InvitationListResponse(BaseModel):
    """Schema for list of invitations."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "invitations": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "email": "newmember@example.com",
                        "role": "member",
                        "status": "pending",
                        "expires_at": "2024-01-22T10:30:00Z",
                        "created_at": "2024-01-15T10:30:00Z",
                        "inviter_email": "admin@example.com",
                    }
                ]
            }
        }
    )

    invitations: list[InvitationResponse]


class InvitationAccept(BaseModel):
    """Schema for accepting an invitation."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"token": "abc123def456ghi789jkl012mno345pqr678"}}
    )

    token: str


class InvitationCreatedResponse(BaseModel):
    """Schema for invitation created response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "invitation": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "email": "newmember@example.com",
                    "role": "member",
                    "status": "pending",
                    "expires_at": "2024-01-22T10:30:00Z",
                    "created_at": "2024-01-15T10:30:00Z",
                    "inviter_email": "admin@example.com",
                },
                "invitation_url": "https://app.cubex.com/invite/abc123def456",
            }
        }
    )

    invitation: InvitationResponse
    invitation_url: str


# ============================================================================
# Message Schemas
# ============================================================================


class MessageResponse(BaseModel):
    """Generic message response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"message": "Operation completed successfully", "success": True}
        }
    )

    message: str
    success: bool = True


__all__ = [
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
]
