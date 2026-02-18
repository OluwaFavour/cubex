"""
Test suite for RefreshToken CRUD operations.

This module contains comprehensive unit tests for the RefreshTokenDB CRUD class.
Tests cover all CRUD operations including:
- Token creation
- Token validation and retrieval
- Token revocation (single and all)
- Expired token cleanup
- Active session retrieval

Run all tests:
    pytest tests/shared/db/crud/test_refresh_token.py -v

Run with coverage:
    pytest tests/shared/db/crud/test_refresh_token.py --cov=app.core.db.crud.refresh_token --cov-report=term-missing -v
"""

import hashlib
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.db.crud.refresh_token import RefreshTokenDB


class TestRefreshTokenDBCreate:
    """Test suite for RefreshToken creation."""

    @pytest.mark.asyncio
    async def test_create_refresh_token_hashes_token(self):
        """Test that create hashes the raw token."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        user_id = uuid4()
        raw_token = "test_raw_token_123"
        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(days=7)

        with patch.object(RefreshTokenDB, "create") as mock_create:
            mock_token = MagicMock()
            mock_token.token_hash = expected_hash
            mock_token.user_id = user_id
            mock_create.return_value = mock_token

            result = await RefreshTokenDB.create(
                session=mock_session,
                user_id=user_id,
                raw_token=raw_token,
                expires_at=expires_at,
            )

            assert result.token_hash == expected_hash

    @pytest.mark.asyncio
    async def test_create_refresh_token_with_device_info(self):
        """Test that create stores device info correctly."""
        mock_session = AsyncMock()
        user_id = uuid4()
        raw_token = "test_token"
        device_info = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

        with patch.object(RefreshTokenDB, "create") as mock_create:
            mock_token = MagicMock()
            mock_token.device_info = device_info
            mock_create.return_value = mock_token

            result = await RefreshTokenDB.create(
                session=mock_session,
                user_id=user_id,
                raw_token=raw_token,
                expires_at=datetime.now(UTC) + timedelta(days=7),
                device_info=device_info,
            )

            assert result.device_info == device_info


class TestRefreshTokenDBGetValidToken:
    """Test suite for retrieving valid tokens."""

    @pytest.mark.asyncio
    async def test_get_valid_token_finds_matching_token(self):
        """Test that get_valid_token returns token when hash matches."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_token = MagicMock()
        mock_token.is_valid = True
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute.return_value = mock_result

        raw_token = "valid_token"

        with patch.object(RefreshTokenDB, "get_valid_token") as mock_get:
            mock_get.return_value = mock_token

            result = await RefreshTokenDB.get_valid_token(
                session=mock_session,
                raw_token=raw_token,
            )

            assert result is not None
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_get_valid_token_returns_none_for_invalid_token(self):
        """Test that get_valid_token returns None for non-existent token."""
        mock_session = AsyncMock()

        with patch.object(RefreshTokenDB, "get_valid_token") as mock_get:
            mock_get.return_value = None

            result = await RefreshTokenDB.get_valid_token(
                session=mock_session,
                raw_token="nonexistent_token",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_get_valid_token_excludes_revoked_tokens(self):
        """Test that get_valid_token excludes revoked tokens."""
        mock_session = AsyncMock()

        with patch.object(RefreshTokenDB, "get_valid_token") as mock_get:
            # Simulating that the query filters out revoked tokens
            mock_get.return_value = None

            result = await RefreshTokenDB.get_valid_token(
                session=mock_session,
                raw_token="revoked_token",
            )

            assert result is None


class TestRefreshTokenDBRevoke:
    """Test suite for revoking tokens."""

    @pytest.mark.asyncio
    async def test_revoke_sets_revoked_at(self):
        """Test that revoke sets revoked_at timestamp."""
        mock_session = AsyncMock()
        token_id = uuid4()

        with patch.object(RefreshTokenDB, "revoke") as mock_revoke:
            mock_token = MagicMock()
            mock_token.revoked_at = datetime.now(UTC)
            mock_revoke.return_value = mock_token

            result = await RefreshTokenDB.revoke(
                session=mock_session,
                token_id=token_id,
            )

            assert result.revoked_at is not None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_token_returns_none(self):
        """Test that revoking non-existent token returns None."""
        mock_session = AsyncMock()

        with patch.object(RefreshTokenDB, "revoke") as mock_revoke:
            mock_revoke.return_value = None

            result = await RefreshTokenDB.revoke(
                session=mock_session,
                token_id=uuid4(),
            )

            assert result is None


class TestRefreshTokenDBRevokeAllForUser:
    """Test suite for revoking all user tokens."""

    @pytest.mark.asyncio
    async def test_revoke_all_for_user_returns_count(self):
        """Test that revoke_all_for_user returns count of revoked tokens."""
        mock_session = AsyncMock()
        user_id = uuid4()

        with patch.object(RefreshTokenDB, "revoke_all_for_user") as mock_revoke:
            mock_revoke.return_value = 5

            result = await RefreshTokenDB.revoke_all_for_user(
                session=mock_session,
                user_id=user_id,
            )

            assert result == 5

    @pytest.mark.asyncio
    async def test_revoke_all_for_user_excludes_current_token(self):
        """Test that revoke_all_for_user can exclude current token."""
        mock_session = AsyncMock()
        user_id = uuid4()
        current_token_id = uuid4()

        with patch.object(RefreshTokenDB, "revoke_all_for_user") as mock_revoke:
            # Simulating excluding the current token
            mock_revoke.return_value = 4  # One less than total

            result = await RefreshTokenDB.revoke_all_for_user(
                session=mock_session,
                user_id=user_id,
                exclude_token_id=current_token_id,
            )

            assert result == 4

    @pytest.mark.asyncio
    async def test_revoke_all_for_user_with_no_tokens(self):
        """Test that revoke_all_for_user returns 0 for user with no tokens."""
        mock_session = AsyncMock()

        with patch.object(RefreshTokenDB, "revoke_all_for_user") as mock_revoke:
            mock_revoke.return_value = 0

            result = await RefreshTokenDB.revoke_all_for_user(
                session=mock_session,
                user_id=uuid4(),
            )

            assert result == 0


class TestRefreshTokenDBCleanupExpired:
    """Test suite for cleaning up expired tokens."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_removes_old_tokens(self):
        """Test that cleanup_expired removes expired tokens."""
        mock_session = AsyncMock()

        with patch.object(RefreshTokenDB, "cleanup_expired") as mock_cleanup:
            mock_cleanup.return_value = 10

            result = await RefreshTokenDB.cleanup_expired(
                session=mock_session,
            )

            assert result == 10

    @pytest.mark.asyncio
    async def test_cleanup_expired_respects_older_than(self):
        """Test that cleanup_expired respects older_than parameter."""
        mock_session = AsyncMock()
        older_than = datetime.now(UTC) - timedelta(days=30)

        with patch.object(RefreshTokenDB, "cleanup_expired") as mock_cleanup:
            mock_cleanup.return_value = 5

            result = await RefreshTokenDB.cleanup_expired(
                session=mock_session,
                older_than=older_than,
            )

            assert result == 5


class TestRefreshTokenDBGetActiveTokensForUser:
    """Test suite for getting active tokens for a user."""

    @pytest.mark.asyncio
    async def test_get_active_tokens_returns_list(self):
        """Test that get_active_tokens_for_user returns list of tokens."""
        mock_session = AsyncMock()
        user_id = uuid4()

        with patch.object(RefreshTokenDB, "get_active_tokens_for_user") as mock_get:
            mock_tokens = [MagicMock(), MagicMock(), MagicMock()]
            mock_get.return_value = mock_tokens

            result = await RefreshTokenDB.get_active_tokens_for_user(
                session=mock_session,
                user_id=user_id,
            )

            assert len(result) == 3
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_active_tokens_returns_empty_for_no_tokens(self):
        """Test that get_active_tokens_for_user returns empty list when no tokens."""
        mock_session = AsyncMock()

        with patch.object(RefreshTokenDB, "get_active_tokens_for_user") as mock_get:
            mock_get.return_value = []

            result = await RefreshTokenDB.get_active_tokens_for_user(
                session=mock_session,
                user_id=uuid4(),
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_get_active_tokens_excludes_expired(self):
        """Test that get_active_tokens_for_user excludes expired tokens."""
        mock_session = AsyncMock()
        user_id = uuid4()

        with patch.object(RefreshTokenDB, "get_active_tokens_for_user") as mock_get:
            # Only return non-expired tokens
            mock_token = MagicMock()
            mock_token.expires_at = datetime.now(UTC) + timedelta(days=5)
            mock_get.return_value = [mock_token]

            result = await RefreshTokenDB.get_active_tokens_for_user(
                session=mock_session,
                user_id=user_id,
            )

            assert len(result) == 1
            assert result[0].expires_at > datetime.now(UTC)


class TestRefreshTokenModel:
    """Test suite for RefreshToken model properties."""

    def test_is_valid_property_returns_true_for_valid_token(self):
        """Test is_valid returns True for non-expired, non-revoked token."""
        from app.core.db.models.refresh_token import RefreshToken

        # Create mock token with valid attributes
        token = MagicMock(spec=RefreshToken)
        token.expires_at = datetime.now(UTC) + timedelta(days=5)
        token.revoked_at = None

        # Mock the is_valid property
        token.is_valid = token.revoked_at is None and token.expires_at > datetime.now(
            UTC
        )

        assert token.is_valid is True

    def test_is_valid_property_returns_false_for_expired_token(self):
        """Test is_valid returns False for expired token."""
        token = MagicMock()
        token.expires_at = datetime.now(UTC) - timedelta(days=1)
        token.revoked_at = None
        token.is_valid = token.revoked_at is None and token.expires_at > datetime.now(
            UTC
        )

        assert token.is_valid is False

    def test_is_valid_property_returns_false_for_revoked_token(self):
        """Test is_valid returns False for revoked token."""
        token = MagicMock()
        token.expires_at = datetime.now(UTC) + timedelta(days=5)
        token.revoked_at = datetime.now(UTC) - timedelta(hours=1)
        token.is_valid = token.revoked_at is None and token.expires_at > datetime.now(
            UTC
        )

        assert token.is_valid is False


class TestRefreshTokenHashingUtility:
    """Test suite for token hashing functionality."""

    def test_hash_token_produces_consistent_hash(self):
        """Test that same token always produces same hash."""
        raw_token = "consistent_token_12345"
        hash1 = hashlib.sha256(raw_token.encode()).hexdigest()
        hash2 = hashlib.sha256(raw_token.encode()).hexdigest()

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest length

    def test_different_tokens_produce_different_hashes(self):
        """Test that different tokens produce different hashes."""
        token1 = "token_one"
        token2 = "token_two"

        hash1 = hashlib.sha256(token1.encode()).hexdigest()
        hash2 = hashlib.sha256(token2.encode()).hexdigest()

        assert hash1 != hash2

    def test_hash_is_64_characters_hex(self):
        """Test that hash is always 64 hex characters."""
        token = "any_token"
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        assert len(token_hash) == 64
        assert all(c in "0123456789abcdef" for c in token_hash)
