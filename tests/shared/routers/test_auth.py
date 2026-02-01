"""
Test suite for auth router endpoints.

This module contains comprehensive unit tests for all auth endpoints:
- POST /signup - User registration
- POST /signup/verify - Email verification
- POST /signup/resend - Resend verification email
- POST /signin - User login
- POST /token/refresh - Refresh access token
- POST /signout - Sign out current session
- POST /signout/all - Sign out all sessions
- GET /oauth/{provider} - OAuth initiation
- GET /oauth/{provider}/callback - OAuth callback
- POST /password/reset - Request password reset
- POST /password/reset/confirm - Confirm password reset
- POST /password/change - Change password
- GET /me - Get current user profile
- PATCH /me - Update profile
- DELETE /me - Delete account
- GET /sessions - Get active sessions

Run all tests:
    pytest tests/shared/routers/test_auth.py -v

Run with coverage:
    pytest tests/shared/routers/test_auth.py --cov=app.shared.routers.auth --cov-report=term-missing -v
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    # Create an async context manager for begin()
    context_manager = AsyncMock()
    context_manager.__aenter__ = AsyncMock(return_value=None)
    context_manager.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=context_manager)
    return session


@pytest.fixture
def mock_user():
    """Create a mock user object."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.email_verified = True
    user.full_name = "Test User"
    user.avatar_url = None
    user.is_active = True
    user.is_deleted = False
    user.password_hash = "hashed_password"
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    user.oauth_accounts = []
    return user


@pytest.fixture
def mock_token_pair():
    """Create a mock token pair."""
    from app.shared.services.auth import TokenPair

    return TokenPair(
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        token_type="bearer",
        expires_in=900,
    )


@pytest.fixture
def mock_request():
    """Create a mock request object."""
    request = MagicMock()
    request.headers = {"User-Agent": "Test Browser"}
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    request.session = {}
    return request


# =============================================================================
# Signup Endpoint Tests
# =============================================================================


class TestSignupEndpoint:
    """Test suite for POST /signup endpoint."""

    @pytest.mark.asyncio
    async def test_signup_success(self, mock_session, mock_user):
        """Test successful user signup."""
        from app.shared.routers.auth import signup
        from app.shared.schemas.auth import SignupRequest

        request_data = SignupRequest(
            email="test@example.com",
            password="SecurePass123!",
            full_name="Test User",
        )

        with patch(
            "app.shared.routers.auth.AuthService.email_signup",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.AuthService.send_otp",
            new_callable=AsyncMock,
        ):
            response = await signup(request_data=request_data, session=mock_session)

            assert response.message == "Verification code sent to your email"
            assert response.email == "test@example.com"
            assert response.requires_verification is True

    @pytest.mark.asyncio
    async def test_signup_user_already_exists(self, mock_session):
        """Test signup fails when user already exists."""
        from app.shared.routers.auth import signup
        from app.shared.schemas.auth import SignupRequest
        from app.shared.exceptions.types import (
            AuthenticationException,
            ConflictException,
        )

        request_data = SignupRequest(
            email="existing@example.com",
            password="SecurePass123!",
            full_name="Test User",
        )

        # Use a function to properly raise the exception inside async context
        async def mock_email_signup(*args, **kwargs):
            raise AuthenticationException("User with this email already exists")

        with patch(
            "app.shared.routers.auth.AuthService.email_signup",
            side_effect=mock_email_signup,
        ):
            with pytest.raises(ConflictException):
                await signup(request_data=request_data, session=mock_session)


