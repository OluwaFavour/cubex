"""
Test suite for EmailManagerService.

This module contains comprehensive tests for the EmailManagerService including:
- OTP email sending (verification, password reset)
- Welcome email sending
- Password reset confirmation email
- Template rendering integration
- Error handling and logging

Run all tests:
    pytest app/tests/services/test_email_manager.py -v

Run with coverage:
    pytest app/tests/services/test_email_manager.py --cov=app.shared.services.email_manager --cov-report=term-missing -v
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.shared.enums import OTPPurpose


class TestEmailManagerServiceInit:
    """Test suite for EmailManagerService initialization."""

    @pytest.fixture(autouse=True)
    def reset_service(self):
        """Reset EmailManagerService state after each test."""
        from app.shared.services.email_manager import EmailManagerService

        yield
        EmailManagerService._initialized = False

    def test_init_sets_initialized_flag(self):
        """Test that init sets the initialized flag."""
        from app.shared.services.email_manager import EmailManagerService

        EmailManagerService.init()

        assert EmailManagerService._initialized is True

    def test_init_is_idempotent(self):
        """Test that init can be called multiple times safely."""
        from app.shared.services.email_manager import EmailManagerService

        EmailManagerService.init()
        EmailManagerService.init()

        assert EmailManagerService._initialized is True

    def test_is_initialized_returns_correct_state(self):
        """Test that is_initialized returns correct state."""
        from app.shared.services.email_manager import EmailManagerService

        assert EmailManagerService.is_initialized() is False

        EmailManagerService.init()

        assert EmailManagerService.is_initialized() is True


class TestSendOtpEmail:
    """Test suite for send_otp_email method."""

    @pytest.fixture(autouse=True)
    def reset_service(self):
        """Reset EmailManagerService state after each test."""
        from app.shared.services.email_manager import EmailManagerService

        EmailManagerService._initialized = True
        yield
        EmailManagerService._initialized = False

    @pytest.mark.asyncio
    async def test_send_otp_email_for_verification(self):
        """Test sending OTP email for email verification."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo:
            # Setup mocks
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>OTP: 123456</html>", "OTP: 123456"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "test-123"}
            )

            result = await EmailManagerService.send_otp_email(
                email="user@example.com",
                user_name="John Doe",
                otp_code="123456",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            assert result is True
            assert mock_renderer.render_template.call_count == 2
            mock_brevo.send_transactional_email.assert_called_once()

            # Verify template was called with correct context
            html_call = mock_renderer.render_template.call_args_list[0]
            assert html_call[0][0] == "otp_email.html"
            assert html_call[1]["context"]["otp_code"] == "123456"
            assert html_call[1]["context"]["user_name"] == "John Doe"
            assert html_call[1]["context"]["purpose"] == "email verification"

    @pytest.mark.asyncio
    async def test_send_otp_email_for_password_reset(self):
        """Test sending OTP email for password reset."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo:
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>Reset OTP</html>", "Reset OTP"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "test-456"}
            )

            result = await EmailManagerService.send_otp_email(
                email="user@example.com",
                user_name="Jane Doe",
                otp_code="654321",
                purpose=OTPPurpose.PASSWORD_RESET,
            )

            assert result is True

            # Verify purpose is correctly passed
            html_call = mock_renderer.render_template.call_args_list[0]
            assert html_call[1]["context"]["purpose"] == "password reset"

    @pytest.mark.asyncio
    async def test_send_otp_email_default_user_name(self):
        """Test sending OTP email with default user name."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo:
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>OTP</html>", "OTP"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "test-789"}
            )

            result = await EmailManagerService.send_otp_email(
                email="user@example.com",
                otp_code="111222",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            assert result is True

            html_call = mock_renderer.render_template.call_args_list[0]
            assert html_call[1]["context"]["user_name"] == "User"

    @pytest.mark.asyncio
    async def test_send_otp_email_includes_app_name(self):
        """Test that OTP email includes app name from settings."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo, patch(
            "app.shared.services.email_manager.settings"
        ) as mock_settings:
            mock_settings.APP_NAME = "TestApp"
            mock_settings.OTP_EXPIRY_MINUTES = 10
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>OTP</html>", "OTP"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "test"}
            )

            await EmailManagerService.send_otp_email(
                email="user@example.com",
                otp_code="123456",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            html_call = mock_renderer.render_template.call_args_list[0]
            assert html_call[1]["context"]["app_name"] == "TestApp"
            assert html_call[1]["context"]["expiry_minutes"] == 10

    @pytest.mark.asyncio
    async def test_send_otp_email_includes_year(self):
        """Test that OTP email includes current year."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo:
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>OTP</html>", "OTP"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "test"}
            )

            await EmailManagerService.send_otp_email(
                email="user@example.com",
                otp_code="123456",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            html_call = mock_renderer.render_template.call_args_list[0]
            assert html_call[1]["context"]["year"] == datetime.now().year

    @pytest.mark.asyncio
    async def test_send_otp_email_correct_subject_for_verification(self):
        """Test that verification email has correct subject."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo, patch(
            "app.shared.services.email_manager.settings"
        ) as mock_settings:
            mock_settings.APP_NAME = "MyApp"
            mock_settings.OTP_EXPIRY_MINUTES = 10
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>OTP</html>", "OTP"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "test"}
            )

            await EmailManagerService.send_otp_email(
                email="user@example.com",
                otp_code="123456",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            brevo_call = mock_brevo.send_transactional_email.call_args
            assert brevo_call[1]["subject"] == "Verify Your Email - MyApp"

    @pytest.mark.asyncio
    async def test_send_otp_email_correct_subject_for_password_reset(self):
        """Test that password reset email has correct subject."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo, patch(
            "app.shared.services.email_manager.settings"
        ) as mock_settings:
            mock_settings.APP_NAME = "MyApp"
            mock_settings.OTP_EXPIRY_MINUTES = 10
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>OTP</html>", "OTP"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "test"}
            )

            await EmailManagerService.send_otp_email(
                email="user@example.com",
                otp_code="123456",
                purpose=OTPPurpose.PASSWORD_RESET,
            )

            brevo_call = mock_brevo.send_transactional_email.call_args
            assert brevo_call[1]["subject"] == "Password Reset - MyApp"

    @pytest.mark.asyncio
    async def test_send_otp_email_handles_brevo_failure(self):
        """Test handling of Brevo service failure."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo:
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>OTP</html>", "OTP"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                side_effect=Exception("Brevo API error")
            )

            result = await EmailManagerService.send_otp_email(
                email="user@example.com",
                otp_code="123456",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_otp_email_handles_template_failure(self):
        """Test handling of template rendering failure."""
        from app.shared.services.email_manager import EmailManagerService

        with patch("app.shared.services.email_manager.Renderer") as mock_renderer:
            mock_renderer.render_template = AsyncMock(
                side_effect=Exception("Template not found")
            )

            result = await EmailManagerService.send_otp_email(
                email="user@example.com",
                otp_code="123456",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            assert result is False


class TestSendWelcomeEmail:
    """Test suite for send_welcome_email method."""

    @pytest.fixture(autouse=True)
    def reset_service(self):
        """Reset EmailManagerService state after each test."""
        from app.shared.services.email_manager import EmailManagerService

        EmailManagerService._initialized = True
        yield
        EmailManagerService._initialized = False

    @pytest.mark.asyncio
    async def test_send_welcome_email_success(self):
        """Test successful welcome email sending."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo, patch(
            "app.shared.services.email_manager.settings"
        ) as mock_settings:
            mock_settings.APP_NAME = "CueBX"
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>Welcome</html>", "Welcome"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "welcome-123"}
            )

            result = await EmailManagerService.send_welcome_email(
                email="newuser@example.com",
                user_name="New User",
            )

            assert result is True
            assert mock_renderer.render_template.call_count == 2

            # Verify HTML template call
            html_call = mock_renderer.render_template.call_args_list[0]
            assert html_call[0][0] == "welcome_email.html"
            assert html_call[1]["context"]["user_name"] == "New User"
            assert html_call[1]["context"]["app_name"] == "CueBX"

            # Verify Brevo was called with correct subject
            brevo_call = mock_brevo.send_transactional_email.call_args
            assert brevo_call[1]["subject"] == "Welcome to CueBX!"

    @pytest.mark.asyncio
    async def test_send_welcome_email_default_user_name(self):
        """Test welcome email with default user name."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo:
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>Welcome</html>", "Welcome"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "welcome-456"}
            )

            result = await EmailManagerService.send_welcome_email(
                email="newuser@example.com",
            )

            assert result is True

            html_call = mock_renderer.render_template.call_args_list[0]
            assert html_call[1]["context"]["user_name"] == "User"

    @pytest.mark.asyncio
    async def test_send_welcome_email_handles_failure(self):
        """Test handling of welcome email failure."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo:
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>Welcome</html>", "Welcome"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                side_effect=Exception("Email sending failed")
            )

            result = await EmailManagerService.send_welcome_email(
                email="newuser@example.com",
                user_name="New User",
            )

            assert result is False


