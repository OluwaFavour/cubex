"""
Admin DLQ metrics API router.

Provides a single ``GET /admin/api/dlq/metrics`` endpoint that returns
aggregated DLQ message counts per queue and status.  Protected by the
same HMAC session token used by SQLAdmin.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.auth import admin_auth
from app.core.db.crud.dlq_message import dlq_message_db
from app.core.dependencies.db import get_async_session
from app.core.exceptions.types import AuthenticationException

router = APIRouter()


# ---------------------------------------------------------------------------
# Auth dependency – reuses the SQLAdmin HMAC token from the session cookie
# ---------------------------------------------------------------------------


async def require_admin_auth(request: Request) -> None:
    """Verify the caller holds a valid admin session token."""
    result = await admin_auth.authenticate(request)
    if result is not True:
        raise AuthenticationException("Admin authentication required.")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DLQMetricsItem(BaseModel):
    queue_name: Annotated[str, Field(description="DLQ queue name")]
    status: Annotated[
        str, Field(description="Message status (pending/retried/discarded)")
    ]
    count: Annotated[int, Field(description="Number of messages")]


class DLQMetricsResponse(BaseModel):
    total: Annotated[int, Field(description="Total DLQ messages")]
    by_status: Annotated[
        dict[str, int],
        Field(description="Counts keyed by status"),
    ]
    by_queue: Annotated[
        dict[str, dict[str, int]],
        Field(description="Counts keyed by queue_name → status → count"),
    ]
    items: Annotated[
        list[DLQMetricsItem],
        Field(description="Raw per-queue per-status rows"),
    ]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/dlq/metrics",
    response_model=DLQMetricsResponse,
    summary="DLQ Metrics",
    description=(
        "## DLQ Metrics\n\n"
        "Returns aggregated dead-letter queue message counts grouped by\n"
        "`queue_name` and `status`.  Useful for monitoring dashboards\n"
        "and alerting.\n\n"
        "### Authentication\n\n"
        "Requires a valid admin session (same HMAC token as `/admin`)."
    ),
    dependencies=[Depends(require_admin_auth)],
)
async def dlq_metrics(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> DLQMetricsResponse:
    summary = await dlq_message_db.get_metrics_summary(session)
    rows = await dlq_message_db.get_metrics(session)

    items = [
        DLQMetricsItem(
            queue_name=queue_name,
            status=status.value if hasattr(status, "value") else str(status),
            count=count,
        )
        for queue_name, status, count in rows
    ]

    return DLQMetricsResponse(
        total=summary["total"],
        by_status=summary["by_status"],
        by_queue=summary["by_queue"],
        items=items,
    )
