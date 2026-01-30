"""
Test suite for AuthService.

This module contains comprehensive tests for the AuthService including:
- Email signup with OTP verification
- Email signin with password
- OAuth authentication (Google, GitHub)
- OTP generation, sending, and verification
- Password reset flow
- Token generation

Run all tests:
    pytest app/tests/services/test_auth.py -v

Run with coverage:
    pytest app/tests/services/test_auth.py --cov=app.shared.services.auth --cov-report=term-missing -v
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.shared.enums import OAuthProviders, OTPPurpose
from app.shared.exceptions.types import (
    AuthenticationException,
    InvalidCredentialsException,
    OAuthException,
    OTPInvalidException,
    TooManyAttemptsException,
)


class TestAuthServiceInit:
    """Test suite for AuthService initialization."""

    @pytest.fixture(autouse=True)
    def reset_service(self):
        """Reset AuthService state after each test."""
        from app.shared.services.auth import AuthService

        yield
        AuthService._initialized = False

    def test_init_sets_initialized_flag(self):
        """Test that init sets the initialized flag."""
        from app.shared.services.auth import AuthService

        AuthService.init()

        assert AuthService._initialized is True

    def test_init_is_idempotent(self):
        """Test that init can be called multiple times safely."""
        from app.shared.services.auth import AuthService

        AuthService.init()
        AuthService.init()

        assert AuthService._initialized is True

    def test_is_initialized_returns_correct_state(self):
        """Test that is_initialized returns correct state."""
        from app.shared.services.auth import AuthService

        assert AuthService.is_initialized() is False

        AuthService.init()

        assert AuthService.is_initialized() is True


class TestGenerateOTP:
    """Test suite for OTP generation."""

    def test_generate_otp_returns_string(self):
        """Test that generate_otp returns a string."""
        from app.shared.services.auth import AuthService

        otp = AuthService.generate_otp()
        assert isinstance(otp, str)

    def test_generate_otp_default_length(self):
        """Test that generate_otp uses default length from settings."""
        from app.shared.services.auth import AuthService

        with patch("app.shared.services.auth.settings") as mock_settings:
            mock_settings.OTP_LENGTH = 6

            otp = AuthService.generate_otp()

            assert len(otp) == 6

    def test_generate_otp_custom_length(self):
        """Test that generate_otp respects custom length."""
        from app.shared.services.auth import AuthService

        otp = AuthService.generate_otp(length=8)
        assert len(otp) == 8

    def test_generate_otp_only_digits(self):
        """Test that generate_otp returns only digits."""
        from app.shared.services.auth import AuthService

        for _ in range(100):
            otp = AuthService.generate_otp()
            assert otp.isdigit()

    def test_generate_otp_is_random(self):
        """Test that generate_otp produces random values."""
        from app.shared.services.auth import AuthService

        otps = [AuthService.generate_otp() for _ in range(100)]
        # With 6 digits, should have many unique values
        assert len(set(otps)) > 50


class TestHashPassword:
    """Test suite for password hashing."""

    def test_hash_password_returns_string(self):
        """Test that hash_password returns a string."""
        from app.shared.services.auth import AuthService

        hashed = AuthService.hash_password("password123")
        assert isinstance(hashed, str)

    def test_hash_password_different_from_input(self):
        """Test that hashed password differs from input."""
        from app.shared.services.auth import AuthService

        password = "password123"
        hashed = AuthService.hash_password(password)
        assert hashed != password

    def test_hash_password_different_for_same_input(self):
        """Test that same password produces different hashes (salt)."""
        from app.shared.services.auth import AuthService

        password = "password123"
        hash1 = AuthService.hash_password(password)
        hash2 = AuthService.hash_password(password)
        assert hash1 != hash2


class TestVerifyPassword:
    """Test suite for password verification."""

    def test_verify_password_correct(self):
        """Test that verify_password returns True for correct password."""
        from app.shared.services.auth import AuthService

        password = "password123"
        hashed = AuthService.hash_password(password)

        assert AuthService.verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test that verify_password returns False for incorrect password."""
        from app.shared.services.auth import AuthService

        password = "password123"
        hashed = AuthService.hash_password(password)

        assert AuthService.verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty(self):
        """Test that verify_password handles empty password."""
        from app.shared.services.auth import AuthService

        hashed = AuthService.hash_password("password123")
        assert AuthService.verify_password("", hashed) is False


