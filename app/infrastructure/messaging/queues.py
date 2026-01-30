from typing import Annotated, Any, Callable

from functools import lru_cache
from pydantic import BaseModel, Field, model_validator


class RetryQueue(BaseModel):
    name: Annotated[str, Field(description="Name of the retry queue")]
    ttl: Annotated[int, Field(gt=0, description="Time to live in milliseconds")]


class QueueConfig(BaseModel):
    name: Annotated[str, Field(description="Name of the main queue")]
    handler: Annotated[
        Callable[[dict[str, Any]], Any],
        Field(description="Function to handle messages from the queue"),
    ]
    retry_queue: Annotated[
        str | None, Field(description="Name of the retry queue (if single retry)")
    ] = None
    retry_queues: Annotated[
        list[RetryQueue] | None,
        Field(description="List of retry queues with TTLs (if multiple retries)"),
    ] = None
    retry_ttl: Annotated[
        int | None,
        Field(
            gt=0,
            description="Time to live in milliseconds for single retry queue",
        ),
    ] = None
    max_retries: Annotated[
        int | None,
        Field(
            gt=0,
            description="Maximum number of retries for single retry queue",
        ),
    ] = None
    dead_letter_queue: Annotated[
        str | None, Field(description="Name of the dead letter queue")
    ] = None

    @model_validator(mode="before")
    @classmethod
    def check_retry_configuration(cls, values: dict[str, Any]) -> dict[str, Any]:
        retry_queue = values.get("retry_queue")
        retry_queues = values.get("retry_queues")
        retry_ttl = values.get("retry_ttl")

        if retry_queue and retry_queues:
            raise ValueError(
                "Specify either 'retry_queue' or 'retry_queues', not both."
            )
        if retry_queue and not retry_ttl:
            raise ValueError("'retry_ttl' must be set when using 'retry_queue'.")
        if retry_queues is not None:
            if len(retry_queues) == 0:
                raise ValueError("'retry_queues' must contain at least one entry.")
        return values


QUEUE_CONFIG = [
    # Example queue configurations:
    # {
    #     "name": "paystack_events",
    #     "handler": handle_paystack_events,
    #     "retry_queues": [
    #         {"name": "paystack_events_retry_30s", "ttl": 30 * 1000},  # 30 seconds
    #         {"name": "paystack_events_retry_5m", "ttl": 5 * 60 * 1000},  # 5 minutes
    #         {"name": "paystack_events_retry_1h", "ttl": 60 * 60 * 1000},  # 1 hour
    #     ],
    #     "dead_letter_queue": "paystack_events_dead",
    # },
    # {
    #     "name": "paystack_refund",
    #     "handler": handle_paystack_refund,
    #     "retry_queue": "paystack_refund_retry",
    #     "retry_ttl": 60 * 1000,  # 1 minute
    #     "max_retries": 5,
    #     "dead_letter_queue": "paystack_refund_dead",
    # },
    # {
    #     "name": "booking_completed",
    #     "handler": handle_booking_completed,
    #     "retry_ttl": 30 * 1000,  # 30 seconds
    #     "max_retries": 5,
    # },
]


@lru_cache()
def get_queue_configs() -> list[QueueConfig]:
    return [
        QueueConfig.model_validate(config, from_attributes=True)
        for config in QUEUE_CONFIG
    ]
