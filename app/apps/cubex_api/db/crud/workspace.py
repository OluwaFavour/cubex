"""
CRUD operations for Workspace models.

This module provides database operations for managing workspaces,
members, and invitations.
"""

import re
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import SQLColumnExpression, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.shared.db.crud.base import BaseDB
from app.apps.cubex_api.db.models.workspace import (
    Workspace,
    WorkspaceMember,
    WorkspaceInvitation,
)
from app.shared.enums import (
    InvitationStatus,
    MemberRole,
    MemberStatus,
    WorkspaceStatus,
)
from app.shared.exceptions.types import DatabaseException


def slugify(text: str) -> str:
    """
    Convert text to URL-friendly slug.

    Args:
        text: Text to slugify.

    Returns:
        URL-friendly slug (lowercase, alphanumeric + hyphens).
    """
    # Convert to lowercase
    slug = text.lower()
    # Replace spaces and underscores with hyphens
    slug = re.sub(r"[\s_]+", "-", slug)
    # Remove non-alphanumeric characters except hyphens
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Remove multiple consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    return slug or "workspace"


class WorkspaceDB(BaseDB[Workspace]):
    """CRUD operations for Workspace model."""

    SLUG_PREFIX = "ws"

    def __init__(self):
        super().__init__(Workspace)

    async def generate_unique_slug(
        self,
        session: AsyncSession,
        base_name: str,
    ) -> str:
        """
        Generate a unique slug for a workspace.

        Args:
            session: Database session.
            base_name: Base name to generate slug from.

        Returns:
            Unique slug with prefix (e.g., 'ws-john-doe' or 'ws-john-doe-2').
        """
        base_slug = f"{self.SLUG_PREFIX}-{slugify(base_name)}"
        slug = base_slug
        suffix = 1

        while await self.exists(session, {"slug": slug}):
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        return slug

    async def get_by_slug(
        self,
        session: AsyncSession,
        slug: str,
    ) -> Workspace | None:
        """
        Get workspace by slug.

        Args:
            session: Database session.
            slug: Workspace slug.

        Returns:
            Workspace or None if not found.
        """
        return await self.get_one_by_filters(
            session,
            {"slug": slug, "is_deleted": False},
            options=[selectinload(Workspace.members)],
        )

    async def get_personal_workspace(
        self,
        session: AsyncSession,
        owner_id: UUID,
    ) -> Workspace | None:
        """
        Get user's personal workspace.

        Args:
            session: Database session.
            owner_id: User ID.

        Returns:
            Personal workspace or None if not found.
        """
        return await self.get_one_by_filters(
            session,
            {"owner_id": owner_id, "is_personal": True, "is_deleted": False},
            options=[selectinload(Workspace.members)],
        )

    async def get_user_workspaces(
        self,
        session: AsyncSession,
        user_id: UUID,
        include_disabled: bool = False,
        role: MemberRole | None = None,
    ) -> Sequence[Workspace]:
        """
        Get all workspaces a user is a member of.

        Args:
            session: Database session.
            user_id: User ID.
            include_disabled: Include workspaces where user is disabled.
            role: Optional filter by user's role in the workspace.

        Returns:
            List of workspaces.
        """
        conditions = [
            WorkspaceMember.user_id == user_id,
            Workspace.is_deleted.is_(False),
        ]
        if not include_disabled:
            conditions.append(WorkspaceMember.status == MemberStatus.ENABLED)
        if role is not None:
            conditions.append(WorkspaceMember.role == role)

        stmt = (
            select(Workspace)
            .join(WorkspaceMember, Workspace.id == WorkspaceMember.workspace_id)
            .where(and_(*conditions))
            .options(selectinload(Workspace.members))
        )

        try:
            result = await session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            raise DatabaseException(
                f"Error getting workspaces for user {user_id}: {str(e)}"
            ) from e

    async def get_owned_workspaces(
        self,
        session: AsyncSession,
        owner_id: UUID,
    ) -> Sequence[Workspace]:
        """
        Get all workspaces owned by a user.

        Args:
            session: Database session.
            owner_id: User ID.

        Returns:
            List of owned workspaces.
        """
        return await self.get_by_filters(
            session,
            {"owner_id": owner_id, "is_deleted": False},
            options=[selectinload(Workspace.members)],
        )

    async def update_status(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        status: WorkspaceStatus,
        commit_self: bool = True,
    ) -> Workspace | None:
        """
        Update workspace status.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            status: New status.
            commit_self: Whether to commit the transaction.

        Returns:
            Updated workspace or None if not found.
        """
        return await self.update(
            session,
            workspace_id,
            {"status": status},
            commit_self=commit_self,
        )


