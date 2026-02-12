"""
Workspace models for cubex_api.

This module provides models for workspace management including
workspaces, members, invitations, API keys, and usage logs.
These models are designed to support the core functionality of
cubex_api, including team collaboration, access control, and billing.
The models use SQLAlchemy ORM and are structured to ensure data
integrity, efficient queries, and clear relationships between entities.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db.models.base import BaseModel
from app.shared.enums import (
    FailureType,
    InvitationStatus,
    MemberRole,
    MemberStatus,
    UsageLogStatus,
    WorkspaceStatus,
)

if TYPE_CHECKING:
    from app.shared.db.models.user import User
    from app.shared.db.models.subscription import Subscription
    from app.shared.db.models.subscription_context import APISubscriptionContext


class Workspace(BaseModel):
    """
    Model for workspaces (billing and access boundary).

    A workspace is the primary unit for billing and team collaboration.
    Each user gets a personal workspace on signup. Paid workspaces can
    have multiple members with seat-based billing.

    Attributes:
        display_name: Human-readable workspace name.
        slug: URL-friendly unique identifier (prefixed for uniqueness).
        owner_id: Foreign key to the workspace owner.
        status: Workspace status (active, frozen, suspended).
        is_personal: Whether this is a personal workspace (auto-created).
        description: Optional workspace description.
    """

    __tablename__ = "workspaces"

    display_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
        comment="URL-friendly identifier (e.g., 'ws-john-doe-1')",
    )

    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            comment="Delete workspace when owner is deleted",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[WorkspaceStatus] = mapped_column(
        Enum(WorkspaceStatus, native_enum=False, name="workspace_status"),
        nullable=False,
        index=True,
        default=WorkspaceStatus.ACTIVE,
    )

    is_personal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Personal workspaces are auto-created and cannot be deleted",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    owner: Mapped["User"] = relationship(
        "User",
        foreign_keys=[owner_id],
        lazy="selectin",
    )

    members: Mapped[list["WorkspaceMember"]] = relationship(
        "WorkspaceMember",
        back_populates="workspace",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    invitations: Mapped[list["WorkspaceInvitation"]] = relationship(
        "WorkspaceInvitation",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )

    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )

    usage_logs: Mapped[list["UsageLog"]] = relationship(
        "UsageLog",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )

    # Subscription context relationship (one-to-one)
    api_subscription_context: Mapped["APISubscriptionContext | None"] = relationship(
        "APISubscriptionContext",
        back_populates="workspace",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # Association proxy for convenient access: workspace.subscription
    subscription: AssociationProxy["Subscription | None"] = association_proxy(
        "api_subscription_context",
        "subscription",
    )

    __table_args__ = (
        UniqueConstraint("slug", name="uq_workspaces_slug"),
        Index("ix_workspaces_owner_personal", "owner_id", "is_personal"),
    )

    def __str__(self) -> str:
        return f"{self.display_name} ({self.slug})"

    @property
    def is_active(self) -> bool:
        """Check if workspace is active."""
        return self.status == WorkspaceStatus.ACTIVE

    @property
    def is_frozen(self) -> bool:
        """Check if workspace is frozen (subscription expired)."""
        return self.status == WorkspaceStatus.FROZEN

    @property
    def enabled_member_count(self) -> int:
        """Count of enabled members (consuming seats)."""
        return sum(1 for m in self.members if m.status == MemberStatus.ENABLED)


class WorkspaceMember(BaseModel):
    """
    Model for workspace membership.

    Tracks user membership in workspaces with role and status.
    Enabled members consume seats; disabled members retain access
    configuration but cannot access the workspace.

    Attributes:
        workspace_id: Foreign key to the workspace.
        user_id: Foreign key to the user.
        role: Member role (owner, admin, member).
        status: Member status (enabled, disabled).
        joined_at: When the user joined the workspace.
    """

    __tablename__ = "workspace_members"

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            ondelete="CASCADE",
            comment="Delete membership when workspace is deleted",
        ),
        nullable=False,
        index=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            comment="Delete membership when user is deleted",
        ),
        nullable=False,
        index=True,
    )

    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, native_enum=False, name="member_role"),
        nullable=False,
        default=MemberRole.MEMBER,
    )

    status: Mapped[MemberStatus] = mapped_column(
        Enum(MemberStatus, native_enum=False, name="member_status"),
        nullable=False,
        index=True,
        default=MemberStatus.ENABLED,
    )

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="members",
    )

    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_members_workspace_user",
        ),
        Index("ix_workspace_members_user_status", "user_id", "status"),
        Index("ix_workspace_members_workspace_status", "workspace_id", "status"),
    )

    @property
    def is_owner(self) -> bool:
        """Check if member is workspace owner."""
        return self.role == MemberRole.OWNER

    @property
    def is_admin(self) -> bool:
        """Check if member has admin privileges."""
        return self.role in (MemberRole.OWNER, MemberRole.ADMIN)

    @property
    def is_enabled(self) -> bool:
        """Check if member is enabled (has access)."""
        return self.status == MemberStatus.ENABLED

    @property
    def consumes_seat(self) -> bool:
        """Check if member consumes a seat."""
        return self.status == MemberStatus.ENABLED


class WorkspaceInvitation(BaseModel):
    """
    Model for workspace invitations.

    Tracks pending and accepted invitations to workspaces.
    Invitations use URL-safe tokens for secure acceptance.

    Attributes:
        workspace_id: Foreign key to the workspace.
        inviter_id: Foreign key to the user who sent the invitation.
        email: Email address of the invitee.
        role: Role to assign when invitation is accepted.
        token_hash: HMAC hash of the invitation token.
        status: Invitation status (pending, accepted, expired, revoked).
        expires_at: When the invitation expires.
        accepted_at: When the invitation was accepted.
        accepted_by_id: User who accepted (may differ from invited email).
    """

    __tablename__ = "workspace_invitations"

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            ondelete="CASCADE",
            comment="Delete invitation when workspace is deleted",
        ),
        nullable=False,
        index=True,
    )

    inviter_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            comment="Keep invitation if inviter is deleted",
        ),
        nullable=True,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, native_enum=False, name="member_role"),
        nullable=False,
        default=MemberRole.MEMBER,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="HMAC-SHA256 hash of invitation token",
    )

    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, native_enum=False, name="invitation_status"),
        nullable=False,
        index=True,
        default=InvitationStatus.PENDING,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    accepted_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            comment="User who accepted the invitation",
        ),
        nullable=True,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="invitations",
    )

    inviter: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[inviter_id],
    )

    accepted_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[accepted_by_id],
    )

    __table_args__ = (
        Index(
            "ix_workspace_invitations_workspace_email_pending",
            "workspace_id",
            "email",
            postgresql_where="status = 'pending'",
        ),
        Index("ix_workspace_invitations_token_hash", "token_hash"),
    )

    @property
    def is_pending(self) -> bool:
        """Check if invitation is pending."""
        return self.status == InvitationStatus.PENDING

    @property
    def is_expired(self) -> bool:
        """Check if invitation has expired."""
        if self.status == InvitationStatus.EXPIRED:
            return True

        return datetime.now(timezone.utc) > self.expires_at


class APIKey(BaseModel):
    """
    Model for API keys used by external developer APIs.

    API keys authenticate requests to external APIs and are tied to workspaces.
    Each key has a unique HMAC-SHA256 hash stored for secure lookup. The raw key
    is only shown once upon creation and cannot be retrieved afterwards.

    Key format: cbx_live_{random_token}
    Display format: cbx_live_xxxxx***...*** (prefix + first 5 chars of token)

    Attributes:
        workspace_id: Foreign key to the workspace owning this key.
        name: User-defined label for the key.
        key_hash: HMAC-SHA256 hash of the full API key for lookup.
        key_prefix: First portion of key for display (cbx_live_ + 5 chars).
        expires_at: When the key expires (null = never).
        revoked_at: When the key was revoked (null = not revoked).
        is_active: Whether the key is active and usable.
        last_used_at: Last time the key was used.
        scopes: Optional JSON field for future permission scopes.
    """

    __tablename__ = "api_keys"

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="User-defined label for the API key",
    )

    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        unique=True,
        comment="HMAC-SHA256 hash of the API key for secure lookup",
    )

    key_prefix: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Display prefix: cbx_live_ + first 5 chars of token",
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the key expires (null = never expires)",
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the key was revoked (null = not revoked)",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether the key is active and can be used",
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time the key was used for a request",
    )

    scopes: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Optional permission scopes for future use",
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="api_keys",
    )

    usage_logs: Mapped[list["UsageLog"]] = relationship(
        "UsageLog",
        back_populates="api_key",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_api_keys_workspace_active", "workspace_id", "is_active"),
    )

    @property
    def is_expired(self) -> bool:
        """Check if API key has expired."""
        if self.expires_at is None:
            return False

        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_revoked(self) -> bool:
        """Check if API key has been revoked."""
        return self.revoked_at is not None

    @property
    def is_usable(self) -> bool:
        """Check if API key can be used (active, not expired, not revoked)."""
        return self.is_active and not self.is_expired and not self.is_revoked

    def get_masked_display(self) -> str:
        """Get masked display version of the key for UI."""
        return f"{self.key_prefix}***...***"


class UsageLog(BaseModel):
    """
    Model for API usage logs.

    Tracks each API usage event for quota management and billing.
    Usage logs are IMMUTABLE - once created, only the status field
    can be updated via the commit endpoint. This ensures audit trail integrity.

    Note: Quota tracking is per-workspace (via APISubscriptionContext),
    not per-key. Multiple API keys share the workspace's quota.

    Idempotency:
        Uses workspace_id + request_id + fingerprint_hash for true idempotency.
        - Same workspace + request_id + fingerprint_hash = return existing record
        - Same request_id + different fingerprint = create new record
        - Different workspace = always independent (workspace isolation)

    Status lifecycle:
        PENDING -> SUCCESS (request completed successfully)
        PENDING -> FAILED (request failed, does not count toward quota)
        PENDING -> EXPIRED (pending too long, expired by scheduler)

    Attributes:
        api_key_id: Foreign key to the API key used.
        workspace_id: Foreign key to the workspace (denormalized for efficient queries).
        request_id: Globally unique request ID for idempotency.
        fingerprint_hash: Hash of endpoint+method+payload_hash+usage_estimate.
        access_status: The access decision (GRANTED/DENIED) for this request.
        endpoint: The API endpoint path being called.
        method: HTTP method (GET, POST, etc.).
        client_ip: Optional client IP address.
        client_user_agent: Optional client user agent string.
        usage_estimate: JSON field storing usage estimation data.
        credits_reserved: The billable cost in credits.
        status: Current status of this usage log entry.
        committed_at: When the status changed from PENDING.
    """

    __tablename__ = "usage_logs"
    __table_args__ = (
        Index("ix_usage_logs_workspace_created", "workspace_id", "created_at"),
        Index("ix_usage_logs_api_key_created", "api_key_id", "created_at"),
        Index("ix_usage_logs_status", "status"),
        Index("ix_usage_logs_endpoint", "endpoint"),
        Index(
            "ix_usage_logs_request_fingerprint_workspace",
            "request_id",
            "fingerprint_hash",
            "workspace_id",
            unique=True,
        ),
        {"comment": "Immutable usage log. Only status/committed_at can be updated."},
    )

    api_key_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Denormalized for efficient workspace-level quota queries",
    )

    request_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
        comment="Globally unique request ID for idempotency",
    )

    fingerprint_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Hash of endpoint+method+payload_hash+usage_estimate for idempotency",
    )

    access_status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Access decision: 'granted' or 'denied'",
    )

    endpoint: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="The API endpoint path being called",
    )

    method: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="HTTP method (GET, POST, etc.)",
    )

    client_ip: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="Optional client IP address",
    )

    client_user_agent: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="Optional client user agent string",
    )

    usage_estimate: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Usage estimation data (input_chars, max_output_tokens, model)",
    )

    credits_reserved: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        comment="The billable cost in credits",
    )

    status: Mapped[UsageLogStatus] = mapped_column(
        Enum(UsageLogStatus),
        nullable=False,
        default=UsageLogStatus.PENDING,
        comment="Status of this usage log entry",
    )

    committed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the status changed from PENDING",
    )

    # Metrics fields (populated on commit for successful requests)
    model_used: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Model identifier used (e.g., 'gpt-4o')",
    )

    input_tokens: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Actual input tokens used",
    )

    output_tokens: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Actual output tokens generated",
    )

    latency_ms: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Request latency in milliseconds",
    )

    # Failure tracking fields (populated on commit for failed requests)
    failure_type: Mapped[FailureType | None] = mapped_column(
        Enum(FailureType, native_enum=False, name="failure_type"),
        nullable=True,
        index=True,
        comment="Category of failure when status=FAILED",
    )

    failure_reason: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Human-readable failure description",
    )

    # Relationships
    api_key: Mapped["APIKey"] = relationship(
        "APIKey",
        back_populates="usage_logs",
    )

    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="usage_logs",
    )


__all__ = ["Workspace", "WorkspaceMember", "WorkspaceInvitation", "APIKey", "UsageLog"]
