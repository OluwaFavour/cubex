"""
Career Analysis History router.

- List past analysis results (paginated)
- View a single analysis result
- Delete an analysis result (soft-delete)
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_career.db.crud import career_analysis_result_db
from app.apps.cubex_career.schemas.history import (
    AnalysisHistoryDetail,
    AnalysisHistoryItem,
    AnalysisHistoryListResponse,
)
from app.core.config import request_logger
from app.core.dependencies import CurrentActiveUser, get_async_session
from app.core.enums import FeatureKey
from app.core.exceptions.types import NotFoundException

router = APIRouter(prefix="/history")


@router.get(
    "",
    response_model=AnalysisHistoryListResponse,
    summary="List analysis history",
    description="""
## List Analysis History

Return the authenticated user's past analysis results, newest first,
with cursor-based pagination. Each item is a lightweight summary — use
`GET /career/history/{result_id}` to fetch the full `result_data`.

Analysis history records are created automatically when the AI tool server
commits a successful usage log with `result_data` via
`POST /internal/usage/commit`.

### Authorization

- User must be authenticated (Bearer JWT)

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `feature_key` | string | No | — | Filter by career feature key (see Feature Keys table) |
| `limit` | int | No | 20 | Maximum items per page (1-100) |
| `before` | UUID | No | — | Cursor: return items created before this result ID |

### Feature Keys

| Key | Analysis type |
|-----|---------------|
| `career.job_match` | Job Match Analysis |
| `career.career_path` | Career Path Analysis |
| `career.feedback_analyzer` | Feedback Analysis |
| `career.generate_feedback` | Feedback Generation |
| `career.extract_keywords` | Keyword Extraction |
| `career.extract_cues.resume` | Resume Cue Extraction |
| `career.extract_cues.feedback` | Feedback Cue Extraction |
| `career.extract_cues.interview` | Interview Cue Extraction |
| `career.extract_cues.assessment` | Assessment Cue Extraction |
| `career.reframe_feedback` | Feedback Reframing |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `items` | array | Page of analysis history summaries |
| `items[].id` | UUID | Analysis result identifier (use as `before` cursor or in detail URL) |
| `items[].feature_key` | string | Career feature key — see table above |
| `items[].title` | string | Human-readable label (e.g. "Job Match Analysis") |
| `items[].result_data` | object | Complete structured JSON analysis output — shape varies by feature key |
| `items[].created_at` | datetime | When the analysis was performed (ISO 8601) |
| `next_cursor` | UUID / null | Pass as `before` to fetch the next page, `null` when no more pages |
| `has_more` | boolean | `true` if additional results exist beyond this page |

### Pagination Flow

1. First request — `GET /career/history?limit=20`
2. Check `has_more` in the response
3. If `true`, take `next_cursor` and call `GET /career/history?limit=20&before={next_cursor}`
4. Repeat until `has_more` is `false`

### Notes

- Results are scoped to the authenticated user — other users' results are never visible
- Soft-deleted results are excluded automatically
- An invalid `before` cursor (non-existent UUID) returns results from the beginning
- The `items` array is empty when the user has no analysis history
""",
    responses={
        200: {
            "description": "Paginated list of analysis history",
            "content": {
                "application/json": {
                    "examples": {
                        "with_results": {
                            "summary": "Page with results",
                            "value": {
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
                            },
                        },
                        "empty": {
                            "summary": "No results",
                            "value": {
                                "items": [],
                                "next_cursor": None,
                                "has_more": False,
                            },
                        },
                    }
                }
            },
        },
        401: {"description": "Missing or invalid Bearer JWT"},
    },
)
async def list_history(
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    feature_key: Annotated[
        FeatureKey | None,
        Query(description="Filter by career feature key"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum items to return"),
    ] = 20,
    before: Annotated[
        UUID | None,
        Query(description="Cursor: return items created before this result ID"),
    ] = None,
) -> AnalysisHistoryListResponse:
    """List the authenticated user's past analysis results with cursor-based pagination."""
    request_logger.info(
        f"GET /career/history - user={user.id} "
        f"feature_key={feature_key} limit={limit} before={before}"
    )
    items = await career_analysis_result_db.list_by_user(
        session,
        user_id=user.id,
        feature_key=feature_key,
        limit=limit + 1,  # fetch one extra to determine has_more
        before_id=before,
    )

    has_more = len(items) > limit
    page = items[:limit]

    return AnalysisHistoryListResponse(
        items=[
            AnalysisHistoryItem(
                id=r.id,
                feature_key=r.feature_key,
                title=r.title,
                result_data=r.result_data,
                created_at=r.created_at,
            )
            for r in page
        ],
        next_cursor=page[-1].id if has_more else None,
        has_more=has_more,
    )


