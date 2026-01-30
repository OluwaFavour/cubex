"""
Authentication Service for managing user authentication flows.

This module provides a centralized authentication service that handles:
- Email signup with password hashing and OTP verification
- Email signin with password verification
- OAuth authentication (Google, GitHub)
- OTP generation, sending, and verification
- Password reset flow

Example usage:
    from app.shared.services.auth import AuthService

    # Initialize
    AuthService.init()

    # Email signup
    user = await AuthService.email_signup(
        session=db_session,
        email="user@example.com",
        password="SecurePassword123!",
        full_name="John Doe",
    )

    # Email signin
    user = await AuthService.email_signin(
        session=db_session,
        email="user@example.com",
        password="SecurePassword123!",
    )

    # OAuth authentication
    user = await AuthService.oauth_authenticate(
        session=db_session,
        user_info=oauth_user_info,
    )
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Type
from uuid import UUID

import bcrypt

from app.shared.config import auth_logger, settings
from app.shared.db.crud import OAuthAccountDB, UserDB
from app.shared.db.crud.otp import OTPTokenDB
from app.shared.enums import OAuthProviders, OTPPurpose
from app.shared.exceptions.types import (
    AuthenticationException,
    InvalidCredentialsException,
    OAuthException,
    OTPInvalidException,
    TooManyAttemptsException,
)
from app.shared.services.email_manager import EmailManagerService
from app.shared.services.oauth import (
    GitHubOAuthService,
    GoogleOAuthService,
)
from app.shared.services.oauth.base import BaseOAuthProvider, OAuthUserInfo
from app.shared.utils import hmac_hash_otp


__all__ = ["AuthService"]


class AuthService:
    """
    Centralized authentication service.

    This class provides a unified interface for user authentication including
    email/password signup and signin, OAuth authentication with Google and
    GitHub, and OTP-based email verification and password reset.

    Attributes:
        _initialized: Flag indicating whether the service has been initialized.

    Example:
        >>> AuthService.init()
        >>> user = await AuthService.email_signin(
        ...     session=db_session,
        ...     email="user@example.com",
        ...     password="password123",
        ... )
    """

    _initialized: bool = False

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
        otp_db = OTPTokenDB()

        # Invalidate previous tokens
        await otp_db.invalidate_previous_tokens(
            session=session,
            email=email,
            purpose=purpose,
            commit_self=False,
        )

        # Generate new OTP
        otp_code = cls.generate_otp()
        code_hash = hmac_hash_otp(otp_code)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.OTP_EXPIRY_MINUTES
        )

        # Create OTP token
        await otp_db.create(
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

        await session.commit()

        # Send OTP email
        result = await EmailManagerService.send_otp_email(
            email=email,
            otp_code=otp_code,
            purpose=purpose,
            user_name=user_name,
        )

        auth_logger.info(f"OTP sent: email={email}, purpose={purpose.value}")
        return result

    @classmethod
    async def verify_otp(
        cls,
        session,
        email: str,
        otp_code: str,
        purpose: OTPPurpose,
    ) -> bool:
        """
        Verify an OTP code.

        Args:
            session: The database session.
            email: The email address the OTP was sent to.
            otp_code: The OTP code to verify.
            purpose: The purpose of the OTP.

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
        otp_db = OTPTokenDB()

        # Hash the provided OTP
        code_hash = hmac_hash_otp(otp_code)

        # Find valid token
        token = await otp_db.get_valid_token_by_hash(
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
        await otp_db.mark_as_used(session=session, token=token, commit_self=True)

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
    ):
        """
        Register a new user with email and password.

        Args:
            session: The database session.
            email: The user's email address.
            password: The user's password (will be hashed).
            full_name: Optional full name.

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
        user_db = UserDB()

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
            commit_self=True,
        )

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
        user_db = UserDB()

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
            raise AuthenticationException(
                message="This account has been deactivated"
            )

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

        Returns:
            The authenticated User object.

        Example:
            >>> user = await AuthService.oauth_authenticate(
            ...     session=db_session,
            ...     user_info=oauth_user_info,
            ... )
        """
        user_db = UserDB()
        oauth_db = OAuthAccountDB()

        # Map provider string to enum
        provider_enum = OAuthProviders(user_info.provider)

        # Check if OAuth account exists
        existing_oauth = await oauth_db.get_one_by_conditions(
            session=session,
            conditions=[
                oauth_db.model.provider == provider_enum,
                oauth_db.model.provider_account_id == user_info.provider_user_id,
            ],
            options=[oauth_db.user_loader],
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
                    data=updates,
                    commit_self=True,
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
            await oauth_db.create(
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
                    data=updates,
                    commit_self=False,
                )

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
        await oauth_db.create(
            session=session,
            data={
                "user_id": new_user.id,
                "provider": provider_enum,
                "provider_account_id": user_info.provider_user_id,
            },
            commit_self=False,
        )

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
    ) -> bool:
        """
        Reset a user's password.

        Args:
            session: The database session.
            email: The user's email address.
            new_password: The new password.

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
        user_db = UserDB()

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
            data={"password_hash": password_hash},
            commit_self=True,
        )

        # Send confirmation email
        await EmailManagerService.send_password_reset_confirmation_email(
            email=email,
            user_name=user.full_name,
        )

        auth_logger.info(f"Password reset: email={email}")
        return True
