"""
Test suite for authentication dependencies.

This module contains comprehensive unit tests for the auth dependencies including:
- get_current_user: Token extraction and validation
- get_current_active_user: Active user verification
- get_current_verified_user: Email verification check
- get_optional_user: Optional authentication

Run all tests:
    pytest tests/shared/dependencies/test_auth.py -v

Run with coverage:
    pytest tests/shared/dependencies/test_auth.py --cov=app.shared.dependencies.auth --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


class TestGetCurrentUser:
    """Test suite for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        """Test that valid token returns the user object."""
        from app.shared.dependencies.auth import get_current_user

        user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.email = "test@example.com"
        mock_user.is_deleted = False

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        mock_session = AsyncMock()

        with patch("app.shared.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "type": "access",
                "exp": 9999999999,
            }

            with patch("app.shared.dependencies.auth.user_db") as mock_user_db:
                mock_user_db.get_by_id = AsyncMock(return_value=mock_user)

                result = await get_current_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

                assert result == mock_user
                mock_decode.assert_called_once_with("valid_token")
                mock_user_db.get_by_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        """Test that invalid token raises 401 Unauthorized."""
        from app.shared.dependencies.auth import get_current_user

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "invalid_token"

        mock_session = AsyncMock()

        with patch("app.shared.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = None  # Invalid token

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 401
            assert "Invalid or expired access token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_token_missing_sub_claim_raises_401(self):
        """Test that token without 'sub' claim raises 401."""
        from app.shared.dependencies.auth import get_current_user

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "token_no_sub"

        mock_session = AsyncMock()

        with patch("app.shared.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "type": "access",
                "exp": 9999999999,
                # Missing 'sub' claim
            }

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 401
            assert "Invalid access token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_wrong_token_type_raises_401(self):
        """Test that refresh token used as access token raises 401."""
        from app.shared.dependencies.auth import get_current_user

        user_id = uuid4()
        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "refresh_token"

        mock_session = AsyncMock()

        with patch("app.shared.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "type": "refresh",  # Wrong type
                "exp": 9999999999,
            }

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 401
            assert "Invalid access token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_user_id_format_raises_401(self):
        """Test that invalid user ID format raises 401."""
        from app.shared.dependencies.auth import get_current_user

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "token_bad_id"

        mock_session = AsyncMock()

        with patch("app.shared.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": "not-a-valid-uuid",  # Invalid UUID
                "type": "access",
                "exp": 9999999999,
            }

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 401
            assert "Invalid access token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_user_not_found_raises_401(self):
        """Test that non-existent user raises 401."""
        from app.shared.dependencies.auth import get_current_user

        user_id = uuid4()
        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        mock_session = AsyncMock()

        with patch("app.shared.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "type": "access",
                "exp": 9999999999,
            }

            with patch("app.shared.dependencies.auth.user_db") as mock_user_db:
                mock_user_db.get_by_id = AsyncMock(return_value=None)  # User not found

                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(
                        credentials=mock_credentials,
                        session=mock_session,
                    )

                assert exc_info.value.status_code == 401
                assert "User not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_deleted_user_raises_401(self):
        """Test that deleted user raises 401."""
        from app.shared.dependencies.auth import get_current_user

        user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.is_deleted = True  # User is deleted

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        mock_session = AsyncMock()

        with patch("app.shared.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "type": "access",
                "exp": 9999999999,
            }

            with patch("app.shared.dependencies.auth.user_db") as mock_user_db:
                mock_user_db.get_by_id = AsyncMock(return_value=mock_user)

                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(
                        credentials=mock_credentials,
                        session=mock_session,
                    )

                assert exc_info.value.status_code == 401
                assert "User account has been deleted" in exc_info.value.detail


class TestGetCurrentActiveUser:
    """Test suite for get_current_active_user dependency."""

    @pytest.mark.asyncio
    async def test_active_user_returns_user(self):
        """Test that active user is returned successfully."""
        from app.shared.dependencies.auth import get_current_active_user

        mock_user = MagicMock()
        mock_user.is_active = True
        mock_user.email = "active@example.com"

        result = await get_current_active_user(user=mock_user)

        assert result == mock_user

    @pytest.mark.asyncio
    async def test_inactive_user_raises_403(self):
        """Test that inactive user raises 403 Forbidden."""
        from app.shared.dependencies.auth import get_current_active_user

        mock_user = MagicMock()
        mock_user.is_active = False
        mock_user.email = "inactive@example.com"

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(user=mock_user)

        assert exc_info.value.status_code == 403
        assert "User account is deactivated" in exc_info.value.detail


class TestGetCurrentVerifiedUser:
    """Test suite for get_current_verified_user dependency."""

    @pytest.mark.asyncio
    async def test_verified_user_returns_user(self):
        """Test that verified user is returned successfully."""
        from app.shared.dependencies.auth import get_current_verified_user

        mock_user = MagicMock()
        mock_user.email_verified = True
        mock_user.email = "verified@example.com"

        result = await get_current_verified_user(user=mock_user)

        assert result == mock_user

    @pytest.mark.asyncio
    async def test_unverified_user_raises_403(self):
        """Test that unverified user raises 403 Forbidden."""
        from app.shared.dependencies.auth import get_current_verified_user

        mock_user = MagicMock()
        mock_user.email_verified = False
        mock_user.email = "unverified@example.com"

        with pytest.raises(HTTPException) as exc_info:
            await get_current_verified_user(user=mock_user)

        assert exc_info.value.status_code == 403
        assert "Email verification required" in exc_info.value.detail


class TestGetOptionalUser:
    """Test suite for get_optional_user dependency."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        """Test that valid token returns user."""
        from app.shared.dependencies.auth import get_optional_user

        user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.is_deleted = False

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        mock_session = AsyncMock()

        with patch("app.shared.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "type": "access",
                "exp": 9999999999,
            }

            with patch("app.shared.dependencies.auth.user_db") as mock_user_db:
                mock_user_db.get_by_id = AsyncMock(return_value=mock_user)

                result = await get_optional_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

                assert result == mock_user

    @pytest.mark.asyncio
    async def test_no_credentials_returns_none(self):
        """Test that missing credentials returns None."""
        from app.shared.dependencies.auth import get_optional_user

        mock_session = AsyncMock()

        result = await get_optional_user(
            credentials=None,  # No credentials
            session=mock_session,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self):
        """Test that invalid token returns None instead of raising."""
        from app.shared.dependencies.auth import get_optional_user

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "invalid_token"

        mock_session = AsyncMock()

        with patch("app.shared.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = None  # Invalid token

            result = await get_optional_user(
                credentials=mock_credentials,
                session=mock_session,
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_user_not_found_returns_none(self):
        """Test that user not found returns None instead of raising."""
        from app.shared.dependencies.auth import get_optional_user

        user_id = uuid4()
        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        mock_session = AsyncMock()

        with patch("app.shared.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "type": "access",
                "exp": 9999999999,
            }

            with patch("app.shared.dependencies.auth.user_db") as mock_user_db:
                mock_user_db.get_by_id = AsyncMock(return_value=None)

                result = await get_optional_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

                assert result is None


class TestBearerScheme:
    """Test suite for HTTPBearer scheme configuration."""

    def test_bearer_scheme_auto_error_true(self):
        """Test that bearer_scheme has auto_error=True."""
        from app.shared.dependencies.auth import bearer_scheme

        assert bearer_scheme.auto_error is True

    def test_optional_bearer_scheme_auto_error_false(self):
        """Test that optional_bearer_scheme has auto_error=False."""
        from app.shared.dependencies.auth import optional_bearer_scheme

        assert optional_bearer_scheme.auto_error is False


class TestTypeAliases:
    """Test suite for dependency type aliases."""

    def test_type_aliases_are_defined(self):
        """Test that type aliases are properly defined."""
        from app.shared.dependencies.auth import (
            CurrentUser,
            CurrentActiveUser,
            CurrentVerifiedUser,
            OptionalUser,
        )

        # Type aliases should exist
        assert CurrentUser is not None
        assert CurrentActiveUser is not None
        assert CurrentVerifiedUser is not None
        assert OptionalUser is not None


class TestModuleExports:
    """Test suite for module exports."""

    def test_all_exports_available(self):
        """Test that all expected exports are available."""
        from app.shared.dependencies.auth import (
            bearer_scheme,
            optional_bearer_scheme,
            get_current_user,
            get_current_active_user,
            get_current_verified_user,
            get_optional_user,
            CurrentUser,
            CurrentActiveUser,
            CurrentVerifiedUser,
            OptionalUser,
        )

        # All exports should be callable or defined
        assert callable(get_current_user)
        assert callable(get_current_active_user)
        assert callable(get_current_verified_user)
        assert callable(get_optional_user)
        assert bearer_scheme is not None
        assert optional_bearer_scheme is not None

    def test_dependencies_init_exports(self):
        """Test that dependencies __init__ exports auth functions."""
        from app.shared.dependencies import (
            get_current_user,
            get_current_active_user,
            get_current_verified_user,
            get_optional_user,
            CurrentUser,
            CurrentActiveUser,
            CurrentVerifiedUser,
            OptionalUser,
        )

        # All should be importable from __init__
        assert callable(get_current_user)
        assert callable(get_current_active_user)
        assert callable(get_current_verified_user)
        assert callable(get_optional_user)
