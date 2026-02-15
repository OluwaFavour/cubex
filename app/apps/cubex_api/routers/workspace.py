"""
Workspace router for cubex_api.

This module provides endpoints for:
- Workspace CRUD operations
- Member management (invite, enable/disable, remove)
- Invitation management
"""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_api.services.quota_cache import QuotaCacheService
from app.core.dependencies import get_async_session
from app.shared.config import request_logger
from app.shared.dependencies.auth import CurrentActiveUser
from app.shared.exceptions.types import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    PaymentRequiredException,
)
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
    APIKeyCreate,
    APIKeyResponse,
    APIKeyCreatedResponse,
    APIKeyListResponse,
)
from app.apps.cubex_api.services import (
    workspace_service,
    subscription_service,
    quota_service,
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
    APIKeyNotFoundException,
)
from app.shared.enums import MemberRole, MemberStatus
from app.shared.services.oauth.base import OAuthStateManager
from app.apps.cubex_api.db.models import (
    Workspace,
    WorkspaceMember,
    WorkspaceInvitation,
)


router = APIRouter(prefix="/workspaces")


# ============================================================================
# Helper Functions
# ============================================================================


async def _build_workspace_response(
    session: AsyncSession, workspace: Workspace
) -> WorkspaceResponse:
    """Build WorkspaceResponse from Workspace model."""
    # Get seat count
    seat_count = (
        workspace.api_subscription_context.subscription.seat_count
        if workspace.api_subscription_context
        else 0
    )
    enabled_count = len(
        [m for m in workspace.members if m.status == MemberStatus.ENABLED]
    )
    available_seats = seat_count - enabled_count

    # Get credits
    credits_used = (
        workspace.api_subscription_context.credits_used
        if workspace.api_subscription_context
        else Decimal("0.00")
    )
    credits_limit = await QuotaCacheService.get_plan_credits_allocation_with_fallback(
        session,
        (
            workspace.api_subscription_context.subscription.plan_id
            if workspace.api_subscription_context
            else None
        ),
    )
    return WorkspaceResponse(
        id=workspace.id,
        display_name=workspace.display_name,
        slug=workspace.slug,
        status=workspace.status,
        is_personal=workspace.is_personal,
        description=workspace.description,
        created_at=workspace.created_at,
        owner_id=workspace.owner_id,
        enabled_member_count=enabled_count,
        total_member_count=len(workspace.members) if workspace.members else 0,
        seat_count=seat_count,
        available_seats=available_seats,
        credits_used=credits_used,
        credits_limit=credits_limit,
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

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `member_role` | string | ❌ | Filter by user's role: `owner`, `admin`, or `member` |

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
- Use `member_role` to filter workspaces by your role in them
""",
)
async def list_workspaces(
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    role_filter: Annotated[MemberRole | None, Query(alias="member_role")] = None,
) -> WorkspaceListResponse:
    """List all workspaces the current user has access to."""
    request_logger.info(f"GET /workspaces - user={current_user.id} role={role_filter}")
    async with session.begin():
        workspaces = await workspace_service.get_user_workspaces(
            session, current_user.id, role=role_filter
        )
        request_logger.info(
            f"GET /workspaces - user={current_user.id} returned {len(workspaces)} workspaces"
        )
        workspaces_response = [
            await _build_workspace_response(session, w) for w in workspaces
        ]
        return WorkspaceListResponse(workspaces=workspaces_response)


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
| `credits_used` | decimal | API credits used in current billing period |
| `credits_limit` | decimal | Total API credits allocated by subscription |
| `credits_remaining` | decimal | Remaining API credits (limit - used) |

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
            raise NotFoundException("Workspace not found or access denied.")

        workspace = await workspace_service.get_workspace(session, workspace_id)
        members = workspace.members if workspace.members else []

        # Get subscription info
        subscription = (
            workspace.api_subscription_context.subscription
            if workspace.api_subscription_context
            else None
        )
        seat_count = subscription.seat_count if subscription else 0
        enabled_count = len([m for m in members if m.status == MemberStatus.ENABLED])

        # Get credits
        credits_used = (
            subscription.api_context.credits_used
            if subscription and subscription.api_context
            else Decimal("0.00")
        )
        credits_limit = (
            await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session, subscription.plan_id if subscription else None
            )
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
            enabled_member_count=enabled_count,
            total_member_count=len(members),
            members=[_build_member_response(m) for m in members],
            seat_count=seat_count,
            available_seats=seat_count - enabled_count,
            credits_used=credits_used,
            credits_limit=credits_limit,
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
            workspace_response = await _build_workspace_response(session, workspace)
            return workspace_response
    except PermissionDeniedException as e:
        raise ForbiddenException(str(e.message)) from e
    except WorkspaceNotFoundException as e:
        raise NotFoundException(str(e.message)) from e


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
            raise NotFoundException("Workspace not found or access denied.")

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
        raise ForbiddenException(str(e.message)) from e
    except MemberNotFoundException as e:
        raise NotFoundException(str(e.message)) from e
    except InsufficientSeatsException as e:
        raise PaymentRequiredException(str(e.message)) from e


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
        raise ForbiddenException(str(e.message)) from e
    except MemberNotFoundException as e:
        raise NotFoundException(str(e.message)) from e


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
        raise ForbiddenException(str(e.message)) from e
    except MemberNotFoundException as e:
        raise NotFoundException(str(e.message)) from e


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
        raise ForbiddenException(str(e.message)) from e
    except MemberNotFoundException as e:
        raise NotFoundException(str(e.message)) from e


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
            workspace_response = await _build_workspace_response(session, workspace)
            return workspace_response
    except PermissionDeniedException as e:
        raise ForbiddenException(str(e.message)) from e
    except MemberNotFoundException as e:
        raise NotFoundException(str(e.message)) from e


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
            raise ForbiddenException("Admin permission required.")

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
| `callback_url` | string | ✅ | Frontend URL to redirect after accepting (must be in allowed origins) |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `invitation` | object | Created invitation details |
| `invitation_url` | string | URL for the invitee to accept |

### Invitation Flow

1. Admin sends invitation with this endpoint
2. System generates invitation token (valid 7 days)
3. Send `invitation_url` to the invitee
   - The `invitation_url` is the provided `callback_url` with the token as a query parameter
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

    # Validate callback URL is in allowed CORS origins
    if not OAuthStateManager.validate_callback_url(data.callback_url):
        raise BadRequestException(
            "Invalid callback URL. Must be in allowed origins and use HTTPS in production."
        )

    try:
        async with session.begin():
            invitation, raw_token = await workspace_service.invite_member(
                session,
                workspace_id=workspace_id,
                inviter_id=current_user.id,
                email=data.email,
                role=data.role,
                callback_url=data.callback_url,
                commit_self=False,
            )

            # Build invitation URL for the response (frontend URL with token)
            invitation_url = f"{data.callback_url}?token={raw_token}"

            return InvitationCreatedResponse(
                invitation=_build_invitation_response(invitation),
                invitation_url=invitation_url,
            )
    except PermissionDeniedException as e:
        raise ForbiddenException(str(e.message)) from e
    except CannotInviteOwnerException as e:
        raise BadRequestException(str(e.message)) from e
    except MemberAlreadyExistsException as e:
        raise ConflictException(str(e.message)) from e
    except InvitationAlreadyExistsException as e:
        raise ConflictException(str(e.message)) from e
    except FreeWorkspaceNoInvitesException as e:
        raise PaymentRequiredException(str(e.message)) from e
    except InsufficientSeatsException as e:
        raise PaymentRequiredException(str(e.message)) from e
    except WorkspaceFrozenException as e:
        raise ForbiddenException(str(e.message)) from e


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
        raise ForbiddenException(str(e.message)) from e
    except InvitationNotFoundException as e:
        raise NotFoundException(str(e.message)) from e


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
        raise NotFoundException(str(e.message)) from e
    except MemberAlreadyExistsException as e:
        raise ConflictException(str(e.message)) from e
    except InsufficientSeatsException as e:
        raise PaymentRequiredException(str(e.message)) from e


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
        workspace_response = await _build_workspace_response(session, workspace)

    request_logger.info(
        f"POST /workspaces/activate - workspace={workspace.id} for user={current_user.id}"
    )
    return workspace_response


# ============================================================================
# API Key Endpoints
# ============================================================================


def _build_api_key_response(api_key) -> APIKeyResponse:
    """Build APIKeyResponse from APIKey model."""
    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        is_active=api_key.is_active,
        is_test_key=api_key.is_test_key,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        revoked_at=api_key.revoked_at,
    )


@router.post(
    "/{workspace_id}/api-keys",
    response_model=APIKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API key",
    description="""
## Create API Key

Generate a new API key for the workspace. The key is used to authenticate
requests to the external developer API.

### Authorization

- User must be an **admin** or **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace identifier |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | User-defined label for the key (1-128 characters) |
| `expires_in_days` | integer | ❌ | Days until expiry (1-365). Default: 90. |
| `is_test_key` | boolean | ❌ | Whether this is a test key. Default: false. |

### Key Types

| Type | Prefix | Credits | Description |
|------|--------|---------|-------------|
| Live | `cbx_live_` | Charged | Production keys that consume credits |
| Test | `cbx_test_` | Never | Development keys for testing (no credits charged) |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `api_key` | string | The full API key. **Store securely - shown only once!** |
| `key` | object | API key metadata |
| `key.id` | UUID | Key identifier |
| `key.name` | string | User-defined label |
| `key.key_prefix` | string | Display prefix for identification |
| `key.is_active` | boolean | Whether key is active |
| `key.is_test_key` | boolean | Whether this is a test key |
| `key.expires_at` | datetime | Expiration timestamp (null if never) |
| `message` | string | Security reminder |

### Security Notes

- The full API key is shown **only once** in this response
- Store the key securely (e.g., environment variable, secrets manager)
- The key cannot be retrieved again - if lost, revoke and create a new one
- Keys are hashed with HMAC-SHA256 before storage

### Error Responses

| Status | Reason |
|--------|---------|
| `403 Forbidden` | User is not an admin of the workspace |
| `404 Not Found` | Workspace not found |
""",
    responses={
        201: {"description": "API key created successfully"},
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
async def create_api_key(
    workspace_id: UUID,
    data: APIKeyCreate,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> APIKeyCreatedResponse:
    """Create a new API key for the workspace."""
    request_logger.info(
        f"POST /workspaces/{workspace_id}/api-keys - user={current_user.id}"
    )

    async with session.begin():
        # Get member and verify admin permission
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )
        if not member:
            raise NotFoundException("Workspace not found or access denied.")
        if member.role not in [MemberRole.ADMIN, MemberRole.OWNER]:
            raise ForbiddenException("Admin permission required.")
        api_key, raw_key = await quota_service.create_api_key(
            session=session,
            workspace_id=workspace_id,
            name=data.name,
            expires_in_days=data.expires_in_days,
            is_test_key=data.is_test_key,
            commit_self=False,
        )

    request_logger.info(
        f"POST /workspaces/{workspace_id}/api-keys - created key={api_key.id}"
    )

    return APIKeyCreatedResponse(
        api_key=raw_key,
        key=_build_api_key_response(api_key),
    )


@router.get(
    "/{workspace_id}/api-keys",
    response_model=APIKeyListResponse,
    summary="List API keys",
    description="""
## List API Keys

Retrieve all API keys for the workspace.

### Authorization

- User must be a **member** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace identifier |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `api_keys` | array | List of API key objects |
| `api_keys[].id` | UUID | Key identifier |
| `api_keys[].name` | string | User-defined label |
| `api_keys[].key_prefix` | string | Display prefix for identification |
| `api_keys[].is_active` | boolean | Whether key is active |
| `api_keys[].created_at` | datetime | Creation timestamp |
| `api_keys[].expires_at` | datetime | Expiration timestamp (null if never) |
| `api_keys[].last_used_at` | datetime | Last usage timestamp (null if never used) |
| `api_keys[].revoked_at` | datetime | Revocation timestamp (null if active) |

### Notes

- Only metadata is returned, never the actual key
- Includes both active and revoked keys
- Use `key_prefix` to identify keys (e.g., "cbx_live_abc12...")
""",
    responses={
        404: {
            "description": "Workspace not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Workspace not found or access denied."}
                }
            },
        },
    },
)
async def list_api_keys(
    workspace_id: UUID,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> APIKeyListResponse:
    """List all API keys for the workspace."""
    request_logger.info(
        f"GET /workspaces/{workspace_id}/api-keys - user={current_user.id}"
    )

    async with session.begin():
        # Verify user is a member of the workspace
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )
        if not member:
            raise NotFoundException("Workspace not found or access denied.")

        api_keys = await quota_service.list_api_keys(session, workspace_id)

    return APIKeyListResponse(
        api_keys=[_build_api_key_response(key) for key in api_keys],
    )


@router.delete(
    "/{workspace_id}/api-keys/{api_key_id}",
    response_model=MessageResponse,
    summary="Revoke API key",
    description="""
## Revoke API Key

Revoke an API key. The key will immediately stop working.

### Authorization

- User must be an **admin** or **owner** of the workspace

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | The workspace identifier |
| `api_key_id` | UUID | The API key identifier |

### Response

```json
{
  "message": "API key revoked."
}
```

### Error Responses

| Status | Reason |
|--------|--------|
| `403 Forbidden` | User is not an admin of the workspace |
| `404 Not Found` | API key not found |

### Notes

- Revocation is immediate and permanent
- Revoked keys are kept in the list for audit purposes
- Create a new key if needed after revocation
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
            "description": "API key not found",
            "content": {
                "application/json": {"example": {"detail": "API key not found."}}
            },
        },
    },
)
async def revoke_api_key(
    workspace_id: UUID,
    api_key_id: UUID,
    current_user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """Revoke an API key."""
    request_logger.info(
        f"DELETE /workspaces/{workspace_id}/api-keys/{api_key_id} - user={current_user.id}"
    )

    try:
        async with session.begin():
            # Get member and verify admin permission
            member = await workspace_member_db.get_member(
                session, workspace_id, current_user.id
            )
            if not member:
                raise NotFoundException("Workspace not found or access denied.")
            if member.role not in [MemberRole.ADMIN, MemberRole.OWNER]:
                raise ForbiddenException("Admin permission required.")
            await quota_service.revoke_api_key(
                session=session,
                workspace_id=workspace_id,
                api_key_id=api_key_id,
                commit_self=False,
            )
    except APIKeyNotFoundException as e:
        raise NotFoundException(str(e.message)) from e

    request_logger.info(
        f"DELETE /workspaces/{workspace_id}/api-keys/{api_key_id} - revoked"
    )

    return MessageResponse(message="API key revoked.")


__all__ = ["router"]
