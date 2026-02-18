"""
Workspace access dependencies for cubex_api.

This module provides FastAPI dependency injection functions for:
- Verifying workspace membership
- Checking admin/owner permissions
- Validating workspace status (active/frozen)

These dependencies simplify router code by handling common access
control patterns consistently.

Example usage:
    from app.apps.cubex_api.dependencies import (
        WorkspaceMember,
        WorkspaceAdmin,
        WorkspaceOwner,
    )

    @router.get("/workspaces/{workspace_id}")
    async def get_workspace(member: WorkspaceMember):
        # member is the WorkspaceMember object for current user
        return {"workspace_id": member.workspace_id}

    @router.patch("/workspaces/{workspace_id}/settings")
    async def update_settings(member: WorkspaceAdmin):
        # Only admins/owners reach here
        return {"success": True}

    @router.delete("/workspaces/{workspace_id}")
    async def delete_workspace(member: WorkspaceOwner):
        # Only owners reach here
        return {"deleted": True}
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_api.db.crud import workspace_member_db, workspace_db
from app.apps.cubex_api.db.models import Workspace, WorkspaceMember
from app.core.dependencies.db import get_async_session
from app.core.config import request_logger, settings
from app.core.db.models import User
from app.core.dependencies.auth import get_current_active_user
from app.core.enums import WorkspaceStatus
from app.core.exceptions.types import (
    AuthenticationException,
    ForbiddenException,
    NotFoundException,
)


# ============================================================================
# Exceptions
# ============================================================================


class WorkspaceAccessDeniedException(NotFoundException):
    """Raised when user is not a member of the workspace."""

    def __init__(
        self, workspace_id: UUID | None = None, message: str | None = None
    ) -> None:
        msg = message or "Workspace not found or access denied."
        if workspace_id:
            msg = f"Workspace {workspace_id} not found or access denied."
        super().__init__(msg)


class AdminPermissionRequiredException(ForbiddenException):
    """Raised when admin permission is required but user is not admin."""

    def __init__(self, message: str = "Admin permission required.") -> None:
        super().__init__(message)


class OwnerPermissionRequiredException(ForbiddenException):
    """Raised when owner permission is required but user is not owner."""

    def __init__(
        self, message: str = "Only workspace owner can perform this action."
    ) -> None:
        super().__init__(message)


class WorkspaceFrozenException(ForbiddenException):
    """Raised when workspace is frozen and operation requires active workspace."""

    def __init__(
        self, workspace_id: UUID | None = None, message: str | None = None
    ) -> None:
        msg = message or "Workspace is frozen. Please renew subscription."
        if workspace_id:
            msg = f"Workspace {workspace_id} is frozen. Please renew subscription."
        super().__init__(msg)


# ============================================================================
# Dependency Functions
# ============================================================================


async def get_workspace_member(
    workspace_id: Annotated[UUID, Path(description="Workspace ID")],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WorkspaceMember:
    """
    Verify user is a member of the workspace and return membership.

    This dependency:
    1. Extracts workspace_id from path parameters
    2. Gets current authenticated user
    3. Checks if user is a member of the workspace
    4. Returns the WorkspaceMember object

    Args:
        workspace_id: The workspace ID from the path.
        current_user: The authenticated user.
        session: The database session.

    Returns:
        WorkspaceMember: The membership record for the current user.

    Raises:
        WorkspaceAccessDeniedException: If user is not a member.

    Example:
        @router.get("/workspaces/{workspace_id}/info")
        async def get_info(member: WorkspaceMember):
            return {"role": member.role.value}
    """
    async with session.begin():
        member = await workspace_member_db.get_member(
            session, workspace_id, current_user.id
        )

    if not member:
        request_logger.warning(
            f"Workspace access denied: user={current_user.id} workspace={workspace_id}"
        )
        raise WorkspaceAccessDeniedException(workspace_id)

    request_logger.debug(
        f"Workspace access granted: user={current_user.id} "
        f"workspace={workspace_id} role={member.role.value}"
    )
    return member


async def get_workspace_admin(
    member: Annotated[WorkspaceMember, Depends(get_workspace_member)],
) -> WorkspaceMember:
    """
    Verify user is an admin or owner of the workspace.

    This dependency wraps get_workspace_member and adds a check
    to ensure the user has admin privileges.

    Args:
        member: The workspace member from get_workspace_member.

    Returns:
        WorkspaceMember: The membership record if user is admin/owner.

    Raises:
        AdminPermissionRequiredException: If user is not admin/owner.

    Example:
        @router.patch("/workspaces/{workspace_id}/settings")
        async def update_settings(member: WorkspaceAdmin):
            # Only admins/owners can update settings
            return {"updated": True}
    """
    if not member.is_admin:
        request_logger.warning(
            f"Admin permission denied: user={member.user_id} "
            f"workspace={member.workspace_id} role={member.role.value}"
        )
        raise AdminPermissionRequiredException()

    return member


async def get_workspace_owner(
    member: Annotated[WorkspaceMember, Depends(get_workspace_member)],
) -> WorkspaceMember:
    """
    Verify user is the owner of the workspace.

    This dependency wraps get_workspace_member and adds a check
    to ensure the user is the workspace owner.

    Args:
        member: The workspace member from get_workspace_member.

    Returns:
        WorkspaceMember: The membership record if user is owner.

    Raises:
        OwnerPermissionRequiredException: If user is not owner.

    Example:
        @router.delete("/workspaces/{workspace_id}")
        async def delete_workspace(member: WorkspaceOwner):
            # Only owners can delete workspaces
            return {"deleted": True}
    """
    if not member.is_owner:
        request_logger.warning(
            f"Owner permission denied: user={member.user_id} "
            f"workspace={member.workspace_id} role={member.role.value}"
        )
        raise OwnerPermissionRequiredException()

    return member


async def get_active_workspace(
    workspace_id: Annotated[UUID, Path(description="Workspace ID")],
    member: Annotated[WorkspaceMember, Depends(get_workspace_member)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Workspace:
    """
    Get workspace and verify it is not frozen.

    This dependency:
    1. Verifies user is a member (via get_workspace_member)
    2. Fetches the workspace
    3. Checks workspace is not frozen

    Args:
        workspace_id: The workspace ID from the path.
        member: The workspace member (ensures access).
        session: The database session.

    Returns:
        Workspace: The workspace if it exists and is active.

    Raises:
        WorkspaceAccessDeniedException: If workspace not found.
        WorkspaceFrozenException: If workspace is frozen.

    Example:
        @router.post("/workspaces/{workspace_id}/invitations")
        async def create_invitation(workspace: ActiveWorkspace):
            # Only works for active workspaces
            return {"invited": True}
    """
    async with session.begin():
        workspace = await workspace_db.get_by_id(session, workspace_id)

    if not workspace or workspace.is_deleted:
        raise WorkspaceAccessDeniedException(workspace_id)

    if workspace.status == WorkspaceStatus.FROZEN:
        request_logger.warning(
            f"Workspace frozen: user={member.user_id} workspace={workspace_id}"
        )
        raise WorkspaceFrozenException(workspace_id)

    return workspace


async def get_active_workspace_admin(
    member: Annotated[WorkspaceMember, Depends(get_workspace_admin)],
    workspace: Annotated[Workspace, Depends(get_active_workspace)],
) -> tuple[WorkspaceMember, Workspace]:
    """
    Get admin member and verify workspace is active.

    Combines admin check with active workspace check.

    Args:
        member: The admin member.
        workspace: The active workspace.

    Returns:
        Tuple of (member, workspace).

    Example:
        @router.post("/workspaces/{workspace_id}/members")
        async def add_member(context: ActiveWorkspaceAdmin):
            member, workspace = context
            return {"added": True}
    """
    return member, workspace


async def get_active_workspace_owner(
    member: Annotated[WorkspaceMember, Depends(get_workspace_owner)],
    workspace: Annotated[Workspace, Depends(get_active_workspace)],
) -> tuple[WorkspaceMember, Workspace]:
    """
    Get owner member and verify workspace is active.

    Combines owner check with active workspace check.

    Args:
        member: The owner member.
        workspace: The active workspace.

    Returns:
        Tuple of (member, workspace).

    Example:
        @router.delete("/workspaces/{workspace_id}")
        async def delete_workspace(context: ActiveWorkspaceOwner):
            member, workspace = context
            return {"deleted": True}
    """
    return member, workspace


# ============================================================================
# Type Aliases
# ============================================================================

# Basic workspace access
WorkspaceMemberDep = Annotated[WorkspaceMember, Depends(get_workspace_member)]
WorkspaceAdminDep = Annotated[WorkspaceMember, Depends(get_workspace_admin)]
WorkspaceOwnerDep = Annotated[WorkspaceMember, Depends(get_workspace_owner)]

# Active workspace (not frozen)
ActiveWorkspaceDep = Annotated[Workspace, Depends(get_active_workspace)]
ActiveWorkspaceAdminDep = Annotated[
    tuple[WorkspaceMember, Workspace], Depends(get_active_workspace_admin)
]
ActiveWorkspaceOwnerDep = Annotated[
    tuple[WorkspaceMember, Workspace], Depends(get_active_workspace_owner)
]


# ============================================================================
# Internal API Authentication
# ============================================================================


class InvalidInternalAPIKeyException(AuthenticationException):
    """Raised when internal API key is invalid or missing."""

    def __init__(self, message: str = "Invalid or missing internal API key.") -> None:
        super().__init__(message)


async def verify_internal_api_key(
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> str:
    """
    Verify the internal API key for internal endpoints.

    This dependency validates the X-Internal-API-Key header against
    the configured INTERNAL_API_SECRET. Used for internal communication
    between this app and external developer APIs.

    Args:
        x_internal_api_key: The API key from X-Internal-API-Key header.

    Returns:
        The validated API key.

    Raises:
        InvalidInternalAPIKeyException: If the key is missing or invalid.
    """
    if not x_internal_api_key:
        request_logger.warning("Internal API request missing X-Internal-API-Key header")
        raise InvalidInternalAPIKeyException("Missing X-Internal-API-Key header.")

    if x_internal_api_key != settings.INTERNAL_API_SECRET:
        request_logger.warning("Internal API request with invalid API key")
        raise InvalidInternalAPIKeyException("Invalid internal API key.")

    return x_internal_api_key


# Type alias for internal API authentication
InternalAPIKeyDep = Annotated[str, Depends(verify_internal_api_key)]


__all__ = [
    # Dependency functions
    "get_workspace_member",
    "get_workspace_admin",
    "get_workspace_owner",
    "get_active_workspace",
    "get_active_workspace_admin",
    "get_active_workspace_owner",
    "verify_internal_api_key",
    # Type aliases
    "WorkspaceMemberDep",
    "WorkspaceAdminDep",
    "WorkspaceOwnerDep",
    "ActiveWorkspaceDep",
    "ActiveWorkspaceAdminDep",
    "ActiveWorkspaceOwnerDep",
    "InternalAPIKeyDep",
    # Exceptions
    "WorkspaceAccessDeniedException",
    "AdminPermissionRequiredException",
    "OwnerPermissionRequiredException",
    "WorkspaceFrozenException",
    "InvalidInternalAPIKeyException",
]
