import json
from typing import Callable, Any

import aio_pika

from app.core.config import rabbitmq_logger
from app.core.services.email_manager import EmailManagerService


async def process_message(
    message: aio_pika.IncomingMessage,
    handler: Callable[[dict[str, Any]], Any],
    channel: aio_pika.Channel,
    retry_queue: str | None = None,
    retry_queues: list[dict[str, Any]] | None = None,
    max_retries: int | None = None,
    dead_letter_queue: str | None = None,
) -> None:
    """
    Processes an incoming RabbitMQ message with a given handler, supporting retry and dead-letter queues.
    Args:
        message (aio_pika.IncomingMessage): The incoming message to process.
        handler (Callable[[Dict[str, Any]], Any]): The async function to handle the message payload.
        channel (aio_pika.Channel): The channel to use for publishing messages.
        retry_queue (str, optional): The name of the queue to use for retrying failed messages. Defaults to None.
        retry_queues (list[Dict[str, Any]], optional): A list of retry queue configurations for multiple retries. Each dict should have 'name' and 'ttl' keys. Defaults to None.
        max_retries (int, optional): The maximum number of retry attempts for single retry queue. Defaults to None.
        dead_letter_queue (str, optional): The name of the dead-letter queue for messages that exceed retry attempts. Defaults to None.
    Raises:
        None. All exceptions are caught and handled internally.
    Behavior:
        - Decodes the message body and passes it to the handler.
        - If the handler raises an exception, increments the retry attempt count.
        - Retries the message by publishing it to the retry queue, if the maximum number of attempts has not been reached.
        - If the maximum number of attempts is reached or no retry queue is specified, publishes the message to the dead-letter queue (if provided).
        - Logs errors, retries, and dead-lettering actions.
        - Rejects the message without requeuing after handling.
    """
    async with message.process(ignore_processed=True):
        try:
            event = json.loads(message.body.decode())
            await handler(event)
        except Exception as e:
            rabbitmq_logger.error(f"Error in handler: {e}")
            headers = dict(message.headers or {})
            attempt = int(headers.get("x-retry-attempt", 0))  # type: ignore[arg-type]
            next_queue: str | None = None

            # Multiple retry queues logic
            if retry_queues:
                if attempt < len(retry_queues):
                    next_queue = retry_queues[attempt]["name"]
                    rabbitmq_logger.info(f"Retrying message via {next_queue}")
            # Single retry queue logic
            elif retry_queue:
                if not max_retries or attempt < max_retries:
                    next_queue = retry_queue
                    rabbitmq_logger.info(f"Retrying message via {next_queue}")

            if next_queue:
                headers["x-retry-attempt"] = attempt + 1
                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=message.body,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        headers=headers,
                    ),
                    routing_key=next_queue,
                )
                print(f"Message requeued to {next_queue}")

            # Dead-letter logic
            elif dead_letter_queue:
                headers["x-error-message"] = str(e)
                # Derive the original main queue from the DLQ name
                if dead_letter_queue.endswith("_dead"):
                    headers["x-original-queue"] = dead_letter_queue[: -len("_dead")]

                await channel.default_exchange.publish(
                    aio_pika.Message(body=message.body, headers=headers),
                    routing_key=dead_letter_queue,
                )
                rabbitmq_logger.warning(f"Message dead-lettered to {dead_letter_queue}")

                try:
                    message_body = message.body.decode()
                    await EmailManagerService.send_dlq_alert(
                        queue_name=dead_letter_queue,
                        message_body=message_body,
                        attempt_count=attempt,
                    )
                except Exception as alert_error:
                    rabbitmq_logger.error(
                        f"Failed to send DLQ alert for {dead_letter_queue}: {alert_error}"
                    )

            # Reject the message without requeuing
            await message.reject(requeue=False)
