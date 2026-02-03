"""
Workspace router for cubex_api.

This module provides endpoints for:
- Workspace CRUD operations
- Member management (invite, enable/disable, remove)
- Invitation management
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_async_session
from app.shared.config import request_logger, settings
from app.shared.dependencies.auth import CurrentActiveUser
from app.apps.cubex_api.db.crud import (
    workspace_member_db,
    workspace_invitation_db,
)
from app.apps.cubex_api.schemas import (
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
)
from app.apps.cubex_api.services import (
    workspace_service,
    subscription_service,
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
from app.shared.enums import MemberRole, MemberStatus
from app.apps.cubex_api.db.models import (
    Workspace,
    WorkspaceMember,
    WorkspaceInvitation,
)


router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


# ============================================================================
# Helper Functions
# ============================================================================


def _build_workspace_response(workspace, enabled_count: int = 0) -> WorkspaceResponse:
    """Build WorkspaceResponse from Workspace model."""
    return WorkspaceResponse(
        id=workspace.id,
        display_name=workspace.display_name,
        slug=workspace.slug,
        status=workspace.status,
        is_personal=workspace.is_personal,
        description=workspace.description,
        created_at=workspace.created_at,
        owner_id=workspace.owner_id,
        enabled_member_count=enabled_count
        or len([m for m in workspace.members if m.status == MemberStatus.ENABLED]),
        total_member_count=len(workspace.members) if workspace.members else 0,
    )


def _build_member_response(member: WorkspaceMember) -> WorkspaceMemberResponse:
    """Build WorkspaceMemberResponse from WorkspaceMember model."""
    return WorkspaceMemberResponse(
        id=member.id,
        user_id=member.user_id,
        role=member.role,
        status=member.status,
        joined_at=member.joined_at,
        user_email=member.user.email if member.user else None,
        user_name=member.user.full_name if member.user else None,
    )


def _build_invitation_response(invitation: WorkspaceInvitation) -> InvitationResponse:
    """Build InvitationResponse from WorkspaceInvitation model."""
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        inviter_email=invitation.inviter.email if invitation.inviter else None,
    )


# ============================================================================
# Workspace Endpoints
# ============================================================================


@router.get(
    "",
    response_model=WorkspaceListResponse,
    summary="List user workspaces",
    description="""
## List User Workspaces

Retrieve all workspaces the authenticated user has access to as a member.

### Authorization

- User must be authenticated

### Response

Returns a list of workspaces with basic information:

| Field | Type | Description |
|-------|------|-------------|
| `workspaces` | array | List of workspace objects |
| `workspaces[].id` | UUID | Workspace identifier |
| `workspaces[].display_name` | string | Workspace name |
| `workspaces[].slug` | string | URL-friendly identifier |
| `workspaces[].status` | string | `active` or `frozen` |
| `workspaces[].is_personal` | boolean | Whether this is a personal workspace |
| `workspaces[].owner_id` | UUID | Workspace owner's user ID |
| `workspaces[].enabled_member_count` | integer | Count of enabled members |
| `workspaces[].total_member_count` | integer | Total member count |

### Notes

- Includes both personal and team workspaces
- Results include workspaces where user is owner, admin, or member
""",
)
async def list_workspaces(
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WorkspaceListResponse:
    """List all workspaces the current user has access to."""
    request_logger.info(f"GET /workspaces - user={current_user.id}")
    async with session.begin():
        workspaces = await workspace_service.get_user_workspaces(
            session, current_user.id
        )
        request_logger.info(
            f"GET /workspaces - user={current_user.id} returned {len(workspaces)} workspaces"
        )
        return WorkspaceListResponse(
            workspaces=[_build_workspace_response(w) for w in workspaces]
        )


@router.post(
    "",
    response_model=WorkspaceDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workspace",
    description="""
## Create New Workspace

Create a new team workspace. The authenticated user becomes the owner.

### Authorization

- User must be authenticated

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `display_name` | string | ✅ | Workspace name (2-100 characters) |
| `description` | string | ❌ | Optional description |

### Response

