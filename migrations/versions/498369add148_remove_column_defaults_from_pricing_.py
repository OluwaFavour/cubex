"""remove_column_defaults_from_pricing_models

Revision ID: 498369add148
Revises: d77c282ab61b
Create Date: 2026-02-27 13:35:40.512005

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "498369add148"
down_revision: Union[str, Sequence[str], None] = "d77c282ab61b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop server_default on rate_limit_per_minute (was default=20)
    op.alter_column(
        "plan_pricing_rules",
        "rate_limit_per_minute",
        existing_type=sa.INTEGER(),
        comment="Maximum API requests allowed per minute (None = unlimited)",
        existing_comment="Maximum API requests allowed per minute",
        existing_nullable=True,
        server_default=None,
    )
    op.alter_column(
        "plan_pricing_rules",
        "rate_limit_per_day",
        existing_type=sa.INTEGER(),
        comment="Maximum API requests allowed per day (None = unlimited)",
        existing_comment="Maximum API requests allowed per day",
        existing_nullable=True,
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "plan_pricing_rules",
        "rate_limit_per_day",
        existing_type=sa.INTEGER(),
        comment="Maximum API requests allowed per day",
        existing_comment="Maximum API requests allowed per day (None = unlimited)",
        existing_nullable=True,
    )
    op.alter_column(
        "plan_pricing_rules",
        "rate_limit_per_minute",
        existing_type=sa.INTEGER(),
        comment="Maximum API requests allowed per minute",
        existing_comment="Maximum API requests allowed per minute (None = unlimited)",
        existing_nullable=True,
        server_default=sa.text("20"),
    )
    # ### end Alembic commands ###
