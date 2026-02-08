from datetime import datetime, timedelta, timezone

from apscheduler.triggers.cron import CronTrigger

from app.infrastructure.scheduler.main import scheduler
from app.shared.config import scheduler_logger
from app.shared.db import AsyncSessionLocal
from app.shared.db.crud import user_db


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


def schedule_cleanup_soft_deleted_users_job(
    days_threshold: int = 30, hour: int = 3, minute: int = 0
) -> None:
    """
    Schedule a daily job to permanently delete soft-deleted users.

    The job runs at the specified time (default: 3:00 AM UTC) and removes
    users that have been soft-deleted for longer than the days_threshold.

    Args:
        days_threshold (int): Number of days after soft-delete before permanent removal. Defaults to 30.
        hour (int): Hour of day to run the job (0-23, UTC). Defaults to 3.
        minute (int): Minute of hour to run the job (0-59). Defaults to 0.
    """
    scheduler_logger.info(
        f"Scheduling 'cleanup_soft_deleted_users' job to run daily at {hour:02d}:{minute:02d} UTC"
    )
    scheduler.add_job(
        cleanup_soft_deleted_users,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone.utc),
        replace_existing=True,
        id="cleanup_soft_deleted_users_job",
        misfire_grace_time=60 * 60,  # 1 hour grace time
        kwargs={"days_threshold": days_threshold},
    )
    scheduler_logger.info("'cleanup_soft_deleted_users' job scheduled successfully.")