Returns the created workspace with details:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Workspace identifier |
| `display_name` | string | Workspace name |
| `slug` | string | Auto-generated URL-friendly identifier |
| `status` | string | Always `active` for new workspaces |
| `is_personal` | boolean | Always `false` for team workspaces |
| `owner_id` | UUID | Creator's user ID |
| `members` | array | Empty initially |
| `seat_count` | integer | 0 until subscription is created |
| `available_seats` | integer | 0 until subscription is created |

### Workspace Creation Flow

1. Workspace is created with owner as the only member
2. Subscribe to a paid plan to enable invitations
3. Invite team members
4. Manage seats as needed

### Notes

- A subscription is required to invite members
- Personal workspaces are created automatically at signup
- Slug is auto-generated from display_name
""",
    responses={
        201: {
            "description": "Workspace created successfully",
        },
    },
)
async def create_workspace(
    data: WorkspaceCreate,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WorkspaceDetailResponse:
    """Create a new workspace."""
    request_logger.info(f"POST /workspaces - user={current_user.id}")
    async with session.begin():
        workspace = await workspace_service.create_workspace(
            session,
            owner=current_user,
            display_name=data.display_name,
            description=data.description,
            commit_self=False,
        )

    request_logger.info(
        f"POST /workspaces - user={current_user.id} created workspace={workspace.id}"
    )
    return WorkspaceDetailResponse(
        id=workspace.id,
        display_name=workspace.display_name,
        slug=workspace.slug,
        status=workspace.status,
        is_personal=workspace.is_personal,
        description=workspace.description,
        created_at=workspace.created_at,
        owner_id=workspace.owner_id,
        enabled_member_count=1,
        total_member_count=1,
        members=[],
        seat_count=0,
        available_seats=0,
    )


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceDetailResponse,
    summary="Get workspace details",
    description="""
## Get Workspace Details

Retrieve detailed information about a specific workspace including members and subscription info.

### Authorization

- User must be a **member** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace identifier |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Workspace identifier |
| `display_name` | string | Workspace name |
| `slug` | string | URL-friendly identifier |
| `status` | string | `active` or `frozen` |
| `is_personal` | boolean | Personal workspace flag |
| `description` | string | Optional description |
| `owner_id` | UUID | Owner's user ID |
| `members` | array | List of workspace members |
| `seat_count` | integer | Total seats in subscription |
| `available_seats` | integer | Seats available for new members |

### Error Responses

| Status | Reason |
|--------|--------|
| `404 Not Found` | Workspace not found or access denied |

### Notes

- All members can view workspace details
- Members list includes status (enabled/disabled)
""",
    responses={
        404: {
            "description": "Workspace not found or access denied",
            "content": {
                "application/json": {
                    "example": {"detail": "Workspace not found or access denied."}
                }
            },
        },
    },
)
async def get_workspace(
    workspace_id: UUID,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WorkspaceDetailResponse:
    """Get workspace details."""
    request_logger.info(f"GET /workspaces/{workspace_id} - user={current_user.id}")
    async with session.begin():
        # Check user has access
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found or access denied.",
            )

        workspace = await workspace_service.get_workspace(session, workspace_id)
        members = await workspace_member_db.get_workspace_members(session, workspace_id)

        # Get subscription info
        subscription = await subscription_service.get_subscription(
            session, workspace_id
        )
        seat_count = subscription.seat_count if subscription else 0
        enabled_count = len([m for m in members if m.status == MemberStatus.ENABLED])

        return WorkspaceDetailResponse(
            id=workspace.id,
            display_name=workspace.display_name,
            slug=workspace.slug,
            status=workspace.status,
            is_personal=workspace.is_personal,
            description=workspace.description,
            created_at=workspace.created_at,
            owner_id=workspace.owner_id,
            enabled_member_count=enabled_count,
            total_member_count=len(members),
            members=[_build_member_response(m) for m in members],
            seat_count=seat_count,
            available_seats=seat_count - enabled_count,
        )


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Update workspace",
    description="""
## Update Workspace Details

Update workspace display name, slug, or description.

### Authorization

- User must be an **admin** or **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace to update |

### Request Body

All fields are optional. Only provided fields will be updated.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `display_name` | string | ❌ | New workspace name |
| `slug` | string | ❌ | New URL-friendly identifier |
| `description` | string | ❌ | New description |

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not an admin of the workspace |
| `404 Not Found` | Workspace not found |

