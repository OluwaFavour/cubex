"""
Email message handlers for async email processing.

This module contains handlers for processing email-related messages from queues.
Emails are sent asynchronously to avoid blocking the main request flow.
"""

from typing import Any

from app.shared.config import auth_logger
from app.shared.enums import OTPPurpose
from app.shared.services.email_manager import EmailManagerService


async def handle_otp_email(event: dict[str, Any]) -> None:
    """
    Handle OTP email sending events.

    This handler is idempotent - if an email has already been sent for a given
    OTP, calling this handler again will simply resend it (which is acceptable
    for OTPs as users may request resends).

    Args:
        event: Event data containing:
            - email (str): Recipient email address
            - otp_code (str): The OTP code to send
            - purpose (str): OTPPurpose value (e.g., "email_verification", "password_reset")
            - user_name (str | None): Optional user name for personalization

    Raises:
        Exception: If email sending fails, exception is raised to trigger retry.
    """
    email = event["email"]
    otp_code = event["otp_code"]
    purpose = OTPPurpose(event["purpose"])
    user_name = event.get("user_name")

    auth_logger.info(f"Processing OTP email: email={email}, purpose={purpose.value}")

    try:
        result = await EmailManagerService.send_otp_email(
            email=email,
            otp_code=otp_code,
            purpose=purpose,
            user_name=user_name,
        )

        if result:
            auth_logger.info(
                f"OTP email sent successfully: email={email}, purpose={purpose.value}"
            )
        else:
            # Email service returned False - might be a soft failure
            auth_logger.warning(
                f"OTP email service returned False: email={email}, purpose={purpose.value}"
            )
            raise Exception(f"Email service failed for {email}")

    except Exception as e:
        auth_logger.error(
            f"Failed to send OTP email: email={email}, purpose={purpose.value}, error={e}"
        )
        raise  # Re-raise to trigger retry mechanism


async def handle_password_reset_confirmation_email(event: dict[str, Any]) -> None:
    """
    Handle password reset confirmation email sending events.

    This handler sends a confirmation email after a password has been successfully reset.

    Args:
        event: Event data containing:
            - email (str): Recipient email address
            - user_name (str | None): Optional user name for personalization

    Raises:
        Exception: If email sending fails, exception is raised to trigger retry.
    """
    email = event["email"]
    user_name = event.get("user_name")

    auth_logger.info(f"Processing password reset confirmation email: email={email}")

    try:
        result = await EmailManagerService.send_password_reset_confirmation_email(
            email=email,
            user_name=user_name,
        )

        if result:
            auth_logger.info(
                f"Password reset confirmation email sent successfully: email={email}"
            )
        else:
            auth_logger.warning(
                f"Password reset confirmation email service returned False: email={email}"
            )
            raise Exception(f"Email service failed for {email}")

    except Exception as e:
        auth_logger.error(
            f"Failed to send password reset confirmation email: email={email}, error={e}"
        )
        raise  # Re-raise to trigger retry mechanism
