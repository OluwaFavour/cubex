"""
Pydantic schemas for Career analysis history endpoints.

"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import FeatureKey


class AnalysisHistoryItem(BaseModel):
    """Summary item returned in the paginated analysis history list.

    Each item represents one completed career analysis. The ``result_data``
    field is a compact preview (same JSON stored at commit time) so the
    client can render inline summaries without fetching the detail endpoint.
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
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

    id: Annotated[
        UUID,
        Field(
            description=(
                "Unique identifier for this analysis result. "
                "Use as `before` cursor for pagination or in the "
                "detail URL `GET /career/history/{id}`."
            ),
        ),
    ]
    feature_key: Annotated[
        FeatureKey,
        Field(
            description=(
                "Career feature that produced this result "
                "(e.g. `career.job_match`, `career.career_path`)."
            ),
        ),
    ]
    title: Annotated[
        str | None,
        Field(
            description=(
                "Human-readable label derived from the feature key "
                "(e.g. 'Job Match Analysis'). Null if no title could be determined."
            ),
        ),
    ]
    result_data: Annotated[
        dict[str, Any],
        Field(
            description=(
                "Complete structured JSON output from the AI analysis, "
                "exactly as saved during `POST /internal/usage/commit`. "
                "Shape varies by feature key — see the detail endpoint docs "
                "for per-feature examples."
            ),
        ),
    ]
    created_at: Annotated[
        datetime,
        Field(description="When the analysis was performed (ISO 8601 UTC)."),
    ]


class AnalysisHistoryDetail(BaseModel):
    """Full detail view of a single analysis result.

    Includes the ``usage_log_id`` for debugging / billing correlation and
    the complete ``result_data`` payload.

    The shape of ``result_data`` depends on ``feature_key``:

    * **career.job_match** — ``{"match_score": 0.85, "strengths": [...], "gaps": [...]}``
    * **career.career_path** — ``{"paths": [...], "recommended": "..."}``
    * **career.feedback_analyzer** — ``{"sentiment": "positive", "themes": [...]}``
    * **career.extract_keywords** — ``{"keywords": [...], "categories": {...}}``

    The frontend should inspect ``feature_key`` to decide how to render
    each payload.
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "usage_log_id": "f9e8d7c6-b5a4-3210-fedc-ba0987654321",
                "feature_key": "career.job_match",
                "title": "Job Match Analysis",
                "result_data": {
                    "match_score": 0.85,
                    "strengths": ["Python", "FastAPI", "PostgreSQL"],
                    "gaps": ["Kubernetes", "Terraform"],
                    "recommendations": ["Consider obtaining a CKA certification"],
                },
                "created_at": "2026-02-28T12:00:00Z",
            }
        },
    )

    id: Annotated[
        UUID,
        Field(description="Unique identifier for this analysis result."),
    ]
    usage_log_id: Annotated[
        UUID,
        Field(
            description=(
                "ID of the associated usage log entry. Useful for "
                "debugging and correlating with billing records."
            ),
        ),
    ]
    feature_key: Annotated[
        FeatureKey,
        Field(
            description=(
                "Career feature that produced this result "
                "(e.g. `career.job_match`, `career.career_path`)."
            ),
        ),
    ]
    title: Annotated[
        str | None,
        Field(
            description=(
                "Human-readable label derived from the feature key "
                "(e.g. 'Job Match Analysis'). Null if no title could be determined."
            ),
        ),
    ]
    result_data: Annotated[
        dict[str, Any],
        Field(
            description=(
                "Complete structured JSON output from the AI analysis, "
                "exactly as saved during `POST /internal/usage/commit`. "
                "Shape varies by feature key — see class docstring for examples."
            ),
        ),
    ]
    created_at: Annotated[
        datetime,
        Field(description="When the analysis was performed (ISO 8601 UTC)."),
    ]


class AnalysisHistoryListResponse(BaseModel):
    """Cursor-paginated list of analysis history items.

    Use ``next_cursor`` to walk through pages:

    1. ``GET /career/history?limit=20``
    2. If ``has_more`` is true → ``GET /career/history?limit=20&before={next_cursor}``
    3. Repeat until ``has_more`` is false.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "feature_key": "career.job_match",
                        "title": "Job Match Analysis",
                        "result_data": {
                            "match_score": 0.85,
                            "strengths": ["Python", "FastAPI"],
                            "gaps": ["Kubernetes"],
                        },
                        "created_at": "2026-02-28T10:30:00Z",
                    },
                    {
                        "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
                        "feature_key": "career.career_path",
                        "title": "Career Path Analysis",
                        "result_data": {
                            "paths": [
                                "Senior Backend Engineer",
                                "Staff Engineer",
                            ],
                            "recommended": "Senior Backend Engineer",
                        },
                        "created_at": "2026-02-28T09:15:00Z",
                    },
                ],
                "next_cursor": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
                "has_more": True,
            }
        },
    )

    items: Annotated[
        list[AnalysisHistoryItem],
        Field(
            description=(
                "Page of analysis history items, newest first. "
                "Empty list when the user has no matching results."
            ),
        ),
    ]
    next_cursor: Annotated[
        UUID | None,
        Field(
            description=(
                "Pass as the `before` query parameter to fetch the next page. "
                "Null when there are no more results."
            ),
        ),
    ]
    has_more: Annotated[
        bool,
        Field(
            description=(
                "True if additional results exist beyond this page. "
                "When false, `next_cursor` will be null."
            ),
        ),
    ]


__all__ = [
    "AnalysisHistoryItem",
    "AnalysisHistoryDetail",
    "AnalysisHistoryListResponse",
]
