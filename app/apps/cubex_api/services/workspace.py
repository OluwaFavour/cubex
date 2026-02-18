"""
Workspace service for cubex_api.

This module provides business logic for workspace management including
creating workspaces, managing members, and handling invitations.
"""

from decimal import Decimal
import secrets
from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_api.db.crud import (
    workspace_db,
    workspace_member_db,
    workspace_invitation_db,
)
from app.apps.cubex_api.db.models import (
    Workspace,
    WorkspaceMember,
    WorkspaceInvitation,
)
from app.apps.cubex_api.services.quota_cache import QuotaCacheService
from app.core.config import settings, workspace_logger
from app.core.db.crud import (
    api_subscription_context_db,
    plan_db,
    subscription_db,
    user_db,
)
from app.core.db.models import User, Subscription, Plan
from app.core.enums import (
    InvitationStatus,
    MemberRole,
    MemberStatus,
    ProductType,
    SubscriptionStatus,
    WorkspaceStatus,
)
from app.core.exceptions.types import (
    AppException,
    ConflictException,
    NotFoundException,
)
from app.core.utils import hmac_hash_otp
from app.infrastructure.messaging.publisher import publish_event


# ============================================================================
# Exceptions
# ============================================================================


class WorkspaceNotFoundException(NotFoundException):
    """Raised when workspace is not found."""

    def __init__(self, message: str = "Workspace not found."):
        super().__init__(message)


class WorkspaceFrozenException(AppException):
    """Raised when workspace is frozen."""

    def __init__(
        self, message: str = "Workspace is frozen. Please renew subscription."
    ):
        super().__init__(message, status_code=403)


class InsufficientSeatsException(AppException):
    """Raised when there are not enough seats available."""

    def __init__(self, message: str = "Not enough seats available."):
        super().__init__(message, status_code=402)


class MemberNotFoundException(NotFoundException):
    """Raised when workspace member is not found."""

    def __init__(self, message: str = "Member not found."):
        super().__init__(message)


class InvitationNotFoundException(NotFoundException):
    """Raised when invitation is not found."""

    def __init__(self, message: str = "Invitation not found or expired."):
        super().__init__(message)


class InvitationAlreadyExistsException(ConflictException):
    """Raised when invitation already exists."""

    def __init__(self, message: str = "Invitation already pending for this email."):
        super().__init__(message)


class MemberAlreadyExistsException(ConflictException):
    """Raised when user is already a member."""

    def __init__(self, message: str = "User is already a member of this workspace."):
        super().__init__(message)


class CannotInviteOwnerException(AppException):
    """Raised when trying to invite the workspace owner."""

    def __init__(self, message: str = "Cannot invite the workspace owner."):
        super().__init__(message, status_code=400)


class PermissionDeniedException(AppException):
    """Raised when user lacks permission."""

    def __init__(self, message: str = "Permission denied."):
        super().__init__(message, status_code=403)


class FreeWorkspaceNoInvitesException(AppException):
    """Raised when trying to invite to a free workspace."""

    def __init__(
        self, message: str = "Free workspaces cannot have additional members."
    ):
        super().__init__(message, status_code=402)


# ============================================================================
# Service
# ============================================================================


