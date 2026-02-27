"""
Messaging Module for CubeX Application.

Standalone Usage:
    python -m app.infrastructure.messaging.main

Docker Usage:
    docker compose --profile worker-only up -d
"""

import asyncio
import signal
from functools import partial

import aio_pika

from app.infrastructure.messaging.connection import get_connection
from app.infrastructure.messaging.consumer import process_message
from app.infrastructure.messaging.queues import get_queue_configs
from app.core.config import rabbitmq_logger, settings
from app.core.db import init_db, dispose_db
from app.core.services import BrevoService, RedisService, Renderer


async def start_consumers(keep_alive: bool) -> aio_pika.RobustConnection | None:
    """
    Asynchronously starts message consumers for all queues defined in get_queue_configs().
    This function establishes a connection to the message broker, sets the channel's QoS,
    and declares the main, retry, and dead-letter queues as specified in the configuration.
    It then registers a consumer for each queue, using the provided message handler and
    optional retry and dead-letter queues. The consumers run indefinitely until the process
    is stopped, at which point the connection is gracefully closed.

    Args:
        keep_alive (bool): If True, the consumers will run indefinitely. If False, they
            will stop only after the caller closes the connection.
    Returns:
        Optional[aio_pika.RobustConnection]: The connection object if keep_alive is False,
            None otherwise.

    Raises:
        Any exceptions raised during connection, queue declaration, or consumer registration.
    Note:
        This function is intended to be run within an asyncio event loop.
    """
    conn = await get_connection()
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=10)  # fetch 10 messages at a time

    queue_configs = get_queue_configs()
    for q in queue_configs:
        # Declare main, retry, and DLX queues
        queue = await channel.declare_queue(q.name, durable=True)

        # Single retry queue setup
        if retry := q.retry_queue:
            await channel.declare_queue(
                retry,
                durable=True,
                arguments={
                    "x-message-ttl": q.retry_ttl,
                    "x-dead-letter-exchange": "",
                    "x-dead-letter-routing-key": q.name,
                },
            )

        # Multiple retry queues setup
        if retries := q.retry_queues:
            for retry in retries:
                await channel.declare_queue(
                    retry.name,
                    durable=True,
                    arguments={
                        "x-message-ttl": retry.ttl,
                        "x-dead-letter-exchange": "",
                        "x-dead-letter-routing-key": q.name,
                    },
                )

        # Dead-letter queue setup
        if dead := q.dead_letter_queue:
            await channel.declare_queue(dead, durable=True)

        # Register consumer
        await queue.consume(  # type: ignore[arg-type]
            partial(
                process_message,
                handler=q.handler,
                channel=channel,  # type: ignore[arg-type]
                retry_queue=q.retry_queue,
                retry_queues=(
                    [retry_queue.model_dump() for retry_queue in q.retry_queues]
                    if q.retry_queues
                    else None
                ),
                max_retries=q.max_retries,
                dead_letter_queue=q.dead_letter_queue,
            ),
            no_ack=False,
        )
    print("Consumers started. Waiting for messages...")
    if keep_alive:
        try:
            await asyncio.Future()  # Run forever
        finally:
            await conn.close()
            print("Connection closed.")
    else:
        return conn


async def main() -> None:
    """
    Main entry point for standalone message consumer execution.

    Initializes required services (database, Redis, Brevo, templates),
    starts the message consumers, and runs until interrupted.
    """
    # Track shutdown state
    shutdown_event = asyncio.Event()
    conn: aio_pika.RobustConnection | None = None

    def handle_shutdown(signum, frame):
        rabbitmq_logger.info(f"Received signal {signum}, initiating shutdown...")
        shutdown_event.set()

    # Register signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    rabbitmq_logger.info("Starting standalone message consumer...")

    try:
        rabbitmq_logger.info("Initializing database...")
        await init_db()
        rabbitmq_logger.info("Database initialized successfully.")

        rabbitmq_logger.info("Initializing Redis service...")
        await RedisService.init(settings.REDIS_URL)
        rabbitmq_logger.info("Redis service initialized successfully.")

        rabbitmq_logger.info("Initializing Brevo service...")
        await BrevoService.init(
            api_key=settings.BREVO_API_KEY,
            sender_email=settings.BREVO_SENDER_EMAIL,
            sender_name=settings.BREVO_SENDER_NAME,
        )
        rabbitmq_logger.info("Brevo service initialized successfully.")

        rabbitmq_logger.info("Initializing template renderer...")
        Renderer.initialize("app/templates")
        rabbitmq_logger.info("Template renderer initialized successfully.")

        # Start consumers (don't keep_alive, we manage lifecycle here)
        rabbitmq_logger.info("Starting message consumers...")
        conn = await start_consumers(keep_alive=False)
        rabbitmq_logger.info(
            "Message consumers started successfully. Waiting for messages..."
        )

        # Wait for shutdown signal
        await shutdown_event.wait()

    except Exception as e:
        rabbitmq_logger.exception(f"Messaging error: {e}")
        raise

    finally:
        rabbitmq_logger.info("Shutting down message consumer...")

        if conn:
            await conn.close()
            rabbitmq_logger.info("RabbitMQ connection closed successfully.")

        await RedisService.aclose()
        rabbitmq_logger.info("Redis service closed successfully.")

        await dispose_db()
        rabbitmq_logger.info("Database disposed successfully.")

        rabbitmq_logger.info("Message consumer shutdown complete.")


# This code initializes message consumers for RabbitMQ queues defined in get_queue_configs().
# It establishes a connection, declares the necessary queues, and sets up consumers
# to process messages from those queues.
if __name__ == "__main__":
    asyncio.run(main())

