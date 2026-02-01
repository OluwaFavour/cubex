"""
Scheduler Module for CubeX Application.

This module provides the APScheduler-based task scheduler for running
background jobs. It can be run standalone via Docker or integrated
into the FastAPI lifespan.

Standalone Usage:
    python -m app.infrastructure.scheduler.main

Docker Usage:
    docker compose --profile scheduler-only up -d
"""

import asyncio
import logging
import signal
from datetime import timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.shared.config import scheduler_logger, settings
from app.shared.db import init_db, dispose_db
from app.shared.services import BrevoService, RedisService, Renderer


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
        # Initialize database
        scheduler_logger.info("Initializing database...")
        await init_db()
        scheduler_logger.info("Database initialized successfully.")

        # Initialize Redis service
        scheduler_logger.info("Initializing Redis service...")
        await RedisService.init(settings.REDIS_URL)
        scheduler_logger.info("Redis service initialized successfully.")

        # Initialize Brevo Service
        scheduler_logger.info("Initializing Brevo service...")
        await BrevoService.init(
            api_key=settings.BREVO_API_KEY,
            sender_email=settings.BREVO_SENDER_EMAIL,
            sender_name=settings.BREVO_SENDER_NAME,
        )
        scheduler_logger.info("Brevo service initialized successfully.")

        # Initialize template renderer
        scheduler_logger.info("Initializing template renderer...")
        Renderer.initialize("app/templates")
        scheduler_logger.info("Template renderer initialized successfully.")

        # Start scheduler
        scheduler_logger.info("Starting scheduler...")
        scheduler.start()
        scheduler_logger.info("Scheduler started successfully. Waiting for jobs...")

        # Wait for shutdown signal
        await shutdown_event.wait()

    except Exception as e:
        scheduler_logger.exception(f"Scheduler error: {e}")
        raise

    finally:
        # Cleanup
        scheduler_logger.info("Shutting down scheduler...")

        if scheduler.running:
            scheduler.shutdown(wait=True)
            scheduler_logger.info("Scheduler stopped successfully.")

        await RedisService.aclose()
        scheduler_logger.info("Redis service closed successfully.")

        await dispose_db()
        scheduler_logger.info("Database disposed successfully.")

        scheduler_logger.info("Scheduler shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
