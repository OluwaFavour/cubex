"""
Test suite for authentication dependencies.

- get_current_user: Token extraction and validation
- get_current_active_user: Active user verification
- get_current_verified_user: Email verification check
- get_optional_user: Optional authentication

Run all tests:
    pytest tests/core/dependencies/test_auth.py -v

Run with coverage:
    pytest tests/core/dependencies/test_auth.py --cov=app.core.dependencies.auth --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.core.exceptions.types import AuthenticationException, ForbiddenException


class TestGetCurrentUser:

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        from app.core.dependencies import get_current_user

        user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.email = "test@example.com"
        mock_user.is_deleted = False

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        # Create mock session with proper begin() context manager
        mock_session = MagicMock()
        mock_session.begin = MagicMock(return_value=AsyncMock())

        with patch("app.core.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "type": "access",
                "exp": 9999999999,
            }

            with patch("app.core.dependencies.auth.user_db") as mock_user_db:
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
        from app.core.dependencies import get_current_user

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "invalid_token"

        mock_session = AsyncMock()

        with patch("app.core.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = None  # Invalid token

            with pytest.raises(AuthenticationException) as exc_info:
                await get_current_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 401
            assert "Invalid or expired access token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_token_missing_sub_claim_raises_401(self):
        from app.core.dependencies import get_current_user

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "token_no_sub"

        mock_session = AsyncMock()

        with patch("app.core.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "type": "access",
                "exp": 9999999999,
                # Missing 'sub' claim
            }

            with pytest.raises(AuthenticationException) as exc_info:
                await get_current_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 401
            assert "Invalid access token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_wrong_token_type_raises_401(self):
        from app.core.dependencies import get_current_user

        user_id = uuid4()
        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "refresh_token"

        mock_session = AsyncMock()

        with patch("app.core.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "type": "refresh",  # Wrong type
                "exp": 9999999999,
            }

            with pytest.raises(AuthenticationException) as exc_info:
                await get_current_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 401
            assert "Invalid access token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_user_id_format_raises_401(self):
        from app.core.dependencies import get_current_user

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "token_bad_id"

        mock_session = AsyncMock()

        with patch("app.core.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": "not-a-valid-uuid",  # Invalid UUID
                "type": "access",
                "exp": 9999999999,
            }

            with pytest.raises(AuthenticationException) as exc_info:
                await get_current_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 401
            assert "Invalid access token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_user_not_found_raises_401(self):
        from app.core.dependencies import get_current_user

        user_id = uuid4()
        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        # Create mock session with proper begin() context manager
        mock_session = MagicMock()
        mock_session.begin = MagicMock(return_value=AsyncMock())

        with patch("app.core.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "type": "access",
                "exp": 9999999999,
            }

            with patch("app.core.dependencies.auth.user_db") as mock_user_db:
                mock_user_db.get_by_id = AsyncMock(return_value=None)  # User not found

                with pytest.raises(AuthenticationException) as exc_info:
                    await get_current_user(
                        credentials=mock_credentials,
                        session=mock_session,
                    )

                assert exc_info.value.status_code == 401
                assert "User not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_deleted_user_raises_401(self):
        from app.core.dependencies import get_current_user

        user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.is_deleted = True  # User is deleted

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        # Create mock session with proper begin() context manager
        mock_session = MagicMock()
        mock_session.begin = MagicMock(return_value=AsyncMock())

        with patch("app.core.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "type": "access",
                "exp": 9999999999,
            }

            with patch("app.core.dependencies.auth.user_db") as mock_user_db:
                mock_user_db.get_by_id = AsyncMock(return_value=mock_user)

                with pytest.raises(AuthenticationException) as exc_info:
                    await get_current_user(
                        credentials=mock_credentials,
                        session=mock_session,
                    )

                assert exc_info.value.status_code == 401
                assert "User account has been deleted" in str(exc_info.value)


class TestGetCurrentActiveUser:

    @pytest.mark.asyncio
    async def test_active_user_returns_user(self):
        from app.core.dependencies import get_current_active_user

        mock_user = MagicMock()
        mock_user.is_active = True
        mock_user.email = "active@example.com"

        result = await get_current_active_user(user=mock_user)

        assert result == mock_user

    @pytest.mark.asyncio
    async def test_inactive_user_raises_403(self):
        from app.core.dependencies import get_current_active_user

        mock_user = MagicMock()
        mock_user.is_active = False
        mock_user.email = "inactive@example.com"

        with pytest.raises(ForbiddenException) as exc_info:
            await get_current_active_user(user=mock_user)

        assert exc_info.value.status_code == 403
        assert "User account is deactivated" in str(exc_info.value)


class TestGetCurrentVerifiedUser:

    @pytest.mark.asyncio
    async def test_verified_user_returns_user(self):
        from app.core.dependencies import get_current_verified_user

        mock_user = MagicMock()
        mock_user.email_verified = True
        mock_user.email = "verified@example.com"

        result = await get_current_verified_user(user=mock_user)

        assert result == mock_user

    @pytest.mark.asyncio
    async def test_unverified_user_raises_403(self):
        from app.core.dependencies import get_current_verified_user

        mock_user = MagicMock()
        mock_user.email_verified = False
        mock_user.email = "unverified@example.com"

        with pytest.raises(ForbiddenException) as exc_info:
            await get_current_verified_user(user=mock_user)

        assert exc_info.value.status_code == 403
        assert "Email verification required" in str(exc_info.value)


class TestGetOptionalUser:

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        from app.core.dependencies import get_optional_user

        user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.is_deleted = False

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        # Create mock session with proper begin() context manager
        mock_session = MagicMock()
        mock_session.begin = MagicMock(return_value=AsyncMock())

        with patch("app.core.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "type": "access",
                "exp": 9999999999,
            }

            with patch("app.core.dependencies.auth.user_db") as mock_user_db:
                mock_user_db.get_by_id = AsyncMock(return_value=mock_user)

                result = await get_optional_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

                assert result == mock_user

    @pytest.mark.asyncio
    async def test_no_credentials_returns_none(self):
        from app.core.dependencies import get_optional_user

        mock_session = AsyncMock()

        result = await get_optional_user(
            credentials=None,  # No credentials
            session=mock_session,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self):
        from app.core.dependencies import get_optional_user

        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "invalid_token"

        mock_session = AsyncMock()

        with patch("app.core.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = None  # Invalid token

            result = await get_optional_user(
                credentials=mock_credentials,
                session=mock_session,
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_user_not_found_returns_none(self):
        from app.core.dependencies import get_optional_user

        user_id = uuid4()
        mock_credentials = MagicMock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        # Create mock session with proper begin() context manager
        mock_session = MagicMock()
        mock_session.begin = MagicMock(return_value=AsyncMock())

        with patch("app.core.dependencies.auth.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "type": "access",
                "exp": 9999999999,
            }

            with patch("app.core.dependencies.auth.user_db") as mock_user_db:
                mock_user_db.get_by_id = AsyncMock(return_value=None)

                result = await get_optional_user(
                    credentials=mock_credentials,
                    session=mock_session,
                )

                assert result is None


class TestBearerScheme:

    def test_bearer_scheme_auto_error_true(self):
        from app.core.dependencies import bearer_scheme

        assert bearer_scheme.auto_error is True

    def test_optional_bearer_scheme_auto_error_false(self):
        from app.core.dependencies import optional_bearer_scheme

        assert optional_bearer_scheme.auto_error is False


class TestTypeAliases:

    def test_type_aliases_are_defined(self):
        from app.core.dependencies import (
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

    def test_all_exports_available(self):
        from app.core.dependencies import (
            bearer_scheme,
            optional_bearer_scheme,
            get_current_user,
            get_current_active_user,
            get_current_verified_user,
            get_optional_user,
        )

        # All exports should be callable or defined
        assert callable(get_current_user)
        assert callable(get_current_active_user)
        assert callable(get_current_verified_user)
        assert callable(get_optional_user)
        assert bearer_scheme is not None
        assert optional_bearer_scheme is not None

    def test_dependencies_init_exports(self):
        from app.core.dependencies import (
            get_current_user,
            get_current_active_user,
            get_current_verified_user,
            get_optional_user,
        )

        # All should be importable from __init__
        assert callable(get_current_user)
        assert callable(get_current_active_user)
        assert callable(get_current_verified_user)
        assert callable(get_optional_user)

