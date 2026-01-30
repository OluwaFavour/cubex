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
from typing import Any

from app.shared.config import email_manager_logger, settings
from app.shared.enums import OTPPurpose
from app.shared.services.brevo import BrevoService
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
            recipient = {"email": email}
            if recipient_name:
                recipient["name"] = recipient_name

            # Send via Brevo
            await BrevoService.send_transactional_email(
                recipients=[recipient],
                subject=subject,
                html_content=html_content,
                text_content=text_content,
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
