"""
Message handlers for the messaging infrastructure.

This module contains handlers for processing messages from various queues:
- email_handler: Handles OTP and other email sending tasks
- stripe: Handles Stripe webhook events (checkout, subscription changes, etc.)
- usage_handler: Handles API usage commit messages
- career_usage_handler: Handles career usage commit messages
"""

from app.infrastructure.messaging.handlers.email_handler import (
    handle_otp_email,
    handle_password_reset_confirmation_email,
)
from app.infrastructure.messaging.handlers.stripe import (
    handle_stripe_checkout_completed,
    handle_stripe_subscription_updated,
    handle_stripe_subscription_deleted,
    handle_stripe_payment_failed,
)
from app.infrastructure.messaging.handlers.career_usage_handler import (
    handle_career_usage_commit,
)

__all__ = [
    "handle_otp_email",
    "handle_password_reset_confirmation_email",
    "handle_stripe_checkout_completed",
    "handle_stripe_subscription_updated",
    "handle_stripe_subscription_deleted",
    "handle_stripe_payment_failed",
    "handle_career_usage_commit",
]