class TestSendOTP:
    """Test suite for OTP sending."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_send_otp_creates_token(self, mock_session):
        """Test that send_otp creates an OTP token."""
        from app.shared.services.auth import AuthService

        with patch(
            "app.shared.services.auth.OTPTokenDB"
        ) as mock_otp_db, patch(
            "app.shared.services.auth.EmailManagerService"
        ) as mock_email, patch(
            "app.shared.services.auth.hmac_hash_otp"
        ) as mock_hash:
            mock_otp_instance = MagicMock()
            mock_otp_instance.invalidate_previous_tokens = AsyncMock(return_value=0)
            mock_otp_instance.create = AsyncMock(return_value=MagicMock())
            mock_otp_db.return_value = mock_otp_instance

            mock_email.send_otp_email = AsyncMock(return_value=True)
            mock_hash.return_value = "hashed_otp"

            result = await AuthService.send_otp(
                session=mock_session,
                email="user@example.com",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            assert result is True
            mock_otp_instance.invalidate_previous_tokens.assert_called_once()
            mock_otp_instance.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_otp_invalidates_previous_tokens(self, mock_session):
        """Test that send_otp invalidates previous tokens."""
        from app.shared.services.auth import AuthService

        with patch(
            "app.shared.services.auth.OTPTokenDB"
        ) as mock_otp_db, patch(
            "app.shared.services.auth.EmailManagerService"
        ) as mock_email, patch(
            "app.shared.services.auth.hmac_hash_otp"
        ):
            mock_otp_instance = MagicMock()
            mock_otp_instance.invalidate_previous_tokens = AsyncMock(return_value=2)
            mock_otp_instance.create = AsyncMock(return_value=MagicMock())
            mock_otp_db.return_value = mock_otp_instance

            mock_email.send_otp_email = AsyncMock(return_value=True)

            await AuthService.send_otp(
                session=mock_session,
                email="user@example.com",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            mock_otp_instance.invalidate_previous_tokens.assert_called_once_with(
                session=mock_session,
                email="user@example.com",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
                commit_self=False,
            )

    @pytest.mark.asyncio
    async def test_send_otp_sends_email(self, mock_session):
        """Test that send_otp sends email via EmailManagerService."""
        from app.shared.services.auth import AuthService

        with patch(
            "app.shared.services.auth.OTPTokenDB"
        ) as mock_otp_db, patch(
            "app.shared.services.auth.EmailManagerService"
        ) as mock_email, patch(
            "app.shared.services.auth.hmac_hash_otp"
        ):
            mock_otp_instance = MagicMock()
            mock_otp_instance.invalidate_previous_tokens = AsyncMock(return_value=0)
            mock_otp_instance.create = AsyncMock(return_value=MagicMock())
            mock_otp_db.return_value = mock_otp_instance

            mock_email.send_otp_email = AsyncMock(return_value=True)

            await AuthService.send_otp(
                session=mock_session,
                email="user@example.com",
                purpose=OTPPurpose.PASSWORD_RESET,
                user_name="John",
            )

            mock_email.send_otp_email.assert_called_once()
            call_kwargs = mock_email.send_otp_email.call_args[1]
            assert call_kwargs["email"] == "user@example.com"
            assert call_kwargs["purpose"] == OTPPurpose.PASSWORD_RESET
            assert call_kwargs["user_name"] == "John"

    @pytest.mark.asyncio
    async def test_send_otp_with_user_id(self, mock_session):
        """Test that send_otp associates token with user_id."""
        from app.shared.services.auth import AuthService

        user_id = uuid4()

        with patch(
            "app.shared.services.auth.OTPTokenDB"
        ) as mock_otp_db, patch(
            "app.shared.services.auth.EmailManagerService"
        ) as mock_email, patch(
            "app.shared.services.auth.hmac_hash_otp"
        ):
            mock_otp_instance = MagicMock()
            mock_otp_instance.invalidate_previous_tokens = AsyncMock(return_value=0)
            mock_otp_instance.create = AsyncMock(return_value=MagicMock())
            mock_otp_db.return_value = mock_otp_instance

            mock_email.send_otp_email = AsyncMock(return_value=True)

            await AuthService.send_otp(
                session=mock_session,
                email="user@example.com",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
                user_id=user_id,
            )

            create_call = mock_otp_instance.create.call_args
            assert create_call[1]["data"]["user_id"] == user_id


class TestVerifyOTP:
    """Test suite for OTP verification."""

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
        """Test successful OTP verification."""
        from app.shared.services.auth import AuthService

        with patch(
            "app.shared.services.auth.OTPTokenDB"
        ) as mock_otp_db, patch(
            "app.shared.services.auth.hmac_hash_otp"
        ) as mock_hash:
            mock_hash.return_value = "hashed_otp"

            mock_otp_instance = MagicMock()
            mock_otp_instance.get_valid_token_by_hash = AsyncMock(
                return_value=valid_token
            )
            mock_otp_instance.mark_as_used = AsyncMock(return_value=valid_token)
            mock_otp_db.return_value = mock_otp_instance

            result = await AuthService.verify_otp(
                session=mock_session,
                email="user@example.com",
                otp_code="123456",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

            assert result is True
            mock_otp_instance.mark_as_used.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_otp_invalid_code(self, mock_session):
        """Test OTP verification with invalid code."""
        from app.shared.services.auth import AuthService

        with patch(
            "app.shared.services.auth.OTPTokenDB"
        ) as mock_otp_db, patch(
            "app.shared.services.auth.hmac_hash_otp"
        ) as mock_hash:
            mock_hash.return_value = "hashed_otp"

            mock_otp_instance = MagicMock()
            mock_otp_instance.get_valid_token_by_hash = AsyncMock(return_value=None)
            mock_otp_db.return_value = mock_otp_instance

            with pytest.raises(OTPInvalidException):
                await AuthService.verify_otp(
                    session=mock_session,
                    email="user@example.com",
                    otp_code="000000",
                    purpose=OTPPurpose.EMAIL_VERIFICATION,
                )

    @pytest.mark.asyncio
    async def test_verify_otp_too_many_attempts(self, mock_session, valid_token):
        """Test OTP verification with too many attempts."""
        from app.shared.services.auth import AuthService

        valid_token.attempts = 5  # Max attempts reached

        with patch(
            "app.shared.services.auth.OTPTokenDB"
        ) as mock_otp_db, patch(
            "app.shared.services.auth.hmac_hash_otp"
        ) as mock_hash, patch(
            "app.shared.services.auth.settings"
        ) as mock_settings:
            mock_settings.OTP_MAX_ATTEMPTS = 5
            mock_hash.return_value = "hashed_otp"

            mock_otp_instance = MagicMock()
            mock_otp_instance.get_valid_token_by_hash = AsyncMock(
                return_value=valid_token
            )
            mock_otp_db.return_value = mock_otp_instance

            with pytest.raises(TooManyAttemptsException):
                await AuthService.verify_otp(
                    session=mock_session,
                    email="user@example.com",
                    otp_code="123456",
                    purpose=OTPPurpose.EMAIL_VERIFICATION,
                )


class TestEmailSignup:
    """Test suite for email signup."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_email_signup_creates_user(self, mock_session):
        """Test that email_signup creates a new user."""
        from app.shared.services.auth import AuthService

        new_user = MagicMock()
        new_user.id = uuid4()
        new_user.email = "newuser@example.com"

        with patch(
            "app.shared.services.auth.UserDB"
        ) as mock_user_db, patch(
            "app.shared.services.auth.AuthService.hash_password"
        ) as mock_hash:
            mock_hash.return_value = "hashed_password"

            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(return_value=None)
            mock_user_instance.create = AsyncMock(return_value=new_user)
            mock_user_db.return_value = mock_user_instance

            user = await AuthService.email_signup(
                session=mock_session,
                email="newuser@example.com",
                password="password123",
                full_name="New User",
            )

            assert user.email == "newuser@example.com"
            mock_user_instance.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_signup_existing_user_raises(self, mock_session):
        """Test that email_signup raises for existing user."""
        from app.shared.services.auth import AuthService

        existing_user = MagicMock()
        existing_user.email = "existing@example.com"

        with patch("app.shared.services.auth.UserDB") as mock_user_db:
            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(
                return_value=existing_user
            )
            mock_user_db.return_value = mock_user_instance

            with pytest.raises(AuthenticationException) as exc_info:
                await AuthService.email_signup(
                    session=mock_session,
                    email="existing@example.com",
                    password="password123",
                )

            assert "already exists" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_email_signup_hashes_password(self, mock_session):
        """Test that email_signup hashes the password."""
        from app.shared.services.auth import AuthService

        new_user = MagicMock()
        new_user.id = uuid4()

        with patch(
            "app.shared.services.auth.UserDB"
        ) as mock_user_db, patch(
            "app.shared.services.auth.AuthService.hash_password"
        ) as mock_hash:
            mock_hash.return_value = "hashed_password_xyz"

            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(return_value=None)
            mock_user_instance.create = AsyncMock(return_value=new_user)
            mock_user_db.return_value = mock_user_instance

            await AuthService.email_signup(
                session=mock_session,
                email="user@example.com",
                password="plaintext",
            )

            mock_hash.assert_called_once_with("plaintext")
            create_call = mock_user_instance.create.call_args
            assert create_call[1]["data"]["password_hash"] == "hashed_password_xyz"


