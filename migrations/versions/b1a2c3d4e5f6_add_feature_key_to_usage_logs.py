"""add_feature_key_to_usage_logs

Revision ID: b1a2c3d4e5f6
Revises: 967d49c9390e
Create Date: 2026-02-23 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1a2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "967d49c9390e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add feature_key column to usage_logs table."""
    op.add_column(
        "usage_logs",
        sa.Column(
            "feature_key",
            sa.Enum(
                "API_CAREER_PATH",
                "API_EXTRACT_KEYWORDS",
                "API_FEEDBACK_ANALYZER",
                "API_GENERATE_FEEDBACK",
                "API_JOB_MATCH",
                "API_EXTRACT_CUES_RESUME",
                "API_EXTRACT_CUES_FEEDBACK",
                "API_EXTRACT_CUES_INTERVIEW",
                "API_EXTRACT_CUES_ASSESSMENT",
                "API_REFRAME_FEEDBACK",
                "CAREER_CAREER_PATH",
                "CAREER_EXTRACT_KEYWORDS",
                "CAREER_FEEDBACK_ANALYZER",
                "CAREER_GENERATE_FEEDBACK",
                "CAREER_JOB_MATCH",
                "CAREER_EXTRACT_CUES_RESUME",
                "CAREER_EXTRACT_CUES_FEEDBACK",
                "CAREER_EXTRACT_CUES_INTERVIEW",
                "CAREER_EXTRACT_CUES_ASSESSMENT",
                "CAREER_REFRAME_FEEDBACK",
                name="feature_key",
                native_enum=False,
            ),
            nullable=True,
            comment="Feature Key (e.g., 'api.analyze')",
        ),
    )
    # Backfill existing rows: set a default feature key based on endpoint
    # For existing data, we'll set a sensible default so we can make it NOT NULL
    op.execute(
        "UPDATE usage_logs SET feature_key = 'API_EXTRACT_CUES_RESUME' WHERE feature_key IS NULL"
    )
    # Now make the column NOT NULL
    op.alter_column("usage_logs", "feature_key", nullable=False)
    # Add the index
    op.create_index(
        "ix_usage_logs_feature_key", "usage_logs", ["feature_key"], unique=False
    )


def downgrade() -> None:
    """Remove feature_key column from usage_logs table."""
    op.drop_index("ix_usage_logs_feature_key", table_name="usage_logs")
    op.drop_column("usage_logs", "feature_key")
