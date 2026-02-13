"""
Email Manager Service for centralized email sending.

This module provides a unified interface for sending various types of emails
including OTP verification, welcome emails, and password reset confirmations.
It leverages the BrevoService for actual email delivery and the Renderer
for template rendering.

Example usage:
    # Initialize the service
    EmailManagerService.init()

    # Send OTP email
    await EmailManagerService.send_otp_email(
        email="user@example.com",
        user_name="John",
        otp_code="123456",
        purpose=OTPPurpose.EMAIL_VERIFICATION,
    )

    # Send welcome email
    await EmailManagerService.send_welcome_email(
        email="user@example.com",
        user_name="John",
    )
"""

from datetime import datetime
import json
from typing import Any

from app.shared.config import email_manager_logger, settings
from app.shared.enums import OTPPurpose
from app.shared.services.brevo import BrevoService, Contact, ListContact
from app.shared.services.template import Renderer


__all__ = ["EmailManagerService"]


class EmailManagerService:
    """
    Centralized email management service.

    This class provides a unified interface for sending various types of emails
    using the BrevoService for delivery and Jinja2 templates for content rendering.
    It follows the singleton pattern with class methods.

    Attributes:
        _initialized: Flag indicating whether the service has been initialized.

    Example:
        >>> EmailManagerService.init()
        >>> await EmailManagerService.send_otp_email(
        ...     email="user@example.com",
        ...     otp_code="123456",
        ...     purpose=OTPPurpose.EMAIL_VERIFICATION,
        ... )
        True
    """

    _initialized: bool = False

    @classmethod
    def init(cls) -> None:
        """
        Initialize the EmailManagerService.

        This method marks the service as initialized. It should be called
        during application startup after BrevoService and Renderer are
        initialized.

        Returns:
            None
        """
        cls._initialized = True
        email_manager_logger.info("EmailManagerService initialized")

    @classmethod
    def is_initialized(cls) -> bool:
        """
        Check if the service has been initialized.

        Returns:
            bool: True if initialized, False otherwise.
        """
        return cls._initialized

    @classmethod
    def _get_purpose_display_text(cls, purpose: OTPPurpose) -> str:
        """
        Get human-readable display text for an OTP purpose.

        Args:
            purpose: The OTP purpose enum value.

        Returns:
            str: Human-readable purpose text.
        """
        purpose_map = {
            OTPPurpose.EMAIL_VERIFICATION: "email verification",
            OTPPurpose.PASSWORD_RESET: "password reset",
        }
        return purpose_map.get(purpose, "verification")

    @classmethod
    def _get_subject_for_purpose(cls, purpose: OTPPurpose) -> str:
        """
        Get email subject line for an OTP purpose.

        Args:
            purpose: The OTP purpose enum value.

        Returns:
            str: Email subject line including app name.
        """
        subject_map = {
            OTPPurpose.EMAIL_VERIFICATION: f"Verify Your Email - {settings.APP_NAME}",
            OTPPurpose.PASSWORD_RESET: f"Password Reset - {settings.APP_NAME}",
        }
        return subject_map.get(purpose, f"Verification Code - {settings.APP_NAME}")

    @classmethod
    async def send_email(
        cls,
        email: str,
        subject: str,
        html_template: str,
        context: dict[str, Any],
        text_template: str | None = None,
        recipient_name: str | None = None,
    ) -> bool:
        """
        Send an email using a custom template.

        This is the base method for sending emails. It renders the provided
        templates with the given context and sends the email via BrevoService.

        Args:
            email: Recipient email address.
            subject: Email subject line.
            html_template: Name of the HTML template file.
            context: Dictionary of context variables for template rendering.
            text_template: Optional name of the plain text template file.
            recipient_name: Optional recipient name for personalization.

        Returns:
            bool: True if email was sent successfully, False otherwise.

        Example:
            >>> await EmailManagerService.send_email(
            ...     email="user@example.com",
            ...     subject="Custom Email",
            ...     html_template="custom.html",
            ...     context={"message": "Hello!"},
            ... )
            True
        """
        try:
            # Render HTML template
            html_content = await Renderer.render_template(
                html_template, context=context
            )

            # Render text template if provided
            text_content = None
            if text_template:
                text_content = await Renderer.render_template(
                    text_template, context=context
                )

            # Prepare recipient
            recipient = Contact(email=email, name=recipient_name)

            # Send via Brevo
            await BrevoService.send_transactional_email(
                to=ListContact(to=[recipient]),
                subject=subject,
                htmlContent=html_content,
                textContent=text_content,
            )

            email_manager_logger.info(
                f"Email sent successfully: subject='{subject}', to='{email}'"
            )
            return True

        except Exception as e:
            email_manager_logger.error(
                f"Failed to send email: subject='{subject}', to='{email}', error={e}"
            )
            return False

    @classmethod
    async def send_otp_email(
        cls,
        email: str,
        otp_code: str,
        purpose: OTPPurpose,
        user_name: str | None = None,
    ) -> bool:
        """
        Send an OTP verification email.

        Sends an email containing a one-time password code for verification
        or password reset purposes.

        Args:
            email: Recipient email address.
            otp_code: The OTP code to include in the email.
            purpose: The purpose of the OTP (verification or password reset).
            user_name: Optional recipient name for personalization.

        Returns:
            bool: True if email was sent successfully, False otherwise.

        Example:
            >>> await EmailManagerService.send_otp_email(
            ...     email="user@example.com",
            ...     otp_code="123456",
            ...     purpose=OTPPurpose.EMAIL_VERIFICATION,
            ...     user_name="John",
            ... )
            True
        """
        display_name = user_name or "User"
        purpose_text = cls._get_purpose_display_text(purpose)
        subject = cls._get_subject_for_purpose(purpose)

        context = {
            "app_name": settings.APP_NAME,
            "user_name": display_name,
            "otp_code": otp_code,
            "expiry_minutes": settings.OTP_EXPIRY_MINUTES,
            "purpose": purpose_text,
            "year": datetime.now().year,
        }

        return await cls.send_email(
            email=email,
            subject=subject,
            html_template="otp_email.html",
            text_template="otp_email.txt",
            context=context,
            recipient_name=display_name,
        )

    @classmethod
    async def send_welcome_email(
        cls,
        email: str,
        user_name: str | None = None,
    ) -> bool:
        """
        Send a welcome email to a new user.

        Sends a welcome email after successful account creation.

        Args:
            email: Recipient email address.
            user_name: Optional recipient name for personalization.

        Returns:
            bool: True if email was sent successfully, False otherwise.

        Example:
            >>> await EmailManagerService.send_welcome_email(
            ...     email="newuser@example.com",
            ...     user_name="John",
            ... )
            True
        """
        display_name = user_name or "User"

        context = {
            "app_name": settings.APP_NAME,
            "user_name": display_name,
            "year": datetime.now().year,
        }

        return await cls.send_email(
            email=email,
            subject=f"Welcome to {settings.APP_NAME}!",
            html_template="welcome_email.html",
            text_template="welcome_email.txt",
            context=context,
            recipient_name=display_name,
        )

    @classmethod
    async def send_password_reset_confirmation_email(
        cls,
        email: str,
        user_name: str | None = None,
    ) -> bool:
        """
        Send a password reset confirmation email.

        Sends an email confirming that the user's password has been
        successfully changed. This serves as a security notification.

        Args:
            email: Recipient email address.
            user_name: Optional recipient name for personalization.

        Returns:
            bool: True if email was sent successfully, False otherwise.

        Example:
            >>> await EmailManagerService.send_password_reset_confirmation_email(
            ...     email="user@example.com",
            ...     user_name="John",
            ... )
            True
        """
        display_name = user_name or "User"

        context = {
            "app_name": settings.APP_NAME,
            "user_name": display_name,
            "year": datetime.now().year,
        }

        return await cls.send_email(
            email=email,
            subject=f"Password Changed Successfully - {settings.APP_NAME}",
            html_template="password_reset_confirmation_email.html",
            text_template="password_reset_confirmation_email.txt",
            context=context,
            recipient_name=display_name,
        )

    @classmethod
    async def send_subscription_activated_email(
        cls,
        email: str,
        user_name: str | None = None,
        plan_name: str | None = None,
        workspace_name: str | None = None,
        seat_count: int | None = None,
        product_name: str = "Cubex",
    ) -> bool:
        """
        Send a subscription activation confirmation email.

        Notifies the user when their subscription becomes active.

        Args:
            email: Recipient email address.
            user_name: Recipient name for personalization.
            plan_name: Name of the subscribed plan.
            workspace_name: Name of the workspace (for API subscriptions).
            seat_count: Number of seats in the subscription (for API subscriptions).
            product_name: Product name (e.g., "Cubex API", "Cubex Career").

        Returns:
            bool: True if email was sent successfully, False otherwise.

        Example:
            >>> await EmailManagerService.send_subscription_activated_email(
            ...     email="owner@example.com",
            ...     user_name="John",
            ...     plan_name="Pro",
            ...     workspace_name="Acme Corp",
            ...     seat_count=5,
            ...     product_name="Cubex API",
            ... )
            True
        """
        display_name = user_name or "User"

        context = {
            "name": display_name,
            "plan_name": plan_name or "your plan",
            "workspace_name": workspace_name,
            "seat_count": seat_count,
            "product_name": product_name,
        }

        return await cls.send_email(
            email=email,
            subject=f"Your {product_name} Subscription is Active - {settings.APP_NAME}",
            html_template="subscription_activated.html",
            text_template="subscription_activated.txt",
            context=context,
            recipient_name=display_name,
        )

    @classmethod
    async def send_subscription_canceled_email(
        cls,
        email: str,
        user_name: str | None = None,
        plan_name: str | None = None,
        workspace_name: str | None = None,
        product_name: str = "Cubex",
    ) -> bool:
        """
        Send a subscription cancellation confirmation email.

        Notifies the user when their subscription is canceled.

        Args:
            email: Recipient email address.
            user_name: Recipient name for personalization.
            plan_name: Name of the canceled plan.
            workspace_name: Name of the workspace (for API subscriptions).
            product_name: Product name (e.g., "Cubex API", "Cubex Career").

        Returns:
            bool: True if email was sent successfully, False otherwise.

        Example:
            >>> await EmailManagerService.send_subscription_canceled_email(
            ...     email="owner@example.com",
            ...     user_name="John",
            ...     plan_name="Pro",
            ...     workspace_name="Acme Corp",
            ...     product_name="Cubex API",
            ... )
            True
        """
        display_name = user_name or "User"

        context = {
            "name": display_name,
            "plan_name": plan_name or "your plan",
            "workspace_name": workspace_name,
            "product_name": product_name,
        }

        return await cls.send_email(
            email=email,
            subject=f"{product_name} Subscription Canceled - {settings.APP_NAME}",
            html_template="subscription_canceled.html",
            text_template="subscription_canceled.txt",
            context=context,
            recipient_name=display_name,
        )

    @classmethod
    async def send_payment_failed_email(
        cls,
        email: str,
        user_name: str | None = None,
        plan_name: str | None = None,
        workspace_name: str | None = None,
        amount: str | None = None,
        update_payment_url: str | None = None,
        product_name: str = "Cubex",
    ) -> bool:
        """
        Send a payment failure notification email.

        Notifies the user when a subscription payment fails.

        Args:
            email: Recipient email address.
            user_name: Recipient name for personalization.
            plan_name: Name of the plan.
            workspace_name: Name of the workspace (for API subscriptions).
            amount: Payment amount that failed.
            update_payment_url: URL to update payment method.
            product_name: Product name (e.g., "Cubex API", "Cubex Career").

        Returns:
            bool: True if email was sent successfully, False otherwise.

        Example:
            >>> await EmailManagerService.send_payment_failed_email(
            ...     email="owner@example.com",
            ...     user_name="John",
            ...     plan_name="Pro",
            ...     workspace_name="Acme Corp",
            ...     amount="49.00",
            ...     update_payment_url="https://app.cubex.com/billing",
            ...     product_name="Cubex API",
            ... )
            True
        """
        display_name = user_name or "User"

        context = {
            "name": display_name,
            "plan_name": plan_name or "your plan",
            "workspace_name": workspace_name,
            "amount": amount or "N/A",
            "update_payment_url": update_payment_url or "#",
            "product_name": product_name,
        }

        return await cls.send_email(
            email=email,
            subject=f"{product_name} Payment Failed - Action Required - {settings.APP_NAME}",
            html_template="payment_failed.html",
            text_template="payment_failed.txt",
            context=context,
            recipient_name=display_name,
        )

    @classmethod
    async def send_workspace_invitation_email(
        cls,
        email: str,
        inviter_name: str,
        workspace_name: str,
        role: str,
        invitation_link: str,
        expiry_hours: int = 72,
    ) -> bool:
        """
        Send a workspace invitation email.

        Notifies a user that they've been invited to join a workspace.

        Args:
            email: Recipient email address (invitee).
            inviter_name: Name of the person sending the invitation.
            workspace_name: Name of the workspace.
            role: Role being offered (e.g., "Admin", "Member").
            invitation_link: Full URL to accept the invitation.
            expiry_hours: Hours until invitation expires (default: 72).

        Returns:
            bool: True if email was sent successfully, False otherwise.

        Example:
            >>> await EmailManagerService.send_workspace_invitation_email(
            ...     email="newmember@example.com",
            ...     inviter_name="John Doe",
            ...     workspace_name="Acme Corp",
            ...     role="Member",
            ...     invitation_link="https://app.cubex.com/invites/accept/abc123",
            ...     expiry_hours=72,
            ... )
            True
        """
        context = {
            "app_name": settings.APP_NAME,
            "invitee_email": email,
            "inviter_name": inviter_name,
            "workspace_name": workspace_name,
            "role": role,
            "invitation_link": invitation_link,
            "expiry_hours": expiry_hours,
            "year": datetime.now().year,
        }

        return await cls.send_email(
            email=email,
            subject=f"You're invited to join {workspace_name} - {settings.APP_NAME}",
            html_template="workspace_invitation.html",
            text_template="workspace_invitation.txt",
            context=context,
        )

    @classmethod
    async def send_dlq_alert(
        cls,
        queue_name: str,
        message_body: str,
        attempt_count: int,
    ) -> bool:
        """
        Send a Dead Letter Queue alert email to admin.

        Notifies the admin when a message is moved to a DLQ after
        exhausting all retry attempts.

        Args:
            queue_name: Name of the queue that dead-lettered the message.
            message_body: The message content (JSON string or dict).
            attempt_count: Number of retry attempts made.

        Returns:
            bool: True if email was sent successfully, False otherwise.
        """
        admin_email = settings.ADMIN_ALERT_EMAIL
        if not admin_email:
            email_manager_logger.warning(
                f"DLQ alert skipped: ADMIN_ALERT_EMAIL not configured. "
                f"Queue: {queue_name}"
            )
            return False

        # Format message body for display
        if isinstance(message_body, dict):
            formatted_body = json.dumps(message_body, indent=2, default=str)
        else:
            formatted_body = str(message_body)

        context = {
            "app_name": settings.APP_NAME,
            "queue_name": queue_name,
            "message_body": formatted_body,
            "attempt_count": attempt_count,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "environment": settings.SENTRY_ENVIRONMENT,
        }

        return await cls.send_email(
            email=admin_email,
            subject=f"[CUBEX ALERT] DLQ: {queue_name}",
            html_template="dlq_alert.html",
            text_template="dlq_alert.txt",
            context=context,
            recipient_name="Admin",
        )

    @classmethod
    async def send_invalid_payload_alert(
        cls,
        queue_name: str,
        message_body: Any,
        validation_errors: list[dict[str, Any]],
    ) -> bool:
        """
        Send an invalid payload alert email to admin.

        Notifies the admin when a message fails schema validation.
        This indicates a bug in the publishing service.

        Args:
            queue_name: Name of the queue that received the invalid message.
            message_body: The raw message content.
            validation_errors: List of Pydantic validation errors.

        Returns:
            bool: True if email was sent successfully, False otherwise.
        """
        admin_email = settings.ADMIN_ALERT_EMAIL
        if not admin_email:
            email_manager_logger.warning(
                f"Invalid payload alert skipped: ADMIN_ALERT_EMAIL not configured. "
                f"Queue: {queue_name}"
            )
            return False

        # Format message body for display
        if isinstance(message_body, dict):
            formatted_body = json.dumps(message_body, indent=2, default=str)
        else:
            formatted_body = str(message_body)

        context = {
            "app_name": settings.APP_NAME,
            "queue_name": queue_name,
            "message_body": formatted_body,
            "validation_errors": validation_errors,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "environment": settings.SENTRY_ENVIRONMENT,
        }

        return await cls.send_email(
            email=admin_email,
            subject=f"[CUBEX ALERT] Invalid Payload: {queue_name}",
            html_template="invalid_payload_alert.html",
            text_template="invalid_payload_alert.txt",
            context=context,
            recipient_name="Admin",
        )