### Notes

- Cannot update personal workspace settings
- Slug must be unique across all workspaces
""",
    responses={
        403: {
            "description": "Admin permission required",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin permission required."}
                }
            },
        },
        404: {
            "description": "Workspace not found",
            "content": {
                "application/json": {"example": {"detail": "Workspace not found."}}
            },
        },
    },
)
async def update_workspace(
    workspace_id: UUID,
    data: WorkspaceUpdate,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WorkspaceResponse:
    """Update workspace details."""
    request_logger.info(f"PATCH /workspaces/{workspace_id} - user={current_user.id}")
    try:
        async with session.begin():
            workspace = await workspace_service.update_workspace(
                session,
                workspace_id=workspace_id,
                user_id=current_user.id,
                display_name=data.display_name,
                slug=data.slug,
                description=data.description,
                commit_self=False,
            )
            return _build_workspace_response(workspace)
    except PermissionDeniedException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e.message)
        )
    except WorkspaceNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e.message)
        )


# ============================================================================
# Member Endpoints
# ============================================================================


@router.get(
    "/{workspace_id}/members",
    response_model=list[WorkspaceMemberResponse],
    summary="List workspace members",
    description="""
## List Workspace Members

Retrieve all members of a workspace with optional status filtering.

### Authorization

- User must be a **member** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace identifier |

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | string | ❌ | Filter by status: `enabled` or `disabled` |

### Response

Array of member objects:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Member record ID |
| `user_id` | UUID | User's ID |
| `role` | string | `owner`, `admin`, or `member` |
| `status` | string | `enabled` or `disabled` |
| `joined_at` | datetime | When member joined |
| `user_email` | string | Member's email |
| `user_name` | string | Member's full name |

### Error Responses

| Status | Reason |
|--------|--------|
| `404 Not Found` | Workspace not found or access denied |

### Notes

- All members can view the member list
- Disabled members cannot access the workspace
""",
    responses={
        404: {
            "description": "Workspace not found or access denied",
            "content": {
                "application/json": {
                    "example": {"detail": "Workspace not found or access denied."}
                }
            },
        },
    },
)
async def list_members(
    workspace_id: UUID,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    status_filter: MemberStatus | None = Query(None, alias="status"),
) -> list[WorkspaceMemberResponse]:
    """List workspace members."""
    request_logger.info(
        f"GET /workspaces/{workspace_id}/members - user={current_user.id}"
    )
    async with session.begin():
        # Check access
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found or access denied.",
            )

        members = await workspace_member_db.get_workspace_members(
            session, workspace_id, status=status_filter
        )
        return [_build_member_response(m) for m in members]


@router.patch(
    "/{workspace_id}/members/{member_user_id}/status",
    response_model=WorkspaceMemberResponse,
    summary="Update member status",
    description="""
## Enable or Disable Workspace Member

Change a member's status between enabled and disabled. Disabled members cannot
access the workspace but remain in the member list.

### Authorization

- User must be an **admin** or **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace identifier |
| `member_user_id` | UUID | The user ID of the member to update |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | ✅ | New status: `enabled` or `disabled` |

### Response

Returns the updated member object.

### Status Behavior

**Enabling a member:**
- Requires an available seat
- Member gains access to workspace

**Disabling a member:**
- Frees up a seat for other members
- Member loses workspace access but remains in list

### Error Responses

| Status | Reason |
|--------|--------|
| `402 Payment Required` | No available seats to enable member |
| `403 Forbidden` | User is not an admin of the workspace |
| `404 Not Found` | Member not found |

### Notes

