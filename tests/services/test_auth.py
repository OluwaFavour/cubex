"""
Test suite for AuthService.

- Email signup with OTP verification
- Email signin with password
- OAuth authentication (Google, GitHub)
- OTP generation, sending, and verification
- Password reset flow
- Token generation

Run all tests:
    pytest app/tests/services/test_auth.py -v

Run with coverage:
    pytest app/tests/services/test_auth.py --cov=app.core.services.auth --cov-report=term-missing -v
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.enums import OAuthProviders, OTPPurpose
from app.core.exceptions.types import (
    AuthenticationException,
    InvalidCredentialsException,
    OAuthException,
    OTPInvalidException,
    TooManyAttemptsException,
)


class TestAuthServiceInit:

    @pytest.fixture(autouse=True)
    def reset_service(self):
        """Reset AuthService state after each test."""
        from app.core.services.auth import AuthService

        yield
        AuthService._initialized = False

    def test_init_sets_initialized_flag(self):
        from app.core.services.auth import AuthService

        AuthService.init()

        assert AuthService._initialized is True

    def test_init_is_idempotent(self):
        from app.core.services.auth import AuthService

        AuthService.init()
        AuthService.init()

        assert AuthService._initialized is True

    def test_is_initialized_returns_correct_state(self):
        from app.core.services.auth import AuthService

        assert AuthService.is_initialized() is False

        AuthService.init()

        assert AuthService.is_initialized() is True


class TestGenerateOTP:

    def test_generate_otp_returns_string(self):
        from app.core.services.auth import AuthService

        otp = AuthService.generate_otp()
        assert isinstance(otp, str)

    def test_generate_otp_default_length(self):
        from app.core.services.auth import AuthService

        with patch("app.core.services.auth.settings") as mock_settings:
            mock_settings.OTP_LENGTH = 6

            otp = AuthService.generate_otp()

            assert len(otp) == 6

    def test_generate_otp_custom_length(self):
        from app.core.services.auth import AuthService

        otp = AuthService.generate_otp(length=8)
        assert len(otp) == 8

    def test_generate_otp_only_digits(self):
        from app.core.services.auth import AuthService

        for _ in range(100):
            otp = AuthService.generate_otp()
            assert otp.isdigit()

    def test_generate_otp_is_random(self):
        from app.core.services.auth import AuthService

        otps = [AuthService.generate_otp() for _ in range(100)]
        # With 6 digits, should have many unique values
        assert len(set(otps)) > 50


class TestHashPassword:

    def test_hash_password_returns_string(self):
        from app.core.services.auth import AuthService

        hashed = AuthService.hash_password("password123")
        assert isinstance(hashed, str)

    def test_hash_password_different_from_input(self):
        from app.core.services.auth import AuthService

        password = "password123"
        hashed = AuthService.hash_password(password)
        assert hashed != password

    def test_hash_password_different_for_same_input(self):
        from app.core.services.auth import AuthService

        password = "password123"
        hash1 = AuthService.hash_password(password)
        hash2 = AuthService.hash_password(password)
        assert hash1 != hash2


class TestVerifyPassword:

    def test_verify_password_correct(self):
        from app.core.services.auth import AuthService

        password = "password123"
        hashed = AuthService.hash_password(password)

        assert AuthService.verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        from app.core.services.auth import AuthService

        password = "password123"
        hashed = AuthService.hash_password(password)

        assert AuthService.verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty(self):
        from app.core.services.auth import AuthService

        hashed = AuthService.hash_password("password123")
        assert AuthService.verify_password("", hashed) is False


class TestSendOTP:

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_send_otp_creates_token(self, mock_session):
        from app.core.services.auth import AuthService

        with (
            patch("app.core.services.auth.otp_token_db") as mock_otp_db,
            patch("app.core.services.auth.get_publisher", return_value=AsyncMock()),
            patch("app.core.services.auth.hmac_hash_otp") as mock_hash,
        ):
            mock_otp_db.invalidate_previous_tokens = AsyncMock(return_value=0)
            mock_otp_db.create = AsyncMock(return_value=MagicMock())

            mock_hash.return_value = "hashed_otp"

            result = await AuthService.send_otp(
                session=mock_session,
                email="user@example.com",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            assert result is True
            mock_otp_db.invalidate_previous_tokens.assert_called_once()
            mock_otp_db.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_otp_invalidates_previous_tokens(self, mock_session):
        from app.core.services.auth import AuthService

        with (
            patch("app.core.services.auth.otp_token_db") as mock_otp_db,
            patch("app.core.services.auth.get_publisher", return_value=AsyncMock()),
            patch("app.core.services.auth.hmac_hash_otp"),
        ):
            mock_otp_db.invalidate_previous_tokens = AsyncMock(return_value=2)
            mock_otp_db.create = AsyncMock(return_value=MagicMock())

            await AuthService.send_otp(
                session=mock_session,
                email="user@example.com",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            mock_otp_db.invalidate_previous_tokens.assert_called_once_with(
                session=mock_session,
                email="user@example.com",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
                commit_self=False,
            )

    @pytest.mark.asyncio
    async def test_send_otp_publishes_email_event(self, mock_session):
        from app.core.services.auth import AuthService

        mock_publisher = AsyncMock()
        with (
            patch("app.core.services.auth.otp_token_db") as mock_otp_db,
            patch("app.core.services.auth.get_publisher", return_value=mock_publisher),
            patch("app.core.services.auth.hmac_hash_otp"),
        ):
            mock_otp_db.invalidate_previous_tokens = AsyncMock(return_value=0)
            mock_otp_db.create = AsyncMock(return_value=MagicMock())

            await AuthService.send_otp(
                session=mock_session,
                email="user@example.com",
                purpose=OTPPurpose.PASSWORD_RESET,
                user_name="John",
            )

            mock_publisher.assert_called_once()
            call_kwargs = mock_publisher.call_args[1]
            assert call_kwargs["queue_name"] == "otp_emails"
            assert call_kwargs["event"]["email"] == "user@example.com"
            assert call_kwargs["event"]["purpose"] == OTPPurpose.PASSWORD_RESET.value
            assert call_kwargs["event"]["user_name"] == "John"
            assert "otp_code" in call_kwargs["event"]

    @pytest.mark.asyncio
    async def test_send_otp_with_user_id(self, mock_session):
        from app.core.services.auth import AuthService

        user_id = uuid4()

        with (
            patch("app.core.services.auth.otp_token_db") as mock_otp_db,
            patch("app.core.services.auth.get_publisher", return_value=AsyncMock()),
            patch("app.core.services.auth.hmac_hash_otp"),
        ):
            mock_otp_db.invalidate_previous_tokens = AsyncMock(return_value=0)
            mock_otp_db.create = AsyncMock(return_value=MagicMock())

            await AuthService.send_otp(
                session=mock_session,
                email="user@example.com",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
                user_id=user_id,
            )

            create_call = mock_otp_db.create.call_args
            assert create_call[1]["data"]["user_id"] == user_id


class TestVerifyOTP:

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def valid_token(self):
        """Create a valid OTP token mock."""
        token = MagicMock()
        token.id = uuid4()
        token.email = "user@example.com"
        token.purpose = OTPPurpose.EMAIL_VERIFICATION
        token.attempts = 0
        token.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        token.used_at = None
        return token

    @pytest.mark.asyncio
    async def test_verify_otp_success(self, mock_session, valid_token):
        from app.core.services.auth import AuthService

        with (
            patch("app.core.services.auth.otp_token_db") as mock_otp_db,
            patch("app.core.services.auth.hmac_hash_otp") as mock_hash,
        ):
            mock_hash.return_value = "hashed_otp"

            mock_otp_db.get_valid_token_by_hash = AsyncMock(return_value=valid_token)
            mock_otp_db.mark_as_used = AsyncMock(return_value=valid_token)

            result = await AuthService.verify_otp(
                session=mock_session,
                email="user@example.com",
                otp_code="123456",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            assert result is True
            mock_otp_db.mark_as_used.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_otp_invalid_code(self, mock_session):
        from app.core.services.auth import AuthService

        with (
            patch("app.core.services.auth.otp_token_db") as mock_otp_db,
            patch("app.core.services.auth.hmac_hash_otp") as mock_hash,
        ):
            mock_hash.return_value = "hashed_otp"

            mock_otp_db.get_valid_token_by_hash = AsyncMock(return_value=None)

            with pytest.raises(OTPInvalidException):
                await AuthService.verify_otp(
                    session=mock_session,
                    email="user@example.com",
                    otp_code="000000",
                    purpose=OTPPurpose.EMAIL_VERIFICATION,
                )

    @pytest.mark.asyncio
    async def test_verify_otp_too_many_attempts(self, mock_session, valid_token):
        from app.core.services.auth import AuthService

        valid_token.attempts = 5  # Max attempts reached

        with (
            patch("app.core.services.auth.otp_token_db") as mock_otp_db,
            patch("app.core.services.auth.hmac_hash_otp") as mock_hash,
            patch("app.core.services.auth.settings") as mock_settings,
        ):
            mock_settings.OTP_MAX_ATTEMPTS = 5
            mock_hash.return_value = "hashed_otp"

            mock_otp_db.get_valid_token_by_hash = AsyncMock(return_value=valid_token)

            with pytest.raises(TooManyAttemptsException):
                await AuthService.verify_otp(
                    session=mock_session,
                    email="user@example.com",
                    otp_code="123456",
                    purpose=OTPPurpose.EMAIL_VERIFICATION,
                )


class TestEmailSignup:

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_email_signup_creates_user(self, mock_session):
        from app.core.services.auth import AuthService

        new_user = MagicMock()
        new_user.id = uuid4()
        new_user.email = "newuser@example.com"

        with (
            patch("app.core.services.auth.user_db") as mock_user_db,
            patch("app.core.services.auth.AuthService.hash_password") as mock_hash,
        ):
            mock_hash.return_value = "hashed_password"

            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=None)
            mock_user_db.create = AsyncMock(return_value=new_user)

            user = await AuthService.email_signup(
                session=mock_session,
                email="newuser@example.com",
                password="password123",
                full_name="New User",
            )

            assert user.email == "newuser@example.com"
            mock_user_db.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_signup_existing_user_raises(self, mock_session):
        from app.core.services.auth import AuthService

        existing_user = MagicMock()
        existing_user.email = "existing@example.com"

        with patch("app.core.services.auth.user_db") as mock_user_db:
            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=existing_user)

            with pytest.raises(AuthenticationException) as exc_info:
                await AuthService.email_signup(
                    session=mock_session,
                    email="existing@example.com",
                    password="password123",
                )

            assert "already exists" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_email_signup_hashes_password(self, mock_session):
        from app.core.services.auth import AuthService

        new_user = MagicMock()
        new_user.id = uuid4()

        with (
            patch("app.core.services.auth.user_db") as mock_user_db,
            patch("app.core.services.auth.AuthService.hash_password") as mock_hash,
        ):
            mock_hash.return_value = "hashed_password_xyz"

            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=None)
            mock_user_db.create = AsyncMock(return_value=new_user)

            await AuthService.email_signup(
                session=mock_session,
                email="user@example.com",
                password="plaintext",
            )

            mock_hash.assert_called_once_with("plaintext")
            create_call = mock_user_db.create.call_args
            assert create_call[1]["data"]["password_hash"] == "hashed_password_xyz"


class TestEmailSignin:

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def valid_user(self):
        """Create a valid user mock."""
        user = MagicMock()
        user.id = uuid4()
        user.email = "user@example.com"
        user.password_hash = "hashed_password"
        user.is_active = True
        user.email_verified = True
        return user

    @pytest.mark.asyncio
    async def test_email_signin_success(self, mock_session, valid_user):
        from app.core.services.auth import AuthService

        with (
            patch("app.core.services.auth.user_db") as mock_user_db,
            patch("app.core.services.auth.AuthService.verify_password") as mock_verify,
        ):
            mock_verify.return_value = True

            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=valid_user)

            user = await AuthService.email_signin(
                session=mock_session,
                email="user@example.com",
                password="password123",
            )

            assert user.email == "user@example.com"

    @pytest.mark.asyncio
    async def test_email_signin_user_not_found(self, mock_session):
        from app.core.services.auth import AuthService

        with patch("app.core.services.auth.user_db") as mock_user_db:
            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=None)

            with pytest.raises(InvalidCredentialsException):
                await AuthService.email_signin(
                    session=mock_session,
                    email="nonexistent@example.com",
                    password="password123",
                )

    @pytest.mark.asyncio
    async def test_email_signin_wrong_password(self, mock_session, valid_user):
        from app.core.services.auth import AuthService

        with (
            patch("app.core.services.auth.user_db") as mock_user_db,
            patch("app.core.services.auth.AuthService.verify_password") as mock_verify,
        ):
            mock_verify.return_value = False

            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=valid_user)

            with pytest.raises(InvalidCredentialsException):
                await AuthService.email_signin(
                    session=mock_session,
                    email="user@example.com",
                    password="wrongpassword",
                )

    @pytest.mark.asyncio
    async def test_email_signin_inactive_user(self, mock_session, valid_user):
        from app.core.services.auth import AuthService

        valid_user.is_active = False

        with (
            patch("app.core.services.auth.user_db") as mock_user_db,
            patch("app.core.services.auth.AuthService.verify_password") as mock_verify,
        ):
            mock_verify.return_value = True

            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=valid_user)

            with pytest.raises(AuthenticationException) as exc_info:
                await AuthService.email_signin(
                    session=mock_session,
                    email="user@example.com",
                    password="password123",
                )

            assert "deactivated" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_email_signin_no_password_set(self, mock_session, valid_user):
        from app.core.services.auth import AuthService

        valid_user.password_hash = None

        with patch("app.core.services.auth.user_db") as mock_user_db:
            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=valid_user)

            with pytest.raises(AuthenticationException) as exc_info:
                await AuthService.email_signin(
                    session=mock_session,
                    email="user@example.com",
                    password="password123",
                )

            assert "oauth" in str(exc_info.value.message).lower()


class TestOAuthAuthenticate:

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def oauth_user_info(self):
        """Create OAuth user info mock."""
        from app.core.services.oauth.base import OAuthUserInfo

        return OAuthUserInfo(
            provider="google",
            provider_user_id="google_123",
            email="oauthuser@gmail.com",
            email_verified=True,
            name="OAuth User",
            picture="https://example.com/photo.jpg",
        )

    @pytest.mark.asyncio
    async def test_oauth_authenticate_new_user(self, mock_session, oauth_user_info):
        from app.core.services.auth import AuthService

        new_user = MagicMock()
        new_user.id = uuid4()
        new_user.email = oauth_user_info.email

        with (
            patch("app.core.services.auth.user_db") as mock_user_db,
            patch("app.core.services.auth.oauth_account_db") as mock_oauth_db,
        ):
            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=None)
            mock_user_db.create = AsyncMock(return_value=new_user)

            mock_oauth_db.model = MagicMock()
            mock_oauth_db.model.provider = "provider"
            mock_oauth_db.model.provider_account_id = "provider_account_id"
            mock_oauth_db.user_loader = MagicMock()
            mock_oauth_db.get_one_by_conditions = AsyncMock(return_value=None)
            mock_oauth_db.create = AsyncMock(return_value=MagicMock())

            user = await AuthService.oauth_authenticate(
                session=mock_session,
                user_info=oauth_user_info,
            )

            assert user.email == oauth_user_info.email
            mock_user_db.create.assert_called_once()
            mock_oauth_db.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_oauth_authenticate_existing_user_new_provider(
        self, mock_session, oauth_user_info
    ):
        from app.core.services.auth import AuthService

        existing_user = MagicMock()
        existing_user.id = uuid4()
        existing_user.email = oauth_user_info.email
        existing_user.full_name = "Existing Name"
        existing_user.avatar_url = "https://example.com/avatar.jpg"
        existing_user.email_verified = True

        with (
            patch("app.core.services.auth.user_db") as mock_user_db,
            patch("app.core.services.auth.oauth_account_db") as mock_oauth_db,
        ):
            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=existing_user)

            mock_oauth_db.model = MagicMock()
            mock_oauth_db.model.provider = "provider"
            mock_oauth_db.model.provider_account_id = "provider_account_id"
            mock_oauth_db.user_loader = MagicMock()
            mock_oauth_db.get_one_by_conditions = AsyncMock(return_value=None)
            mock_oauth_db.create = AsyncMock(return_value=MagicMock())

            user = await AuthService.oauth_authenticate(
                session=mock_session,
                user_info=oauth_user_info,
            )

            assert user == existing_user
            mock_oauth_db.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_oauth_authenticate_existing_oauth_account(
        self, mock_session, oauth_user_info
    ):
        from app.core.services.auth import AuthService

        existing_user = MagicMock()
        existing_user.id = uuid4()
        existing_user.email = oauth_user_info.email
        existing_user.full_name = "Existing Name"
        existing_user.avatar_url = "https://example.com/avatar.jpg"
        existing_user.email_verified = True

        existing_oauth = MagicMock()
        existing_oauth.user_id = existing_user.id
        existing_oauth.user = existing_user

        with (
            patch("app.core.services.auth.user_db") as mock_user_db,
            patch("app.core.services.auth.oauth_account_db") as mock_oauth_db,
        ):
            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=existing_user)

            mock_oauth_db.model = MagicMock()
            mock_oauth_db.model.provider = "provider"
            mock_oauth_db.model.provider_account_id = "provider_account_id"
            mock_oauth_db.user_loader = MagicMock()
            mock_oauth_db.get_one_by_conditions = AsyncMock(return_value=existing_oauth)

            user = await AuthService.oauth_authenticate(
                session=mock_session,
                user_info=oauth_user_info,
            )

            assert user == existing_user
            # Should not create new OAuth account
            mock_oauth_db.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_oauth_authenticate_updates_user_info(
        self, mock_session, oauth_user_info
    ):
        from app.core.services.auth import AuthService

        existing_user = MagicMock()
        existing_user.id = uuid4()
        existing_user.email = oauth_user_info.email
        existing_user.full_name = None
        existing_user.avatar_url = None
        existing_user.email_verified = False

        existing_oauth = MagicMock()
        existing_oauth.user = existing_user

        with (
            patch("app.core.services.auth.user_db") as mock_user_db,
            patch("app.core.services.auth.oauth_account_db") as mock_oauth_db,
        ):
            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=existing_user)
            mock_user_db.update = AsyncMock(return_value=existing_user)

            mock_oauth_db.model = MagicMock()
            mock_oauth_db.model.provider = "provider"
            mock_oauth_db.model.provider_account_id = "provider_account_id"
            mock_oauth_db.user_loader = MagicMock()
            mock_oauth_db.get_one_by_conditions = AsyncMock(return_value=existing_oauth)

            await AuthService.oauth_authenticate(
                session=mock_session,
                user_info=oauth_user_info,
            )

            # Should update user with new info
            mock_user_db.update.assert_called_once()


class TestGetOAuthProvider:

    def test_get_oauth_provider_google(self):
        from app.core.services.auth import AuthService
        from app.core.services.oauth import GoogleOAuthService

        provider = AuthService.get_oauth_provider(OAuthProviders.GOOGLE)
        assert provider == GoogleOAuthService

    def test_get_oauth_provider_github(self):
        from app.core.services.auth import AuthService
        from app.core.services.oauth import GitHubOAuthService

        provider = AuthService.get_oauth_provider(OAuthProviders.GITHUB)
        assert provider == GitHubOAuthService

    def test_get_oauth_provider_invalid(self):
        from app.core.services.auth import AuthService

        with pytest.raises(OAuthException):
            AuthService.get_oauth_provider("invalid_provider")


class TestPasswordReset:

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def valid_user(self):
        """Create a valid user mock."""
        user = MagicMock()
        user.id = uuid4()
        user.email = "user@example.com"
        user.password_hash = "old_hash"
        user.is_active = True
        return user

    @pytest.mark.asyncio
    async def test_reset_password_success(self, mock_session, valid_user):
        from app.core.services.auth import AuthService

        with (
            patch("app.core.services.auth.user_db") as mock_user_db,
            patch("app.core.services.auth.AuthService.hash_password") as mock_hash,
            patch("app.core.services.auth.get_publisher") as mock_get_pub,
        ):
            mock_hash.return_value = "new_hashed_password"

            mock_publish = AsyncMock(return_value=None)
            mock_get_pub.return_value = mock_publish

            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=valid_user)
            mock_user_db.update = AsyncMock(return_value=valid_user)

            result = await AuthService.reset_password(
                session=mock_session,
                email="user@example.com",
                new_password="newpassword123",
            )

            assert result is True
            mock_user_db.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_password_publishes_confirmation_email_event(
        self, mock_session, valid_user
    ):
        from app.core.services.auth import AuthService

        with (
            patch("app.core.services.auth.user_db") as mock_user_db,
            patch("app.core.services.auth.AuthService.hash_password"),
            patch("app.core.services.auth.get_publisher") as mock_get_pub,
        ):
            mock_publish = AsyncMock(return_value=None)
            mock_get_pub.return_value = mock_publish

            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=valid_user)
            mock_user_db.update = AsyncMock(return_value=valid_user)

            await AuthService.reset_password(
                session=mock_session,
                email="user@example.com",
                new_password="newpassword123",
            )

            mock_publish.assert_called_once()
            call_kwargs = mock_publish.call_args[1]
            assert call_kwargs["queue_name"] == "password_reset_confirmation_emails"
            assert call_kwargs["event"]["email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_reset_password_user_not_found(self, mock_session):
        from app.core.services.auth import AuthService

        with patch("app.core.services.auth.user_db") as mock_user_db:
            mock_user_db.model = MagicMock()
            mock_user_db.model.email = "email"
            mock_user_db.get_one_by_conditions = AsyncMock(return_value=None)

            with pytest.raises(AuthenticationException):
                await AuthService.reset_password(
                    session=mock_session,
                    email="nonexistent@example.com",
                    new_password="newpassword123",
                )


class TestModuleExports:

    def test_all_exports(self):
        from app.core.services import auth

        assert hasattr(auth, "__all__")
        assert "AuthService" in auth.__all__
