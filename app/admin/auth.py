"""
SQLAdmin authentication backend.

Provides secure token-based authentication for the admin interface.
Uses HMAC-signed tokens that encode credentials hash and timestamp.
Credentials are configured via environment variables:
- ADMIN_USERNAME
- ADMIN_PASSWORD
"""

import base64
import hashlib
import hmac
import time

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.core.config import settings

# Token expiry in seconds (24 hours)
TOKEN_MAX_AGE = 86400


class AdminAuth(AuthenticationBackend):
    """
    HMAC-based authentication backend for SQLAdmin.

    Uses stateless signed tokens that:
    - Include credentials hash (auto-invalidates if password changes)
    - Include timestamp (tokens expire after TOKEN_MAX_AGE)
    - Are signed with HMAC-SHA256 (tamper-proof)
    """

    @staticmethod
    def _get_credentials_hash() -> str:
        """Generate a hash of the current admin credentials."""
        credentials = f"{settings.ADMIN_USERNAME}:{settings.ADMIN_PASSWORD}"
        return hashlib.sha256(credentials.encode()).hexdigest()[:16]

    @staticmethod
    def _create_token(secret_key: str) -> str:
        """
        Create a signed token containing credentials hash and timestamp.

        Token format (base64 encoded): credentials_hash:timestamp:signature
        """
        timestamp = int(time.time())
        credentials_hash = AdminAuth._get_credentials_hash()

        # Create message to sign
        message = f"{credentials_hash}:{timestamp}"

        # Sign with HMAC-SHA256
        signature = hmac.new(
            secret_key.encode(), message.encode(), hashlib.sha256
        ).hexdigest()[:32]

        # Combine and encode
        token_data = f"{message}:{signature}"
        return base64.urlsafe_b64encode(token_data.encode()).decode()

    @staticmethod
    def _validate_token(token: str, secret_key: str) -> bool:
        """
        Validate a token by checking signature, credentials hash, and expiry.

        Returns True if token is valid, False otherwise.
        """
        try:
            # Decode token
            decoded = base64.urlsafe_b64decode(token.encode()).decode()
            parts = decoded.split(":")

            if len(parts) != 3:
                return False

            credentials_hash, timestamp_str, signature = parts
            timestamp = int(timestamp_str)

            # Check expiry
            if time.time() - timestamp > TOKEN_MAX_AGE:
                return False

            # Verify credentials hash matches current credentials
            # (invalidates token if password changed)
            expected_hash = AdminAuth._get_credentials_hash()
            if not hmac.compare_digest(credentials_hash, expected_hash):
                return False

            # Verify signature
            message = f"{credentials_hash}:{timestamp_str}"
            expected_signature = hmac.new(
                secret_key.encode(), message.encode(), hashlib.sha256
            ).hexdigest()[:32]

            if not hmac.compare_digest(signature, expected_signature):
                return False

            return True
        except Exception:
            return False

    async def login(self, request: Request) -> bool:
        """
        Authenticate admin user and create signed token.

        Args:
            request: The incoming request with form data.

        Returns:
            True if authentication successful, False otherwise.
        """
        form = await request.form()
        username = form.get("username")
        password = form.get("password")

        # Validate credentials using constant-time comparison
        username_valid = hmac.compare_digest(
            str(username or ""), settings.ADMIN_USERNAME
        )
        password_valid = hmac.compare_digest(
            str(password or ""), settings.ADMIN_PASSWORD
        )

        if username_valid and password_valid:
            # Generate signed token
            token = self._create_token(settings.SESSION_SECRET_KEY)
            request.session.update({"admin_token": token})
            return True

        return False

    async def logout(self, request: Request) -> bool:
        """
        Log out admin user by clearing session.

        Args:
            request: The incoming request.

        Returns:
            Always returns True.
        """
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> RedirectResponse | bool:
        """
        Check if the current request is authenticated.

        Validates the token by:
        1. Checking the HMAC signature
        2. Verifying credentials hash matches current credentials
        3. Checking token hasn't expired

        Args:
            request: The incoming request.

        Returns:
            True if authenticated, RedirectResponse to login otherwise.
        """
        token = request.session.get("admin_token")

        if not token or not self._validate_token(token, settings.SESSION_SECRET_KEY):
            # Clear invalid session
            request.session.clear()
            return RedirectResponse(request.url_for("admin:login"), status_code=302)

        return True


# Singleton instance
admin_auth = AdminAuth(secret_key=settings.SESSION_SECRET_KEY)
