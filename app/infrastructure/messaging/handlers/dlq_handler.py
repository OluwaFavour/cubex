"""
Dead-letter queue message handler.

Consumes messages from ``*_dead`` queues and persists them as
:class:`DLQMessage` rows.  Once written to the database the message
is ACK'd, draining the RabbitMQ DLQ.
"""

from typing import Any

import aio_pika

from app.core.config import rabbitmq_logger
from app.core.db import AsyncSessionLocal
from app.core.db.models.dlq_message import DLQMessage
from app.core.enums import DLQMessageStatus


async def handle_dlq_message(
    message: aio_pika.IncomingMessage,
    queue_name: str,
) -> None:
    """
    Persist a dead-letter message to the database, then ACK it.

    Args:
        message: The incoming AMQP message from the DLQ.
        queue_name: The DLQ queue name (e.g. ``otp_emails_dead``).
    """
    async with message.process(ignore_processed=True):
        try:
            body = message.body.decode("utf-8", errors="replace")
            headers: dict[str, Any] = dict(message.headers or {})

            attempt_count = int(headers.get("x-retry-attempt", 0))
            error_message = headers.get("x-error-message")
            if isinstance(error_message, bytes):
                error_message = error_message.decode("utf-8", errors="replace")
            elif error_message is not None and not isinstance(error_message, str):
                error_message = str(error_message)

            # Sanitise header values so they are JSON-serialisable
            safe_headers = _sanitise_headers(headers)

            async with AsyncSessionLocal() as session:
                async with session.begin():
                    dlq_entry = DLQMessage(
                        queue_name=queue_name,
                        message_body=body,
                        error_message=error_message,
                        headers=safe_headers,
                        attempt_count=attempt_count,
                        status=DLQMessageStatus.PENDING,
                    )
                    session.add(dlq_entry)

            rabbitmq_logger.info(
                f"Persisted DLQ message from {queue_name} "
                f"(attempts={attempt_count})"
            )

        except Exception as e:
            rabbitmq_logger.error(
                f"Failed to persist DLQ message from {queue_name}: {e}"
            )
            # Reject without requeue so the message stays in the DLQ
            # for manual intervention via RabbitMQ Management UI.
            await message.reject(requeue=False)


def _sanitise_headers(headers: dict[str, Any]) -> dict[str, Any]:
    """
    Convert header values to JSON-safe types.

    ``aio_pika`` can deliver ``bytes`` or other non-serialisable
    objects in headers; this helper normalises them.
    """
    safe: dict[str, Any] = {}
    for key, value in headers.items():
        if isinstance(value, bytes):
            safe[key] = value.decode("utf-8", errors="replace")
        elif isinstance(value, (str, int, float, bool, type(None))):
            safe[key] = value
        else:
            safe[key] = str(value)
    return safe