class TestEmailSignin:
    """Test suite for email signin."""

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
        """Test successful email signin."""
        from app.shared.services.auth import AuthService

        with patch(
            "app.shared.services.auth.UserDB"
        ) as mock_user_db, patch(
            "app.shared.services.auth.AuthService.verify_password"
        ) as mock_verify:
            mock_verify.return_value = True

            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(return_value=valid_user)
            mock_user_db.return_value = mock_user_instance

            user = await AuthService.email_signin(
                session=mock_session,
                email="user@example.com",
                password="password123",
            )

            assert user.email == "user@example.com"

    @pytest.mark.asyncio
    async def test_email_signin_user_not_found(self, mock_session):
        """Test email signin with non-existent user."""
        from app.shared.services.auth import AuthService

        with patch("app.shared.services.auth.UserDB") as mock_user_db:
            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(return_value=None)
            mock_user_db.return_value = mock_user_instance

            with pytest.raises(InvalidCredentialsException):
                await AuthService.email_signin(
                    session=mock_session,
                    email="nonexistent@example.com",
                    password="password123",
                )

    @pytest.mark.asyncio
    async def test_email_signin_wrong_password(self, mock_session, valid_user):
        """Test email signin with wrong password."""
        from app.shared.services.auth import AuthService

        with patch(
            "app.shared.services.auth.UserDB"
        ) as mock_user_db, patch(
            "app.shared.services.auth.AuthService.verify_password"
        ) as mock_verify:
            mock_verify.return_value = False

            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(return_value=valid_user)
            mock_user_db.return_value = mock_user_instance

            with pytest.raises(InvalidCredentialsException):
                await AuthService.email_signin(
                    session=mock_session,
                    email="user@example.com",
                    password="wrongpassword",
                )

    @pytest.mark.asyncio
    async def test_email_signin_inactive_user(self, mock_session, valid_user):
        """Test email signin with inactive user."""
        from app.shared.services.auth import AuthService

        valid_user.is_active = False

        with patch(
            "app.shared.services.auth.UserDB"
        ) as mock_user_db, patch(
            "app.shared.services.auth.AuthService.verify_password"
        ) as mock_verify:
            mock_verify.return_value = True

            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(return_value=valid_user)
            mock_user_db.return_value = mock_user_instance

            with pytest.raises(AuthenticationException) as exc_info:
                await AuthService.email_signin(
                    session=mock_session,
                    email="user@example.com",
                    password="password123",
                )

            assert "deactivated" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_email_signin_no_password_set(self, mock_session, valid_user):
        """Test email signin for OAuth-only user (no password)."""
        from app.shared.services.auth import AuthService

        valid_user.password_hash = None

        with patch("app.shared.services.auth.UserDB") as mock_user_db:
            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(return_value=valid_user)
            mock_user_db.return_value = mock_user_instance

            with pytest.raises(AuthenticationException) as exc_info:
                await AuthService.email_signin(
                    session=mock_session,
                    email="user@example.com",
                    password="password123",
                )

            assert "oauth" in str(exc_info.value.message).lower()


