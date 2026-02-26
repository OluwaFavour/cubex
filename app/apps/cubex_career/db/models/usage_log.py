"""
Career usage log model.

This module provides the CareerUsageLog model for tracking per-user
usage of career product features. It mirrors the API UsageLog but
scopes to users instead of workspaces/API keys.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.models.base import BaseModel
from app.core.enums import (
    FailureType,
    FeatureKey,
    UsageLogStatus,
)

if TYPE_CHECKING:
    from app.core.db.models.subscription import Subscription
    from app.core.db.models.user import User


class CareerUsageLog(BaseModel):
    """
    Model for Career usage logs.

    Tracks each feature usage event for quota management and billing.
    Usage logs are IMMUTABLE - once created, only the status field
    can be updated via the commit endpoint. This ensures audit trail integrity.

    Note: Quota tracking is per-user (via CareerSubscriptionContext).
    Users access career features via JWT auth through an AI tool server.

    Idempotency:
        Uses user_id + request_id + fingerprint_hash for true idempotency.
        - Same user + request_id + fingerprint_hash = return existing record
        - Same request_id + different fingerprint = create new record
        - Different user = always independent (user isolation)

    Status lifecycle:
        PENDING -> SUCCESS (request completed successfully)
        PENDING -> FAILED (request failed, does not count toward quota)
        PENDING -> EXPIRED (pending too long, expired by scheduler)

    Attributes:
        user_id: Foreign key to the user.
        subscription_id: Foreign key to the subscription (denormalized for queries).
        request_id: Globally unique request ID for idempotency.
        feature_key: The key of feature being used.
        fingerprint_hash: Hash of endpoint+method+payload_hash+usage_estimate.
        access_status: The access decision (GRANTED/DENIED) for this request.
        endpoint: The API endpoint path being called.
        method: HTTP method (GET, POST, etc.).
        client_ip: Optional client IP address.
        client_user_agent: Optional client user agent string.
        usage_estimate: JSON field storing usage estimation data.
        credits_reserved: The billable cost in credits.
        credits_charged: Actual credits charged on commit.
        status: Current status of this usage log entry.
        committed_at: When the status changed from PENDING.
    """

    __tablename__ = "career_usage_logs"
    __table_args__ = (
        Index("ix_career_usage_logs_user_created", "user_id", "created_at"),
        Index(
            "ix_career_usage_logs_subscription_created",
            "subscription_id",
            "created_at",
        ),
        Index("ix_career_usage_logs_status", "status"),
        Index("ix_career_usage_logs_endpoint", "endpoint"),
        Index("ix_career_usage_logs_feature_key", "feature_key"),
        Index(
            "ix_career_usage_logs_request_fingerprint_user",
            "request_id",
            "fingerprint_hash",
            "user_id",
            unique=True,
        ),
        {"comment": "Immutable usage log. Only status/committed_at can be updated."},
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who made this request",
    )

    subscription_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Denormalized for efficient subscription-level queries",
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

    feature_key: Mapped[FeatureKey] = mapped_column(
        Enum(FeatureKey, native_enum=False, name="feature_key"),
        nullable=False,
        index=True,
        comment="Feature Key (e.g., 'career.career_path')",
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
        Numeric(12, 2),
        nullable=False,
        comment="The billable cost in credits",
    )

    credits_charged: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Actual credits charged on commit (null for pending/failed)",
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
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
    )

    subscription: Mapped["Subscription"] = relationship(
        "Subscription",
        foreign_keys=[subscription_id],
    )


__all__ = ["CareerUsageLog"]