class WorkspaceService:
    """Service for workspace management."""

    # Default invitation expiry (7 days)
    INVITATION_EXPIRY_DAYS = 7

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _generate_workspace_identity(
        self,
        session: AsyncSession,
        user: User,
    ) -> tuple[str, str]:
        """
        Generate display name and slug for a personal workspace.

        Args:
            session: Database session.
            user: User to generate identity for.

        Returns:
            Tuple of (display_name, slug).
        """
        base_name = user.full_name or user.email.split("@")[0]
        display_name = f"{base_name}'s Workspace"
        slug = await workspace_db.generate_unique_slug(session, base_name)
        return display_name, slug

    async def _get_required_free_plan(
        self,
        session: AsyncSession,
        product_type: ProductType,
    ) -> Plan:
        """
        Get the free plan for a product type.

        Args:
            session: Database session.
            product_type: Product type to get free plan for.

        Returns:
            Free plan.

        Raises:
            ValueError: If free plan not found (seeding issue).
        """
        free_plan = await plan_db.get_free_plan(session, product_type=product_type)
        if not free_plan:
            raise ValueError(
                f"Free plan not found for {product_type.value}. "
                "Ensure plans are seeded."
            )
        return free_plan

    def _generate_secure_token(self) -> tuple[str, str]:
        """
        Generate a secure token and its hash.

        Returns:
            Tuple of (raw_token, token_hash).
        """
        raw_token = secrets.token_urlsafe(32)
        token_hash = hmac_hash_otp(raw_token, settings.OTP_HMAC_SECRET)
        return raw_token, token_hash

    async def _get_invitation_by_token(
        self,
        session: AsyncSession,
        token: str,
    ) -> WorkspaceInvitation | None:
        """
        Find an invitation by its raw token.

        Args:
            session: Database session.
            token: Raw invitation token.

        Returns:
            Invitation if found, None otherwise.
        """
        token_hash = hmac_hash_otp(token, settings.OTP_HMAC_SECRET)
        return await workspace_invitation_db.get_by_token_hash(session, token_hash)

    async def _check_email_not_member(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        email: str,
    ) -> None:
        """
        Check that an email is not already a member of the workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            email: Email to check.

        Raises:
            MemberAlreadyExistsException: If user is already a member.
        """
        existing_user = await user_db.get_one_by_filters(session, {"email": email})
        if existing_user:
            is_member = await workspace_member_db.is_user_member(
                session, workspace_id, existing_user.id
            )
            if is_member:
                raise MemberAlreadyExistsException()

    async def _check_email_not_owner(
        self,
        session: AsyncSession,
        owner_id: UUID,
        email: str,
    ) -> None:
        """
        Check that an email is not the workspace owner's email.

        Args:
            session: Database session.
            owner_id: Owner user ID.
            email: Email to check.

        Raises:
            CannotInviteOwnerException: If email belongs to owner.
        """
        owner = await user_db.get_by_id(session, owner_id)
        if owner and owner.email.lower() == email:
            raise CannotInviteOwnerException()

    async def _require_admin_member(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        user_id: UUID,
        error_message: str = "Only admins can perform this action.",
    ) -> WorkspaceMember:
        """
        Get a member and verify they have admin privileges.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            user_id: User ID to check.
            error_message: Custom error message.

        Returns:
            The admin member.

        Raises:
            PermissionDeniedException: If user is not an admin.
        """
        member = await workspace_member_db.get_member(session, workspace_id, user_id)
        if not member or not member.is_admin:
            raise PermissionDeniedException(error_message)
        return member

    async def _require_owner_member(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        user_id: UUID,
        error_message: str = "Only owner can perform this action.",
    ) -> WorkspaceMember:
        """
        Get a member and verify they are the owner.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            user_id: User ID to check.
            error_message: Custom error message.

        Returns:
            The owner member.

        Raises:
            PermissionDeniedException: If user is not the owner.
        """
        member = await workspace_member_db.get_member(session, workspace_id, user_id)
        if not member or not member.is_owner:
            raise PermissionDeniedException(error_message)
        return member

    async def _mark_invitation_accepted(
        self,
        session: AsyncSession,
        invitation_id: UUID,
        user_id: UUID,
    ) -> None:
        """
        Mark an invitation as accepted.

        Args:
            session: Database session.
            invitation_id: Invitation ID.
            user_id: User who accepted.
        """
        await workspace_invitation_db.update(
            session,
            invitation_id,
            {
                "status": InvitationStatus.ACCEPTED,
                "accepted_at": datetime.now(timezone.utc),
                "accepted_by_id": user_id,
            },
            commit_self=False,
        )

    def _calculate_invitation_expiry(self) -> datetime:
        """
        Calculate the expiration datetime for an invitation.

        Returns:
            Expiration datetime.
        """
        return datetime.now(timezone.utc) + timedelta(days=self.INVITATION_EXPIRY_DAYS)

    # ========================================================================
    # Public Methods
    # ========================================================================

    async def create_personal_workspace(
        self,
        session: AsyncSession,
        user: User,
        commit_self: bool = True,
    ) -> tuple[Workspace, WorkspaceMember, Subscription]:
        """
        Create a personal workspace for a user with free plan.

        This is called automatically on user signup. Idempotent - returns
        existing workspace if one already exists.

        Args:
            session: Database session.
            user: User to create workspace for.
            commit_self: Whether to commit the transaction.

        Returns:
            Tuple of (workspace, member, subscription).
        """
        # Check if user already has a personal workspace (idempotent)
        existing_workspace = await workspace_db.get_personal_workspace(session, user.id)
        if existing_workspace:
            # Get the owner member
            owner_member = next(
                (m for m in existing_workspace.members if m.is_owner), None
            )
            if not owner_member:
                raise ValueError(
                    f"Personal workspace {existing_workspace.id} has no owner member"
                )

            # Get the subscription
            existing_sub = await subscription_db.get_by_workspace(
                session, existing_workspace.id, active_only=False
            )
            if not existing_sub:
                raise ValueError(
                    f"Personal workspace {existing_workspace.id} has no subscription"
                )

            workspace_logger.debug(
                f"Personal workspace already exists for user {user.id}"
            )
            return existing_workspace, owner_member, existing_sub

        # Generate workspace identity
        display_name, slug = await self._generate_workspace_identity(session, user)

        # Create workspace
        workspace = await workspace_db.create(
            session,
            {
                "display_name": display_name,
                "slug": slug,
                "owner_id": user.id,
                "status": WorkspaceStatus.ACTIVE,
                "is_personal": True,
            },
            commit_self=False,
        )

        # Add owner as member
        member = await workspace_member_db.create(
            session,
            {
                "workspace_id": workspace.id,
                "user_id": user.id,
                "role": MemberRole.OWNER,
                "status": MemberStatus.ENABLED,
                "joined_at": datetime.now(timezone.utc),
            },
            commit_self=False,
        )

        # Get free plan for API product (must exist - seeded in migrations)
        free_plan = await self._get_required_free_plan(session, ProductType.API)

        # Create subscription (free plan, no Stripe)
        subscription = await subscription_db.create(
            session,
            {
                "plan_id": free_plan.id,
                "product_type": ProductType.API,
                "status": SubscriptionStatus.ACTIVE,
                "seat_count": 1,
            },
            commit_self=False,
        )

        # Create API subscription context to link subscription to workspace
        await api_subscription_context_db.create(
            session,
            {
                "subscription_id": subscription.id,
                "workspace_id": workspace.id,
            },
            commit_self=False,
        )

        if commit_self:
            await session.commit()
        else:
            await session.flush()
        await session.refresh(workspace)
        await session.refresh(member)
        await session.refresh(subscription)

        workspace_logger.info(
            f"Personal workspace created: {workspace.id} for user {user.id}"
        )

        return workspace, member, subscription

    async def create_workspace(
        self,
        session: AsyncSession,
        owner: User,
        display_name: str,
        description: str | None = None,
        commit_self: bool = True,
    ) -> Workspace:
        """
        Create a new non-personal workspace.

        Note: This creates the workspace only. Subscription must be
        set up separately via checkout.

        Args:
            session: Database session.
            owner: Workspace owner.
            display_name: Workspace display name.
            description: Optional description.
            commit_self: Whether to commit the transaction.

        Returns:
            Created workspace.
        """
        slug = await workspace_db.generate_unique_slug(session, display_name)

        workspace = await workspace_db.create(
            session,
            {
                "display_name": display_name,
                "slug": slug,
                "owner_id": owner.id,
                "status": WorkspaceStatus.ACTIVE,
                "is_personal": False,
                "description": description,
            },
            commit_self=False,
        )

        # Add owner as member
        await workspace_member_db.create(
            session,
            {
                "workspace_id": workspace.id,
                "user_id": owner.id,
                "role": MemberRole.OWNER,
                "status": MemberStatus.ENABLED,
                "joined_at": datetime.now(timezone.utc),
            },
            commit_self=False,
        )

        if commit_self:
            await session.commit()
        else:
            await session.flush()
        await session.refresh(workspace)

        workspace_logger.info(f"Workspace created: {workspace.id} by user {owner.id}")

        return workspace

    async def get_workspace(
        self,
        session: AsyncSession,
        workspace_id: UUID,
    ) -> Workspace:
        """
        Get workspace by ID.

        Args:
            session: Database session.
            workspace_id: Workspace ID.

        Returns:
            Workspace.

        Raises:
            WorkspaceNotFoundException: If workspace not found.
        """
        workspace = await workspace_db.get_by_id(session, workspace_id)
        if not workspace or workspace.is_deleted:
            raise WorkspaceNotFoundException()
        return workspace

    async def get_workspace_by_slug(
        self,
        session: AsyncSession,
        slug: str,
    ) -> Workspace:
        """
        Get workspace by slug.

        Args:
            session: Database session.
            slug: Workspace slug.

        Returns:
            Workspace.

        Raises:
            WorkspaceNotFoundException: If workspace not found.
        """
        workspace = await workspace_db.get_by_slug(session, slug)
        if not workspace:
            raise WorkspaceNotFoundException()
        return workspace

    async def get_user_workspaces(
        self,
        session: AsyncSession,
        user_id: UUID,
        role: MemberRole | None = None,
    ) -> Sequence[Workspace]:
        """
        Get all workspaces a user has access to.

        Args:
            session: Database session.
            user_id: User ID.
            role: Optional filter by user's role in the workspace.

        Returns:
            List of workspaces.
        """
        return await workspace_db.get_user_workspaces(session, user_id, role=role)

    async def update_workspace(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        user_id: UUID,
        display_name: str | None = None,
        slug: str | None = None,
        description: str | None = None,
        commit_self: bool = True,
    ) -> Workspace:
        """
        Update workspace details.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            user_id: User making the update.
            display_name: New display name.
            slug: New slug (must be unique).
            description: New description.
            commit_self: Whether to commit the transaction.

        Returns:
            Updated workspace.

        Raises:
            WorkspaceNotFoundException: If workspace not found.
            PermissionDeniedException: If user lacks permission.
            ConflictException: If slug already exists.
        """
        workspace = await self.get_workspace(session, workspace_id)
        await self._require_admin_member(
            session, workspace_id, user_id, "Only admins can update workspace settings."
        )

        updates = {}
        if display_name is not None:
            updates["display_name"] = display_name
        if description is not None:
            updates["description"] = description
        if slug is not None:
            # Validate slug uniqueness
            existing = await workspace_db.get_by_slug(session, slug)
            if existing and existing.id != workspace_id:
                raise ConflictException("Slug already in use.")
            updates["slug"] = slug

        if updates:
            workspace = await workspace_db.update(
                session, workspace_id, updates, commit_self=commit_self
            )

        return workspace  # type: ignore

    async def get_available_seats(
        self,
        session: AsyncSession,
        workspace_id: UUID,
    ) -> int:
        """
        Get number of available seats in workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.

        Returns:
            Number of available seats (can be negative if over limit).
        """
        subscription = await subscription_db.get_by_workspace(session, workspace_id)
        if not subscription:
            return 0

        enabled_count = await workspace_member_db.get_enabled_member_count(
            session, workspace_id
        )
        return subscription.seat_count - enabled_count

    async def get_credits_consumed(
        self,
        session: AsyncSession,
        workspace_id: UUID,
    ) -> Decimal:
        """
        Get total credits consumed in current billing period for workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.

        Returns:
            Total credits consumed as Decimal.
        """
        context = await api_subscription_context_db.get_by_workspace(
            session, workspace_id
        )
        if not context:
            return Decimal("0.00")
        return context.credits_used

    async def get_credits_limit(
        self,
        session: AsyncSession,
        workspace_id: UUID,
    ) -> Decimal:
        """
        Get total credits limit for workspace based on subscription plan.

        Args:
            session: Database session.
            workspace_id: Workspace ID.

        Returns:
            Total credits limit as Decimal.
        """
        subscription = await subscription_db.get_by_workspace(session, workspace_id)
        if not subscription:
            return Decimal("0.00")
        credits_limit = (
            await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session, subscription.plan_id
            )
        )
        return credits_limit

    async def _check_can_add_member(
        self,
        session: AsyncSession,
        workspace: Workspace,
    ) -> None:
        """
        Check if a new member can be added to workspace.

        Args:
            session: Database session.
            workspace: Workspace to check.

        Raises:
            WorkspaceFrozenException: If workspace is frozen.
            FreeWorkspaceNoInvitesException: If workspace is free.
            InsufficientSeatsException: If no seats available.
        """
        if workspace.is_frozen:
            raise WorkspaceFrozenException()

        subscription = await subscription_db.get_by_workspace(session, workspace.id)
        if not subscription:
            raise InsufficientSeatsException("No active subscription.")

        # Check if free plan
        plan = subscription.plan
        if plan.is_free:
            raise FreeWorkspaceNoInvitesException()

        # Check seat availability
        available_seats = await self.get_available_seats(session, workspace.id)
        if available_seats <= 0:
            raise InsufficientSeatsException(
                f"No seats available. Current: {subscription.seat_count} seats."
            )

    async def invite_member(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        inviter_id: UUID,
        email: str,
        callback_url: str,
        role: MemberRole = MemberRole.MEMBER,
        commit_self: bool = True,
    ) -> tuple[WorkspaceInvitation, str]:
        """
        Invite a user to join the workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            inviter_id: User sending the invitation.
            email: Email to invite.
            callback_url: Frontend URL for accepting the invitation.
            role: Role to assign (cannot be OWNER).
            commit_self: Whether to commit the transaction.

        Returns:
            Tuple of (invitation, raw_token).

        Raises:
            WorkspaceNotFoundException: If workspace not found.
            PermissionDeniedException: If inviter lacks permission.
            CannotInviteOwnerException: If trying to invite as owner or invite owner's email.
            MemberAlreadyExistsException: If user is already a member.
            InvitationAlreadyExistsException: If pending invitation exists.
            InsufficientSeatsException: If no seats available.
        """
        email = email.lower()

        # Get workspace
        workspace = await self.get_workspace(session, workspace_id)

        # Check inviter permission
        await self._require_admin_member(
            session, workspace_id, inviter_id, "Only admins can invite members."
        )

        # Cannot assign owner role via invitation
        if role == MemberRole.OWNER:
            raise CannotInviteOwnerException("Cannot invite with owner role.")

        # Check if email is owner's email
        await self._check_email_not_owner(session, workspace.owner_id, email)

        # Check if already a member
        await self._check_email_not_member(session, workspace_id, email)

        # Check if pending invitation exists
        existing_invitation = await workspace_invitation_db.get_pending_invitation(
            session, workspace_id, email
        )
        if existing_invitation:
            raise InvitationAlreadyExistsException()

        # Check seat availability
        await self._check_can_add_member(session, workspace)

        # Generate secure token
        raw_token, token_hash = self._generate_secure_token()

        # Create invitation
        invitation = await workspace_invitation_db.create(
            session,
            {
                "workspace_id": workspace_id,
                "inviter_id": inviter_id,
                "email": email,
                "role": role,
                "token_hash": token_hash,
                "status": InvitationStatus.PENDING,
                "expires_at": self._calculate_invitation_expiry(),
            },
            commit_self=commit_self,
        )

        # Queue invitation email
        inviter = await user_db.get_by_id(session, inviter_id)
        inviter_name = inviter.full_name if inviter else "A team member"
        invitation_link = f"{callback_url}?token={raw_token}"

        await publish_event(
            "workspace_invitation_emails",
            {
                "email": email,
                "inviter_name": inviter_name,
                "workspace_name": workspace.display_name,
                "role": role.value.title(),  # e.g., "Member", "Admin"
                "invitation_link": invitation_link,
                "expiry_hours": self.INVITATION_EXPIRY_DAYS * 24,
            },
        )

        workspace_logger.info(
            f"Invitation sent to {email} for workspace {workspace_id} by {inviter_id}"
        )

        return invitation, raw_token

    async def accept_invitation(
        self,
        session: AsyncSession,
        token: str,
        user: User,
        commit_self: bool = True,
    ) -> WorkspaceMember:
        """
        Accept a workspace invitation.

        Args:
            session: Database session.
            token: Invitation token.
            user: User accepting the invitation.
            commit_self: Whether to commit the transaction.

        Returns:
            Created workspace member.

        Raises:
            InvitationNotFoundException: If invitation not found or expired.
            MemberAlreadyExistsException: If user is already a member.
            InsufficientSeatsException: If no seats available.
        """
        # Find invitation by token hash
        invitation = await self._get_invitation_by_token(session, token)

        if not invitation:
            raise InvitationNotFoundException()

        # Check if expired
        if invitation.is_expired or invitation.status != InvitationStatus.PENDING:
            raise InvitationNotFoundException()

        # Check if current user is the owner of the invitation
        if user.email.lower() != invitation.email.lower():
            raise InvitationNotFoundException()

        # Check if already a member
        is_member = await workspace_member_db.is_user_member(
            session, invitation.workspace_id, user.id
        )
        if is_member:
            raise MemberAlreadyExistsException()

        # Check seat availability
        workspace = await self.get_workspace(session, invitation.workspace_id)
        await self._check_can_add_member(session, workspace)

        # Create member
        member = await workspace_member_db.create(
            session,
            {
                "workspace_id": invitation.workspace_id,
                "user_id": user.id,
                "role": invitation.role,
                "status": MemberStatus.ENABLED,
                "joined_at": datetime.now(timezone.utc),
            },
            commit_self=False,
        )

        # Mark invitation as accepted
        await self._mark_invitation_accepted(session, invitation.id, user.id)

        if commit_self:
            await session.commit()
        else:
            await session.flush()
        await session.refresh(member)

        workspace_logger.info(
            f"User {user.id} accepted invitation and joined workspace {invitation.workspace_id}"
        )

        return member

    async def accept_invitations_for_email(
        self,
        session: AsyncSession,
        user: User,
        commit_self: bool = True,
    ) -> list[WorkspaceMember]:
        """
        Accept all pending invitations for a user's email.

        Called after user signup to auto-join workspaces they were invited to.

        Args:
            session: Database session.
            user: User who just signed up.
            commit_self: Whether to commit the transaction.

        Returns:
            List of created memberships.
        """
        invitations = await workspace_invitation_db.get_user_pending_invitations(
            session, user.email
        )

        members = []
        for invitation in invitations:
            try:
                # Check seat availability
                workspace = await workspace_db.get_by_id(
                    session, invitation.workspace_id
                )
                if not workspace or workspace.is_frozen:
                    continue

                subscription = await subscription_db.get_by_workspace(
                    session, invitation.workspace_id
                )
                if not subscription or not subscription.is_active:
                    continue

                available_seats = await self.get_available_seats(
                    session, invitation.workspace_id
                )
                if available_seats <= 0:
                    continue

                # Create member
                member = await workspace_member_db.create(
                    session,
                    {
                        "workspace_id": invitation.workspace_id,
                        "user_id": user.id,
                        "role": invitation.role,
                        "status": MemberStatus.ENABLED,
                        "joined_at": datetime.now(timezone.utc),
                    },
                    commit_self=False,
                )

                # Mark invitation as accepted
                await self._mark_invitation_accepted(session, invitation.id, user.id)

                members.append(member)

            except Exception:
                # Skip failed invitations silently
                continue

        if members:
            if commit_self:
                await session.commit()
            else:
                await session.flush()
            for member in members:
                await session.refresh(member)

        workspace_logger.info(
            f"User {user.id} auto-joined {len(members)} workspaces via email invitations"
        )

        return members

    async def revoke_invitation(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        invitation_id: UUID,
        user_id: UUID,
        commit_self: bool = True,
    ) -> WorkspaceInvitation:
        """
        Revoke a pending invitation.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            invitation_id: Invitation ID.
            user_id: User revoking.
            commit_self: Whether to commit the transaction.

        Returns:
            Revoked invitation.

        Raises:
            PermissionDeniedException: If user lacks permission.
            InvitationNotFoundException: If invitation not found.
        """
        # Check permission
        await self._require_admin_member(
            session, workspace_id, user_id, "Only admins can revoke invitations."
        )

        invitation = await workspace_invitation_db.get_by_id(session, invitation_id)
        if (
            not invitation
            or invitation.workspace_id != workspace_id
            or invitation.status != InvitationStatus.PENDING
        ):
            raise InvitationNotFoundException()

        invitation = await workspace_invitation_db.revoke_invitation(
            session, invitation_id, commit_self=commit_self
        )

        workspace_logger.info(f"Invitation {invitation_id} revoked by user {user_id}")

        return invitation  # type: ignore

    async def update_member_status(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        member_user_id: UUID,
        admin_user_id: UUID,
        status: MemberStatus,
        commit_self: bool = True,
    ) -> WorkspaceMember:
        """
        Enable or disable a workspace member.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            member_user_id: User ID of member to update.
            admin_user_id: User ID of admin making the change.
            status: New status.
            commit_self: Whether to commit the transaction.

        Returns:
            Updated member.

        Raises:
            PermissionDeniedException: If user lacks permission.
            MemberNotFoundException: If member not found.
            InsufficientSeatsException: If enabling would exceed seats.
        """
        # Check admin permission
        await self._require_admin_member(
            session, workspace_id, admin_user_id, "Only admins can manage members."
        )

        # Get target member
        target_member = await workspace_member_db.get_member(
            session, workspace_id, member_user_id
        )
        if not target_member:
            raise MemberNotFoundException()

        # Cannot disable owner
        if target_member.is_owner and status == MemberStatus.DISABLED:
            raise PermissionDeniedException("Cannot disable workspace owner.")

        # Check seat availability when enabling
        if (
            status == MemberStatus.ENABLED
            and target_member.status == MemberStatus.DISABLED
        ):
            subscription = await subscription_db.get_by_workspace(session, workspace_id)
            if subscription:
                enabled_count = await workspace_member_db.get_enabled_member_count(
                    session, workspace_id
                )
                if enabled_count >= subscription.seat_count:
                    raise InsufficientSeatsException()

        target_member = await workspace_member_db.update_status(
            session, target_member.id, status, commit_self=commit_self
        )

        workspace_logger.info(
            f"Member {member_user_id} status updated to {status.value} "
            f"in workspace {workspace_id} by {admin_user_id}"
        )

        return target_member  # type: ignore

    async def update_member_role(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        member_user_id: UUID,
        admin_user_id: UUID,
        role: MemberRole,
        commit_self: bool = True,
    ) -> WorkspaceMember:
        """
        Update a member's role.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            member_user_id: User ID of member to update.
            admin_user_id: User ID of admin making the change.
            role: New role (cannot be OWNER).
            commit_self: Whether to commit the transaction.

        Returns:
            Updated member.

        Raises:
            PermissionDeniedException: If user lacks permission.
            MemberNotFoundException: If member not found.
        """
        # Only owner can change roles
        await self._require_owner_member(
            session, workspace_id, admin_user_id, "Only owner can change member roles."
        )

        target_member = await workspace_member_db.get_member(
            session, workspace_id, member_user_id
        )
        if not target_member:
            raise MemberNotFoundException()

        # Cannot change owner's role
        if target_member.is_owner:
            raise PermissionDeniedException("Cannot change owner's role.")

        # Cannot assign owner role
        if role == MemberRole.OWNER:
            raise PermissionDeniedException("Use transfer_ownership to change owner.")

        target_member = await workspace_member_db.update(
            session, target_member.id, {"role": role}, commit_self=commit_self
        )

        workspace_logger.info(
            f"Member {member_user_id} role updated to {role.value} "
            f"in workspace {workspace_id} by {admin_user_id}"
        )

        return target_member  # type: ignore

    async def remove_member(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        member_user_id: UUID,
        admin_user_id: UUID,
        commit_self: bool = True,
    ) -> bool:
        """
        Remove a member from workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            member_user_id: User ID of member to remove.
            admin_user_id: User ID of admin making the change.
            commit_self: Whether to commit the transaction.

        Returns:
            True if removed.

        Raises:
            PermissionDeniedException: If user lacks permission or trying to remove owner.
            MemberNotFoundException: If member not found.
        """
        # Check admin permission
        await self._require_admin_member(
            session, workspace_id, admin_user_id, "Only admins can remove members."
        )

        target_member = await workspace_member_db.get_member(
            session, workspace_id, member_user_id
        )
        if not target_member:
            raise MemberNotFoundException()

        # Cannot remove owner
        if target_member.is_owner:
            raise PermissionDeniedException("Cannot remove workspace owner.")

        await workspace_member_db.delete(
            session, target_member.id, commit_self=commit_self
        )

        workspace_logger.info(
            f"Member {member_user_id} removed from workspace {workspace_id} by {admin_user_id}"
        )

        return True

    async def leave_workspace(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        user_id: UUID,
        commit_self: bool = True,
    ) -> bool:
        """
        Leave a workspace (self-removal).

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            user_id: User leaving.
            commit_self: Whether to commit the transaction.

        Returns:
            True if left.

        Raises:
            PermissionDeniedException: If owner trying to leave.
            MemberNotFoundException: If not a member.
        """
        member = await workspace_member_db.get_member(session, workspace_id, user_id)
        if not member:
            raise MemberNotFoundException()

        if member.is_owner:
            raise PermissionDeniedException(
                "Owner cannot leave. Transfer ownership first."
            )

        await workspace_member_db.delete(session, member.id, commit_self=commit_self)

        workspace_logger.info(f"User {user_id} left workspace {workspace_id}")

        return True

    async def transfer_ownership(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        current_owner_id: UUID,
        new_owner_id: UUID,
        commit_self: bool = True,
    ) -> Workspace:
        """
        Transfer workspace ownership.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            current_owner_id: Current owner's user ID.
            new_owner_id: New owner's user ID.
            commit_self: Whether to commit the transaction.

        Returns:
            Updated workspace.

        Raises:
            PermissionDeniedException: If not current owner.
            MemberNotFoundException: If new owner is not a member.
        """
        workspace = await self.get_workspace(session, workspace_id)

        if workspace.owner_id != current_owner_id:
            raise PermissionDeniedException("Only owner can transfer ownership.")

        # Check new owner is a member
        new_owner_member = await workspace_member_db.get_member(
            session, workspace_id, new_owner_id
        )
        if not new_owner_member:
            raise MemberNotFoundException("New owner must be a workspace member.")

        # Update current owner's role to admin
        current_owner_member = await workspace_member_db.get_member(
            session, workspace_id, current_owner_id
        )
        if current_owner_member:
            await workspace_member_db.update(
                session,
                current_owner_member.id,
                {"role": MemberRole.ADMIN},
                commit_self=False,
            )

        # Update new owner's role
        await workspace_member_db.update(
            session,
            new_owner_member.id,
            {"role": MemberRole.OWNER, "status": MemberStatus.ENABLED},
            commit_self=False,
        )

        # Update workspace owner_id
        workspace = await workspace_db.update(
            session,
            workspace_id,
            {"owner_id": new_owner_id},
            commit_self=False,
        )

        if commit_self:
            await session.commit()
        else:
            await session.flush()
        await session.refresh(workspace)

        workspace_logger.info(
            f"Ownership transferred in workspace {workspace_id} "
            f"from {current_owner_id} to {new_owner_id}"
        )

        return workspace  # type: ignore


# Global service instance
workspace_service = WorkspaceService()


__all__ = [
    "WorkspaceService",
    "workspace_service",
    # Exceptions
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
