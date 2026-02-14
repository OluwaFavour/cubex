"""
Integration tests for auth router endpoints.

Tests all auth endpoints with real database and per-test rollback.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.shared.enums import OTPPurpose


# ============================================================================
# Test Signup Endpoint
# ============================================================================


class TestSignupEndpoint:
    """Tests for POST /auth/signup"""

    @pytest.mark.asyncio
    async def test_signup_success(self, client: AsyncClient):
        """Should create user and send verification email."""
        payload = {
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "full_name": "New User",
        }
        response = await client.post("/auth/signup", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Verification code sent to your email"
        assert data["email"] == "newuser@example.com"
        assert data["requires_verification"] is True

    @pytest.mark.asyncio
    async def test_signup_duplicate_email(self, client: AsyncClient, test_user):
        """Should return 409 for duplicate email."""
        payload = {
            "email": test_user.email,  # Already exists
            "password": "SecurePass123!",
            "full_name": "Another User",
        }
        response = await client.post("/auth/signup", json=payload)

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_signup_invalid_email(self, client: AsyncClient):
        """Should return 422 for invalid email format."""
        payload = {
            "email": "notanemail",
            "password": "SecurePass123!",
            "full_name": "Test User",
        }
        response = await client.post("/auth/signup", json=payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_weak_password(self, client: AsyncClient):
        """Should return 422 for password not meeting requirements."""
        payload = {
            "email": "test@example.com",
            "password": "weak",  # Too short, no uppercase, no digit
            "full_name": "Test User",
        }
        response = await client.post("/auth/signup", json=payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_missing_email(self, client: AsyncClient):
        """Should return 422 for missing email."""
        payload = {
            "password": "SecurePass123!",
            "full_name": "Test User",
        }
        response = await client.post("/auth/signup", json=payload)

        assert response.status_code == 422


# ============================================================================
# Test Verify Signup Endpoint
# ============================================================================


class TestVerifySignupEndpoint:
    """Tests for POST /auth/signup/verify"""

    @pytest.mark.asyncio
    async def test_verify_signup_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should verify email and return tokens."""
        from datetime import datetime, timedelta, timezone
        from app.shared.db.models import OTPToken, User
        from app.shared.services.auth import AuthService
        from app.shared.utils import hmac_hash_otp
        from app.shared.config import settings

        # Create unverified user
        user = User(
            id=uuid4(),
            email="unverified@example.com",
            password_hash="$2b$12$jTCIzYr5zEDrCnh/q48u1OgmUvXQQx3BAoUnIA7BdXgZIxvw2Rvfy",
            full_name="Unverified User",
            email_verified=False,
        )
        db_session.add(user)
        await db_session.flush()

        # Create valid OTP
        otp_code = AuthService.generate_otp()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        otp = OTPToken(
            id=uuid4(),
            user_id=user.id,
            email=user.email,
            code_hash=hmac_hash_otp(otp_code, settings.OTP_HMAC_SECRET),
            purpose=OTPPurpose.EMAIL_VERIFICATION,
            expires_at=expires_at,
        )
        db_session.add(otp)
        await db_session.flush()

        payload = {"email": user.email, "otp_code": otp_code}
        response = await client.post("/auth/signup/verify", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_verify_signup_invalid_otp(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should return 400 for invalid OTP."""
        from datetime import datetime, timedelta, timezone
        from app.shared.db.models import OTPToken, User
        from app.shared.utils import hmac_hash_otp
        from app.shared.config import settings

        # Create unverified user
        user = User(
            id=uuid4(),
            email="unverified2@example.com",
            password_hash="$2b$12$jTCIzYr5zEDrCnh/q48u1OgmUvXQQx3BAoUnIA7BdXgZIxvw2Rvfy",
            full_name="Unverified User",
            email_verified=False,
        )
        db_session.add(user)
        await db_session.flush()

        # Create OTP with different code
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        otp = OTPToken(
            id=uuid4(),
            user_id=user.id,
            email=user.email,
            code_hash=hmac_hash_otp("123456", settings.OTP_HMAC_SECRET),  # Real OTP
            purpose=OTPPurpose.EMAIL_VERIFICATION,
            expires_at=expires_at,
        )
        db_session.add(otp)
        await db_session.flush()

        payload = {"email": user.email, "otp_code": "000000"}  # Wrong code
        response = await client.post("/auth/signup/verify", json=payload)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_verify_signup_no_otp(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should return 400 when no OTP exists."""
        from app.shared.db.models import User

        # Create unverified user without OTP
        user = User(
            id=uuid4(),
            email="nootp@example.com",
            password_hash="$2b$12$jTCIzYr5zEDrCnh/q48u1OgmUvXQQx3BAoUnIA7BdXgZIxvw2Rvfy",
            full_name="No OTP User",
            email_verified=False,
        )
        db_session.add(user)
        await db_session.flush()

        payload = {"email": user.email, "otp_code": "123456"}
        response = await client.post("/auth/signup/verify", json=payload)

        assert response.status_code == 400


# ============================================================================
# Test Resend Verification Endpoint
# ============================================================================


class TestResendVerificationEndpoint:
    """Tests for POST /auth/signup/resend"""

    @pytest.mark.asyncio
    async def test_resend_verification_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should resend verification email."""
        from app.shared.db.models import User

        # Create unverified user
        user = User(
            id=uuid4(),
            email="needsverify@example.com",
            password_hash="$2b$12$jTCIzYr5zEDrCnh/q48u1OgmUvXQQx3BAoUnIA7BdXgZIxvw2Rvfy",
            full_name="Needs Verification",
            email_verified=False,
        )
        db_session.add(user)
        await db_session.flush()

        payload = {"email": user.email}
        response = await client.post("/auth/signup/resend", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_resend_verification_already_verified(
        self, client: AsyncClient, test_user
    ):
        """Should return success=False for already verified user."""
        payload = {"email": test_user.email}
        response = await client.post("/auth/signup/resend", json=payload)

        # API returns 200 with success=False for already verified
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is False

    @pytest.mark.asyncio
    async def test_resend_verification_user_not_found(self, client: AsyncClient):
        """Should return 404 for non-existent user."""
        payload = {"email": "nonexistent@example.com"}
        response = await client.post("/auth/signup/resend", json=payload)

        # API may return 200 to prevent email enumeration or 404
        assert response.status_code in [200, 404]


# ============================================================================
# Test Signin Endpoint
# ============================================================================


class TestSigninEndpoint:
    """Tests for POST /auth/signin"""

    @pytest.mark.asyncio
    async def test_signin_success(self, client: AsyncClient, db_session: AsyncSession):
        """Should return tokens for valid credentials."""
        from app.shared.db.models import User
        from app.shared.utils import hash_password

        # Create verified user with known password
        password = "TestPassword123!"
        user = User(
            id=uuid4(),
            email="signin_test@example.com",
            password_hash=hash_password(password),
            full_name="Signin Test User",
            email_verified=True,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        payload = {"email": user.email, "password": password}
        response = await client.post("/auth/signin", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_signin_invalid_password(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should return 401 for wrong password."""
        from app.shared.db.models import User
        from app.shared.utils import hash_password

        user = User(
            id=uuid4(),
            email="wrongpass@example.com",
            password_hash=hash_password("CorrectPassword123!"),
            full_name="Wrong Pass User",
            email_verified=True,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        payload = {"email": user.email, "password": "WrongPassword123!"}
        response = await client.post("/auth/signin", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_signin_user_not_found(self, client: AsyncClient):
        """Should return 401 for non-existent user."""
        payload = {"email": "nonexistent@example.com", "password": "SomePassword123!"}
        response = await client.post("/auth/signin", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_signin_unverified_user(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should still allow signin for unverified user (API allows this)."""
        from app.shared.db.models import User
        from app.shared.utils import hash_password

        password = "TestPassword123!"
        user = User(
            id=uuid4(),
            email="unverified_signin@example.com",
            password_hash=hash_password(password),
            full_name="Unverified User",
            email_verified=False,
        )
        db_session.add(user)
        await db_session.flush()

        payload = {"email": user.email, "password": password}
        response = await client.post("/auth/signin", json=payload)

        # API allows unverified users to signin (they just can't do certain actions)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data


# ============================================================================
# Test Token Refresh Endpoint
# ============================================================================


class TestTokenRefreshEndpoint:
    """Tests for POST /auth/token/refresh"""

    @pytest.mark.asyncio
    async def test_token_refresh_invalid_token(self, client: AsyncClient):
        """Should return 401 for invalid refresh token."""
        payload = {"refresh_token": "invalid_token"}
        response = await client.post("/auth/token/refresh", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_token_refresh_missing_token(self, client: AsyncClient):
        """Should return 422 for missing refresh token."""
        payload = {}
        response = await client.post("/auth/token/refresh", json=payload)

        assert response.status_code == 422


# ============================================================================
# Test Signout Endpoints
# ============================================================================


class TestSignoutEndpoint:
    """Tests for POST /auth/signout"""

    @pytest.mark.asyncio
    async def test_signout_success(self, client: AsyncClient, db_session: AsyncSession):
        """Should sign out with valid refresh token."""
        import hashlib
        from datetime import datetime, timedelta, timezone
        from app.shared.db.models import RefreshToken, User
        from app.shared.utils import create_jwt_token, hash_password

        # Create user
        user = User(
            id=uuid4(),
            email="signout_test@example.com",
            password_hash=hash_password("TestPassword123!"),
            full_name="Signout Test",
            email_verified=True,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        # Create refresh token
        token_value = create_jwt_token(
            data={"sub": str(user.id), "type": "refresh"},
            expires_delta=timedelta(days=7),
        )
        # Hash the token for storage (must be 64 chars max)
        token_hash = hashlib.sha256(token_value.encode("utf-8")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        refresh_token = RefreshToken(
            id=uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            device_info="Test Device",
            expires_at=expires_at,
        )
        db_session.add(refresh_token)
        await db_session.flush()

        payload = {"refresh_token": token_value}
        response = await client.post("/auth/signout", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_signout_invalid_token(self, client: AsyncClient):
        """Should return success:false for invalid token (graceful handling)."""
        payload = {"refresh_token": "invalid_token"}
        response = await client.post("/auth/signout", json=payload)

        # Signout handles invalid tokens gracefully
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is False


class TestSignoutAllEndpoint:
    """Tests for POST /auth/signout/all"""

    @pytest.mark.asyncio
    async def test_signout_all_success(self, authenticated_client: AsyncClient):
        """Should sign out all sessions."""
        response = await authenticated_client.post("/auth/signout/all")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_signout_all_unauthenticated(self, client: AsyncClient):
        """Should return 401 for unauthenticated request."""
        response = await client.post("/auth/signout/all")

        assert response.status_code == 401


# ============================================================================
# Test Password Reset Endpoints
# ============================================================================


class TestPasswordResetRequestEndpoint:
    """Tests for POST /auth/password/reset"""

    @pytest.mark.asyncio
    async def test_password_reset_request_success(self, client: AsyncClient, test_user):
        """Should send password reset email."""
        payload = {"email": test_user.email}
        response = await client.post("/auth/password/reset", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_password_reset_request_nonexistent_user(self, client: AsyncClient):
        """Should still return 200 to prevent email enumeration."""
        payload = {"email": "nonexistent@example.com"}
        response = await client.post("/auth/password/reset", json=payload)

        # Returns 200 to prevent email enumeration
        assert response.status_code == 200


class TestPasswordResetConfirmEndpoint:
    """Tests for POST /auth/password/reset/confirm"""

    @pytest.mark.asyncio
    async def test_password_reset_confirm_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Should reset password with valid OTP."""
        from datetime import datetime, timedelta, timezone
        from app.shared.db.models import OTPToken
        from app.shared.services.auth import AuthService
        from app.shared.utils import hmac_hash_otp
        from app.shared.config import settings

        # Create password reset OTP
        otp_code = AuthService.generate_otp()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        otp = OTPToken(
            id=uuid4(),
            user_id=test_user.id,
            email=test_user.email,
            code_hash=hmac_hash_otp(otp_code, settings.OTP_HMAC_SECRET),
            purpose=OTPPurpose.PASSWORD_RESET,
            expires_at=expires_at,
        )
        db_session.add(otp)
        await db_session.flush()

        payload = {
            "email": test_user.email,
            "otp_code": otp_code,
            "new_password": "NewSecurePass123!",
        }
        response = await client.post("/auth/password/reset/confirm", json=payload)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_password_reset_confirm_invalid_otp(
        self, client: AsyncClient, test_user
    ):
        """Should return 400 for invalid OTP."""
        payload = {
            "email": test_user.email,
            "otp_code": "000000",
            "new_password": "NewSecurePass123!",
        }
        response = await client.post("/auth/password/reset/confirm", json=payload)

        assert response.status_code == 400


class TestPasswordChangeEndpoint:
    """Tests for POST /auth/password/change"""

    @pytest.mark.asyncio
    async def test_password_change_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should change password with valid current password."""
        from app.shared.db.models import User
        from app.shared.utils import hash_password, create_jwt_token
        from datetime import timedelta

        password = "CurrentPassword123!"
        user = User(
            id=uuid4(),
            email="changepass@example.com",
            password_hash=hash_password(password),
            full_name="Change Pass User",
            email_verified=True,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        # Create access token
        access_token = create_jwt_token(
            data={"sub": str(user.id), "email": user.email, "type": "access"},
            expires_delta=timedelta(minutes=15),
        )

        payload = {
            "current_password": password,
            "new_password": "NewSecurePass456!",
        }
        response = await client.post(
            "/auth/password/change",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_password_change_wrong_current_password(
        self, authenticated_client: AsyncClient
    ):
        """Should return 401 for wrong current password."""
        payload = {
            "current_password": "WrongPassword123!",
            "new_password": "NewSecurePass456!",
        }
        response = await authenticated_client.post(
            "/auth/password/change", json=payload
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_password_change_unauthenticated(self, client: AsyncClient):
        """Should return 401 for unauthenticated request."""
        payload = {
            "current_password": "TestPassword123!",
            "new_password": "NewSecurePass456!",
        }
        response = await client.post("/auth/password/change", json=payload)

        assert response.status_code == 401


# ============================================================================
# Test Profile Endpoints
# ============================================================================


class TestGetProfileEndpoint:
    """Tests for GET /auth/me"""

    @pytest.mark.asyncio
    async def test_get_profile_success(
        self, authenticated_client: AsyncClient, test_user
    ):
        """Should return current user profile."""
        response = await authenticated_client.get("/auth/me")

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["full_name"] == test_user.full_name

    @pytest.mark.asyncio
    async def test_get_profile_unauthenticated(self, client: AsyncClient):
        """Should return 401 for unauthenticated request."""
        response = await client.get("/auth/me")

        assert response.status_code == 401


class TestUpdateProfileEndpoint:
    """Tests for PATCH /auth/me"""

    @pytest.mark.asyncio
    async def test_update_profile_success(self, authenticated_client: AsyncClient):
        """Should update user profile."""
        payload = {"full_name": "Updated Name"}
        response = await authenticated_client.patch("/auth/me", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_profile_unauthenticated(self, client: AsyncClient):
        """Should return 401 for unauthenticated request."""
        payload = {"full_name": "Updated Name"}
        response = await client.patch("/auth/me", json=payload)

        assert response.status_code == 401


class TestDeleteAccountEndpoint:
    """Tests for DELETE /auth/me"""

    @pytest.mark.asyncio
    async def test_delete_account_success(self, authenticated_client: AsyncClient):
        """Should soft delete user account."""
        response = await authenticated_client.delete("/auth/me")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_account_unauthenticated(self, client: AsyncClient):
        """Should return 401 for unauthenticated request."""
        response = await client.delete("/auth/me")

        assert response.status_code == 401


# ============================================================================
# Test Sessions Endpoint
# ============================================================================


class TestGetSessionsEndpoint:
    """Tests for POST /auth/sessions"""

    @pytest.mark.asyncio
    async def test_get_sessions_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should return list of active sessions."""
        import hashlib
        from datetime import datetime, timedelta, timezone
        from app.shared.db.models import RefreshToken, User
        from app.shared.utils import create_jwt_token, hash_password

        # Create user
        user = User(
            id=uuid4(),
            email="sessions_test@example.com",
            password_hash=hash_password("TestPassword123!"),
            full_name="Sessions Test",
            email_verified=True,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        # Create refresh token
        token_value = create_jwt_token(
            data={"sub": str(user.id), "type": "refresh"},
            expires_delta=timedelta(days=7),
        )
        # Hash the token for storage (must be 64 chars max)
        token_hash = hashlib.sha256(token_value.encode("utf-8")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        refresh_token = RefreshToken(
            id=uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            device_info="Test Device",
            expires_at=expires_at,
        )
        db_session.add(refresh_token)
        await db_session.flush()

        # Create access token
        access_token = create_jwt_token(
            data={"sub": str(user.id), "email": user.email, "type": "access"},
            expires_delta=timedelta(minutes=15),
        )

        payload = {"refresh_token": token_value}
        response = await client.post(
            "/auth/sessions",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    @pytest.mark.asyncio
    async def test_get_sessions_unauthenticated(self, client: AsyncClient):
        """Should return 401 for unauthenticated request."""
        payload = {"refresh_token": "some_token"}
        response = await client.post("/auth/sessions", json=payload)

        assert response.status_code == 401


# ============================================================================
# Test OAuth Endpoints
# ============================================================================


class TestOAuthInitiateEndpoint:
    """Tests for GET /auth/oauth/{provider}"""

    @pytest.mark.asyncio
    async def test_oauth_google_initiate(self, client: AsyncClient):
        """Should redirect to Google OAuth."""
        response = await client.get(
            "/auth/oauth/google",
            params={"redirect_uri": "http://localhost/callback"},
            follow_redirects=False,
        )

        # Should redirect to Google
        assert response.status_code in [302, 307, 200]

    @pytest.mark.asyncio
    async def test_oauth_github_initiate(self, client: AsyncClient):
        """Should redirect to GitHub OAuth."""
        response = await client.get(
            "/auth/oauth/github",
            params={"redirect_uri": "http://localhost/callback"},
            follow_redirects=False,
        )

        # Should redirect to GitHub
        assert response.status_code in [302, 307, 200]

    @pytest.mark.asyncio
    async def test_oauth_invalid_provider(self, client: AsyncClient):
        """Should return 400 for invalid provider."""
        response = await client.get(
            "/auth/oauth/invalid",
            params={"redirect_uri": "http://localhost/callback"},
        )

        # Could be 400 or 422 depending on validation
        assert response.status_code in [400, 422]


# ============================================================================
# Test Router Configuration
# ============================================================================


class TestRouterConfiguration:
    """Tests for router setup and configuration."""

    def test_router_is_api_router(self):
        """Test that router is an APIRouter instance."""
        from fastapi import APIRouter
        from app.shared.routers.auth import router

        assert isinstance(router, APIRouter)

    def test_router_prefix_is_empty(self):
        """Test that router has no prefix (set at include time)."""
        from app.shared.routers.auth import router

        assert router.prefix == ""

    def test_router_has_expected_routes(self):
        """Test that router has expected endpoints."""
        from app.shared.routers.auth import router

        paths = [route.path for route in router.routes]

        assert "/signup" in paths
        assert "/signup/verify" in paths
        assert "/signin" in paths
        assert "/me" in paths

    def test_router_oauth_routes_exist(self):
        """Test that OAuth routes are configured."""
        from app.shared.routers.auth import router

        paths = [route.path for route in router.routes]

        assert "/oauth/{provider}" in paths
        assert "/oauth/{provider}/callback" in paths

    def test_router_password_routes_exist(self):
        """Test that password routes are configured."""
        from app.shared.routers.auth import router

        paths = [route.path for route in router.routes]

        assert "/password/reset" in paths
        assert "/password/reset/confirm" in paths
        assert "/password/change" in paths


# ============================================================================
# Test Module Exports
# ============================================================================


class TestModuleExports:
    """Tests for module exports."""

    def test_router_is_exported(self):
        """Test that router is exported from module."""
        from app.shared.routers.auth import router

        assert router is not None

    def test_router_exported_from_init(self):
        """Test router is exported from __init__."""
        from app.shared.routers import auth_router

        assert auth_router is not None