class TestSendPasswordResetConfirmationEmail:
    """Test suite for send_password_reset_confirmation_email method."""

    @pytest.fixture(autouse=True)
    def reset_service(self):
        """Reset EmailManagerService state after each test."""
        from app.shared.services.email_manager import EmailManagerService

        EmailManagerService._initialized = True
        yield
        EmailManagerService._initialized = False

    @pytest.mark.asyncio
    async def test_send_password_reset_confirmation_success(self):
        """Test successful password reset confirmation email."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo, patch(
            "app.shared.services.email_manager.settings"
        ) as mock_settings:
            mock_settings.APP_NAME = "CueBX"
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>Password changed</html>", "Password changed"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "reset-123"}
            )

            result = await EmailManagerService.send_password_reset_confirmation_email(
                email="user@example.com",
                user_name="Existing User",
            )

            assert result is True

            # Verify template was called correctly
            html_call = mock_renderer.render_template.call_args_list[0]
            assert html_call[0][0] == "password_reset_confirmation_email.html"
            assert html_call[1]["context"]["user_name"] == "Existing User"

            # Verify subject
            brevo_call = mock_brevo.send_transactional_email.call_args
            assert brevo_call[1]["subject"] == "Password Changed Successfully - CueBX"

    @pytest.mark.asyncio
    async def test_send_password_reset_confirmation_handles_failure(self):
        """Test handling of password reset confirmation email failure."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo:
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>Changed</html>", "Changed"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                side_effect=Exception("Failed")
            )

            result = await EmailManagerService.send_password_reset_confirmation_email(
                email="user@example.com",
                user_name="User",
            )

            assert result is False


