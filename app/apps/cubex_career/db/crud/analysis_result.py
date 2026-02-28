"""
CRUD operations for Career analysis result model.

"""

from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.db.crud.base import BaseDB
from app.apps.cubex_career.db.models.analysis_result import CareerAnalysisResult
from app.core.enums import FeatureKey
from app.core.exceptions.types import DatabaseException

# Human-readable titles for career features
_FEATURE_TITLES: dict[FeatureKey, str] = {
    FeatureKey.CAREER_CAREER_PATH: "Career Path Analysis",
    FeatureKey.CAREER_EXTRACT_KEYWORDS: "Keyword Extraction",
    FeatureKey.CAREER_FEEDBACK_ANALYZER: "Feedback Analysis",
    FeatureKey.CAREER_GENERATE_FEEDBACK: "Feedback Generation",
    FeatureKey.CAREER_JOB_MATCH: "Job Match Analysis",
    FeatureKey.CAREER_EXTRACT_CUES_RESUME: "Resume Cue Extraction",
    FeatureKey.CAREER_EXTRACT_CUES_FEEDBACK: "Feedback Cue Extraction",
    FeatureKey.CAREER_EXTRACT_CUES_INTERVIEW: "Interview Cue Extraction",
    FeatureKey.CAREER_EXTRACT_CUES_ASSESSMENT: "Assessment Cue Extraction",
    FeatureKey.CAREER_REFRAME_FEEDBACK: "Feedback Reframing",
}


def _default_title(feature_key: FeatureKey) -> str:
    """Generate a default user-facing title from a feature key."""
    return _FEATURE_TITLES.get(
        feature_key,
        feature_key.value.replace("career.", "").replace("_", " ").title(),
    )


class CareerAnalysisResultDB(BaseDB[CareerAnalysisResult]):
    """
    CRUD operations for CareerAnalysisResult model.

    Provides history listing, ownership lookups, and
    creation from successful usage commits.
    """

    def __init__(self):
        super().__init__(CareerAnalysisResult)

    async def create_from_commit(
        self,
        session: AsyncSession,
        usage_log_id: UUID,
        user_id: UUID,
        feature_key: FeatureKey,
        result_data: dict[str, Any],
        title: str | None = None,
        commit_self: bool = True,
    ) -> CareerAnalysisResult:
        """
        Create an analysis result record from a successful commit.

        Args:
            session: Database session.
            usage_log_id: The usage log this result belongs to.
            user_id: The user who requested the analysis.
            feature_key: The career feature used.
            result_data: The structured JSON analysis response.
            title: Optional user-facing title (auto-generated if omitted).
            commit_self: Whether to commit the transaction.

        Returns:
            The created CareerAnalysisResult.
        """
        return await self.create(
            session,
            data={
                "usage_log_id": usage_log_id,
                "user_id": user_id,
                "feature_key": feature_key,
                "title": title or _default_title(feature_key),
                "result_data": result_data,
            },
            commit_self=commit_self,
        )

    async def get_by_usage_log_id(
        self,
        session: AsyncSession,
        usage_log_id: UUID,
    ) -> CareerAnalysisResult | None:
        """
        Get an analysis result by its usage log ID.

        Args:
            session: Database session.
            usage_log_id: The usage log ID to look up.

        Returns:
            The analysis result or None if not found.
        """
        stmt = select(CareerAnalysisResult).where(
            and_(
                CareerAnalysisResult.usage_log_id == usage_log_id,
                CareerAnalysisResult.is_deleted.is_(False),
            )
        )
        try:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            raise DatabaseException(
                f"Error getting analysis result for usage log {usage_log_id}: {e}"
            ) from e

    async def get_user_result(
        self,
        session: AsyncSession,
        result_id: UUID,
        user_id: UUID,
    ) -> CareerAnalysisResult | None:
        """
        Get a single analysis result with ownership check.

        Args:
            session: Database session.
            result_id: The analysis result ID.
            user_id: The user ID to verify ownership.

        Returns:
            The analysis result if found and owned by user, else None.
        """
        stmt = select(CareerAnalysisResult).where(
            and_(
                CareerAnalysisResult.id == result_id,
                CareerAnalysisResult.user_id == user_id,
                CareerAnalysisResult.is_deleted.is_(False),
            )
        )
        try:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            raise DatabaseException(
                f"Error getting analysis result {result_id}: {e}"
            ) from e

    async def list_by_user(
        self,
        session: AsyncSession,
        user_id: UUID,
        feature_key: FeatureKey | None = None,
        limit: int = 20,
        before_id: UUID | None = None,
    ) -> Sequence[CareerAnalysisResult]:
        """
        List analysis results for a user with cursor-based pagination.

        Results are ordered by created_at DESC. Use ``before_id`` to
        fetch the next page (pass the last result's ID from the previous page).

        Args:
            session: Database session.
            user_id: The user ID to list results for.
            feature_key: Optional filter by feature key.
            limit: Maximum number of results to return.
            before_id: Cursor — return results created before this ID's record.

        Returns:
            List of analysis results, newest first.
        """
        conditions: list[Any] = [
            CareerAnalysisResult.user_id == user_id,
            CareerAnalysisResult.is_deleted.is_(False),
        ]

        if feature_key is not None:
            conditions.append(CareerAnalysisResult.feature_key == feature_key)

        if before_id is not None:
            # Subquery to get the created_at of the cursor record
            cursor_subq = (
                select(CareerAnalysisResult.created_at)
                .where(CareerAnalysisResult.id == before_id)
                .scalar_subquery()
            )
            conditions.append(CareerAnalysisResult.created_at < cursor_subq)

        stmt = (
            select(CareerAnalysisResult)
            .where(and_(*conditions))
            .order_by(CareerAnalysisResult.created_at.desc())
            .limit(limit)
        )

        try:
            result = await session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            raise DatabaseException(
                f"Error listing analysis results for user {user_id}: {e}"
            ) from e


# Global CRUD instance
career_analysis_result_db = CareerAnalysisResultDB()


__all__ = [
    "CareerAnalysisResultDB",
    "career_analysis_result_db",
]
