from datetime import datetime, timedelta, timezone

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.infrastructure.scheduler.main import scheduler
from app.shared.config import scheduler_logger, settings
from app.shared.db import AsyncSessionLocal
from app.shared.db.crud import user_db
from app.apps.cubex_api.db.crud import usage_log_db


async def cleanup_soft_deleted_users(days_threshold: int = 30) -> None:
    """
    Periodic task to permanently delete users who have been soft-deleted for longer than the specified threshold.

    Args:
        days_threshold (int): The number of days after which soft-deleted users should be permanently removed.
    """

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_threshold)
    async with AsyncSessionLocal.begin() as session:
        scheduler_logger.info(
            f"Starting cleanup of soft-deleted users older than {days_threshold} days (cutoff: {cutoff_date})"
        )
        deleted_count = await user_db.permanently_delete_soft_deleted(
            session, cutoff_date, commit_self=False
        )
        scheduler_logger.info(
            f"Completed cleanup of soft-deleted users. Deleted {deleted_count} record(s)."
        )


async def expire_pending_usage_logs() -> None:
    """
    Periodic task to expire usage logs that have been in PENDING status
    for longer than the configured timeout.

    This ensures that usage logs from abandoned operations don't remain
    in PENDING state indefinitely.
    """
    timeout_minutes = settings.USAGE_LOG_PENDING_TIMEOUT_MINUTES
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

    async with AsyncSessionLocal.begin() as session:
        scheduler_logger.info(
            f"Starting expiration of pending usage logs older than {timeout_minutes} minutes (cutoff: {cutoff_time})"
        )
        expired_count = await usage_log_db.expire_pending(
            session, older_than=cutoff_time, commit_self=False
        )
        scheduler_logger.info(
            f"Completed expiration of pending usage logs. Expired {expired_count} record(s)."
        )