class TestSendGenericEmail:
    """Test suite for send_email generic method."""

    @pytest.fixture(autouse=True)
    def reset_service(self):
        """Reset EmailManagerService state after each test."""
        from app.shared.services.email_manager import EmailManagerService

        EmailManagerService._initialized = True
        yield
        EmailManagerService._initialized = False

    @pytest.mark.asyncio
    async def test_send_email_with_custom_template(self):
        """Test sending email with custom template."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo:
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>Custom</html>", "Custom"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "custom-123"}
            )

            result = await EmailManagerService.send_email(
                email="user@example.com",
                subject="Custom Subject",
                html_template="custom_email.html",
                text_template="custom_email.txt",
                context={"custom_var": "custom_value"},
            )

            assert result is True

            # Verify custom template was used
            html_call = mock_renderer.render_template.call_args_list[0]
            assert html_call[0][0] == "custom_email.html"
            assert html_call[1]["context"]["custom_var"] == "custom_value"

            text_call = mock_renderer.render_template.call_args_list[1]
            assert text_call[0][0] == "custom_email.txt"

    @pytest.mark.asyncio
    async def test_send_email_passes_recipient_correctly(self):
        """Test that email is sent to correct recipient."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo:
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>Test</html>", "Test"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "test-123"}
            )

            await EmailManagerService.send_email(
                email="recipient@example.com",
                subject="Test Subject",
                html_template="test.html",
                text_template="test.txt",
                context={},
            )

            brevo_call = mock_brevo.send_transactional_email.call_args
            to_list = brevo_call[1]["to"]
            assert len(to_list.to) == 1
            assert to_list.to[0].email == "recipient@example.com"

    @pytest.mark.asyncio
    async def test_send_email_with_recipient_name(self):
        """Test sending email with recipient name."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo:
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>Test</html>", "Test"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "test-123"}
            )

            await EmailManagerService.send_email(
                email="recipient@example.com",
                subject="Test Subject",
                html_template="test.html",
                text_template="test.txt",
                context={},
                recipient_name="John Doe",
            )

            brevo_call = mock_brevo.send_transactional_email.call_args
            to_list = brevo_call[1]["to"]
            assert to_list.to[0].name == "John Doe"

    @pytest.mark.asyncio
    async def test_send_email_html_only(self):
        """Test sending email with HTML content only."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo:
            mock_renderer.render_template = AsyncMock(
                return_value="<html>HTML Only</html>"
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "html-only-123"}
            )

            result = await EmailManagerService.send_email(
                email="user@example.com",
                subject="HTML Only",
                html_template="html_only.html",
                context={},
            )

            assert result is True
            assert mock_renderer.render_template.call_count == 1

    @pytest.mark.asyncio
    async def test_send_email_logs_on_success(self):
        """Test that successful email sending is logged."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo, patch(
            "app.shared.services.email_manager.email_manager_logger"
        ) as mock_logger:
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>Test</html>", "Test"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                return_value={"messageId": "logged-123"}
            )

            await EmailManagerService.send_email(
                email="user@example.com",
                subject="Log Test",
                html_template="test.html",
                text_template="test.txt",
                context={},
            )

            mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_send_email_logs_on_failure(self):
        """Test that failed email sending is logged as error."""
        from app.shared.services.email_manager import EmailManagerService

        with patch(
            "app.shared.services.email_manager.Renderer"
        ) as mock_renderer, patch(
            "app.shared.services.email_manager.BrevoService"
        ) as mock_brevo, patch(
            "app.shared.services.email_manager.email_manager_logger"
        ) as mock_logger:
            mock_renderer.render_template = AsyncMock(
                side_effect=["<html>Test</html>", "Test"]
            )
            mock_brevo.send_transactional_email = AsyncMock(
                side_effect=Exception("Send failed")
            )

            await EmailManagerService.send_email(
                email="user@example.com",
                subject="Error Test",
                html_template="test.html",
                text_template="test.txt",
                context={},
            )

            mock_logger.error.assert_called()


class TestPurposeMapping:
    """Test suite for OTP purpose to display text mapping."""

    def test_get_purpose_display_text_email_verification(self):
        """Test display text for email verification purpose."""
        from app.shared.services.email_manager import EmailManagerService

        text = EmailManagerService._get_purpose_display_text(
            OTPPurpose.EMAIL_VERIFICATION
        )
        assert text == "email verification"

    def test_get_purpose_display_text_password_reset(self):
        """Test display text for password reset purpose."""
        from app.shared.services.email_manager import EmailManagerService

        text = EmailManagerService._get_purpose_display_text(OTPPurpose.PASSWORD_RESET)
        assert text == "password reset"

    def test_get_subject_for_purpose_email_verification(self):
        """Test email subject for email verification."""
        from app.shared.services.email_manager import EmailManagerService

        with patch("app.shared.services.email_manager.settings") as mock_settings:
            mock_settings.APP_NAME = "TestApp"

            subject = EmailManagerService._get_subject_for_purpose(
                OTPPurpose.EMAIL_VERIFICATION
            )
            assert subject == "Verify Your Email - TestApp"

    def test_get_subject_for_purpose_password_reset(self):
        """Test email subject for password reset."""
        from app.shared.services.email_manager import EmailManagerService

        with patch("app.shared.services.email_manager.settings") as mock_settings:
            mock_settings.APP_NAME = "TestApp"

            subject = EmailManagerService._get_subject_for_purpose(
                OTPPurpose.PASSWORD_RESET
            )
            assert subject == "Password Reset - TestApp"


class TestEmailManagerAllExports:
    """Test suite for module exports."""

    def test_all_exports(self):
        """Test that __all__ contains expected exports."""
        from app.shared.services import email_manager

        assert hasattr(email_manager, "__all__")
        assert "EmailManagerService" in email_manager.__all__
