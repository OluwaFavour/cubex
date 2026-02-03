"""
Email message handlers for async email processing.

This module contains handlers for processing email-related messages from queues.
Emails are sent asynchronously to avoid blocking the main request flow.
"""

from typing import Any

from app.shared.config import auth_logger, stripe_logger
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


async def handle_subscription_activated_email(event: dict[str, Any]) -> None:
    """
    Handle subscription activated email sending events.

    Sends a confirmation email when a subscription becomes active.

    Args:
        event: Event data containing:
            - email (str): Recipient email address
            - user_name (str | None): Optional user name for personalization
            - plan_name (str | None): Name of the subscribed plan
            - workspace_name (str | None): Name of the workspace (for API subscriptions)
            - seat_count (int | None): Number of seats in the subscription
            - product_name (str): Product name (e.g., "Cubex API", "Cubex Career")

    Raises:
        Exception: If email sending fails, exception is raised to trigger retry.
    """
    email = event["email"]
    user_name = event.get("user_name")
    plan_name = event.get("plan_name")
    workspace_name = event.get("workspace_name")
    seat_count = event.get("seat_count")
    product_name = event.get("product_name", "Cubex")

    stripe_logger.info(f"Processing subscription activated email: email={email}")

    try:
        result = await EmailManagerService.send_subscription_activated_email(
            email=email,
            user_name=user_name,
            plan_name=plan_name,
            workspace_name=workspace_name,
            seat_count=seat_count,
            product_name=product_name,
        )

        if result:
            stripe_logger.info(
                f"Subscription activated email sent successfully: email={email}"
            )
        else:
            stripe_logger.warning(
                f"Subscription activated email service returned False: email={email}"
            )
            raise Exception(f"Email service failed for {email}")

    except Exception as e:
        stripe_logger.error(
            f"Failed to send subscription activated email: email={email}, error={e}"
        )
        raise  # Re-raise to trigger retry mechanism


async def handle_subscription_canceled_email(event: dict[str, Any]) -> None:
    """
    Handle subscription canceled email sending events.

    Sends a notification email when a subscription is canceled.

    Args:
        event: Event data containing:
            - email (str): Recipient email address
            - user_name (str | None): Optional user name for personalization
            - plan_name (str | None): Name of the canceled plan
            - workspace_name (str | None): Name of the workspace (for API subscriptions)
            - product_name (str): Product name (e.g., "Cubex API", "Cubex Career")

    Raises:
        Exception: If email sending fails, exception is raised to trigger retry.
    """
    email = event["email"]
    user_name = event.get("user_name")
    plan_name = event.get("plan_name")
    workspace_name = event.get("workspace_name")
    product_name = event.get("product_name", "Cubex")

    stripe_logger.info(f"Processing subscription canceled email: email={email}")

    try:
        result = await EmailManagerService.send_subscription_canceled_email(
            email=email,
            user_name=user_name,
            plan_name=plan_name,
            workspace_name=workspace_name,
            product_name=product_name,
        )

        if result:
            stripe_logger.info(
                f"Subscription canceled email sent successfully: email={email}"
            )
        else:
            stripe_logger.warning(
                f"Subscription canceled email service returned False: email={email}"
            )
            raise Exception(f"Email service failed for {email}")

    except Exception as e:
        stripe_logger.error(
            f"Failed to send subscription canceled email: email={email}, error={e}"
        )
        raise  # Re-raise to trigger retry mechanism


async def handle_payment_failed_email(event: dict[str, Any]) -> None:
    """
    Handle payment failed email sending events.

    Sends a notification email when a subscription payment fails.

    Args:
        event: Event data containing:
            - email (str): Recipient email address
            - user_name (str | None): Optional user name for personalization
            - plan_name (str | None): Name of the plan
            - workspace_name (str | None): Name of the workspace (for API subscriptions)
            - amount (str | None): Payment amount that failed
            - update_payment_url (str | None): URL to update payment method
            - product_name (str): Product name (e.g., "Cubex API", "Cubex Career")

    Raises:
        Exception: If email sending fails, exception is raised to trigger retry.
    """
    email = event["email"]
    user_name = event.get("user_name")
    plan_name = event.get("plan_name")
    workspace_name = event.get("workspace_name")
    amount = event.get("amount")
    update_payment_url = event.get("update_payment_url")
    product_name = event.get("product_name", "Cubex")

    stripe_logger.info(f"Processing payment failed email: email={email}")

    try:
        result = await EmailManagerService.send_payment_failed_email(
            email=email,
            user_name=user_name,
            plan_name=plan_name,
            workspace_name=workspace_name,
            amount=amount,
            update_payment_url=update_payment_url,
            product_name=product_name,
        )

        if result:
            stripe_logger.info(f"Payment failed email sent successfully: email={email}")
        else:
            stripe_logger.warning(
                f"Payment failed email service returned False: email={email}"
            )
            raise Exception(f"Email service failed for {email}")

    except Exception as e:
        stripe_logger.error(
            f"Failed to send payment failed email: email={email}, error={e}"
        )
        raise  # Re-raise to trigger retry mechanism
