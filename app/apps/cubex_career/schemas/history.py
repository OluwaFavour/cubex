"""
Pydantic schemas for Career analysis history endpoints.

"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import FeatureKey


class AnalysisHistoryItem(BaseModel):
    """Summary item for the analysis history list."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "feature_key": "career.job_match",
                "title": "Job Match Analysis",
                "created_at": "2026-02-28T12:00:00Z",
            }
        },
    )

    id: UUID
    feature_key: FeatureKey
    title: str | None
    created_at: datetime


class AnalysisHistoryDetail(BaseModel):
    """Full detail view of a single analysis result."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "usage_log_id": "550e8400-e29b-41d4-a716-446655440001",
                "feature_key": "career.job_match",
                "title": "Job Match Analysis",
                "result_data": {
                    "match_score": 0.85,
                    "strengths": ["Python", "FastAPI"],
                    "gaps": ["Kubernetes"],
                },
                "created_at": "2026-02-28T12:00:00Z",
            }
        },
    )

    id: UUID
    usage_log_id: UUID
    feature_key: FeatureKey
    title: str | None
    result_data: dict[str, Any]
    created_at: datetime


class AnalysisHistoryListResponse(BaseModel):
    """Paginated list of analysis history items."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "feature_key": "career.job_match",
                        "title": "Job Match Analysis",
                        "created_at": "2026-02-28T12:00:00Z",
                    }
                ],
                "next_cursor": None,
                "has_more": False,
            }
        },
    )

    items: list[AnalysisHistoryItem]
    next_cursor: Annotated[
        UUID | None,
        Field(
            description=(
                "Pass as `before` query parameter to fetch the next page. "
                "Null when there are no more results."
            ),
        ),
    ]
    has_more: bool


__all__ = [
    "AnalysisHistoryItem",
    "AnalysisHistoryDetail",
    "AnalysisHistoryListResponse",
]