- Cannot disable yourself
- Cannot disable the workspace owner
- Enabling requires available seats in subscription
""",
    responses={
        402: {
            "description": "Insufficient seats",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "No available seats. Purchase more seats to enable this member."
                    }
                }
            },
        },
        403: {
            "description": "Admin permission required",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin permission required."}
                }
            },
        },
        404: {
            "description": "Member not found",
            "content": {
                "application/json": {"example": {"detail": "Member not found."}}
            },
        },
    },
)
async def update_member_status(
    workspace_id: UUID,
    member_user_id: UUID,
    data: MemberStatusUpdate,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WorkspaceMemberResponse:
    """Enable or disable a workspace member."""
    request_logger.info(
        f"PATCH /workspaces/{workspace_id}/members/{member_user_id}/status "
        f"- user={current_user.id} status={data.status}"
    )
    try:
        async with session.begin():
            member = await workspace_service.update_member_status(
                session,
                workspace_id=workspace_id,
                member_user_id=member_user_id,
                admin_user_id=current_user.id,
                status=data.status,
                commit_self=False,
            )
            return _build_member_response(member)
    except PermissionDeniedException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e.message)
        )
    except MemberNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e.message)
        )
    except InsufficientSeatsException as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e.message)
        )


@router.patch(
    "/{workspace_id}/members/{member_user_id}/role",
    response_model=WorkspaceMemberResponse,
    summary="Update member role",
    description="""
## Update Member Role

Change a member's role within the workspace.

### Authorization

- User must be the **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace identifier |
| `member_user_id` | UUID | The user ID of the member to update |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | string | ✅ | New role: `admin` or `member` |

### Roles

| Role | Description |
|------|-------------|
| `owner` | Full control, can delete workspace (cannot be assigned) |
| `admin` | Manage members, invitations, subscription |
| `member` | Basic workspace access |

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not the workspace owner |
| `404 Not Found` | Member not found |

### Notes

- Only workspace **owner** can change roles
- Cannot change the owner role (use transfer ownership instead)
- Admins can promote members to admin
""",
    responses={
        403: {
            "description": "Owner permission required",
            "content": {
                "application/json": {
                    "example": {"detail": "Only workspace owner can change roles."}
                }
            },
        },
        404: {
            "description": "Member not found",
            "content": {
                "application/json": {"example": {"detail": "Member not found."}}
            },
        },
    },
)
async def update_member_role(
    workspace_id: UUID,
    member_user_id: UUID,
    data: MemberRoleUpdate,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WorkspaceMemberResponse:
    """Update a member's role."""
    request_logger.info(
        f"PATCH /workspaces/{workspace_id}/members/{member_user_id}/role "
        f"- user={current_user.id} role={data.role}"
    )
    try:
        async with session.begin():
            member = await workspace_service.update_member_role(
                session,
                workspace_id=workspace_id,
                member_user_id=member_user_id,
                admin_user_id=current_user.id,
                role=data.role,
                commit_self=False,
            )
            return _build_member_response(member)
    except PermissionDeniedException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e.message)
        )
    except MemberNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e.message)
        )


@router.delete(
    "/{workspace_id}/members/{member_user_id}",
    response_model=MessageResponse,
    summary="Remove member",
    description="""
## Remove Workspace Member

Remove a member from the workspace. The member loses all access and is
removed from the member list.

### Authorization

- User must be an **admin** or **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace identifier |
| `member_user_id` | UUID | The user ID of the member to remove |

### Response

```json
{
  "message": "Member removed successfully."
}
```

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not an admin of the workspace |
| `404 Not Found` | Member not found |

### Notes

- Cannot remove yourself (use `/leave` instead)
- Cannot remove the workspace owner
- Removing a member frees up a seat
- If member was enabled, available seats increase
""",
    responses={
        403: {
            "description": "Admin permission required",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin permission required."}
                }
            },
        },
        404: {
            "description": "Member not found",
            "content": {
                "application/json": {"example": {"detail": "Member not found."}}
            },
        },
    },
)
async def remove_member(
    workspace_id: UUID,
    member_user_id: UUID,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """Remove a member from workspace."""
    request_logger.info(
        f"DELETE /workspaces/{workspace_id}/members/{member_user_id} "
        f"- user={current_user.id}"
    )
    try:
        async with session.begin():
            await workspace_service.remove_member(
                session,
                workspace_id=workspace_id,
                member_user_id=member_user_id,
                admin_user_id=current_user.id,
                commit_self=False,
            )
            return MessageResponse(message="Member removed successfully.")
    except PermissionDeniedException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e.message)
        )
    except MemberNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e.message)
        )