@router.get(
    "/{result_id}",
    response_model=AnalysisHistoryDetail,
    summary="Get analysis result",
    description="""
## Get Analysis Result

Return the full detail of a single analysis result owned by the
authenticated user, including the structured `result_data` JSON that was
originally returned to the user by the AI tool.

### Authorization

- User must be authenticated (Bearer JWT)
- User must own the analysis result

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `result_id` | UUID | The analysis result identifier (from `GET /career/history`) |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Analysis result identifier |
| `usage_log_id` | UUID | Associated usage log (for debugging / correlation with billing) |
| `feature_key` | string | Career feature key (e.g. `career.job_match`) |
| `title` | string | Human-readable label |
| `result_data` | object | Full structured JSON analysis output — see below |
| `created_at` | datetime | When the analysis was performed (ISO 8601) |

### About `result_data`

The `result_data` field contains the complete AI analysis response exactly
as it was saved during `POST /internal/usage/commit`. Its shape varies
by feature — for example:

- **`career.job_match`** — `{"match_score": 0.85, "strengths": [...], "gaps": [...]}`
- **`career.career_path`** — `{"paths": [...], "recommended": "..."}`
- **`career.feedback_analyzer`** — `{"sentiment": "positive", "themes": [...]}`
- **`career.extract_keywords`** — `{"keywords": [...], "categories": {...}}`

The frontend should read `feature_key` to determine how to render each
result.

### Error Responses

| Status | Reason |
|--------|--------|
| `401 Unauthorized` | Missing or invalid Bearer JWT |
| `404 Not Found` | Result does not exist, is soft-deleted, or belongs to another user |

### Notes

- Soft-deleted results return 404 (they cannot be "un-deleted")
- `usage_log_id` is informational — the usage log itself is not exposed via public endpoints
""",
    responses={
        200: {
            "description": "Full analysis result",
            "content": {
                "application/json": {
                    "example": {
                        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "usage_log_id": "f9e8d7c6-b5a4-3210-fedc-ba0987654321",
                        "feature_key": "career.job_match",
                        "title": "Job Match Analysis",
                        "result_data": {
                            "match_score": 0.85,
                            "strengths": ["Python", "FastAPI", "PostgreSQL"],
                            "gaps": ["Kubernetes", "Terraform"],
                            "recommendations": [
                                "Consider obtaining a CKA certification"
                            ],
                        },
                        "created_at": "2026-02-28T10:30:00Z",
                    }
                }
            },
        },
        404: {
            "description": "Result not found or not owned by user",
            "content": {
                "application/json": {
                    "example": {"detail": "Analysis result not found."}
                }
            },
        },
    },
)
async def get_result(
    result_id: UUID,
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AnalysisHistoryDetail:
    """Get full details of a single analysis result owned by the current user."""
    request_logger.info(f"GET /career/history/{result_id} - user={user.id}")
    result = await career_analysis_result_db.get_user_result(
        session, result_id=result_id, user_id=user.id
    )
    if result is None:
        raise NotFoundException("Analysis result not found.")
    return AnalysisHistoryDetail(
        id=result.id,
        usage_log_id=result.usage_log_id,
        feature_key=result.feature_key,
        title=result.title,
        result_data=result.result_data,
        created_at=result.created_at,
    )


@router.delete(
    "/{result_id}",
    status_code=204,
    summary="Delete analysis result",
    description="""
## Delete Analysis Result

Soft-delete a single analysis result owned by the authenticated user.
After deletion, the result will no longer appear in
`GET /career/history` listings or be retrievable via
`GET /career/history/{result_id}`.

### Authorization

- User must be authenticated (Bearer JWT)
- User must own the analysis result

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `result_id` | UUID | The analysis result identifier |

### Response

Returns HTTP 204 with an empty body on success.

### Error Responses

| Status | Reason |
|--------|--------|
| `401 Unauthorized` | Missing or invalid Bearer JWT |
| `404 Not Found` | Result does not exist, is already deleted, or belongs to another user |

### Side Effects

- This is a **soft-delete** — the database row is preserved with
  `is_deleted=true` and `deleted_at` set. It can be recovered by an
  admin if needed.
- The underlying **usage log is not affected** — quota and billing
  records remain intact regardless of whether the user deletes the
  analysis history entry.

### Idempotency

This operation is **not** idempotent. Deleting an already-deleted result
returns `404 Not Found` on subsequent calls.
""",
    responses={
        204: {
            "description": "Result deleted successfully (empty body)",
        },
        404: {
            "description": "Result not found or not owned by user",
            "content": {
                "application/json": {
                    "example": {"detail": "Analysis result not found."}
                }
            },
        },
    },
)
async def delete_result(
    result_id: UUID,
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Soft-delete a single analysis result owned by the current user."""
    request_logger.info(f"DELETE /career/history/{result_id} - user={user.id}")
    async with session.begin():
        result = await career_analysis_result_db.get_user_result(
            session, result_id=result_id, user_id=user.id
        )
        if result is None:
            raise NotFoundException("Analysis result not found.")
        await career_analysis_result_db.soft_delete(
            session, result_id, commit_self=False
        )


__all__ = ["router"]
