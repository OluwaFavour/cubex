"""
Scheduler Module for CubeX Application.

Standalone Usage:
    python -m app.infrastructure.scheduler.main

Docker Usage:
    docker compose --profile scheduler-only up -d
"""

import asyncio
import logging
import signal
from datetime import timezone

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import scheduler_logger, settings
from app.core.services import BrevoService, RedisService, Renderer


logging.basicConfig(level=logging.INFO)
logging.getLogger("apscheduler").setLevel(logging.DEBUG)


def _sync_database_url() -> str:
    """Convert the async DATABASE_URL to a synchronous one for APScheduler.

    Only modifies the driver scheme (before ://) so the rest of the URL
    — including any percent-encoded password — is preserved exactly.
    """
    scheme, rest = settings.DATABASE_URL.split("://", 1)
    return f"{scheme.replace('+asyncpg', '')}://{rest}"


_sync_url = _sync_database_url()

scheduler = AsyncIOScheduler(
    jobstores={
        "cleanups": SQLAlchemyJobStore(
            url=_sync_url,
            tablename="scheduler_cleanup_jobs",
        ),
        "usage_logs": SQLAlchemyJobStore(
            url=_sync_url,
            tablename="scheduler_usage_log_jobs",
        ),
    },
    timezone=timezone.utc,
)


def schedule_cleanup_soft_deleted_users_job(days_threshold: int = 30) -> None:
    """
    Schedule the cleanup_soft_deleted_users job to run daily at 3:00 AM UTC.
    """
    # Import here to avoid circular import issues
    from app.infrastructure.scheduler.jobs import cleanup_soft_deleted_users

    scheduler_logger.info(
        "Scheduling 'cleanup_soft_deleted_users' job to run daily at 3:00 AM UTC"
    )
    scheduler.add_job(
        cleanup_soft_deleted_users,
        trigger=CronTrigger(hour=3, minute=0, timezone=timezone.utc),
        replace_existing=True,
        id="cleanup_soft_deleted_users_job",
        jobstore="cleanups",
        misfire_grace_time=60 * 60,  # 1 hour grace time
        kwargs={"days_threshold": days_threshold},
    )
    scheduler_logger.info("'cleanup_soft_deleted_users' job scheduled successfully.")


def schedule_expire_pending_usage_logs_job(interval_minutes: int = 5) -> None:
    """
    Schedule the expire_pending_usage_logs job to run at specified intervals.
    """
    # Import here to avoid circular import issues
    from apscheduler.triggers.interval import IntervalTrigger

    from app.infrastructure.scheduler.jobs import expire_pending_usage_logs

    scheduler_logger.info(
        f"Scheduling 'expire_pending_usage_logs' job to run every {interval_minutes} minutes"
    )
    scheduler.add_job(
        expire_pending_usage_logs,
        trigger=IntervalTrigger(minutes=interval_minutes, timezone=timezone.utc),
        replace_existing=True,
        id="expire_pending_usage_logs_job",
        jobstore="usage_logs",
        misfire_grace_time=60 * 5,  # 5 minutes grace time
    )
    scheduler_logger.info("'expire_pending_usage_logs' job scheduled successfully.")


def schedule_expire_pending_career_usage_logs_job(interval_minutes: int = 5) -> None:
    """
    Schedule the expire_pending_career_usage_logs job to run at specified intervals.
    """
    from apscheduler.triggers.interval import IntervalTrigger

    from app.infrastructure.scheduler.jobs import expire_pending_career_usage_logs

    scheduler_logger.info(
        f"Scheduling 'expire_pending_career_usage_logs' job to run every {interval_minutes} minutes"
    )
    scheduler.add_job(
        expire_pending_career_usage_logs,
        trigger=IntervalTrigger(minutes=interval_minutes, timezone=timezone.utc),
        replace_existing=True,
        id="expire_pending_career_usage_logs_job",
        jobstore="usage_logs",
        misfire_grace_time=60 * 5,  # 5 minutes grace time
    )
    scheduler_logger.info(
        "'expire_pending_career_usage_logs' job scheduled successfully."
    )


def initialize_scheduler() -> None:
    """
    Initialize the scheduler by scheduling all required jobs.

    This function should be called during application startup to ensure
    that all scheduled tasks are registered and ready to run.
    """
    schedule_cleanup_soft_deleted_users_job(
        days_threshold=settings.USER_SOFT_DELETE_RETENTION_DAYS
    )
    schedule_expire_pending_usage_logs_job(interval_minutes=5)
    schedule_expire_pending_career_usage_logs_job(interval_minutes=5)


async def main() -> None:
    """
    Main entry point for standalone scheduler execution.

    Initializes required services (database, Redis, Brevo, templates),
    starts the scheduler, and runs until interrupted.
    """
    # Track shutdown state
    shutdown_event = asyncio.Event()

    def handle_shutdown(signum, frame):
        scheduler_logger.info(f"Received signal {signum}, initiating shutdown...")
        shutdown_event.set()

    # Register signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    scheduler_logger.info("Starting standalone scheduler...")

    try:
        scheduler_logger.info("Initializing Redis service...")
        await RedisService.init(settings.REDIS_URL)
        scheduler_logger.info("Redis service initialized successfully.")

        scheduler_logger.info("Initializing Brevo service...")
        await BrevoService.init(
            api_key=settings.BREVO_API_KEY,
            sender_email=settings.BREVO_SENDER_EMAIL,
            sender_name=settings.BREVO_SENDER_NAME,
        )
        scheduler_logger.info("Brevo service initialized successfully.")

        scheduler_logger.info("Initializing template renderer...")
        Renderer.initialize("app/templates")
        scheduler_logger.info("Template renderer initialized successfully.")

        # Start scheduler
        scheduler_logger.info("Starting scheduler...")
        scheduler.start()
        scheduler_logger.info("Scheduler started successfully. Waiting for jobs...")
        initialize_scheduler()  # Schedule jobs after starting the scheduler
        # Wait for shutdown signal
        await shutdown_event.wait()

    except Exception as e:
        scheduler_logger.exception(f"Scheduler error: {e}")
        raise

    finally:
        scheduler_logger.info("Shutting down scheduler...")

        if scheduler.running:
            scheduler.shutdown(wait=True)
            scheduler_logger.info("Scheduler stopped successfully.")

        await RedisService.aclose()
        scheduler_logger.info("Redis service closed successfully.")

        scheduler_logger.info("Scheduler shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
