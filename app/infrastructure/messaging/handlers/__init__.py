"""
Message handlers for the messaging infrastructure.

This module contains handlers for processing messages from various queues:
- email_handler: Handles OTP and other email sending tasks
"""

from app.infrastructure.messaging.handlers.email_handler import (
    handle_otp_email,
    handle_password_reset_confirmation_email,
)

__all__ = ["handle_otp_email", "handle_password_reset_confirmation_email"]
