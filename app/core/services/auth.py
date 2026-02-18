"""
Authentication Service for managing user authentication flows.

This module provides a centralized authentication service that handles:
- Email signup with password hashing and OTP verification
- Email signin with password verification
- OAuth authentication (Google, GitHub)
- OTP generation, sending, and verification
- Password reset flow
- Token pair generation (access + refresh tokens)
- Refresh token management and revocation

Example usage:
    from app.core.services.auth import AuthService

    # Initialize
    AuthService.init()

    # Email signup
    user = await AuthService.email_signup(
        session=db_session,
        email="user@example.com",
        password="SecurePassword123!",
        full_name="John Doe",
    )

    # Email signin with tokens
    tokens = await AuthService.email_signin_with_tokens(
        session=db_session,
        email="user@example.com",
        password="SecurePassword123!",
        remember_me=True,
    )

    # OAuth authentication
    user = await AuthService.oauth_authenticate(
        session=db_session,
        user_info=oauth_user_info,
    )
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Type
from uuid import UUID

import bcrypt

from app.core.config import auth_logger, settings
from app.core.db.crud import (
    oauth_account_db,
    otp_token_db,
    refresh_token_db,
    user_db,
)
from app.core.enums import OAuthProviders, OTPPurpose
from app.core.exceptions.types import (
    AuthenticationException,
    InvalidCredentialsException,
    OAuthException,
    OTPInvalidException,
    TooManyAttemptsException,
)
from app.infrastructure.messaging import publish_event
from app.core.services.oauth import (
    GitHubOAuthService,
    GoogleOAuthService,
)
from app.core.services.oauth.base import BaseOAuthProvider, OAuthUserInfo
from app.core.services.payment.stripe.main import Stripe
from app.core.utils import create_jwt_token, hmac_hash_otp


__all__ = ["AuthService", "TokenPair"]


from dataclasses import dataclass


@dataclass
class TokenPair:
    """
    Data class representing an access/refresh token pair.

    Attributes:
        access_token: Short-lived JWT access token.
        refresh_token: Long-lived refresh token for obtaining new access tokens.
        token_type: The type of token (always "bearer").
        expires_in: Access token expiration time in seconds.
    """

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = 900  # 15 minutes in seconds


class AuthService:
    """
    Centralized authentication service.

    This class provides a unified interface for user authentication including
    email/password signup and signin, OAuth authentication with Google and
    GitHub, and OTP-based email verification and password reset.

    Attributes:
        _initialized: Flag indicating whether the service has been initialized.
        ACCESS_TOKEN_EXPIRE_MINUTES: Access token expiration (15 minutes).
        REFRESH_TOKEN_EXPIRE_DAYS: Normal refresh token expiration (7 days).
        REFRESH_TOKEN_REMEMBER_DAYS: Extended refresh token expiration (30 days).

    Example:
        >>> AuthService.init()
        >>> user = await AuthService.email_signin(
        ...     session=db_session,
        ...     email="user@example.com",
        ...     password="password123",
        ... )
    """

    _initialized: bool = False

    # Token expiration settings
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_TOKEN_REMEMBER_DAYS: int = 30

    # =========================================================================
    # Initialization
    # =========================================================================

    @classmethod
    def init(cls) -> None:
        """
        Initialize the AuthService.

        This method marks the service as initialized. It should be called
        during application startup.

        Returns:
            None
        """
        cls._initialized = True
        auth_logger.info("AuthService initialized")

    @classmethod
    def is_initialized(cls) -> bool:
        """
        Check if the service has been initialized.

        Returns:
            bool: True if initialized, False otherwise.
        """
        return cls._initialized

    # =========================================================================
    # Password Utilities
    # =========================================================================

    @classmethod
    def hash_password(cls, password: str) -> str:
        """
        Hash a password using bcrypt.

        Args:
            password: The plain text password to hash.

        Returns:
            str: The bcrypt hashed password.

        Example:
            >>> hashed = AuthService.hash_password("mypassword")
            >>> hashed.startswith("$2b$")
            True
        """
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @classmethod
    def verify_password(cls, password: str, hashed: str) -> bool:
        """
        Verify a password against its hash.

        Args:
            password: The plain text password to verify.
            hashed: The bcrypt hashed password.

        Returns:
            bool: True if password matches, False otherwise.

        Example:
            >>> hashed = AuthService.hash_password("mypassword")
            >>> AuthService.verify_password("mypassword", hashed)
            True
            >>> AuthService.verify_password("wrongpassword", hashed)
            False
        """
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False

    # =========================================================================
    # OTP Utilities
    # =========================================================================

    @classmethod
    def generate_otp(cls, length: int | None = None) -> str:
        """
        Generate a random numeric OTP code.

        Args:
            length: The length of the OTP. Defaults to settings.OTP_LENGTH.

        Returns:
            str: A random numeric string of the specified length.

        Example:
            >>> otp = AuthService.generate_otp()
            >>> len(otp)
            6
            >>> otp.isdigit()
            True
        """
        if length is None:
            length = settings.OTP_LENGTH

        # Generate secure random digits
        return "".join(str(secrets.randbelow(10)) for _ in range(length))

    @classmethod
    async def send_otp(
        cls,
        session,
        email: str,
        purpose: OTPPurpose,
        user_id: UUID | None = None,
        user_name: str | None = None,
        commit_self: bool = True,
    ) -> bool:
        """
        Generate and send an OTP to the specified email.

        This method invalidates any previous OTPs for the same email and
        purpose, creates a new OTP token, and sends it via email.

        Args:
            session: The database session.
            email: The email address to send the OTP to.
            purpose: The purpose of the OTP.
            user_id: Optional user ID to associate with the OTP.
            user_name: Optional user name for email personalization.
            commit_self: If True, commits the transaction. Default False.

        Returns:
            bool: True if OTP was sent successfully.

        Example:
            >>> await AuthService.send_otp(
            ...     session=db_session,
            ...     email="user@example.com",
            ...     purpose=OTPPurpose.EMAIL_VERIFICATION,
            ... )
            True
        """
        # Invalidate previous tokens
        await otp_token_db.invalidate_previous_tokens(
            session=session,
            email=email,
            purpose=purpose,
            commit_self=False,
        )

        # Generate new OTP
        otp_code = cls.generate_otp()
        code_hash = hmac_hash_otp(otp_code, settings.OTP_HMAC_SECRET)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.OTP_EXPIRY_MINUTES
        )

        # Create OTP token
        await otp_token_db.create(
            session=session,
            data={
                "user_id": user_id,
                "email": email,
                "code_hash": code_hash,
                "purpose": purpose,
                "expires_at": expires_at,
            },
            commit_self=False,
        )

        if commit_self:
            await session.commit()

        # Publish OTP email event to the message queue
        await publish_event(
            queue_name="otp_emails",
            event={
                "email": email,
                "otp_code": otp_code,
                "purpose": purpose.value,
                "user_name": user_name,
            },
        )

        auth_logger.info(f"OTP queued: email={email}, purpose={purpose.value}")
        return True

    @classmethod
    async def verify_otp(
        cls,
        session,
        email: str,
        otp_code: str,
        purpose: OTPPurpose,
        commit_self: bool = True,
    ) -> bool:
        """
        Verify an OTP code.

        Args:
            session: The database session.
            email: The email address the OTP was sent to.
            otp_code: The OTP code to verify.
            purpose: The purpose of the OTP.
            commit_self: If True, commits the transaction. Default False.

        Returns:
            bool: True if OTP is valid.

        Raises:
            OTPInvalidException: If OTP is invalid.
            OTPExpiredException: If OTP has expired.
            TooManyAttemptsException: If too many verification attempts.

        Example:
            >>> await AuthService.verify_otp(
            ...     session=db_session,
            ...     email="user@example.com",
            ...     otp_code="123456",
            ...     purpose=OTPPurpose.EMAIL_VERIFICATION,
            ... )
            True
        """
        # Hash the provided OTP
        code_hash = hmac_hash_otp(otp_code, settings.OTP_HMAC_SECRET)

        # Find valid token
        token = await otp_token_db.get_valid_token_by_hash(
            session=session,
            code_hash=code_hash,
            email=email,
            purpose=purpose,
        )

        if token is None:
            auth_logger.warning(f"OTP verification failed: invalid code for {email}")
            raise OTPInvalidException()

        # Check attempts
        if token.attempts >= settings.OTP_MAX_ATTEMPTS:
            auth_logger.warning(
                f"OTP verification failed: too many attempts for {email}"
            )
            raise TooManyAttemptsException()

        # Mark as used
        await otp_token_db.mark_as_used(
            session=session, token=token, commit_self=commit_self
        )

        auth_logger.info(f"OTP verified: email={email}, purpose={purpose.value}")
        return True

    # =========================================================================
    # Email Authentication
    # =========================================================================

    @classmethod
    async def email_signup(
        cls,
        session,
        email: str,
        password: str,
        full_name: str | None = None,
        commit_self: bool = True,
    ):
        """
        Register a new user with email and password.

        Args:
            session: The database session.
            email: The user's email address.
            password: The user's password (will be hashed).
            full_name: Optional full name.
            commit_self: If True, commits the transaction. Default False.

        Returns:
            The created User object.

        Raises:
            AuthenticationException: If email already exists.

        Example:
            >>> user = await AuthService.email_signup(
            ...     session=db_session,
            ...     email="newuser@example.com",
            ...     password="SecurePass123!",
            ...     full_name="New User",
            ... )
        """
        # Check if user exists
        existing = await user_db.get_one_by_conditions(
            session=session,
            conditions=[user_db.model.email == email],
        )

        if existing:
            auth_logger.warning(f"Signup failed: email already exists {email}")
            raise AuthenticationException(
                message="A user with this email already exists"
            )

        # Hash password
        password_hash = cls.hash_password(password)

        # Create user
        user = await user_db.create(
            session=session,
            data={
                "email": email,
                "password_hash": password_hash,
                "full_name": full_name,
                "email_verified": False,
            },
            commit_self=False,
        )

        # Create Stripe customer (non-blocking - don't fail signup if Stripe fails)
        try:
            stripe_customer = await Stripe.create_customer(
                email=email,
                name=full_name,
                metadata={"user_id": str(user.id)},
            )
            await user_db.update(
                session=session,
                id=user.id,
                updates={"stripe_customer_id": stripe_customer.id},
                commit_self=False,
            )
            auth_logger.info(
                f"Created Stripe customer {stripe_customer.id} for user {email}"
            )
        except Exception as e:
            auth_logger.warning(f"Failed to create Stripe customer for {email}: {e}")

        if commit_self:
            await session.commit()

        auth_logger.info(f"User signup: email={email}")
        return user

    @classmethod
    async def email_signin(
        cls,
        session,
        email: str,
        password: str,
    ):
        """
        Authenticate a user with email and password.

        Args:
            session: The database session.
            email: The user's email address.
            password: The user's password.

        Returns:
            The authenticated User object.

        Raises:
            InvalidCredentialsException: If email or password is incorrect.
            AuthenticationException: If user is inactive or OAuth-only.

        Example:
            >>> user = await AuthService.email_signin(
            ...     session=db_session,
            ...     email="user@example.com",
            ...     password="SecurePass123!",
            ... )
        """
        # Find user
        user = await user_db.get_one_by_conditions(
            session=session,
            conditions=[user_db.model.email == email],
        )

        if user is None:
            auth_logger.warning(f"Signin failed: user not found {email}")
            raise InvalidCredentialsException()

        # Check if OAuth-only user
        if user.password_hash is None:
            auth_logger.warning(f"Signin failed: OAuth-only user {email}")
            raise AuthenticationException(
                message="This account uses OAuth login. Please sign in with Google or GitHub."
            )

        # Verify password
        if not cls.verify_password(password, user.password_hash):
            auth_logger.warning(f"Signin failed: wrong password {email}")
            raise InvalidCredentialsException()

        # Check if active
        if not user.is_active:
            auth_logger.warning(f"Signin failed: user deactivated {email}")
            raise AuthenticationException(message="This account has been deactivated")

        auth_logger.info(f"User signin: email={email}")
        return user

    # =========================================================================
    # OAuth Authentication
    # =========================================================================

    @classmethod
    def get_oauth_provider(cls, provider: OAuthProviders) -> Type[BaseOAuthProvider]:
        """
        Get the OAuth provider service class for a given provider.

        Args:
            provider: The OAuth provider enum value.

        Returns:
            The OAuth provider service class.

        Raises:
            OAuthException: If provider is not supported.

        Example:
            >>> provider = AuthService.get_oauth_provider(OAuthProviders.GOOGLE)
            >>> provider == GoogleOAuthService
            True
        """
        providers = {
            OAuthProviders.GOOGLE: GoogleOAuthService,
            OAuthProviders.GITHUB: GitHubOAuthService,
        }

        if provider not in providers:
            raise OAuthException(message=f"Unsupported OAuth provider: {provider}")

        return providers[provider]

    @classmethod
    async def oauth_authenticate(
        cls,
        session,
        user_info: OAuthUserInfo,
        commit_self: bool = True,
    ):
        """
        Authenticate or create a user from OAuth provider info.

        This method handles the OAuth authentication flow:
        1. Check if OAuth account already exists
        2. If not, check if user with email exists
        3. Create or link user and OAuth account as needed

        Args:
            session: The database session.
            user_info: User information from OAuth provider.
            commit_self: If True, commits the transaction. Default False.

        Returns:
            The authenticated User object.

        Example:
            >>> user = await AuthService.oauth_authenticate(
            ...     session=db_session,
            ...     user_info=oauth_user_info,
            ... )
        """
        # Map provider string to enum
        provider_enum = OAuthProviders(user_info.provider)

        # Check if OAuth account exists
        existing_oauth = await oauth_account_db.get_one_by_conditions(
            session=session,
            conditions=[
                oauth_account_db.model.provider == provider_enum,
                oauth_account_db.model.provider_account_id
                == user_info.provider_user_id,
            ],
            options=[oauth_account_db.user_loader],
        )

        if existing_oauth:
            # OAuth account exists, return associated user
            user = existing_oauth.user

            # Update user info if changed
            updates = {}
            if user_info.name and not user.full_name:
                updates["full_name"] = user_info.name
            if user_info.picture and not user.avatar_url:
                updates["avatar_url"] = user_info.picture
            if user_info.email_verified and not user.email_verified:
                updates["email_verified"] = True

            if updates:
                await user_db.update(
                    session=session,
                    id=user.id,
                    updates=updates,
                    commit_self=commit_self,
                )

            auth_logger.info(
                f"OAuth signin: provider={user_info.provider}, email={user.email}"
            )
            return user

        # Check if user with email exists
        existing_user = await user_db.get_one_by_conditions(
            session=session,
            conditions=[user_db.model.email == user_info.email],
        )

        if existing_user:
            # Link OAuth account to existing user
            await oauth_account_db.create(
                session=session,
                data={
                    "user_id": existing_user.id,
                    "provider": provider_enum,
                    "provider_account_id": user_info.provider_user_id,
                },
                commit_self=False,
            )

            # Update user info if changed
            updates = {}
            if user_info.name and not existing_user.full_name:
                updates["full_name"] = user_info.name
            if user_info.picture and not existing_user.avatar_url:
                updates["avatar_url"] = user_info.picture
            if user_info.email_verified and not existing_user.email_verified:
                updates["email_verified"] = True

            if updates:
                await user_db.update(
                    session=session,
                    id=existing_user.id,
                    updates=updates,
                    commit_self=False,
                )

            if commit_self:
                await session.commit()

            auth_logger.info(
                f"OAuth linked: provider={user_info.provider}, email={existing_user.email}"
            )
            return existing_user

        # Create new user
        new_user = await user_db.create(
            session=session,
            data={
                "email": user_info.email,
                "full_name": user_info.name,
                "avatar_url": user_info.picture,
                "email_verified": user_info.email_verified,
            },
            commit_self=False,
        )

        # Create OAuth account
        await oauth_account_db.create(
            session=session,
            data={
                "user_id": new_user.id,
                "provider": provider_enum,
                "provider_account_id": user_info.provider_user_id,
            },
            commit_self=False,
        )

        # Create Stripe customer (non-blocking - don't fail signup if Stripe fails)
        try:
            stripe_customer = await Stripe.create_customer(
                email=user_info.email,
                name=user_info.name,
                metadata={"user_id": str(new_user.id)},
            )
            await user_db.update(
                session=session,
                id=new_user.id,
                updates={"stripe_customer_id": stripe_customer.id},
                commit_self=False,
            )
            auth_logger.info(
                f"Created Stripe customer {stripe_customer.id} for OAuth user {user_info.email}"
            )
        except Exception as e:
            auth_logger.warning(
                f"Failed to create Stripe customer for OAuth user {user_info.email}: {e}"
            )

        if commit_self:
            await session.commit()

        auth_logger.info(
            f"OAuth signup: provider={user_info.provider}, email={user_info.email}"
        )
        return new_user

    # =========================================================================
    # Password Reset
    # =========================================================================

    @classmethod
    async def reset_password(
        cls,
        session,
        email: str,
        new_password: str,
        commit_self: bool = True,
    ) -> bool:
        """
        Reset a user's password.

        Args:
            session: The database session.
            email: The user's email address.
            new_password: The new password.
            commit_self: If True, commits the transaction. Default False.

        Returns:
            bool: True if password was reset successfully.

        Raises:
            AuthenticationException: If user not found.

        Example:
            >>> await AuthService.reset_password(
            ...     session=db_session,
            ...     email="user@example.com",
            ...     new_password="NewSecurePass123!",
            ... )
            True
        """
        # Find user
        user = await user_db.get_one_by_conditions(
            session=session,
            conditions=[user_db.model.email == email],
        )

        if user is None:
            auth_logger.warning(f"Password reset failed: user not found {email}")
            raise AuthenticationException(message="User not found")

        # Hash new password
        password_hash = cls.hash_password(new_password)

        # Update password
        await user_db.update(
            session=session,
            id=user.id,
            updates={"password_hash": password_hash},
            commit_self=commit_self,
        )

        # Publish password reset confirmation email event
        await publish_event(
            queue_name="password_reset_confirmation_emails",
            event={
                "email": email,
                "user_name": user.full_name,
            },
        )

        auth_logger.info(f"Password reset: email={email}")
        return True

    # =========================================================================
    # Token Management
    # =========================================================================

    @classmethod
    def hash_token(cls, token: str) -> str:
        """
        Hash a token using SHA256.

        This is used to compare refresh tokens without storing them in plain text.

        Args:
            token: The plain token to hash.

        Returns:
            str: The SHA256 hash of the token (64 hex characters).
        """
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def _hash_refresh_token(cls, token: str) -> str:
        """
        Hash a refresh token using SHA256.

        Args:
            token: The plain refresh token.

        Returns:
            str: The SHA256 hash of the token (64 hex characters).
        """
        return cls.hash_token(token)

    @classmethod
    def _generate_refresh_token(cls) -> str:
        """
        Generate a secure random refresh token.

        Returns:
            str: A 64-character URL-safe random token.
        """
        return secrets.token_urlsafe(48)

    @classmethod
    async def create_token_pair(
        cls,
        session,
        user,
        remember_me: bool = False,
        device_info: str | None = None,
        commit_self: bool = True,
    ) -> TokenPair:
        """
        Create an access/refresh token pair for a user.

        This method generates:
        1. A short-lived JWT access token (15 minutes)
        2. A long-lived refresh token stored in the database
           (7 days normal, 30 days with remember_me)

        Args:
            session: The database session.
            user: The User object to create tokens for.
            remember_me: If True, extends refresh token to 30 days.
            device_info: Optional device/client info (user agent, IP).
            commit_self: If True, commits the transaction. Default False.

        Returns:
            TokenPair: Object containing access_token, refresh_token,
                      token_type, and expires_in.

        Example:
            >>> tokens = await AuthService.create_token_pair(
            ...     session=db_session,
            ...     user=user,
            ...     remember_me=True,
            ...     device_info="Mozilla/5.0...",
            ... )
            >>> print(tokens.access_token)
        """
        # Generate access token
        access_token_expires = timedelta(minutes=cls.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_jwt_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "type": "access",
            },
            expires_delta=access_token_expires,
        )

        # Generate refresh token
        refresh_token = cls._generate_refresh_token()
        refresh_token_hash = cls._hash_refresh_token(refresh_token)

        # Calculate refresh token expiration
        if remember_me:
            refresh_expires_delta = timedelta(days=cls.REFRESH_TOKEN_REMEMBER_DAYS)
        else:
            refresh_expires_delta = timedelta(days=cls.REFRESH_TOKEN_EXPIRE_DAYS)

        refresh_expires_at = datetime.now(timezone.utc) + refresh_expires_delta

        # Store refresh token in database
        await refresh_token_db.create(
            session=session,
            data={
                "user_id": user.id,
                "token_hash": refresh_token_hash,
                "expires_at": refresh_expires_at,
                "device_info": device_info,
            },
            commit_self=commit_self,
        )

        auth_logger.info(
            f"Token pair created: user={user.email}, "
            f"remember_me={remember_me}, "
            f"expires_in={cls.ACCESS_TOKEN_EXPIRE_MINUTES * 60}s"
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=cls.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @classmethod
    async def refresh_access_token(
        cls,
        session,
        refresh_token: str,
    ) -> str:
        """
        Generate a new access token using a valid refresh token.

        Args:
            session: The database session.
            refresh_token: The refresh token to validate.

        Returns:
            str: A new JWT access token.

        Raises:
            AuthenticationException: If refresh token is invalid, expired,
                                    or revoked.

        Example:
            >>> new_access_token = await AuthService.refresh_access_token(
            ...     session=db_session,
            ...     refresh_token="abc123...",
            ... )
        """
        # Hash the provided token
        token_hash = cls._hash_refresh_token(refresh_token)

        # Find valid token
        token_record = await refresh_token_db.get_valid_token(
            session=session,
            token_hash=token_hash,
        )

        if token_record is None:
            auth_logger.warning(
                "Token refresh failed: invalid or expired refresh token"
            )
            raise AuthenticationException(message="Invalid or expired refresh token")

        user = token_record.user

        # Check if user is still active
        if not user.is_active or user.is_deleted:
            auth_logger.warning(f"Token refresh failed: user inactive {user.email}")
            raise AuthenticationException(message="User account is not active")

        # Generate new access token
        access_token_expires = timedelta(minutes=cls.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_jwt_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "type": "access",
            },
            expires_delta=access_token_expires,
        )

        auth_logger.info(f"Access token refreshed: user={user.email}")
        return access_token

    @classmethod
    async def revoke_refresh_token(
        cls,
        session,
        refresh_token: str,
        commit_self: bool = True,
    ) -> bool:
        """
        Revoke a single refresh token (sign out from one device).

        Args:
            session: The database session.
            refresh_token: The refresh token to revoke.
            commit_self: If True, commits the transaction. Default False.

        Returns:
            bool: True if token was revoked, False if not found.

        Example:
            >>> await AuthService.revoke_refresh_token(
            ...     session=db_session,
            ...     refresh_token="abc123...",
            ... )
            True
        """
        token_hash = cls._hash_refresh_token(refresh_token)
        revoked = await refresh_token_db.revoke(
            session=session,
            token_hash=token_hash,
            commit_self=commit_self,
        )

        if revoked:
            auth_logger.info("Refresh token revoked")
        else:
            auth_logger.warning("Refresh token revocation failed: token not found")

        return revoked

    @classmethod
    async def revoke_all_user_tokens(
        cls,
        session,
        user_id: UUID,
        commit_self: bool = True,
    ) -> int:
        """
        Revoke all refresh tokens for a user (sign out all devices).

        Args:
            session: The database session.
            user_id: The ID of the user.
            commit_self: If True, commits the transaction. Default False.

        Returns:
            int: The number of tokens revoked.

        Example:
            >>> count = await AuthService.revoke_all_user_tokens(
            ...     session=db_session,
            ...     user_id=user.id,
            ... )
            >>> print(f"Revoked {count} sessions")
        """
        count = await refresh_token_db.revoke_all_for_user(
            session=session,
            user_id=user_id,
            commit_self=commit_self,
        )

        auth_logger.info(f"All tokens revoked: user_id={user_id}, count={count}")
        return count

    @classmethod
    async def get_active_sessions(
        cls,
        session,
        user_id: UUID,
    ) -> list:
        """
        Get all active sessions for a user.

        Args:
            session: The database session.
            user_id: The ID of the user.

        Returns:
            list: List of active RefreshToken records.

        Example:
            >>> sessions = await AuthService.get_active_sessions(
            ...     session=db_session,
            ...     user_id=user.id,
            ... )
        """
        return await refresh_token_db.get_active_tokens_for_user(
            session=session,
            user_id=user_id,
        )

    @classmethod
    async def change_password(
        cls,
        session,
        user,
        current_password: str,
        new_password: str,
        revoke_tokens: bool = True,
        commit_self: bool = True,
    ) -> bool:
        """
        Change a user's password.

        Args:
            session: The database session.
            user: The User object.
            current_password: The current password for verification.
            new_password: The new password.
            revoke_tokens: If True, revokes all refresh tokens after change.
            commit_self: If True, commits the transaction. Default False.

        Returns:
            bool: True if password was changed successfully.

        Raises:
            InvalidCredentialsException: If current password is incorrect.
            AuthenticationException: If user has no password set.

        Example:
            >>> await AuthService.change_password(
            ...     session=db_session,
            ...     user=user,
            ...     current_password="OldPass123!",
            ...     new_password="NewPass456!",
            ... )
            True
        """
        # Check if user has a password
        if user.password_hash is None:
            auth_logger.warning(f"Password change failed: no password set {user.email}")
            raise AuthenticationException(
                message="Cannot change password. Account uses OAuth login only."
            )

        # Verify current password
        if not cls.verify_password(current_password, user.password_hash):
            auth_logger.warning(
                f"Password change failed: wrong current password {user.email}"
            )
            raise InvalidCredentialsException()

        # Hash and update new password
        new_password_hash = cls.hash_password(new_password)
        await user_db.update(
            session=session,
            id=user.id,
            updates={"password_hash": new_password_hash},
            commit_self=False,
        )

        # Optionally revoke all tokens for security
        if revoke_tokens:
            await cls.revoke_all_user_tokens(
                session=session,
                user_id=user.id,
                commit_self=False,
            )

        if commit_self:
            await session.commit()

        auth_logger.info(f"Password changed: email={user.email}")
        return True