class TestOAuthAuthenticate:
    """Test suite for OAuth authentication."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def oauth_user_info(self):
        """Create OAuth user info mock."""
        from app.shared.services.oauth.base import OAuthUserInfo

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
        """Test OAuth authentication creates new user."""
        from app.shared.services.auth import AuthService

        new_user = MagicMock()
        new_user.id = uuid4()
        new_user.email = oauth_user_info.email

        with patch(
            "app.shared.services.auth.UserDB"
        ) as mock_user_db, patch(
            "app.shared.services.auth.OAuthAccountDB"
        ) as mock_oauth_db:
            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(return_value=None)
            mock_user_instance.create = AsyncMock(return_value=new_user)
            mock_user_db.return_value = mock_user_instance

            mock_oauth_instance = MagicMock()
            mock_oauth_instance.get_one_by_conditions = AsyncMock(return_value=None)
            mock_oauth_instance.create = AsyncMock(return_value=MagicMock())
            mock_oauth_db.return_value = mock_oauth_instance

            user = await AuthService.oauth_authenticate(
                session=mock_session,
                user_info=oauth_user_info,
            )

            assert user.email == oauth_user_info.email
            mock_user_instance.create.assert_called_once()
            mock_oauth_instance.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_oauth_authenticate_existing_user_new_provider(
        self, mock_session, oauth_user_info
    ):
        """Test OAuth adds new provider to existing user."""
        from app.shared.services.auth import AuthService

        existing_user = MagicMock()
        existing_user.id = uuid4()
        existing_user.email = oauth_user_info.email

        with patch(
            "app.shared.services.auth.UserDB"
        ) as mock_user_db, patch(
            "app.shared.services.auth.OAuthAccountDB"
        ) as mock_oauth_db:
            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(
                return_value=existing_user
            )
            mock_user_db.return_value = mock_user_instance

            mock_oauth_instance = MagicMock()
            mock_oauth_instance.get_one_by_conditions = AsyncMock(return_value=None)
            mock_oauth_instance.create = AsyncMock(return_value=MagicMock())
            mock_oauth_db.return_value = mock_oauth_instance

            user = await AuthService.oauth_authenticate(
                session=mock_session,
                user_info=oauth_user_info,
            )

            assert user == existing_user
            mock_oauth_instance.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_oauth_authenticate_existing_oauth_account(
        self, mock_session, oauth_user_info
    ):
        """Test OAuth with existing OAuth account."""
        from app.shared.services.auth import AuthService

        existing_user = MagicMock()
        existing_user.id = uuid4()
        existing_user.email = oauth_user_info.email
        existing_user.full_name = "Existing Name"
        existing_user.avatar_url = "https://example.com/avatar.jpg"
        existing_user.email_verified = True

        existing_oauth = MagicMock()
        existing_oauth.user_id = existing_user.id
        existing_oauth.user = existing_user

        with patch(
            "app.shared.services.auth.UserDB"
        ) as mock_user_db, patch(
            "app.shared.services.auth.OAuthAccountDB"
        ) as mock_oauth_db:
            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(
                return_value=existing_user
            )
            mock_user_db.return_value = mock_user_instance

            mock_oauth_instance = MagicMock()
            mock_oauth_instance.get_one_by_conditions = AsyncMock(
                return_value=existing_oauth
            )
            mock_oauth_instance.user_loader = MagicMock()
            mock_oauth_db.return_value = mock_oauth_instance

            user = await AuthService.oauth_authenticate(
                session=mock_session,
                user_info=oauth_user_info,
            )

            assert user == existing_user
            # Should not create new OAuth account
            mock_oauth_instance.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_oauth_authenticate_updates_user_info(
        self, mock_session, oauth_user_info
    ):
        """Test OAuth updates user info from provider."""
        from app.shared.services.auth import AuthService

        existing_user = MagicMock()
        existing_user.id = uuid4()
        existing_user.email = oauth_user_info.email
        existing_user.full_name = None
        existing_user.avatar_url = None
        existing_user.email_verified = False

        existing_oauth = MagicMock()
        existing_oauth.user = existing_user

        with patch(
            "app.shared.services.auth.UserDB"
        ) as mock_user_db, patch(
            "app.shared.services.auth.OAuthAccountDB"
        ) as mock_oauth_db:
            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(
                return_value=existing_user
            )
            mock_user_instance.update = AsyncMock(return_value=existing_user)
            mock_user_instance.user_loader = MagicMock()
            mock_user_db.return_value = mock_user_instance

            mock_oauth_instance = MagicMock()
            mock_oauth_instance.get_one_by_conditions = AsyncMock(
                return_value=existing_oauth
            )
            mock_oauth_instance.user_loader = MagicMock()
            mock_oauth_db.return_value = mock_oauth_instance

            await AuthService.oauth_authenticate(
                session=mock_session,
                user_info=oauth_user_info,
            )

            # Should update user with new info
            mock_user_instance.update.assert_called_once()


class TestGetOAuthProvider:
    """Test suite for OAuth provider retrieval."""

    def test_get_oauth_provider_google(self):
        """Test getting Google OAuth provider."""
        from app.shared.services.auth import AuthService
        from app.shared.services.oauth import GoogleOAuthService

        provider = AuthService.get_oauth_provider(OAuthProviders.GOOGLE)
        assert provider == GoogleOAuthService

    def test_get_oauth_provider_github(self):
        """Test getting GitHub OAuth provider."""
        from app.shared.services.auth import AuthService
        from app.shared.services.oauth import GitHubOAuthService

        provider = AuthService.get_oauth_provider(OAuthProviders.GITHUB)
        assert provider == GitHubOAuthService

    def test_get_oauth_provider_invalid(self):
        """Test getting invalid OAuth provider."""
        from app.shared.services.auth import AuthService

        with pytest.raises(OAuthException):
            AuthService.get_oauth_provider("invalid_provider")


class TestPasswordReset:
    """Test suite for password reset flow."""

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
        """Test successful password reset."""
        from app.shared.services.auth import AuthService

        with patch(
            "app.shared.services.auth.UserDB"
        ) as mock_user_db, patch(
            "app.shared.services.auth.AuthService.hash_password"
        ) as mock_hash, patch(
            "app.shared.services.auth.EmailManagerService"
        ) as mock_email:
            mock_hash.return_value = "new_hashed_password"

            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(return_value=valid_user)
            mock_user_instance.update = AsyncMock(return_value=valid_user)
            mock_user_db.return_value = mock_user_instance

            mock_email.send_password_reset_confirmation_email = AsyncMock(
                return_value=True
            )

            result = await AuthService.reset_password(
                session=mock_session,
                email="user@example.com",
                new_password="newpassword123",
            )

            assert result is True
            mock_user_instance.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_password_sends_confirmation_email(
        self, mock_session, valid_user
    ):
        """Test that password reset sends confirmation email."""
        from app.shared.services.auth import AuthService

        with patch(
            "app.shared.services.auth.UserDB"
        ) as mock_user_db, patch(
            "app.shared.services.auth.AuthService.hash_password"
        ), patch(
            "app.shared.services.auth.EmailManagerService"
        ) as mock_email:
            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(return_value=valid_user)
            mock_user_instance.update = AsyncMock(return_value=valid_user)
            mock_user_db.return_value = mock_user_instance

            mock_email.send_password_reset_confirmation_email = AsyncMock(
                return_value=True
            )

            await AuthService.reset_password(
                session=mock_session,
                email="user@example.com",
                new_password="newpassword123",
            )

            mock_email.send_password_reset_confirmation_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_password_user_not_found(self, mock_session):
        """Test password reset for non-existent user."""
        from app.shared.services.auth import AuthService

        with patch("app.shared.services.auth.UserDB") as mock_user_db:
            mock_user_instance = MagicMock()
            mock_user_instance.get_one_by_conditions = AsyncMock(return_value=None)
            mock_user_db.return_value = mock_user_instance

            with pytest.raises(AuthenticationException):
                await AuthService.reset_password(
                    session=mock_session,
                    email="nonexistent@example.com",
                    new_password="newpassword123",
                )


class TestModuleExports:
    """Test suite for module exports."""

    def test_all_exports(self):
        """Test that __all__ contains expected exports."""
        from app.shared.services import auth

        assert hasattr(auth, "__all__")
        assert "AuthService" in auth.__all__
