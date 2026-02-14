"""Replace reverted with status enum for usage logs

Revision ID: 1c3bb63c6b57
Revises: f4dba42a4be4
Create Date: 2026-02-11 18:48:44.263071

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1c3bb63c6b57"
down_revision: Union[str, Sequence[str], None] = "f4dba42a4be4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Create enum type for use in both upgrade and downgrade
usagelogstatus_enum = postgresql.ENUM(
    "PENDING", "SUCCESS", "FAILED", "EXPIRED", name="usagelogstatus", create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    # Create the enum type first
    usagelogstatus_enum.create(op.get_bind(), checkfirst=True)

    # Add status column with server_default to allow existing rows
    op.add_column(
        "usage_logs",
        sa.Column(
            "status",
            sa.Enum("PENDING", "SUCCESS", "FAILED", "EXPIRED", name="usagelogstatus"),
            nullable=False,
            server_default="PENDING",
            comment="Status of this usage log entry",
        ),
    )

    # Add committed_at column
    op.add_column(
        "usage_logs",
        sa.Column(
            "committed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the status changed from PENDING",
        ),
    )

    # Migrate existing data: reverted=True -> FAILED, reverted=False -> SUCCESS
    # (treat old logs as already committed)
    op.execute(
        """
        UPDATE usage_logs
        SET status = CASE
            WHEN reverted = true THEN 'FAILED'::usagelogstatus
            ELSE 'SUCCESS'::usagelogstatus
        END,
        committed_at = COALESCE(reverted_at, created_at)
    """
    )

    # Remove the server_default (new logs should use model default)
    op.alter_column("usage_logs", "status", server_default=None)

    # Create new index and drop old one
    op.drop_index(op.f("ix_usage_logs_reverted"), table_name="usage_logs")
    op.create_index("ix_usage_logs_status", "usage_logs", ["status"], unique=False)

    # Update table comment
    op.create_table_comment(
        "usage_logs",
        "Immutable usage log. Only status/committed_at can be updated.",
        existing_comment="Immutable usage log. Only reverted/reverted_at can be updated.",
        schema=None,
    )

    # Drop old columns
    op.drop_column("usage_logs", "reverted")
    op.drop_column("usage_logs", "reverted_at")


def downgrade() -> None:
    """Downgrade schema."""
    # Add back old columns with defaults
    op.add_column(
        "usage_logs",
        sa.Column(
            "reverted_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
            comment="When the usage was reverted",
        ),
    )
    op.add_column(
        "usage_logs",
        sa.Column(
            "reverted",
            sa.BOOLEAN(),
            autoincrement=False,
            nullable=False,
            server_default="false",
            comment="Whether this usage has been reverted/refunded",
        ),
    )

    # Migrate data back: FAILED -> reverted=True, others -> reverted=False
    op.execute(
        """
        UPDATE usage_logs
        SET reverted = (status = 'FAILED'),
            reverted_at = CASE WHEN status = 'FAILED' THEN committed_at ELSE NULL END
    """
    )

    # Remove server_default
    op.alter_column("usage_logs", "reverted", server_default=None)

    # Update table comment
    op.create_table_comment(
        "usage_logs",
        "Immutable usage log. Only reverted/reverted_at can be updated.",
        existing_comment="Immutable usage log. Only status/committed_at can be updated.",
        schema=None,
    )

    # Recreate old index and drop new one
    op.drop_index("ix_usage_logs_status", table_name="usage_logs")
    op.create_index(
        op.f("ix_usage_logs_reverted"), "usage_logs", ["reverted"], unique=False
    )

    # Drop new columns
    op.drop_column("usage_logs", "committed_at")
    op.drop_column("usage_logs", "status")

    # Drop the enum type
    usagelogstatus_enum.drop(op.get_bind(), checkfirst=True)
