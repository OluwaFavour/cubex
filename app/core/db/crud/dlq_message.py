"""
CRUD operations for :class:`DLQMessage`.

Provides standard ``BaseDB`` operations (get_by_id, get_all with
keyset pagination) plus a custom ``get_metrics`` aggregation for
the admin dashboard.
"""

from typing import Any, Sequence

from sqlalchemy import Row, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.db.crud.base import BaseDB
from app.core.db.models.dlq_message import DLQMessage
from app.core.enums import DLQMessageStatus
from app.core.exceptions.types import DatabaseException


class DLQMessageDB(BaseDB[DLQMessage]):
    """Extended CRUD for DLQ messages with metrics aggregation."""

    def __init__(self) -> None:
        super().__init__(DLQMessage)

    async def get_metrics(
        self,
        session: AsyncSession,
    ) -> Sequence[Row[tuple[str, DLQMessageStatus, int]]]:
        """
        Return per-queue, per-status message counts.

        Returns:
            A sequence of ``(queue_name, status, count)`` rows.
        """
        try:
            stmt = (
                select(
                    DLQMessage.queue_name,
                    DLQMessage.status,
                    func.count().label("count"),
                )
                .where(DLQMessage.is_deleted == False)  # noqa: E712
                .group_by(DLQMessage.queue_name, DLQMessage.status)
                .order_by(DLQMessage.queue_name, DLQMessage.status)
            )
            result = await session.execute(stmt)
            return result.all()  # type: ignore[return-value]
        except Exception as e:
            raise DatabaseException(f"Error retrieving DLQ metrics: {e}") from e

    async def get_metrics_summary(
        self,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """
        Return a summary dict with total counts and per-queue breakdown.

        Returns:
            ``{"total": int, "by_status": {...}, "by_queue": {...}}``
        """
        rows = await self.get_metrics(session)
        total = 0
        by_status: dict[str, int] = {}
        by_queue: dict[str, dict[str, int]] = {}

        for queue_name, status, count in rows:
            total += count
            status_val = (
                status.value if isinstance(status, DLQMessageStatus) else str(status)
            )
            by_status[status_val] = by_status.get(status_val, 0) + count
            if queue_name not in by_queue:
                by_queue[queue_name] = {}
            by_queue[queue_name][status_val] = count

        return {"total": total, "by_status": by_status, "by_queue": by_queue}


dlq_message_db = DLQMessageDB()

__all__ = ["DLQMessageDB", "dlq_message_db"]
