"""
Integration tests for auth router endpoints.

Tests all auth endpoints with real database and per-test rollback.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.core.enums import OTPPurpose


class TestSignupEndpoint:

    @pytest.mark.asyncio
    async def test_signup_success(self, client: AsyncClient):
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
        payload = {
            "email": test_user.email,  # Already exists
            "password": "SecurePass123!",
            "full_name": "Another User",
        }
        response = await client.post("/auth/signup", json=payload)

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_signup_invalid_email(self, client: AsyncClient):
        payload = {
            "email": "notanemail",
            "password": "SecurePass123!",
            "full_name": "Test User",
        }
        response = await client.post("/auth/signup", json=payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_weak_password(self, client: AsyncClient):
        payload = {
            "email": "test@example.com",
            "password": "weak",  # Too short, no uppercase, no digit
            "full_name": "Test User",
        }
        response = await client.post("/auth/signup", json=payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_missing_email(self, client: AsyncClient):
        payload = {
            "password": "SecurePass123!",
            "full_name": "Test User",
        }
        response = await client.post("/auth/signup", json=payload)

        assert response.status_code == 422


class TestVerifySignupEndpoint:

    @pytest.mark.asyncio
    async def test_verify_signup_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from datetime import datetime, timedelta, timezone
        from app.core.db.models import OTPToken, User
        from app.core.services.auth import AuthService
        from app.core.utils import hmac_hash_otp
        from app.core.config import settings

        user = User(
            id=uuid4(),
            email="unverified@example.com",
            password_hash="$2b$12$jTCIzYr5zEDrCnh/q48u1OgmUvXQQx3BAoUnIA7BdXgZIxvw2Rvfy",
            full_name="Unverified User",
            email_verified=False,
        )
        db_session.add(user)
        await db_session.flush()

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
        from datetime import datetime, timedelta, timezone
        from app.core.db.models import OTPToken, User
        from app.core.utils import hmac_hash_otp
        from app.core.config import settings

        user = User(
            id=uuid4(),
            email="unverified2@example.com",
            password_hash="$2b$12$jTCIzYr5zEDrCnh/q48u1OgmUvXQQx3BAoUnIA7BdXgZIxvw2Rvfy",
            full_name="Unverified User",
            email_verified=False,
        )
        db_session.add(user)
        await db_session.flush()

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
        from app.core.db.models import User

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


class TestResendVerificationEndpoint:

    @pytest.mark.asyncio
    async def test_resend_verification_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from app.core.db.models import User

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
        payload = {"email": test_user.email}
        response = await client.post("/auth/signup/resend", json=payload)

        # API returns 200 with success=False for already verified
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is False

    @pytest.mark.asyncio
    async def test_resend_verification_user_not_found(self, client: AsyncClient):
        payload = {"email": "nonexistent@example.com"}
        response = await client.post("/auth/signup/resend", json=payload)

        # API may return 200 to prevent email enumeration or 404
        assert response.status_code in [200, 404]


class TestSigninEndpoint:

    @pytest.mark.asyncio
    async def test_signin_success(self, client: AsyncClient, db_session: AsyncSession):
        from app.core.db.models import User
        from app.core.utils import hash_password

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
        from app.core.db.models import User
        from app.core.utils import hash_password

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
        payload = {"email": "nonexistent@example.com", "password": "SomePassword123!"}
        response = await client.post("/auth/signin", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_signin_unverified_user(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from app.core.db.models import User
        from app.core.utils import hash_password

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


class TestTokenRefreshEndpoint:

    @pytest.mark.asyncio
    async def test_token_refresh_invalid_token(self, client: AsyncClient):
        payload = {"refresh_token": "invalid_token"}
        response = await client.post("/auth/token/refresh", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_token_refresh_missing_token(self, client: AsyncClient):
        payload = {}
        response = await client.post("/auth/token/refresh", json=payload)

        assert response.status_code == 422


class TestSignoutEndpoint:

    @pytest.mark.asyncio
    async def test_signout_success(self, client: AsyncClient, db_session: AsyncSession):
        import hashlib
        from datetime import datetime, timedelta, timezone
        from app.core.db.models import RefreshToken, User
        from app.core.utils import create_jwt_token, hash_password

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
        payload = {"refresh_token": "invalid_token"}
        response = await client.post("/auth/signout", json=payload)

        # Signout handles invalid tokens gracefully
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is False


class TestSignoutAllEndpoint:

    @pytest.mark.asyncio
    async def test_signout_all_success(self, authenticated_client: AsyncClient):
        response = await authenticated_client.post("/auth/signout/all")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_signout_all_unauthenticated(self, client: AsyncClient):
        response = await client.post("/auth/signout/all")

        assert response.status_code == 401


class TestPasswordResetRequestEndpoint:

    @pytest.mark.asyncio
    async def test_password_reset_request_success(self, client: AsyncClient, test_user):
        payload = {"email": test_user.email}
        response = await client.post("/auth/password/reset", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_password_reset_request_nonexistent_user(self, client: AsyncClient):
        payload = {"email": "nonexistent@example.com"}
        response = await client.post("/auth/password/reset", json=payload)

        # Returns 200 to prevent email enumeration
        assert response.status_code == 200


class TestPasswordResetConfirmEndpoint:

    @pytest.mark.asyncio
    async def test_password_reset_confirm_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        from datetime import datetime, timedelta, timezone
        from app.core.db.models import OTPToken
        from app.core.services.auth import AuthService
        from app.core.utils import hmac_hash_otp
        from app.core.config import settings

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
        payload = {
            "email": test_user.email,
            "otp_code": "000000",
            "new_password": "NewSecurePass123!",
        }
        response = await client.post("/auth/password/reset/confirm", json=payload)

        assert response.status_code == 400


class TestPasswordChangeEndpoint:

    @pytest.mark.asyncio
    async def test_password_change_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from app.core.db.models import User
        from app.core.utils import hash_password, create_jwt_token
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
        payload = {
            "current_password": "TestPassword123!",
            "new_password": "NewSecurePass456!",
        }
        response = await client.post("/auth/password/change", json=payload)

        assert response.status_code == 401


class TestGetProfileEndpoint:

    @pytest.mark.asyncio
    async def test_get_profile_success(
        self, authenticated_client: AsyncClient, test_user
    ):
        response = await authenticated_client.get("/auth/me")

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["full_name"] == test_user.full_name

    @pytest.mark.asyncio
    async def test_get_profile_unauthenticated(self, client: AsyncClient):
        response = await client.get("/auth/me")

        assert response.status_code == 401


class TestUpdateProfileEndpoint:

    @pytest.mark.asyncio
    async def test_update_profile_success(self, authenticated_client: AsyncClient):
        payload = {"full_name": "Updated Name"}
        response = await authenticated_client.patch("/auth/me", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_profile_unauthenticated(self, client: AsyncClient):
        payload = {"full_name": "Updated Name"}
        response = await client.patch("/auth/me", json=payload)

        assert response.status_code == 401


class TestDeleteAccountEndpoint:

    @pytest.mark.asyncio
    async def test_delete_account_success(self, authenticated_client: AsyncClient):
        response = await authenticated_client.delete("/auth/me")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_account_unauthenticated(self, client: AsyncClient):
        response = await client.delete("/auth/me")

        assert response.status_code == 401


class TestGetSessionsEndpoint:

    @pytest.mark.asyncio
    async def test_get_sessions_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        import hashlib
        from datetime import datetime, timedelta, timezone
        from app.core.db.models import RefreshToken, User
        from app.core.utils import create_jwt_token, hash_password

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
        payload = {"refresh_token": "some_token"}
        response = await client.post("/auth/sessions", json=payload)

        assert response.status_code == 401


class TestOAuthInitiateEndpoint:

    @pytest.mark.asyncio
    async def test_oauth_google_initiate(self, client: AsyncClient):
        response = await client.get(
            "/auth/oauth/google",
            params={"redirect_uri": "http://localhost/callback"},
            follow_redirects=False,
        )

        # Should redirect to Google
        assert response.status_code in [302, 307, 200]

    @pytest.mark.asyncio
    async def test_oauth_github_initiate(self, client: AsyncClient):
        response = await client.get(
            "/auth/oauth/github",
            params={"redirect_uri": "http://localhost/callback"},
            follow_redirects=False,
        )

        # Should redirect to GitHub
        assert response.status_code in [302, 307, 200]

    @pytest.mark.asyncio
    async def test_oauth_invalid_provider(self, client: AsyncClient):
        response = await client.get(
            "/auth/oauth/invalid",
            params={"redirect_uri": "http://localhost/callback"},
        )

        # Could be 400 or 422 depending on validation
        assert response.status_code in [400, 422]


class TestRouterConfiguration:

    def test_router_is_api_router(self):
        from fastapi import APIRouter
        from app.core.routers.auth import router

        assert isinstance(router, APIRouter)

    def test_router_prefix_is_empty(self):
        from app.core.routers.auth import router

        assert router.prefix == ""

    def test_router_has_expected_routes(self):
        from app.core.routers.auth import router

        paths = [route.path for route in router.routes]

        assert "/signup" in paths
        assert "/signup/verify" in paths
        assert "/signin" in paths
        assert "/me" in paths

    def test_router_oauth_routes_exist(self):
        from app.core.routers.auth import router

        paths = [route.path for route in router.routes]

        assert "/oauth/{provider}" in paths
        assert "/oauth/{provider}/callback" in paths

    def test_router_password_routes_exist(self):
        from app.core.routers.auth import router

        paths = [route.path for route in router.routes]

        assert "/password/reset" in paths
        assert "/password/reset/confirm" in paths
        assert "/password/change" in paths


class TestModuleExports:

    def test_router_is_exported(self):
        from app.core.routers.auth import router

        assert router is not None

    def test_router_exported_from_init(self):
        from app.core.routers import auth_router

        assert auth_router is not None