@router.post(
    "/{workspace_id}/leave",
    response_model=MessageResponse,
    summary="Leave workspace",
    description="""
## Leave Workspace

Voluntarily leave a workspace. The user loses all access.

### Authorization

- User must be a **member** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace to leave |

### Response

```json
{
  "message": "Successfully left workspace."
}
```

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | Owner cannot leave (must transfer ownership first) |
| `404 Not Found` | Not a member of this workspace |

### Notes

- **Owners cannot leave** - transfer ownership first
- Leaving frees up a seat if you were enabled
- To rejoin, you need a new invitation
""",
    responses={
        403: {
            "description": "Owner cannot leave",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Owner cannot leave workspace. Transfer ownership first."
                    }
                }
            },
        },
        404: {
            "description": "Not a member",
            "content": {
                "application/json": {
                    "example": {"detail": "Not a member of this workspace."}
                }
            },
        },
    },
)
async def leave_workspace(
    workspace_id: UUID,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """Leave a workspace."""
    request_logger.info(
        f"POST /workspaces/{workspace_id}/leave - user={current_user.id}"
    )
    try:
        async with session.begin():
            await workspace_service.leave_workspace(
                session,
                workspace_id=workspace_id,
                user_id=current_user.id,
                commit_self=False,
            )
            return MessageResponse(message="Successfully left workspace.")
    except PermissionDeniedException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e.message)
        )
    except MemberNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e.message)
        )


@router.post(
    "/{workspace_id}/transfer-ownership",
    response_model=WorkspaceResponse,
    summary="Transfer ownership",
    description="""
## Transfer Workspace Ownership

Transfer workspace ownership to another member. The current owner becomes
an admin.

### Authorization

- User must be the **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace identifier |

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `new_owner_id` | UUID | ✅ | User ID of the new owner |

### Response

Returns the updated workspace with new owner.

### Ownership Transfer Process

1. Current owner initiates transfer
2. New owner must be an existing enabled member
3. Current owner becomes admin
4. New owner gains full control

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not the current owner |
| `404 Not Found` | New owner is not a member |

### Notes

- Only workspace **owner** can transfer ownership
- New owner must be an enabled member
- Previous owner becomes admin (not removed)
- This action cannot be undone
""",
    responses={
        403: {
            "description": "Owner permission required",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Only workspace owner can transfer ownership."
                    }
                }
            },
        },
        404: {
            "description": "Member not found",
            "content": {
                "application/json": {
                    "example": {"detail": "New owner must be an existing member."}
                }
            },
        },
    },
)
async def transfer_ownership(
    workspace_id: UUID,
    new_owner_id: UUID,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WorkspaceResponse:
    """Transfer workspace ownership to another member."""
    request_logger.info(
        f"POST /workspaces/{workspace_id}/transfer-ownership "
        f"- user={current_user.id} new_owner={new_owner_id}"
    )
    try:
        async with session.begin():
            workspace = await workspace_service.transfer_ownership(
                session,
                workspace_id=workspace_id,
                current_owner_id=current_user.id,
                new_owner_id=new_owner_id,
                commit_self=False,
            )
            return _build_workspace_response(workspace)
    except PermissionDeniedException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e.message)
        )
    except MemberNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e.message)
        )


# ============================================================================
# Invitation Endpoints
# ============================================================================


@router.get(
    "/{workspace_id}/invitations",
    response_model=InvitationListResponse,
    summary="List invitations",
    description="""
## List Workspace Invitations

Retrieve all pending invitations for a workspace.

### Authorization

- User must be an **admin** or **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace identifier |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `invitations` | array | List of invitation objects |
| `invitations[].id` | UUID | Invitation identifier |
| `invitations[].email` | string | Invited email address |
| `invitations[].role` | string | Role to be assigned |
| `invitations[].status` | string | `pending`, `accepted`, `expired` |
| `invitations[].expires_at` | datetime | Expiration timestamp |
| `invitations[].inviter_email` | string | Who sent the invitation |

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not an admin of the workspace |

### Notes

- Only pending invitations are typically shown
- Expired invitations may still appear
""",
    responses={
        403: {
            "description": "Admin permission required",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin permission required."}
                }
            },
        },
    },
)
async def list_invitations(
    workspace_id: UUID,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> InvitationListResponse:
    """List pending invitations."""
    request_logger.info(
        f"GET /workspaces/{workspace_id}/invitations - user={current_user.id}"
    )
    async with session.begin():
        # Check admin access
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )
        if not member or not member.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin permission required.",
            )

        invitations = await workspace_invitation_db.get_workspace_invitations(
            session, workspace_id
        )
        return InvitationListResponse(
            invitations=[_build_invitation_response(i) for i in invitations]
        )


