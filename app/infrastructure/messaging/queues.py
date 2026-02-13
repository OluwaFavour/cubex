from functools import lru_cache
from typing import Annotated, Any, Callable

from pydantic import BaseModel, Field, model_validator

from app.infrastructure.messaging.handlers.email_handler import (
    handle_otp_email,
    handle_password_reset_confirmation_email,
    handle_subscription_activated_email,
    handle_subscription_canceled_email,
    handle_payment_failed_email,
    handle_workspace_invitation_email,
)
from app.infrastructure.messaging.handlers.stripe import (
    handle_stripe_checkout_completed,
    handle_stripe_subscription_updated,
    handle_stripe_subscription_deleted,
    handle_stripe_payment_failed,
)
from app.infrastructure.messaging.handlers.usage_handler import handle_usage_commit


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
    # OTP Email Queue - sends OTP codes for verification and password reset
    {
        "name": "otp_emails",
        "handler": handle_otp_email,
        "retry_queue": "otp_emails_retry",
        "retry_ttl": 30 * 1000,  # 30 seconds
        "max_retries": 3,
        "dead_letter_queue": "otp_emails_dead",
    },
    # Password Reset Confirmation Email Queue
    {
        "name": "password_reset_confirmation_emails",
        "handler": handle_password_reset_confirmation_email,
        "retry_queue": "password_reset_confirmation_emails_retry",
        "retry_ttl": 30 * 1000,  # 30 seconds
        "max_retries": 3,
        "dead_letter_queue": "password_reset_confirmation_emails_dead",
    },
    # Subscription Activated Email Queue
    {
        "name": "subscription_activated_emails",
        "handler": handle_subscription_activated_email,
        "retry_queue": "subscription_activated_emails_retry",
        "retry_ttl": 30 * 1000,  # 30 seconds
        "max_retries": 3,
        "dead_letter_queue": "subscription_activated_emails_dead",
    },
    # Subscription Canceled Email Queue
    {
        "name": "subscription_canceled_emails",
        "handler": handle_subscription_canceled_email,
        "retry_queue": "subscription_canceled_emails_retry",
        "retry_ttl": 30 * 1000,  # 30 seconds
        "max_retries": 3,
        "dead_letter_queue": "subscription_canceled_emails_dead",
    },
    # Payment Failed Email Queue
    {
        "name": "payment_failed_emails",
        "handler": handle_payment_failed_email,
        "retry_queue": "payment_failed_emails_retry",
        "retry_ttl": 30 * 1000,  # 30 seconds
        "max_retries": 3,
        "dead_letter_queue": "payment_failed_emails_dead",
    },
    # Workspace Invitation Email Queue
    {
        "name": "workspace_invitation_emails",
        "handler": handle_workspace_invitation_email,
        "retry_queue": "workspace_invitation_emails_retry",
        "retry_ttl": 30 * 1000,  # 30 seconds
        "max_retries": 3,
        "dead_letter_queue": "workspace_invitation_emails_dead",
    },
    # Stripe Checkout Completed - activates subscription after payment
    {
        "name": "stripe_checkout_completed",
        "handler": handle_stripe_checkout_completed,
        "retry_queue": "stripe_checkout_completed_retry",
        "retry_ttl": 60 * 1000,  # 1 minute
        "max_retries": 5,
        "dead_letter_queue": "stripe_checkout_completed_dead",
    },
    # Stripe Subscription Updated - syncs subscription status
    {
        "name": "stripe_subscription_updated",
        "handler": handle_stripe_subscription_updated,
        "retry_queue": "stripe_subscription_updated_retry",
        "retry_ttl": 60 * 1000,  # 1 minute
        "max_retries": 5,
        "dead_letter_queue": "stripe_subscription_updated_dead",
    },
    # Stripe Subscription Deleted - freezes workspace
    {
        "name": "stripe_subscription_deleted",
        "handler": handle_stripe_subscription_deleted,
        "retry_queue": "stripe_subscription_deleted_retry",
        "retry_ttl": 60 * 1000,  # 1 minute
        "max_retries": 5,
        "dead_letter_queue": "stripe_subscription_deleted_dead",
    },
    # Stripe Payment Failed - logs failure (subscription update comes separately)
    {
        "name": "stripe_payment_failed",
        "handler": handle_stripe_payment_failed,
        "retry_queue": "stripe_payment_failed_retry",
        "retry_ttl": 60 * 1000,  # 1 minute
        "max_retries": 3,
        "dead_letter_queue": "stripe_payment_failed_dead",
    },
    # Usage Commit Queue - processes usage commits from external servers
    {
        "name": "usage_commits",
        "handler": handle_usage_commit,
        "retry_queue": "usage_commits_retry",
        "retry_ttl": 30 * 1000,  # 30 seconds
        "max_retries": 3,
        "dead_letter_queue": "usage_commits_dead",
    },
]


@lru_cache()
def get_queue_configs() -> list[QueueConfig]:
    return [
        QueueConfig.model_validate(config, from_attributes=True)
        for config in QUEUE_CONFIG
    ]