class TestVerifySignupEndpoint:
    """Test suite for POST /signup/verify endpoint."""

    @pytest.mark.asyncio
    async def test_verify_signup_success(
        self, mock_session, mock_user, mock_token_pair, mock_request
    ):
        """Test successful email verification."""
        from app.shared.routers.auth import verify_signup
        from app.shared.schemas.auth import OTPVerifyRequest

        request_data = OTPVerifyRequest(
            email="test@example.com",
            otp_code="123456",
        )

        with patch(
            "app.shared.routers.auth.AuthService.verify_otp",
            new_callable=AsyncMock,
        ), patch(
            "app.shared.routers.auth.user_db.get_one_by_conditions",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.user_db.update",
            new_callable=AsyncMock,
        ), patch(
            "app.shared.routers.auth.AuthService.create_token_pair",
            new_callable=AsyncMock,
            return_value=mock_token_pair,
        ):
            response = await verify_signup(
                request_data=request_data,
                request=mock_request,
                session=mock_session,
            )

            assert response.access_token == "test_access_token"
            assert response.refresh_token == "test_refresh_token"
            assert response.token_type == "bearer"

    @pytest.mark.asyncio
    async def test_verify_signup_user_not_found(self, mock_session, mock_request):
        """Test verification fails when user not found."""
        from app.shared.routers.auth import verify_signup
        from app.shared.schemas.auth import OTPVerifyRequest
        from app.shared.exceptions.types import UserNotFoundException

        request_data = OTPVerifyRequest(
            email="nonexistent@example.com",
            otp_code="123456",
        )

        with patch(
            "app.shared.routers.auth.AuthService.verify_otp",
            new_callable=AsyncMock,
        ), patch(
            "app.shared.routers.auth.user_db.get_one_by_conditions",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.shared.routers.auth.user_db.update",
            new_callable=AsyncMock,
        ):
            with pytest.raises(UserNotFoundException):
                await verify_signup(
                    request_data=request_data,
                    request=mock_request,
                    session=mock_session,
                )

    @pytest.mark.asyncio
    async def test_verify_signup_invalid_otp(self, mock_session, mock_request):
        """Test verification fails with invalid OTP."""
        from app.shared.routers.auth import verify_signup
        from app.shared.schemas.auth import OTPVerifyRequest
        from app.shared.exceptions.types import OTPInvalidException

        request_data = OTPVerifyRequest(
            email="test@example.com",
            otp_code="000000",  # Valid 6-digit format but wrong code
        )

        # Use a function to properly raise the exception inside async context
        async def mock_verify_otp(*args, **kwargs):
            raise OTPInvalidException()

        with patch(
            "app.shared.routers.auth.AuthService.verify_otp",
            side_effect=mock_verify_otp,
        ):
            with pytest.raises(OTPInvalidException):
                await verify_signup(
                    request_data=request_data,
                    request=mock_request,
                    session=mock_session,
                )

    @pytest.mark.asyncio
    async def test_verify_signup_too_many_attempts(self, mock_session, mock_request):
        """Test verification fails after too many attempts."""
        from app.shared.routers.auth import verify_signup
        from app.shared.schemas.auth import OTPVerifyRequest
        from app.shared.exceptions.types import TooManyAttemptsException

        request_data = OTPVerifyRequest(
            email="test@example.com",
            otp_code="123456",
        )

        # Use a function to properly raise the exception inside async context
        async def mock_verify_otp(*args, **kwargs):
            raise TooManyAttemptsException()

        with patch(
            "app.shared.routers.auth.AuthService.verify_otp",
            side_effect=mock_verify_otp,
        ):
            with pytest.raises(TooManyAttemptsException):
                await verify_signup(
                    request_data=request_data,
                    request=mock_request,
                    session=mock_session,
                )