@router.post(
    "/{workspace_id}/invitations",
    response_model=InvitationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create invitation",
    description="""
## Invite User to Workspace

Send an invitation to a user to join the workspace. The user will receive
an invitation URL to accept.

### Authorization

- User must be an **admin** or **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace identifier |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | ✅ | Email address to invite |
| `role` | string | ❌ | Role to assign: `admin` or `member` (default) |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `invitation` | object | Created invitation details |
| `invitation_url` | string | URL for the invitee to accept |

### Invitation Flow

1. Admin sends invitation with this endpoint
2. System generates invitation token (valid 7 days)
3. Send `invitation_url` to the invitee
4. Invitee logs in and calls `/invitations/accept`
5. Invitee becomes a workspace member

### Error Responses

| Status | Reason |
|--------|--------|
| `400 Bad Request` | Cannot invite the owner |
| `402 Payment Required` | No available seats or free workspace |
| `403 Forbidden` | User is not admin or workspace is frozen |
| `409 Conflict` | User already a member or invitation exists |

### Notes

- Requires available seats in subscription
- Free workspaces cannot invite members
- Frozen workspaces cannot send invitations
- Existing members cannot be re-invited
""",
    responses={
        201: {"description": "Invitation created successfully"},
        402: {
            "description": "Insufficient seats or free workspace",
            "content": {
                "application/json": {"example": {"detail": "No available seats."}}
            },
        },
        403: {
            "description": "Admin permission required or workspace frozen",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin permission required."}
                }
            },
        },
        409: {
            "description": "Already a member or invitation exists",
            "content": {
                "application/json": {"example": {"detail": "User is already a member."}}
            },
        },
    },
)
async def create_invitation(
    workspace_id: UUID,
    data: InvitationCreate,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> InvitationCreatedResponse:
    """Invite a user to join the workspace."""
    request_logger.info(
        f"POST /workspaces/{workspace_id}/invitations "
        f"- user={current_user.id} email={data.email}"
    )
    try:
        async with session.begin():
            invitation, raw_token = await workspace_service.invite_member(
                session,
                workspace_id=workspace_id,
                inviter_id=current_user.id,
                email=data.email,
                role=data.role,
                commit_self=False,
            )

            # Build invitation URL
            invitation_url = f"{settings.API_DOMAIN}{settings.ROOT_PATH}/workspaces/invitations/accept?token={raw_token}"

            return InvitationCreatedResponse(
                invitation=_build_invitation_response(invitation),
                invitation_url=invitation_url,
            )
    except PermissionDeniedException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e.message)
        )
    except CannotInviteOwnerException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e.message)
        )
    except MemberAlreadyExistsException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e.message))
    except InvitationAlreadyExistsException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e.message))
    except FreeWorkspaceNoInvitesException as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e.message)
        )
    except InsufficientSeatsException as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e.message)
        )
    except WorkspaceFrozenException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e.message)
        )


@router.delete(
    "/{workspace_id}/invitations/{invitation_id}",
    response_model=MessageResponse,
    summary="Revoke invitation",
    description="""
## Revoke Workspace Invitation

Revoke a pending invitation. The invitation link will no longer work.

### Authorization

- User must be an **admin** or **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace identifier |
| `invitation_id` | UUID | The invitation to revoke |

### Response

```json
{
  "message": "Invitation revoked."
}
```

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not an admin of the workspace |
| `404 Not Found` | Invitation not found |

### Notes

- Only pending invitations can be revoked
- The invitee will receive an error if they try to use the link
""",
    responses={
        403: {
            "description": "Admin permission required",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin permission required."}
                }
            },
        },
        404: {
            "description": "Invitation not found",
            "content": {
                "application/json": {"example": {"detail": "Invitation not found."}}
            },
        },
    },
)
async def revoke_invitation(
    workspace_id: UUID,
    invitation_id: UUID,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """Revoke a pending invitation."""
    request_logger.info(
        f"DELETE /workspaces/{workspace_id}/invitations/{invitation_id} "
        f"- user={current_user.id}"
    )
    try:
        async with session.begin():
            await workspace_service.revoke_invitation(
                session,
                workspace_id=workspace_id,
                invitation_id=invitation_id,
                user_id=current_user.id,
                commit_self=False,
            )
            return MessageResponse(message="Invitation revoked.")
    except PermissionDeniedException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e.message)
        )
    except InvitationNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e.message)
        )


