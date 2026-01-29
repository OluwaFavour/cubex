import logging
from datetime import datetime, timedelta, timezone
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.shared.config import scheduler_logger, settings


logging.basicConfig(level=logging.INFO)
logging.getLogger("apscheduler").setLevel(logging.DEBUG)

scheduler = AsyncIOScheduler(
    # jobstores={
    #     "refunds": SQLAlchemyJobStore(
    #         url=settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql"),
    #         tablename="scheduler_refunds_jobs",
    #     ),
    #     "payment_reminders": SQLAlchemyJobStore(
    #         url=settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql"),
    #         tablename="scheduler_payment_reminders_jobs",
    #     ),
    # },
    timezone=timezone.utc,
)


def main():
    scheduler_logger.info("Starting scheduler...")
    scheduler.start()
    scheduler_logger.info("Scheduler started successfully.")


if __name__ == "__main__":
    main()