class TestResendVerificationEndpoint:
    """Test suite for POST /signup/resend endpoint."""

    @pytest.mark.asyncio
    async def test_resend_verification_success(self, mock_session, mock_user):
        """Test successful resend verification."""
        from app.shared.routers.auth import resend_verification
        from app.shared.schemas.auth import ResendOTPRequest

        mock_user.email_verified = False
        request_data = ResendOTPRequest(email="test@example.com")

        with patch(
            "app.shared.routers.auth.user_db.get_one_by_conditions",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.AuthService.send_otp",
            new_callable=AsyncMock,
        ):
            response = await resend_verification(
                request_data=request_data,
                session=mock_session,
            )

            assert response.message == "Verification code sent to your email"

    @pytest.mark.asyncio
    async def test_resend_verification_user_not_found(self, mock_session):
        """Test resend returns generic message when user not found."""
        from app.shared.routers.auth import resend_verification
        from app.shared.schemas.auth import ResendOTPRequest

        request_data = ResendOTPRequest(email="nonexistent@example.com")

        with patch(
            "app.shared.routers.auth.user_db.get_one_by_conditions",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = await resend_verification(
                request_data=request_data,
                session=mock_session,
            )

            # Should not reveal if user exists
            assert "verification code has been sent" in response.message

    @pytest.mark.asyncio
    async def test_resend_verification_already_verified(self, mock_session, mock_user):
        """Test resend returns message when already verified."""
        from app.shared.routers.auth import resend_verification
        from app.shared.schemas.auth import ResendOTPRequest

        mock_user.email_verified = True
        request_data = ResendOTPRequest(email="test@example.com")

        with patch(
            "app.shared.routers.auth.user_db.get_one_by_conditions",
            new_callable=AsyncMock,
            return_value=mock_user,
        ):
            response = await resend_verification(
                request_data=request_data,
                session=mock_session,
            )

            assert "already verified" in response.message


# =============================================================================
# Signin Endpoint Tests
# =============================================================================


class TestSigninEndpoint:
    """Test suite for POST /signin endpoint."""

    @pytest.mark.asyncio
    async def test_signin_success(
        self, mock_session, mock_user, mock_token_pair, mock_request
    ):
        """Test successful signin."""
        from app.shared.routers.auth import signin
        from app.shared.schemas.auth import LoginRequest

        request_data = LoginRequest(
            email="test@example.com",
            password="SecurePass123!",
            remember_me=False,
        )

        with patch(
            "app.shared.routers.auth.AuthService.email_signin",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.user_db.get_by_id",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.AuthService.create_token_pair",
            new_callable=AsyncMock,
            return_value=mock_token_pair,
        ):
            response = await signin(
                request_data=request_data,
                request=mock_request,
                session=mock_session,
            )

            assert response.access_token == "test_access_token"
            assert response.refresh_token == "test_refresh_token"

    @pytest.mark.asyncio
    async def test_signin_invalid_credentials(self, mock_session, mock_request):
        """Test signin fails with invalid credentials."""
        from app.shared.routers.auth import signin
        from app.shared.schemas.auth import LoginRequest
        from app.shared.exceptions.types import InvalidCredentialsException

        request_data = LoginRequest(
            email="test@example.com",
            password="wrong_password",
        )

        with patch(
            "app.shared.routers.auth.AuthService.email_signin",
            new_callable=AsyncMock,
            side_effect=InvalidCredentialsException(),
        ):
            with pytest.raises(InvalidCredentialsException):
                await signin(
                    request_data=request_data,
                    request=mock_request,
                    session=mock_session,
                )

    @pytest.mark.asyncio
    async def test_signin_with_remember_me(
        self, mock_session, mock_user, mock_token_pair, mock_request
    ):
        """Test signin with remember_me flag."""
        from app.shared.routers.auth import signin
        from app.shared.schemas.auth import LoginRequest

        request_data = LoginRequest(
            email="test@example.com",
            password="SecurePass123!",
            remember_me=True,
        )

        with patch(
            "app.shared.routers.auth.AuthService.email_signin",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.user_db.get_by_id",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.AuthService.create_token_pair",
            new_callable=AsyncMock,
            return_value=mock_token_pair,
        ) as mock_create_tokens:
            await signin(
                request_data=request_data,
                request=mock_request,
                session=mock_session,
            )

            # Verify remember_me was passed
            mock_create_tokens.assert_called_once()
            call_kwargs = mock_create_tokens.call_args.kwargs
            assert call_kwargs.get("remember_me") is True


# =============================================================================
# Token Management Endpoint Tests
# =============================================================================


class TestRefreshTokenEndpoint:
    """Test suite for POST /token/refresh endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, mock_session):
        """Test successful token refresh."""
        from app.shared.routers.auth import refresh_token
        from app.shared.schemas.auth import RefreshTokenRequest

        request_data = RefreshTokenRequest(refresh_token="valid_refresh_token")

        with patch(
            "app.shared.routers.auth.AuthService.refresh_access_token",
            new_callable=AsyncMock,
            return_value="new_access_token",
        ):
            response = await refresh_token(
                request_data=request_data,
                session=mock_session,
            )

            assert response.access_token == "new_access_token"
            assert response.token_type == "bearer"

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, mock_session):
        """Test refresh fails with invalid token."""
        from app.shared.routers.auth import refresh_token
        from app.shared.schemas.auth import RefreshTokenRequest
        from app.shared.exceptions.types import AuthenticationException

        request_data = RefreshTokenRequest(refresh_token="invalid_token")

        with patch(
            "app.shared.routers.auth.AuthService.refresh_access_token",
            new_callable=AsyncMock,
            side_effect=AuthenticationException("Invalid refresh token"),
        ):
            with pytest.raises(AuthenticationException):
                await refresh_token(
                    request_data=request_data,
                    session=mock_session,
                )


class TestSignoutEndpoint:
    """Test suite for POST /signout endpoint."""

    @pytest.mark.asyncio
    async def test_signout_success(self, mock_session):
        """Test successful signout."""
        from app.shared.routers.auth import signout
        from app.shared.schemas.auth import RefreshTokenRequest

        request_data = RefreshTokenRequest(refresh_token="valid_refresh_token")

        with patch(
            "app.shared.routers.auth.AuthService.revoke_refresh_token",
            new_callable=AsyncMock,
            return_value=True,
        ):
            response = await signout(
                request_data=request_data,
                session=mock_session,
            )

            assert response.message == "Successfully signed out"

    @pytest.mark.asyncio
    async def test_signout_token_not_found(self, mock_session):
        """Test signout when token not found."""
        from app.shared.routers.auth import signout
        from app.shared.schemas.auth import RefreshTokenRequest

        request_data = RefreshTokenRequest(refresh_token="unknown_token")

        with patch(
            "app.shared.routers.auth.AuthService.revoke_refresh_token",
            new_callable=AsyncMock,
            return_value=False,
        ):
            response = await signout(
                request_data=request_data,
                session=mock_session,
            )

            assert "not found or already revoked" in response.message
            assert response.success is False


class TestSignoutAllEndpoint:
    """Test suite for POST /signout/all endpoint."""

    @pytest.mark.asyncio
    async def test_signout_all_success(self, mock_session, mock_user):
        """Test successful signout from all devices."""
        from app.shared.routers.auth import signout_all

        with patch(
            "app.shared.routers.auth.AuthService.revoke_all_user_tokens",
            new_callable=AsyncMock,
            return_value=3,
        ):
            response = await signout_all(
                user=mock_user,
                session=mock_session,
            )

            assert "Signed out from 3 device(s)" in response.message


# =============================================================================
# OAuth Endpoint Tests
# =============================================================================


class TestOAuthInitEndpoint:
    """Test suite for GET /oauth/{provider} endpoint."""

    @pytest.mark.asyncio
    async def test_oauth_init_google(self, mock_request):
        """Test OAuth initiation for Google."""
        from app.shared.routers.auth import oauth_init
        from app.shared.enums import OAuthProviders

        mock_provider = MagicMock()
        mock_provider.get_authorization_url.return_value = (
            "https://accounts.google.com/o/oauth2/auth?..."
        )

        with patch(
            "app.shared.routers.auth.AuthService.get_oauth_provider",
            return_value=mock_provider,
        ):
            response = await oauth_init(
                provider=OAuthProviders.GOOGLE,
                request=mock_request,
                remember_me=False,
                callback_url=None,
            )

            assert "google.com" in response.authorization_url
            # State is now a signed token
            assert response.state is not None
            assert len(response.state) > 0

    @pytest.mark.asyncio
    async def test_oauth_init_with_callback_url(self, mock_request):
        """Test OAuth initiation with callback URL."""
        from app.shared.routers.auth import oauth_init
        from app.shared.enums import OAuthProviders
        from app.shared.services.oauth import OAuthStateManager

        mock_provider = MagicMock()
        mock_provider.get_authorization_url.return_value = (
            "https://accounts.google.com/o/oauth2/auth?..."
        )

        # Mock settings to include callback URL in CORS origins
        with patch(
            "app.shared.routers.auth.AuthService.get_oauth_provider",
            return_value=mock_provider,
        ), patch(
            "app.shared.routers.auth.OAuthStateManager.validate_callback_url",
            return_value=True,
        ):
            response = await oauth_init(
                provider=OAuthProviders.GOOGLE,
                request=mock_request,
                remember_me=True,
                callback_url="https://myapp.com/auth/callback",
            )

            assert response.authorization_url is not None
            assert response.state is not None

    @pytest.mark.asyncio
    async def test_oauth_init_invalid_callback_url(self, mock_request):
        """Test OAuth initiation rejects invalid callback URL."""
        from app.shared.routers.auth import oauth_init
        from app.shared.enums import OAuthProviders
        from app.shared.exceptions.types import BadRequestException

        with patch(
            "app.shared.routers.auth.OAuthStateManager.validate_callback_url",
            return_value=False,
        ):
            with pytest.raises(BadRequestException):
                await oauth_init(
                    provider=OAuthProviders.GOOGLE,
                    request=mock_request,
                    remember_me=False,
                    callback_url="https://evil-site.com/callback",
                )


class TestOAuthCallbackEndpoint:
    """Test suite for GET /oauth/{provider}/callback endpoint."""

    @pytest.mark.asyncio
    async def test_oauth_callback_invalid_state(self, mock_session, mock_request):
        """Test OAuth callback fails with invalid state."""
        from app.shared.routers.auth import oauth_callback
        from app.shared.enums import OAuthProviders
        from app.shared.exceptions.types import InvalidStateException

        with pytest.raises(InvalidStateException):
            await oauth_callback(
                provider=OAuthProviders.GOOGLE,
                request=mock_request,
                session=mock_session,
                code="auth_code",
                state="invalid_state_token",
            )

    @pytest.mark.asyncio
    async def test_oauth_callback_success_json_response(
        self, mock_session, mock_user, mock_token_pair, mock_request
    ):
        """Test successful OAuth callback returns JSON when no callback_url."""
        from app.shared.routers.auth import oauth_callback
        from app.shared.enums import OAuthProviders
        from app.shared.services.oauth import OAuthStateManager, OAuthStateData

        # Mock state data without callback_url
        mock_state_data = OAuthStateData(callback_url=None, remember_me=False)

        mock_provider = MagicMock()
        mock_provider.exchange_code_for_tokens = AsyncMock(
            return_value=MagicMock(access_token="oauth_access_token")
        )
        mock_provider.get_user_info = AsyncMock(
            return_value=MagicMock(
                provider="google",
                provider_user_id="12345",
                email="oauth@example.com",
                name="OAuth User",
            )
        )

        with patch(
            "app.shared.routers.auth.OAuthStateManager.decode_state",
            return_value=mock_state_data,
        ), patch(
            "app.shared.routers.auth.AuthService.get_oauth_provider",
            return_value=mock_provider,
        ), patch(
            "app.shared.routers.auth.AuthService.oauth_authenticate",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.user_db.get_by_id",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.AuthService.create_token_pair",
            new_callable=AsyncMock,
            return_value=mock_token_pair,
        ):
            response = await oauth_callback(
                provider=OAuthProviders.GOOGLE,
                request=mock_request,
                session=mock_session,
                code="auth_code",
                state="valid_state",
            )

            # Should return TokenResponse (JSON)
            assert response.access_token == "test_access_token"
            assert response.refresh_token == "test_refresh_token"

    @pytest.mark.asyncio
    async def test_oauth_callback_redirect_with_callback_url(
        self, mock_session, mock_user, mock_token_pair, mock_request
    ):
        """Test OAuth callback redirects to frontend with tokens in fragment."""
        from app.shared.routers.auth import oauth_callback
        from app.shared.enums import OAuthProviders
        from app.shared.services.oauth import OAuthStateData
        from fastapi.responses import RedirectResponse

        # Mock state data WITH callback_url
        mock_state_data = OAuthStateData(
            callback_url="https://myapp.com/auth/callback",
            remember_me=True,
        )

        mock_provider = MagicMock()
        mock_provider.exchange_code_for_tokens = AsyncMock(
            return_value=MagicMock(access_token="oauth_access_token")
        )
        mock_provider.get_user_info = AsyncMock(
            return_value=MagicMock(
                provider="google",
                provider_user_id="12345",
                email="oauth@example.com",
                name="OAuth User",
            )
        )

        with patch(
            "app.shared.routers.auth.OAuthStateManager.decode_state",
            return_value=mock_state_data,
        ), patch(
            "app.shared.routers.auth.AuthService.get_oauth_provider",
            return_value=mock_provider,
        ), patch(
            "app.shared.routers.auth.AuthService.oauth_authenticate",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.user_db.get_by_id",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.AuthService.create_token_pair",
            new_callable=AsyncMock,
            return_value=mock_token_pair,
        ):
            response = await oauth_callback(
                provider=OAuthProviders.GOOGLE,
                request=mock_request,
                session=mock_session,
                code="auth_code",
                state="valid_state",
            )

            # Should return RedirectResponse
            assert isinstance(response, RedirectResponse)
            assert response.status_code == 307

            # Check redirect URL contains tokens in fragment
            redirect_url = response.headers.get("location", "")
            assert redirect_url.startswith("https://myapp.com/auth/callback#")
            assert "access_token=test_access_token" in redirect_url
            assert "refresh_token=test_refresh_token" in redirect_url
            assert "token_type=bearer" in redirect_url

    @pytest.mark.asyncio
    async def test_oauth_callback_redirect_with_error(self, mock_session, mock_request):
        """Test OAuth callback redirects with error on failure."""
        from app.shared.routers.auth import oauth_callback
        from app.shared.enums import OAuthProviders
        from app.shared.services.oauth import OAuthStateData
        from app.shared.exceptions.types import OAuthException
        from fastapi.responses import RedirectResponse

        # Mock state data WITH callback_url
        mock_state_data = OAuthStateData(
            callback_url="https://myapp.com/auth/callback",
            remember_me=False,
        )

        mock_provider = MagicMock()
        mock_provider.exchange_code_for_tokens = AsyncMock(
            side_effect=OAuthException(message="Token exchange failed")
        )

        with patch(
            "app.shared.routers.auth.OAuthStateManager.decode_state",
            return_value=mock_state_data,
        ), patch(
            "app.shared.routers.auth.AuthService.get_oauth_provider",
            return_value=mock_provider,
        ):
            response = await oauth_callback(
                provider=OAuthProviders.GOOGLE,
                request=mock_request,
                session=mock_session,
                code="auth_code",
                state="valid_state",
            )

            # Should return RedirectResponse with error
            assert isinstance(response, RedirectResponse)
            assert response.status_code == 307

            redirect_url = response.headers.get("location", "")
            assert "https://myapp.com/auth/callback?error=" in redirect_url

    @pytest.mark.asyncio
    async def test_oauth_callback_raises_on_error_without_callback(
        self, mock_session, mock_request
    ):
        """Test OAuth callback raises exception when error and no callback_url."""
        from app.shared.routers.auth import oauth_callback
        from app.shared.enums import OAuthProviders
        from app.shared.services.oauth import OAuthStateData
        from app.shared.exceptions.types import OAuthException

        # Mock state data WITHOUT callback_url
        mock_state_data = OAuthStateData(callback_url=None, remember_me=False)

        mock_provider = MagicMock()
        mock_provider.exchange_code_for_tokens = AsyncMock(
            side_effect=OAuthException(message="Token exchange failed")
        )

        with patch(
            "app.shared.routers.auth.OAuthStateManager.decode_state",
            return_value=mock_state_data,
        ), patch(
            "app.shared.routers.auth.AuthService.get_oauth_provider",
            return_value=mock_provider,
        ):
            with pytest.raises(OAuthException):
                await oauth_callback(
                    provider=OAuthProviders.GOOGLE,
                    request=mock_request,
                    session=mock_session,
                    code="auth_code",
                    state="valid_state",
                )


# =============================================================================
# Password Reset Endpoint Tests
# =============================================================================


class TestPasswordResetEndpoint:
    """Test suite for POST /password/reset endpoint."""

    @pytest.mark.asyncio
    async def test_request_password_reset_success(self, mock_session, mock_user):
        """Test successful password reset request."""
        from app.shared.routers.auth import request_password_reset
        from app.shared.schemas.auth import PasswordResetRequest

        request_data = PasswordResetRequest(email="test@example.com")

        with patch(
            "app.shared.routers.auth.user_db.get_one_by_conditions",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.AuthService.send_otp",
            new_callable=AsyncMock,
        ):
            response = await request_password_reset(
                request_data=request_data,
                session=mock_session,
            )

            # Should not reveal if user exists
            assert "reset code has been sent" in response.message

    @pytest.mark.asyncio
    async def test_request_password_reset_user_not_found(self, mock_session):
        """Test password reset request for non-existent user."""
        from app.shared.routers.auth import request_password_reset
        from app.shared.schemas.auth import PasswordResetRequest

        request_data = PasswordResetRequest(email="nonexistent@example.com")

        with patch(
            "app.shared.routers.auth.user_db.get_one_by_conditions",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = await request_password_reset(
                request_data=request_data,
                session=mock_session,
            )

            # Should not reveal if user exists
            assert "reset code has been sent" in response.message


class TestPasswordResetConfirmEndpoint:
    """Test suite for POST /password/reset/confirm endpoint."""

    @pytest.mark.asyncio
    async def test_confirm_password_reset_success(self, mock_session, mock_user):
        """Test successful password reset confirmation."""
        from app.shared.routers.auth import confirm_password_reset
        from app.shared.schemas.auth import PasswordResetConfirmRequest

        request_data = PasswordResetConfirmRequest(
            email="test@example.com",
            otp_code="123456",
            new_password="NewSecurePass123!",
        )

        with patch(
            "app.shared.routers.auth.AuthService.verify_otp",
            new_callable=AsyncMock,
        ), patch(
            "app.shared.routers.auth.AuthService.reset_password",
            new_callable=AsyncMock,
        ), patch(
            "app.shared.routers.auth.user_db.get_one_by_conditions",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.shared.routers.auth.AuthService.revoke_all_user_tokens",
            new_callable=AsyncMock,
        ):
            response = await confirm_password_reset(
                request_data=request_data,
                session=mock_session,
            )

            assert "reset successfully" in response.message

    @pytest.mark.asyncio
    async def test_confirm_password_reset_invalid_otp(self, mock_session):
        """Test password reset fails with invalid OTP."""
        from app.shared.routers.auth import confirm_password_reset
        from app.shared.schemas.auth import PasswordResetConfirmRequest
        from app.shared.exceptions.types import OTPInvalidException

        request_data = PasswordResetConfirmRequest(
            email="test@example.com",
            otp_code="000000",  # Valid 6-digit format but wrong code
            new_password="NewSecurePass123!",
        )

        # Use a function to properly raise the exception inside async context
        async def mock_verify_otp(*args, **kwargs):
            raise OTPInvalidException()

        with patch(
            "app.shared.routers.auth.AuthService.verify_otp",
            side_effect=mock_verify_otp,
        ):
            with pytest.raises(OTPInvalidException):
                await confirm_password_reset(
                    request_data=request_data,
                    session=mock_session,
                )


class TestChangePasswordEndpoint:
    """Test suite for POST /password/change endpoint."""

    @pytest.mark.asyncio
    async def test_change_password_success(self, mock_session, mock_user):
        """Test successful password change."""
        from app.shared.routers.auth import change_password
        from app.shared.schemas.auth import ChangePasswordRequest

        request_data = ChangePasswordRequest(
            current_password="OldPass123!",
            new_password="NewSecurePass123!",
        )

        with patch(
            "app.shared.routers.auth.AuthService.change_password",
            new_callable=AsyncMock,
        ):
            response = await change_password(
                request_data=request_data,
                user=mock_user,
                session=mock_session,
            )

            assert "changed successfully" in response.message

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, mock_session, mock_user):
        """Test password change fails with wrong current password."""
        from app.shared.routers.auth import change_password
        from app.shared.schemas.auth import ChangePasswordRequest
        from app.shared.exceptions.types import InvalidCredentialsException

        request_data = ChangePasswordRequest(
            current_password="wrong_password",
            new_password="NewSecurePass123!",
        )

        # Mock the context manager to allow the exception to propagate
        async def mock_change_password(*args, **kwargs):
            raise InvalidCredentialsException()

        with patch(
            "app.shared.routers.auth.AuthService.change_password",
            side_effect=mock_change_password,
        ):
            with pytest.raises(InvalidCredentialsException):
                await change_password(
                    request_data=request_data,
                    user=mock_user,
                    session=mock_session,
                )


# =============================================================================
# Profile Endpoint Tests
# =============================================================================


class TestGetProfileEndpoint:
    """Test suite for GET /me endpoint."""

    @pytest.mark.asyncio
    async def test_get_profile_success(self, mock_session, mock_user):
        """Test successful profile retrieval."""
        from app.shared.routers.auth import get_profile

        with patch(
            "app.shared.routers.auth.user_db.get_by_id",
            new_callable=AsyncMock,
            return_value=mock_user,
        ):
            response = await get_profile(user=mock_user, session=mock_session)

            assert response.email == "test@example.com"
            assert response.full_name == "Test User"
            assert response.is_active is True


class TestGetAvatarUploadCredentialsEndpoint:
    """Test suite for GET /me/avatar/upload-credentials endpoint."""

    @pytest.mark.asyncio
    async def test_get_avatar_upload_credentials_success(self, mock_user):
        """Test successful avatar upload credentials generation."""
        from app.shared.routers.auth import get_avatar_upload_credentials
        from app.shared.services.cloudinary import CloudinaryUploadCredentials

        mock_credentials = CloudinaryUploadCredentials(
            upload_url="https://api.cloudinary.com/v1_1/test-cloud/image/upload",
            api_key="test_api_key",
            timestamp=1706745600,
            signature="test_signature",
            cloud_name="test-cloud",
            folder="avatars",
            resource_type="image",
        )

        with patch(
            "app.shared.routers.auth.CloudinaryService.generate_upload_credentials",
            return_value=mock_credentials,
        ) as mock_generate:
            response = await get_avatar_upload_credentials(user=mock_user)

            assert (
                response.upload_url
                == "https://api.cloudinary.com/v1_1/test-cloud/image/upload"
            )
            assert response.api_key == "test_api_key"
            assert response.cloud_name == "test-cloud"
            assert response.folder == "avatars"
            assert response.resource_type == "image"

            # Verify it was called with correct parameters
            mock_generate.assert_called_once_with(
                folder="avatars",
                resource_type="image",
            )

    @pytest.mark.asyncio
    async def test_get_avatar_upload_credentials_returns_correct_model(self, mock_user):
        """Test that the endpoint returns CloudinaryUploadCredentials model."""
        from app.shared.routers.auth import get_avatar_upload_credentials
        from app.shared.services.cloudinary import CloudinaryUploadCredentials

        mock_credentials = CloudinaryUploadCredentials(
            upload_url="https://api.cloudinary.com/v1_1/test-cloud/image/upload",
            api_key="test_api_key",
            timestamp=1706745600,
            signature="test_signature",
            cloud_name="test-cloud",
            folder="avatars",
            resource_type="image",
        )

        with patch(
            "app.shared.routers.auth.CloudinaryService.generate_upload_credentials",
            return_value=mock_credentials,
        ):
            response = await get_avatar_upload_credentials(user=mock_user)

            assert isinstance(response, CloudinaryUploadCredentials)

    @pytest.mark.asyncio
    async def test_get_avatar_upload_credentials_logs_request(self, mock_user):
        """Test that the endpoint logs the request."""
        from app.shared.routers.auth import get_avatar_upload_credentials
        from app.shared.services.cloudinary import CloudinaryUploadCredentials

        mock_credentials = CloudinaryUploadCredentials(
            upload_url="https://api.cloudinary.com/v1_1/test-cloud/image/upload",
            api_key="test_api_key",
            timestamp=1706745600,
            signature="test_signature",
            cloud_name="test-cloud",
            folder="avatars",
            resource_type="image",
        )

        with patch(
            "app.shared.routers.auth.CloudinaryService.generate_upload_credentials",
            return_value=mock_credentials,
        ), patch(
            "app.shared.routers.auth.auth_logger.info",
        ) as mock_logger:
            await get_avatar_upload_credentials(user=mock_user)

            # Verify logging was called
            mock_logger.assert_called_once()
            call_args = mock_logger.call_args[0][0]
            assert str(mock_user.id) in call_args
            assert "avatar upload credentials" in call_args.lower()

    @pytest.mark.asyncio
    async def test_get_avatar_upload_credentials_raises_when_cloudinary_not_configured(
        self, mock_user
    ):
        """Test that the endpoint raises exception when Cloudinary is not configured."""
        from app.shared.routers.auth import get_avatar_upload_credentials
        from app.shared.exceptions.types import AppException
        from fastapi import status

        with patch(
            "app.shared.routers.auth.CloudinaryService.generate_upload_credentials",
            side_effect=AppException(
                message="Cloudinary is not properly configured.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ),
        ):
            with pytest.raises(AppException) as exc_info:
                await get_avatar_upload_credentials(user=mock_user)

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Cloudinary" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_avatar_upload_credentials_raises_on_signature_failure(
        self, mock_user
    ):
        """Test that the endpoint raises exception when signature generation fails."""
        from app.shared.routers.auth import get_avatar_upload_credentials
        from app.shared.exceptions.types import AppException
        from fastapi import status

        with patch(
            "app.shared.routers.auth.CloudinaryService.generate_upload_credentials",
            side_effect=AppException(
                message="Failed to generate upload credentials: Signature error",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ),
        ):
            with pytest.raises(AppException) as exc_info:
                await get_avatar_upload_credentials(user=mock_user)

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestUpdateProfileEndpoint:
    """Test suite for PATCH /me endpoint."""

    @pytest.mark.asyncio
    async def test_update_profile_success(self, mock_session, mock_user):
        """Test successful profile update."""
        from app.shared.routers.auth import update_profile
        from app.shared.schemas.auth import ProfileUpdateRequest

        request_data = ProfileUpdateRequest(full_name="Updated Name")

        with patch(
            "app.shared.routers.auth.user_db.update",
            new_callable=AsyncMock,
        ), patch(
            "app.shared.routers.auth.user_db.get_by_id",
            new_callable=AsyncMock,
            return_value=mock_user,
        ):
            response = await update_profile(
                request_data=request_data,
                user=mock_user,
                session=mock_session,
            )

            assert response.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_update_profile_no_changes(self, mock_session, mock_user):
        """Test profile update with no changes."""
        from app.shared.routers.auth import update_profile
        from app.shared.schemas.auth import ProfileUpdateRequest

        request_data = ProfileUpdateRequest()  # No changes

        with patch(
            "app.shared.routers.auth.user_db.update",
            new_callable=AsyncMock,
        ) as mock_update, patch(
            "app.shared.routers.auth.user_db.get_by_id",
            new_callable=AsyncMock,
            return_value=mock_user,
        ):
            await update_profile(
                request_data=request_data,
                user=mock_user,
                session=mock_session,
            )

            # Update should not be called if no changes
            mock_update.assert_not_called()


class TestDeleteAccountEndpoint:
    """Test suite for DELETE /me endpoint."""

    @pytest.mark.asyncio
    async def test_delete_account_success(self, mock_session, mock_user):
        """Test successful account deletion."""
        from app.shared.routers.auth import delete_account

        with patch(
            "app.shared.routers.auth.user_db.soft_delete",
            new_callable=AsyncMock,
        ), patch(
            "app.shared.routers.auth.AuthService.revoke_all_user_tokens",
            new_callable=AsyncMock,
        ):
            response = await delete_account(user=mock_user, session=mock_session)

            assert "deleted" in response.message


# =============================================================================
# Sessions Endpoint Tests
# =============================================================================


class TestGetSessionsEndpoint:
    """Test suite for POST /sessions endpoint."""

    @pytest.mark.asyncio
    async def test_get_sessions_success(self, mock_session, mock_user):
        """Test successful sessions retrieval."""
        from app.shared.routers.auth import get_sessions
        from app.shared.schemas.auth import RefreshTokenRequest

        # Create mock refresh token request
        request_data = RefreshTokenRequest(refresh_token="test_refresh_token")

        # Create mock session with token_hash for comparison
        mock_token_hash = "expected_hash"
        mock_sessions = [
            MagicMock(
                id=uuid4(),
                device_info="Windows / Chrome",
                token_hash=mock_token_hash,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            ),
            MagicMock(
                id=uuid4(),
                device_info="macOS / Safari",
                token_hash="other_hash",
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            ),
        ]

        with patch(
            "app.shared.routers.auth.AuthService.get_active_sessions",
            new_callable=AsyncMock,
            return_value=mock_sessions,
        ), patch(
            "app.shared.routers.auth.AuthService.hash_token",
            return_value=mock_token_hash,
        ):
            response = await get_sessions(
                user=mock_user,
                request_data=request_data,
                session=mock_session,
            )

            assert response.total == 2
            assert len(response.sessions) == 2
            # First session should be marked as current (matching hash)
            assert response.sessions[0].is_current is True
            assert response.sessions[1].is_current is False


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Test suite for helper functions."""

    def test_get_device_info_from_request_with_user_agent(self, mock_request):
        """Test device info extraction with User-Agent."""
        from app.shared.routers.auth import _get_device_info_from_request

        # Set a realistic user agent
        mock_request.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
        }
        device_info = _get_device_info_from_request(mock_request)

        assert "Windows" in device_info
        assert "Chrome" in device_info

    def test_get_device_info_from_request_without_user_agent(self, mock_request):
        """Test device info extraction without User-Agent."""
        from app.shared.routers.auth import _get_device_info_from_request

        mock_request.headers = {}
        device_info = _get_device_info_from_request(mock_request)

        # Without user agent, returns None (per get_device_info utility)
        assert device_info is None

    def test_build_profile_response(self, mock_user):
        """Test profile response building."""
        from app.shared.routers.auth import _build_profile_response

        response = _build_profile_response(mock_user)

        assert response.email == mock_user.email
        assert response.full_name == mock_user.full_name
        assert response.has_password is True


