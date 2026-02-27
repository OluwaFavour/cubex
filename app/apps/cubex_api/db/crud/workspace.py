"""
CRUD operations for Workspace models.

"""

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import SQLColumnExpression, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.db.crud.base import BaseDB
from app.apps.cubex_api.db.models.workspace import (
    APIKey,
    UsageLog,
    Workspace,
    WorkspaceMember,
    WorkspaceInvitation,
)
from app.core.db.models.subscription_context import APISubscriptionContext
from app.core.enums import (
    InvitationStatus,
    MemberRole,
    MemberStatus,
    UsageLogStatus,
    WorkspaceStatus,
)
from app.core.exceptions.types import DatabaseException


def slugify(text: str) -> str:
    """
    Convert text to URL-friendly slug.

    Args:
        text: Text to slugify.

    Returns:
        URL-friendly slug (lowercase, alphanumeric + hyphens).
    """
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
            .options(
                selectinload(Workspace.members),
                selectinload(Workspace.api_subscription_context).selectinload(
                    APISubscriptionContext.subscription
                ),
            )
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


class APIKeyDB(BaseDB[APIKey]):
    """CRUD operations for APIKey model."""

    def __init__(self):
        super().__init__(APIKey)

    async def get_by_key_hash(
        self,
        session: AsyncSession,
        key_hash: str,
    ) -> APIKey | None:
        """
        Get API key by its hash.

        Args:
            session: Database session.
            key_hash: HMAC-SHA256 hash of the API key.

        Returns:
            APIKey or None if not found.
        """
        return await self.get_one_by_filters(
            session,
            {"key_hash": key_hash, "is_deleted": False},
            options=[selectinload(APIKey.workspace)],
        )

    async def get_active_by_hash(
        self,
        session: AsyncSession,
        key_hash: str,
    ) -> APIKey | None:
        """
        Get active API key by its hash.

        Checks that the key is active, not deleted, not expired, and not revoked.

        Args:
            session: Database session.
            key_hash: HMAC-SHA256 hash of the API key.

        Returns:
            APIKey or None if not found or not usable.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(APIKey)
            .where(
                and_(
                    APIKey.key_hash == key_hash,
                    APIKey.is_deleted.is_(False),
                    APIKey.is_active.is_(True),
                    APIKey.revoked_at.is_(None),
                    (APIKey.expires_at.is_(None) | (APIKey.expires_at > now)),
                )
            )
            .options(
                # Eagerly load workspace -> api_subscription_context -> subscription
                # This avoids N+1 queries when accessing workspace.subscription
                selectinload(APIKey.workspace)
                .selectinload(Workspace.api_subscription_context)
                .selectinload(APISubscriptionContext.subscription)
            )
        )

        try:
            result = await session.execute(stmt)
            return result.scalars().first()
        except Exception as e:
            raise DatabaseException(
                f"Error getting active API key by hash: {str(e)}"
            ) from e

    async def get_by_workspace(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        include_inactive: bool = False,
    ) -> Sequence[APIKey]:
        """
        Get all API keys for a workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            include_inactive: Include inactive/revoked keys.

        Returns:
            List of API keys.
        """
        filters: dict[str, Any] = {
            "workspace_id": workspace_id,
            "is_deleted": False,
        }
        if not include_inactive:
            filters["is_active"] = True

        return await self.get_by_filters(session, filters)

    async def update_last_used(
        self,
        session: AsyncSession,
        api_key_id: UUID,
        commit_self: bool = True,
    ) -> APIKey | None:
        """
        Update the last_used_at timestamp for an API key.

        Args:
            session: Database session.
            api_key_id: API key ID.
            commit_self: Whether to commit the transaction.

        Returns:
            Updated API key or None if not found.
        """
        return await self.update(
            session,
            api_key_id,
            {"last_used_at": datetime.now(timezone.utc)},
            commit_self=commit_self,
        )

    async def revoke(
        self,
        session: AsyncSession,
        api_key_id: UUID,
        commit_self: bool = True,
    ) -> APIKey | None:
        """
        Revoke an API key.

        Args:
            session: Database session.
            api_key_id: API key ID.
            commit_self: Whether to commit the transaction.

        Returns:
            Updated API key or None if not found.
        """
        return await self.update(
            session,
            api_key_id,
            {
                "is_active": False,
                "revoked_at": datetime.now(timezone.utc),
            },
            commit_self=commit_self,
        )


class UsageLogDB(BaseDB[UsageLog]):
    """
    CRUD operations for UsageLog model.

    Note: UsageLog records are immutable after creation.
    Only the status/committed_at fields can be updated via commit().
    """

    def __init__(self):
        super().__init__(UsageLog)

    async def get_by_request_id(
        self,
        session: AsyncSession,
        request_id: str,
    ) -> UsageLog | None:
        """
        Get a usage log by its request_id.

        Used for idempotency - if the same request_id is seen again,
        return the existing log instead of creating a new one.

        Args:
            session: Database session.
            request_id: The globally unique request ID.

        Returns:
            UsageLog if found, None otherwise.
        """
        return await self.get_one_by_conditions(
            session=session,
            conditions=[self.model.request_id == request_id],
        )

    async def get_by_request_id_and_fingerprint(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        request_id: str,
        fingerprint_hash: str,
    ) -> UsageLog | None:
        """
        Get a usage log by workspace_id, request_id, and fingerprint_hash.

        Used for true idempotency with workspace isolation:
        - Same workspace + request_id + fingerprint_hash = return existing record
        - Different fingerprint = different request payload, create new record
        - Different workspace = always independent (workspace isolation)

        Args:
            session: Database session.
            workspace_id: The workspace UUID for isolation.
            request_id: The globally unique request ID.
            fingerprint_hash: Hash of request characteristics.

        Returns:
            UsageLog if found with matching criteria, None otherwise.
        """
        return await self.get_one_by_conditions(
            session=session,
            conditions=[
                self.model.workspace_id == workspace_id,
                self.model.request_id == request_id,
                self.model.fingerprint_hash == fingerprint_hash,
            ],
        )

    async def get_by_workspace(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        status_filter: list[UsageLogStatus] | None = None,
        limit: int = 100,
    ) -> Sequence[UsageLog]:
        """
        Get usage logs for a workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            status_filter: Only include logs with these statuses. If None, includes all.
            limit: Maximum number of logs to return.

        Returns:
            List of usage logs, ordered by created_at descending.
        """
        conditions: list[SQLColumnExpression[bool]] = [
            UsageLog.workspace_id == workspace_id,
            UsageLog.is_deleted.is_(False),
        ]
        if status_filter is not None:
            conditions.append(UsageLog.status.in_(status_filter))

        stmt = (
            select(UsageLog)
            .where(and_(*conditions))
            .order_by(UsageLog.created_at.desc())
            .limit(limit)
        )

        try:
            result = await session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            raise DatabaseException(
                f"Error getting usage logs for workspace {workspace_id}: {str(e)}"
            ) from e

    async def get_by_api_key(
        self,
        session: AsyncSession,
        api_key_id: UUID,
        status_filter: list[UsageLogStatus] | None = None,
        limit: int = 100,
    ) -> Sequence[UsageLog]:
        """
        Get usage logs for an API key.

        Args:
            session: Database session.
            api_key_id: API key ID.
            status_filter: Only include logs with these statuses. If None, includes all.
            limit: Maximum number of logs to return.

        Returns:
            List of usage logs, ordered by created_at descending.
        """
        conditions: list[SQLColumnExpression[bool]] = [
            UsageLog.api_key_id == api_key_id,
            UsageLog.is_deleted.is_(False),
        ]
        if status_filter is not None:
            conditions.append(UsageLog.status.in_(status_filter))

        stmt = (
            select(UsageLog)
            .where(and_(*conditions))
            .order_by(UsageLog.created_at.desc())
            .limit(limit)
        )

        try:
            result = await session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            raise DatabaseException(
                f"Error getting usage logs for API key {api_key_id}: {str(e)}"
            ) from e

    async def commit(
        self,
        session: AsyncSession,
        usage_log_id: UUID,
        success: bool,
        metrics: dict | None = None,
        failure: dict | None = None,
        commit_self: bool = True,
    ) -> UsageLog | None:
        """
        Commit a pending usage log (idempotent).

        Args:
            session: Database session.
            usage_log_id: Usage log ID.
            success: True for SUCCESS status, False for FAILED status.
            metrics: Optional metrics dict with keys: model_used, input_tokens,
                     output_tokens, latency_ms.
            failure: Optional failure dict with keys: failure_type, reason.
            commit_self: Whether to commit the transaction.

        Returns:
            Updated usage log or None if not found.
        """
        existing = await self.get_by_id(session, usage_log_id)
        if existing is None or existing.is_deleted:
            return None

        # Already committed, return as-is (idempotent)
        if existing.status != UsageLogStatus.PENDING:
            return existing

        new_status = UsageLogStatus.SUCCESS if success else UsageLogStatus.FAILED
        update_data: dict = {
            "status": new_status,
            "committed_at": datetime.now(timezone.utc),
        }

        # Set credits_charged on success (actual credits consumed)
        if success:
            update_data["credits_charged"] = existing.credits_reserved

        # Add metrics if provided
        if metrics:
            if metrics.get("model_used") is not None:
                update_data["model_used"] = metrics["model_used"]
            if metrics.get("input_tokens") is not None:
                update_data["input_tokens"] = metrics["input_tokens"]
            if metrics.get("output_tokens") is not None:
                update_data["output_tokens"] = metrics["output_tokens"]
            if metrics.get("latency_ms") is not None:
                update_data["latency_ms"] = metrics["latency_ms"]

        # Add failure info if provided
        if failure:
            if failure.get("failure_type") is not None:
                update_data["failure_type"] = failure["failure_type"]
            if failure.get("reason") is not None:
                update_data["failure_reason"] = failure["reason"]

        return await self.update(
            session,
            usage_log_id,
            update_data,
            commit_self=commit_self,
        )

    async def expire_pending(
        self,
        session: AsyncSession,
        older_than: datetime,
        commit_self: bool = True,
    ) -> int:
        """
        Expire pending usage logs older than the given cutoff.

        Args:
            session: Database session.
            older_than: Expire logs created before this time.
            commit_self: Whether to commit the transaction.

        Returns:
            Number of logs expired.
        """
        from sqlalchemy import update

        stmt = (
            update(UsageLog)
            .where(
                UsageLog.status == UsageLogStatus.PENDING,
                UsageLog.created_at < older_than,
                UsageLog.is_deleted.is_(False),
            )
            .values(
                status=UsageLogStatus.EXPIRED,
                committed_at=datetime.now(timezone.utc),
            )
        )
        result = await session.execute(stmt)

        if commit_self:
            await session.commit()

        return result.rowcount  # type: ignore[return-value]

    async def sum_credits_for_period(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> Decimal:
        """
        Sum credits_reserved for SUCCESS usage logs within a billing period.

        This is used for quota checking - only successfully completed
        requests count toward the usage quota.

        Args:
            session: Database session.
            workspace_id: The workspace to sum usage for.
            period_start: Start of the billing period (inclusive).
            period_end: End of the billing period (exclusive).

        Returns:
            Total credits used in the period, or Decimal("0") if none.
        """

        stmt = select(
            func.coalesce(func.sum(UsageLog.credits_reserved), Decimal("0"))
        ).where(
            UsageLog.workspace_id == workspace_id,
            UsageLog.status == UsageLogStatus.SUCCESS,
            UsageLog.created_at >= period_start,
            UsageLog.created_at < period_end,
            UsageLog.is_deleted.is_(False),
        )

        try:
            result = await session.execute(stmt)
            return result.scalar_one()
        except Exception as e:
            raise DatabaseException(
                f"Error summing credits for workspace {workspace_id}: {str(e)}"
            ) from e


# Global CRUD instances
workspace_db = WorkspaceDB()
workspace_member_db = WorkspaceMemberDB()
workspace_invitation_db = WorkspaceInvitationDB()
api_key_db = APIKeyDB()
usage_log_db = UsageLogDB()


__all__ = [
    "WorkspaceDB",
    "WorkspaceMemberDB",
    "WorkspaceInvitationDB",
    "APIKeyDB",
    "UsageLogDB",
    "workspace_db",
    "workspace_member_db",
    "workspace_invitation_db",
    "api_key_db",
    "usage_log_db",
    "slugify",
]