class WorkspaceMemberDB(BaseDB[WorkspaceMember]):
    """CRUD operations for WorkspaceMember model."""

    def __init__(self):
        super().__init__(WorkspaceMember)

    async def get_member(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        user_id: UUID,
    ) -> WorkspaceMember | None:
        """
        Get workspace member.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            user_id: User ID.

        Returns:
            Member or None if not found.
        """
        return await self.get_one_by_filters(
            session,
            {"workspace_id": workspace_id, "user_id": user_id, "is_deleted": False},
            options=[selectinload(WorkspaceMember.user)],
        )

    async def get_workspace_members(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        status: MemberStatus | None = None,
    ) -> Sequence[WorkspaceMember]:
        """
        Get all members of a workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            status: Optional filter by status.

        Returns:
            List of members.
        """
        filters: dict = {"workspace_id": workspace_id, "is_deleted": False}
        if status:
            filters["status"] = status
        return await self.get_by_filters(
            session,
            filters,
            options=[selectinload(WorkspaceMember.user)],
        )

    async def get_enabled_member_count(
        self,
        session: AsyncSession,
        workspace_id: UUID,
    ) -> int:
        """
        Count enabled members in a workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.

        Returns:
            Number of enabled members.
        """
        try:
            stmt = (
                select(func.count())
                .select_from(WorkspaceMember)
                .where(
                    and_(
                        WorkspaceMember.workspace_id == workspace_id,
                        WorkspaceMember.status == MemberStatus.ENABLED,
                        WorkspaceMember.is_deleted.is_(False),
                    )
                )
            )
            result = await session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            raise DatabaseException(f"Error counting enabled members: {str(e)}") from e

    async def update_status(
        self,
        session: AsyncSession,
        member_id: UUID,
        status: MemberStatus,
        commit_self: bool = True,
    ) -> WorkspaceMember | None:
        """
        Update member status.

        Args:
            session: Database session.
            member_id: Member ID.
            status: New status.
            commit_self: Whether to commit the transaction.

        Returns:
            Updated member or None if not found.
        """
        return await self.update(
            session,
            member_id,
            {"status": status},
            commit_self=commit_self,
        )

    async def disable_all_members(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        except_owner: bool = False,
        commit_self: bool = True,
    ) -> int:
        """
        Disable all members in a workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            except_owner: Keep owner enabled.
            commit_self: Whether to commit the transaction.

        Returns:
            Number of members disabled.
        """
        conditions = [
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.is_deleted.is_(False),
        ]
        if except_owner:
            conditions.append(WorkspaceMember.role != MemberRole.OWNER)

        return await self.update_by_conditions(
            session,
            conditions,
            {"status": MemberStatus.DISABLED},
            commit_self=commit_self,
        )

    async def is_user_member(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Check if user is a member of workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            user_id: User ID.

        Returns:
            True if user is a member.
        """
        return await self.exists(
            session,
            {"workspace_id": workspace_id, "user_id": user_id, "is_deleted": False},
        )


class WorkspaceInvitationDB(BaseDB[WorkspaceInvitation]):
    """CRUD operations for WorkspaceInvitation model."""

    def __init__(self):
        super().__init__(WorkspaceInvitation)

    async def get_by_token_hash(
        self,
        session: AsyncSession,
        token_hash: str,
    ) -> WorkspaceInvitation | None:
        """
        Get invitation by token hash.

        Args:
            session: Database session.
            token_hash: HMAC hash of the invitation token.

        Returns:
            Invitation or None if not found.
        """
        return await self.get_one_by_filters(
            session,
            {"token_hash": token_hash, "is_deleted": False},
            options=[
                selectinload(WorkspaceInvitation.workspace),
                selectinload(WorkspaceInvitation.inviter),
            ],
        )

    async def get_pending_invitation(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        email: str,
    ) -> WorkspaceInvitation | None:
        """
        Get pending invitation for email in workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            email: Invitee email.

        Returns:
            Pending invitation or None if not found.
        """
        return await self.get_one_by_filters(
            session,
            {
                "workspace_id": workspace_id,
                "email": email.lower(),
                "status": InvitationStatus.PENDING,
                "is_deleted": False,
            },
        )

    async def get_workspace_invitations(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        status: InvitationStatus | None = None,
    ) -> Sequence[WorkspaceInvitation]:
        """
        Get all invitations for a workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            status: Optional filter by status.

        Returns:
            List of invitations.
        """
        filters: dict = {"workspace_id": workspace_id, "is_deleted": False}
        if status:
            filters["status"] = status
        return await self.get_by_filters(
            session,
            filters,
            options=[selectinload(WorkspaceInvitation.inviter)],
        )

    async def get_user_pending_invitations(
        self,
        session: AsyncSession,
        email: str,
    ) -> Sequence[WorkspaceInvitation]:
        """
        Get all pending invitations for an email.

        Args:
            session: Database session.
            email: User email.

        Returns:
            List of pending invitations.
        """
        now = datetime.now(timezone.utc)
        conditions = [
            WorkspaceInvitation.email == email.lower(),
            WorkspaceInvitation.status == InvitationStatus.PENDING,
            WorkspaceInvitation.expires_at > now,
            WorkspaceInvitation.is_deleted.is_(False),
        ]
        return await self.get_by_conditions(
            session,
            conditions,
            options=[
                selectinload(WorkspaceInvitation.workspace),
                selectinload(WorkspaceInvitation.inviter),
            ],
        )

    async def expire_old_invitations(
        self,
        session: AsyncSession,
        commit_self: bool = True,
    ) -> int:
        """
        Mark expired invitations as expired.

        Args:
            session: Database session.
            commit_self: Whether to commit the transaction.

        Returns:
            Number of invitations expired.
        """
        now = datetime.now(timezone.utc)
        conditions: list[SQLColumnExpression[Any]] = [
            WorkspaceInvitation.status == InvitationStatus.PENDING,
            WorkspaceInvitation.expires_at <= now,
        ]
        return await self.update_by_conditions(
            session,
            conditions,
            {"status": InvitationStatus.EXPIRED},
            commit_self=commit_self,
        )

    async def revoke_invitation(
        self,
        session: AsyncSession,
        invitation_id: UUID,
        commit_self: bool = True,
    ) -> WorkspaceInvitation | None:
        """
        Revoke a pending invitation.

        Args:
            session: Database session.
            invitation_id: Invitation ID.
            commit_self: Whether to commit the transaction.

        Returns:
            Updated invitation or None if not found.
        """
        return await self.update(
            session,
            invitation_id,
            {"status": InvitationStatus.REVOKED},
            commit_self=commit_self,
        )


# Global CRUD instances
workspace_db = WorkspaceDB()
workspace_member_db = WorkspaceMemberDB()
workspace_invitation_db = WorkspaceInvitationDB()


__all__ = [
    "WorkspaceDB",
    "WorkspaceMemberDB",
    "WorkspaceInvitationDB",
    "workspace_db",
    "workspace_member_db",
    "workspace_invitation_db",
    "slugify",
]