# =============================================================================
# Router Configuration Tests
# =============================================================================


class TestRouterConfiguration:
    """Test suite for router configuration."""

    def test_router_has_authentication_tag(self):
        """Test that router has 'Authentication' tag."""
        from app.shared.routers.auth import router

        assert "Authentication" in router.tags

    def test_router_prefix_is_empty(self):
        """Test that router has no built-in prefix."""
        from app.shared.routers.auth import router

        # Router should not have built-in prefix (prefix added during include)
        assert router.prefix == ""

    def test_router_has_expected_routes(self):
        """Test that router has all expected routes."""
        from app.shared.routers.auth import router

        route_paths = [route.path for route in router.routes]

        # Check for key routes
        assert "/signup" in route_paths
        assert "/signin" in route_paths
        assert "/token/refresh" in route_paths
        assert "/signout" in route_paths
        assert "/signout/all" in route_paths
        assert "/me" in route_paths
        assert "/sessions" in route_paths

    def test_router_oauth_routes_exist(self):
        """Test that OAuth routes exist."""
        from app.shared.routers.auth import router

        route_paths = [route.path for route in router.routes]

        oauth_routes = [p for p in route_paths if "oauth" in p]
        assert len(oauth_routes) >= 2  # At least init and callback

    def test_router_password_routes_exist(self):
        """Test that password routes exist."""
        from app.shared.routers.auth import router

        route_paths = [route.path for route in router.routes]

        assert "/password/reset" in route_paths
        assert "/password/reset/confirm" in route_paths
        assert "/password/change" in route_paths


class TestModuleExports:
    """Test suite for module exports."""

    def test_router_is_exported(self):
        """Test that router is exported from module."""
        from app.shared.routers.auth import router

        assert router is not None

    def test_router_exported_from_init(self):
        """Test that router is exported from __init__."""
        from app.shared.routers import auth_router

        assert auth_router is not None
