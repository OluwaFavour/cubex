"""
Career analysis result model.

Stores AI analysis responses for user-facing history.
Linked 1:1 to a CareerUsageLog (only successful analyses produce results).

"""

from typing import Any, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Enum,
    ForeignKey,
    Index,
    JSON,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.models.base import BaseModel
from app.core.enums import FeatureKey

if TYPE_CHECKING:
    from app.apps.cubex_career.db.models.usage_log import CareerUsageLog
    from app.core.db.models.user import User


class CareerAnalysisResult(BaseModel):
    """
    Stores the structured JSON response from a successful career analysis.

    Each result is linked 1:1 to a CareerUsageLog record. Only successful
    analyses (status=SUCCESS) produce a result. The user_id and feature_key
    are denormalized from the usage log for efficient querying without joins.

    Attributes:
        usage_log_id: FK to the CareerUsageLog that produced this result.
        user_id: FK to the user who requested the analysis (denormalized).
        feature_key: The career feature used (denormalized).
        title: User-facing label for the analysis (auto-generated from feature_key).
        result_data: The structured JSON analysis response from the AI tool.
    """

    __tablename__ = "career_analysis_results"
    __table_args__ = (
        Index(
            "ix_career_analysis_results_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_career_analysis_results_user_feature",
            "user_id",
            "feature_key",
        ),
    )

    usage_log_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("career_usage_logs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    feature_key: Mapped[FeatureKey] = mapped_column(
        Enum(FeatureKey, native_enum=False, name="feature_key"),
        nullable=False,
    )

    title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="User-facing label for this analysis",
    )

    result_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="Structured JSON analysis response from the AI tool",
    )

    # Relationships
    usage_log: Mapped["CareerUsageLog"] = relationship(
        "CareerUsageLog",
        foreign_keys=[usage_log_id],
    )

    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
    )

    def __repr__(self) -> str:
        return (
            f"<CareerAnalysisResult(id={self.id}, "
            f"user_id={self.user_id}, "
            f"feature_key={self.feature_key})>"
        )


__all__ = ["CareerAnalysisResult"]
