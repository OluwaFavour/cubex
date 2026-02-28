"""
Dead-letter queue message model.

Stores messages that have exhausted all retry attempts and landed
in a RabbitMQ dead-letter queue.  The DLQ consumer drains these
queues into the database so they can be inspected, retried, or
discarded through the admin dashboard.
"""

from sqlalchemy import Enum as SAEnum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.models.base import BaseModel
from app.core.enums import DLQMessageStatus


class DLQMessage(BaseModel):
    """
    Persisted dead-letter queue message.

    Attributes:
        queue_name: The DLQ queue the message was consumed from
            (e.g. ``otp_emails_dead``).
        message_body: The original message payload (UTF-8 decoded).
        error_message: The stringified exception that caused the
            final failure, if available.
        headers: Original AMQP headers preserved from the message
            (includes ``x-retry-attempt``, ``x-original-queue``,
            ``x-error-message``).
        attempt_count: Number of retry attempts before dead-lettering.
        status: Current lifecycle status (``pending`` → ``retried``
            or ``discarded``).
    """

    __tablename__ = "dlq_messages"

    queue_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="DLQ queue name the message was consumed from",
    )

    message_body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Original message payload (UTF-8)",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Stringified exception from the final failure",
    )

    headers: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Original AMQP headers (x-retry-attempt, x-original-queue, etc.)",
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of retry attempts before dead-lettering",
    )

    status: Mapped[DLQMessageStatus] = mapped_column(
        SAEnum(DLQMessageStatus, native_enum=False, name="dlq_message_status"),
        nullable=False,
        default=DLQMessageStatus.PENDING,
        index=True,
        comment="Lifecycle status: pending → retried | discarded",
    )

    __table_args__ = (Index("ix_dlq_messages_queue_status", "queue_name", "status"),)


__all__ = ["DLQMessage"]
