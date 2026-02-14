"""
Message handlers for the messaging infrastructure.

This module contains handlers for processing messages from various queues:
- email_handler: Handles OTP and other email sending tasks
- stripe: Handles Stripe webhook events (checkout, subscription changes, etc.)
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

__all__ = [
    "handle_otp_email",
    "handle_password_reset_confirmation_email",
    "handle_stripe_checkout_completed",
    "handle_stripe_subscription_updated",
    "handle_stripe_subscription_deleted",
    "handle_stripe_payment_failed",
]