# ============================================================================
# Public Invitation Accept Endpoint
# ============================================================================


@router.post(
    "/invitations/accept",
    response_model=WorkspaceMemberResponse,
    summary="Accept invitation",
    description="""
## Accept Workspace Invitation

Accept an invitation to join a workspace using the invitation token.

### Authorization

- User must be authenticated
- Token must match the user's email

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `token` | string | ✅ | Invitation token from the invitation URL |

### Response

Returns the created member object:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Member record ID |
| `user_id` | UUID | Your user ID |
| `role` | string | Assigned role |
| `status` | string | `enabled` |
| `joined_at` | datetime | Current timestamp |

### Error Responses

| Status | Reason |
|--------|--------|
| `402 Payment Required` | No available seats |
| `404 Not Found` | Invalid or expired token |
| `409 Conflict` | Already a member of this workspace |

### Notes

- Token is typically received via email or shared link
- Token expires after 7 days
- Email must match the invitation email
- If seats are full, the invitation cannot be accepted
""",
    responses={
        402: {
            "description": "No available seats",
            "content": {
                "application/json": {"example": {"detail": "No available seats."}}
            },
        },
        404: {
            "description": "Invalid or expired token",
            "content": {
                "application/json": {
                    "example": {"detail": "Invitation not found or expired."}
                }
            },
        },
        409: {
            "description": "Already a member",
            "content": {
                "application/json": {
                    "example": {"detail": "Already a member of this workspace."}
                }
            },
        },
    },
)
async def accept_invitation(
    data: InvitationAccept,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WorkspaceMemberResponse:
    """Accept a workspace invitation using the token."""
    request_logger.info(f"POST /workspaces/invitations/accept - user={current_user.id}")
    try:
        async with session.begin():
            member = await workspace_service.accept_invitation(
                session,
                token=data.token,
                user=current_user,
                commit_self=False,
            )
            return _build_member_response(member)
    except InvitationNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e.message)
        )
    except MemberAlreadyExistsException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e.message))
    except InsufficientSeatsException as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e.message)
        )


# ============================================================================
# Manual Activation Endpoint
# ============================================================================


@router.post(
    "/activate",
    response_model=WorkspaceResponse,
    summary="Activate personal workspace",
    description="""
## Activate Personal Workspace

Manually create or retrieve the user's personal workspace with a free subscription.
This is a fallback endpoint for users whose automatic workspace creation failed
during signup.

### Authorization

- User must be authenticated

### Response

Returns the personal workspace:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Workspace identifier |
| `display_name` | string | User's name + "'s Workspace" |
| `slug` | string | Auto-generated slug |
| `status` | string | `active` |
| `is_personal` | boolean | Always `true` |
| `owner_id` | UUID | User's ID |

### Idempotent Behavior

This endpoint is idempotent:
- If personal workspace exists, returns it
- If not, creates workspace + free subscription

### Notes

- Personal workspaces are automatically created at signup
- This endpoint is a safety net for edge cases
- Personal workspaces cannot be deleted
- Each user can only have one personal workspace
""",
)
async def activate_personal_workspace(
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WorkspaceResponse:
    """Manually activate personal workspace."""
    request_logger.info(f"POST /workspaces/activate - user={current_user.id}")
    async with session.begin():
        workspace, member, subscription = (
            await workspace_service.create_personal_workspace(
                session,
                user=current_user,
                commit_self=False,
            )
        )

    request_logger.info(
        f"POST /workspaces/activate - workspace={workspace.id} for user={current_user.id}"
    )
    return _build_workspace_response(workspace)


__all__ = ["router"]
