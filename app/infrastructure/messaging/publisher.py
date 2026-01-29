import json
from typing import Any

import aio_pika

from app.infrastructure.messaging.connection import get_connection


async def publish_event(
    queue_name: str, event: dict[str, Any], headers: dict[str, Any] = {}
) -> None:
    """
    Publishes an event message to the specified queue asynchronously.
    Args:
        queue_name (str): The name of the queue to publish the event to.
        event (dict[str, Any]): The event data to be published as a dictionary.
        headers (dict[str, Any], optional): Additional headers to include in the message. Defaults to an empty dictionary.
    Returns:
        None
    Raises:
        Any exceptions raised by the underlying connection or publishing mechanisms.
    Note:
        The event is serialized to JSON and sent as a persistent message with content type 'application/json'.
    """
    connection = await get_connection()
    channel = await connection.channel()
    await channel.declare_queue(queue_name, durable=True)

    message = aio_pika.Message(
        body=json.dumps(event).encode(),
        headers=headers,
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )

    await channel.default_exchange.publish(message, routing_key=queue_name)
