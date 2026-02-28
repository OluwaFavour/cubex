"""
CRUD operations for Career usage log model.

"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence
from uuid import UUID

from sqlalchemy import SQLColumnExpression, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.db.crud.base import BaseDB
from app.apps.cubex_career.db.models.usage_log import CareerUsageLog
from app.core.enums import UsageLogStatus
from app.core.exceptions.types import DatabaseException


class CareerUsageLogDB(BaseDB[CareerUsageLog]):
    """
    CRUD operations for CareerUsageLog model.

    Note: CareerUsageLog records are immutable after creation.
    Only the status/committed_at fields can be updated via commit().
    """

    def __init__(self):
        super().__init__(CareerUsageLog)

    async def get_by_request_id(
        self,
        session: AsyncSession,
        request_id: str,
    ) -> CareerUsageLog | None:
        """
        Get a usage log by its request_id.

        Args:
            session: Database session.
            request_id: The globally unique request ID.

        Returns:
            CareerUsageLog if found, None otherwise.
        """
        return await self.get_one_by_conditions(
            session=session,
            conditions=[self.model.request_id == request_id],
        )

    async def get_by_request_id_and_fingerprint(
        self,
        session: AsyncSession,
        user_id: UUID,
        request_id: str,
        fingerprint_hash: str,
    ) -> CareerUsageLog | None:
        """
        Get a usage log by user_id, request_id, and fingerprint_hash.

        Used for true idempotency with user isolation:
        - Same user + request_id + fingerprint_hash = return existing record
        - Different fingerprint = different request payload, create new record
        - Different user = always independent (user isolation)

        Args:
            session: Database session.
            user_id: The user UUID for isolation.
            request_id: The globally unique request ID.
            fingerprint_hash: Hash of request characteristics.

        Returns:
            CareerUsageLog if found with matching criteria, None otherwise.
        """
        return await self.get_one_by_conditions(
            session=session,
            conditions=[
                self.model.user_id == user_id,
                self.model.request_id == request_id,
                self.model.fingerprint_hash == fingerprint_hash,
            ],
        )

    async def get_by_user(
        self,
        session: AsyncSession,
        user_id: UUID,
        status_filter: list[UsageLogStatus] | None = None,
        limit: int = 100,
    ) -> Sequence[CareerUsageLog]:
        """
        Get usage logs for a user.

        Args:
            session: Database session.
            user_id: User ID.
            status_filter: Only include logs with these statuses. If None, includes all.
            limit: Maximum number of logs to return.

        Returns:
            List of usage logs, ordered by created_at descending.
        """
        conditions: list[SQLColumnExpression[bool]] = [
            CareerUsageLog.user_id == user_id,
            CareerUsageLog.is_deleted.is_(False),
        ]
        if status_filter is not None:
            conditions.append(CareerUsageLog.status.in_(status_filter))

        stmt = (
            select(CareerUsageLog)
            .where(and_(*conditions))
            .order_by(CareerUsageLog.created_at.desc())
            .limit(limit)
        )

        try:
            result = await session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            raise DatabaseException(
                f"Error getting usage logs for user {user_id}: {str(e)}"
            ) from e

    async def commit(
        self,
        session: AsyncSession,
        usage_log_id: UUID,
        success: bool,
        metrics: dict | None = None,
        failure: dict | None = None,
        commit_self: bool = True,
    ) -> CareerUsageLog | None:
        """
        Commit a pending usage log (idempotent).

        Args:
            session: Database session.
            usage_log_id: Usage log ID.
            success: True for SUCCESS status, False for FAILED status.
            metrics: Optional metrics dict with keys: model_used, input_tokens,
                     output_tokens, latency_ms.
            failure: Optional failure dict with keys: failure_type, reason.
            commit_self: Whether to commit the transaction.

        Returns:
            Updated usage log or None if not found.
        """
        existing = await self.get_by_id(session, usage_log_id)
        if existing is None or existing.is_deleted:
            return None

        # Already committed, return as-is (idempotent)
        if existing.status != UsageLogStatus.PENDING:
            return existing

        new_status = UsageLogStatus.SUCCESS if success else UsageLogStatus.FAILED
        update_data: dict = {
            "status": new_status,
            "committed_at": datetime.now(timezone.utc),
        }

        # Set credits_charged on success (actual credits consumed)
        if success:
            update_data["credits_charged"] = existing.credits_reserved

        # Add metrics if provided
        if metrics:
            if metrics.get("model_used") is not None:
                update_data["model_used"] = metrics["model_used"]
            if metrics.get("input_tokens") is not None:
                update_data["input_tokens"] = metrics["input_tokens"]
            if metrics.get("output_tokens") is not None:
                update_data["output_tokens"] = metrics["output_tokens"]
            if metrics.get("latency_ms") is not None:
                update_data["latency_ms"] = metrics["latency_ms"]

        # Add failure info if provided
        if failure:
            if failure.get("failure_type") is not None:
                update_data["failure_type"] = failure["failure_type"]
            if failure.get("reason") is not None:
                update_data["failure_reason"] = failure["reason"]

        return await self.update(
            session,
            usage_log_id,
            update_data,
            commit_self=commit_self,
        )

    async def expire_pending(
        self,
        session: AsyncSession,
        older_than: datetime,
        commit_self: bool = True,
    ) -> int:
        """
        Expire pending usage logs older than the given cutoff.

        Args:
            session: Database session.
            older_than: Expire logs created before this time.
            commit_self: Whether to commit the transaction.

        Returns:
            Number of logs expired.
        """
        from sqlalchemy import update

        stmt = (
            update(CareerUsageLog)
            .where(
                CareerUsageLog.status == UsageLogStatus.PENDING,
                CareerUsageLog.created_at < older_than,
                CareerUsageLog.is_deleted.is_(False),
            )
            .values(
                status=UsageLogStatus.EXPIRED,
                committed_at=datetime.now(timezone.utc),
            )
        )
        result = await session.execute(stmt)

        if commit_self:
            await session.commit()

        return result.rowcount  # type: ignore[return-value]

    async def sum_credits_for_period(
        self,
        session: AsyncSession,
        user_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> Decimal:
        """
        Sum credits_reserved for SUCCESS usage logs within a billing period.

        This is used for quota checking - only successfully completed
        requests count toward the usage quota.

        Args:
            session: Database session.
            user_id: The user to sum usage for.
            period_start: Start of the billing period (inclusive).
            period_end: End of the billing period (exclusive).

        Returns:
            Total credits used in the period, or Decimal("0") if none.
        """
        stmt = select(
            func.coalesce(func.sum(CareerUsageLog.credits_reserved), Decimal("0"))
        ).where(
            CareerUsageLog.user_id == user_id,
            CareerUsageLog.status == UsageLogStatus.SUCCESS,
            CareerUsageLog.created_at >= period_start,
            CareerUsageLog.created_at < period_end,
            CareerUsageLog.is_deleted.is_(False),
        )

        try:
            result = await session.execute(stmt)
            return result.scalar_one()
        except Exception as e:
            raise DatabaseException(
                f"Error summing credits for user {user_id}: {str(e)}"
            ) from e


# Global CRUD instance
career_usage_log_db = CareerUsageLogDB()


__all__ = [
    "CareerUsageLogDB",
    "career_usage_log_db",
]
