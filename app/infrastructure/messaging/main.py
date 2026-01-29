import asyncio
from functools import partial

import aio_pika

from app.infrastructure.messaging.connection import get_connection
from app.infrastructure.messaging.consumer import process_message
from app.infrastructure.messaging.queues import get_queue_configs


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
        await queue.consume(
            partial(
                process_message,
                handler=q.handler,
                channel=channel,
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


# This code initializes message consumers for RabbitMQ queues defined in get_queue_configs().
# It establishes a connection, declares the necessary queues, and sets up consumers
# to process messages from those queues.
if __name__ == "__main__":
    asyncio.run(start_consumers(keep_alive=True))
