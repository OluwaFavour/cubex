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
with cursor-based pagination.

### Authorization

- User must be authenticated (Bearer JWT)

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `feature_key` | string | No | — | Filter by career feature key (e.g. `career.job_match`) |
| `limit` | int | No | 20 | Maximum items per page (1-100) |
| `before` | UUID | No | — | Cursor: return items created before this result ID |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `items` | array | List of analysis history items |
| `items[].id` | UUID | Analysis result identifier |
| `items[].feature_key` | string | Career feature key |
| `items[].title` | string | User-facing label |
| `items[].created_at` | datetime | When the analysis was performed |
| `next_cursor` | UUID / null | Pass as `before` to fetch the next page |
| `has_more` | boolean | Whether more results exist beyond this page |

### Notes

- Results are scoped to the authenticated user
- Soft-deleted results are excluded
- Pass the last item's `id` as `before` to paginate forward
""",
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
authenticated user, including the structured JSON response data.

### Authorization

- User must be authenticated (Bearer JWT)
- User must own the analysis result

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `result_id` | UUID | The analysis result identifier |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Analysis result identifier |
| `usage_log_id` | UUID | Associated usage log |
| `feature_key` | string | Career feature key |
| `title` | string | User-facing label |
| `result_data` | object | Structured JSON analysis response |
| `created_at` | datetime | When the analysis was performed |

### Error Responses

| Status | Reason |
|--------|--------|
| `404 Not Found` | Result does not exist or is not owned by the user |

### Notes

- Soft-deleted results return 404
- `result_data` contains the full AI analysis output
""",
    responses={
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
The result will no longer appear in history listings or detail lookups.

### Authorization

- User must be authenticated (Bearer JWT)
- User must own the analysis result

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `result_id` | UUID | The analysis result identifier |

### Error Responses

| Status | Reason |
|--------|--------|
| `404 Not Found` | Result does not exist or is not owned by the user |

### Notes

- This is a soft-delete — the database record is preserved
- Deleted results return 404 on subsequent requests
""",
    responses={
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
