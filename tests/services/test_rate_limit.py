"""
Unit tests for rate limiting service.

This module provides comprehensive test coverage for the rate limiting
service including memory and Redis backends, and stackable dependencies.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request


# ============================================================================
# Tests for RateLimitResult
# ============================================================================


class TestRateLimitResult:
    """Test suite for RateLimitResult dataclass."""

    def test_rate_limit_result_allowed(self):
        """Test RateLimitResult when request is allowed."""
        from app.core.services.rate_limit import RateLimitResult

        result = RateLimitResult(
            allowed=True,
            remaining=9,
            limit=10,
            reset_at=datetime.now(timezone.utc),
        )

        assert result.allowed is True
        assert result.remaining == 9
        assert result.limit == 10
        assert result.reset_at is not None

    def test_rate_limit_result_denied(self):
        """Test RateLimitResult when request is denied."""
        from app.core.services.rate_limit import RateLimitResult

        result = RateLimitResult(
            allowed=False,
            remaining=0,
            limit=10,
            reset_at=datetime.now(timezone.utc),
            retry_after=30,
        )

        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after == 30


# ============================================================================
# Tests for MemoryBackend
# ============================================================================


class TestMemoryBackend:
    """Test suite for MemoryBackend."""

    @pytest.mark.asyncio
    async def test_memory_backend_first_request(self):
        """Test first request creates new entry."""
        from app.core.services.rate_limit import MemoryBackend

        backend = MemoryBackend()
        result = await backend.check("test_key", limit=10, window=60)

        assert result.allowed is True
        assert result.remaining == 9
        assert result.limit == 10

    @pytest.mark.asyncio
    async def test_memory_backend_increment(self):
        """Test incrementing request count."""
        from app.core.services.rate_limit import MemoryBackend

        backend = MemoryBackend()

        # First request
        await backend.check("test_key", limit=10, window=60)
        # Second request
        result = await backend.check("test_key", limit=10, window=60)

        assert result.allowed is True
        assert result.remaining == 8

    @pytest.mark.asyncio
    async def test_memory_backend_limit_exceeded(self):
        """Test rate limit exceeded."""
        from app.core.services.rate_limit import MemoryBackend

        backend = MemoryBackend()

        # Exhaust the limit
        for i in range(10):
            await backend.check("test_key", limit=10, window=60)

        # Next request should be denied
        result = await backend.check("test_key", limit=10, window=60)

        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after is not None

    @pytest.mark.asyncio
    async def test_memory_backend_window_reset(self):
        """Test window reset after expiry."""
        from app.core.services.rate_limit import MemoryBackend

        backend = MemoryBackend()

        # Use a very short window
        await backend.check("test_key", limit=1, window=0.1)

        # Wait for window to expire
        await asyncio.sleep(0.15)

        # Should be allowed again
        result = await backend.check("test_key", limit=1, window=0.1)

        assert result.allowed is True
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_memory_backend_reset(self):
        """Test resetting a key."""
        from app.core.services.rate_limit import MemoryBackend

        backend = MemoryBackend()

        # Make some requests
        await backend.check("test_key", limit=10, window=60)
        await backend.check("test_key", limit=10, window=60)

        # Reset
        await backend.reset("test_key")

        # Should start fresh
        result = await backend.check("test_key", limit=10, window=60)

        assert result.remaining == 9

    @pytest.mark.asyncio
    async def test_memory_backend_get_remaining(self):
        """Test getting remaining requests."""
        from app.core.services.rate_limit import MemoryBackend

        backend = MemoryBackend()

        # Make some requests
        await backend.check("test_key", limit=10, window=60)
        await backend.check("test_key", limit=10, window=60)

        remaining = await backend.get_remaining("test_key", limit=10, window=60)

        assert remaining == 8

    @pytest.mark.asyncio
    async def test_memory_backend_get_remaining_no_key(self):
        """Test getting remaining when key doesn't exist."""
        from app.core.services.rate_limit import MemoryBackend

        backend = MemoryBackend()
        remaining = await backend.get_remaining("non_existing", limit=10, window=60)

        assert remaining == 10

    @pytest.mark.asyncio
    async def test_memory_backend_cleanup_expired(self):
        """Test that expired entries are cleaned up."""
        from app.core.services.rate_limit import MemoryBackend

        backend = MemoryBackend()

        # Create entry with short window
        await backend.check("test_key", limit=10, window=0.1)

        # Wait for expiry
        await asyncio.sleep(0.15)

        # Make another request (should trigger cleanup)
        await backend.check("test_key", limit=10, window=0.1)

        # Check internal state - old entry should be replaced
        assert "test_key" in backend._store


# ============================================================================
# Tests for RedisBackend
# ============================================================================


class TestRedisBackend:
    """Test suite for RedisBackend."""

    @pytest.mark.asyncio
    async def test_redis_backend_first_request(self):
        """Test first request creates new entry."""
        from app.core.services.rate_limit import RedisBackend

        with patch("app.core.services.rate_limit.RedisService") as mock_redis:
            mock_redis.incr = AsyncMock(return_value=1)
            mock_redis.expire = AsyncMock(return_value=True)
            mock_redis.ttl = AsyncMock(return_value=60)

            backend = RedisBackend()
            result = await backend.check("test_key", limit=10, window=60)

            assert result.allowed is True
            assert result.remaining == 9
            mock_redis.incr.assert_called_once()
            mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_backend_limit_exceeded(self):
        """Test rate limit exceeded."""
        from app.core.services.rate_limit import RedisBackend

        with patch("app.core.services.rate_limit.RedisService") as mock_redis:
            mock_redis.incr = AsyncMock(return_value=11)
            mock_redis.ttl = AsyncMock(return_value=30)

            backend = RedisBackend()
            result = await backend.check("test_key", limit=10, window=60)

            assert result.allowed is False
            assert result.remaining == 0
            assert result.retry_after == 30

    @pytest.mark.asyncio
    async def test_redis_backend_reset(self):
        """Test resetting a key."""
        from app.core.services.rate_limit import RedisBackend

        with patch("app.core.services.rate_limit.RedisService") as mock_redis:
            mock_redis.delete = AsyncMock(return_value=True)

            backend = RedisBackend()
            await backend.reset("test_key")

            mock_redis.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_redis_backend_get_remaining(self):
        """Test getting remaining requests."""
        from app.core.services.rate_limit import RedisBackend

        with patch("app.core.services.rate_limit.RedisService") as mock_redis:
            mock_redis.get = AsyncMock(return_value="5")

            backend = RedisBackend()
            remaining = await backend.get_remaining("test_key", limit=10, window=60)

            assert remaining == 5

    @pytest.mark.asyncio
    async def test_redis_backend_get_remaining_no_key(self):
        """Test getting remaining when key doesn't exist."""
        from app.core.services.rate_limit import RedisBackend

        with patch("app.core.services.rate_limit.RedisService") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            backend = RedisBackend()
            remaining = await backend.get_remaining("test_key", limit=10, window=60)

            assert remaining == 10


# ============================================================================
# Tests for RateLimiter
# ============================================================================


class TestRateLimiter:
    """Test suite for RateLimiter class."""

    @pytest.mark.asyncio
    async def test_rate_limiter_memory_backend(self):
        """Test RateLimiter with memory backend."""
        from app.core.services.rate_limit import RateLimiter

        limiter = RateLimiter(backend="memory")
        result = await limiter.check("test_key", limit=10, window=60)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_rate_limiter_redis_backend(self):
        """Test RateLimiter with redis backend."""
        from app.core.services.rate_limit import RateLimiter

        with patch("app.core.services.rate_limit.RedisService") as mock_redis:
            mock_redis.incr = AsyncMock(return_value=1)
            mock_redis.expire = AsyncMock(return_value=True)
            mock_redis.ttl = AsyncMock(return_value=60)

            limiter = RateLimiter(backend="redis")
            result = await limiter.check("test_key", limit=10, window=60)

            assert result.allowed is True

    @pytest.mark.asyncio
    async def test_rate_limiter_default_backend_from_settings(self):
        """Test RateLimiter uses settings for default backend."""
        from app.core.services.rate_limit import RateLimiter

        with patch("app.core.services.rate_limit.settings") as mock_settings:
            mock_settings.RATE_LIMIT_BACKEND = "memory"

            limiter = RateLimiter()
            result = await limiter.check("test_key", limit=10, window=60)

            assert result.allowed is True


# ============================================================================
# Tests for Rate Limit Dependencies
# ============================================================================


class TestRateLimitDependencies:
    """Test suite for rate limit FastAPI dependencies."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock FastAPI request."""
        request = MagicMock(spec=Request)
        request.client.host = "192.168.1.1"
        request.url.path = "/api/test"
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_rate_limit_by_ip(self, mock_request):
        """Test rate_limit_by_ip dependency."""
        from app.core.services.rate_limit import rate_limit_by_ip

        with patch("app.core.services.rate_limit.RateLimiter") as mock_limiter_class:
            mock_limiter = MagicMock()
            mock_limiter.check = AsyncMock(
                return_value=MagicMock(allowed=True, remaining=9, limit=10)
            )
            mock_limiter_class.return_value = mock_limiter

            dependency = rate_limit_by_ip(limit=10, window=60)
            result = await dependency(mock_request)

            assert result.allowed is True
            mock_limiter.check.assert_called_once()
            call_args = mock_limiter.check.call_args
            assert "ip:192.168.1.1" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_rate_limit_by_ip_exceeded(self, mock_request):
        """Test rate_limit_by_ip when limit exceeded."""
        from app.core.services.rate_limit import rate_limit_by_ip
        from app.core.exceptions.types import RateLimitExceededException

        with patch("app.core.services.rate_limit.RateLimiter") as mock_limiter_class:
            mock_limiter = MagicMock()
            mock_limiter.check = AsyncMock(
                return_value=MagicMock(
                    allowed=False, remaining=0, limit=10, retry_after=30
                )
            )
            mock_limiter_class.return_value = mock_limiter

            dependency = rate_limit_by_ip(limit=10, window=60)

            with pytest.raises(RateLimitExceededException) as exc_info:
                await dependency(mock_request)

            assert exc_info.value.retry_after == 30

    @pytest.mark.asyncio
    async def test_rate_limit_by_endpoint(self, mock_request):
        """Test rate_limit_by_endpoint dependency."""
        from app.core.services.rate_limit import rate_limit_by_endpoint

        with patch("app.core.services.rate_limit.RateLimiter") as mock_limiter_class:
            mock_limiter = MagicMock()
            mock_limiter.check = AsyncMock(
                return_value=MagicMock(allowed=True, remaining=9, limit=10)
            )
            mock_limiter_class.return_value = mock_limiter

            dependency = rate_limit_by_endpoint(limit=10, window=60)
            result = await dependency(mock_request)

            assert result.allowed is True
            call_args = mock_limiter.check.call_args
            assert "endpoint:/api/test" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_rate_limit_by_user(self):
        """Test rate_limit_by_user dependency."""
        from app.core.services.rate_limit import rate_limit_by_user

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/test"

        with patch("app.core.services.rate_limit.RateLimiter") as mock_limiter_class:
            mock_limiter = MagicMock()
            mock_limiter.check = AsyncMock(
                return_value=MagicMock(allowed=True, remaining=9, limit=10)
            )
            mock_limiter_class.return_value = mock_limiter

            dependency = rate_limit_by_user(limit=10, window=60)
            result = await dependency(mock_request, user_id="user-123")

            assert result.allowed is True
            call_args = mock_limiter.check.call_args
            assert "user:user-123" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_rate_limit_by_user_no_user(self):
        """Test rate_limit_by_user when no user_id provided."""
        from app.core.services.rate_limit import rate_limit_by_user
        from app.core.exceptions.types import AuthenticationException

        mock_request = MagicMock(spec=Request)

        dependency = rate_limit_by_user(limit=10, window=60)

        with pytest.raises(AuthenticationException):
            await dependency(mock_request, user_id=None)


# ============================================================================
# Tests for Key Format
# ============================================================================


class TestKeyFormat:
    """Test suite for rate limit key formatting."""

    def test_key_format_ip(self):
        """Test IP-based key format."""
        from app.core.services.rate_limit import format_rate_limit_key

        key = format_rate_limit_key("ip", "192.168.1.1", "/api/test")
        assert key == "rate_limit:ip:192.168.1.1:/api/test"

    def test_key_format_user(self):
        """Test user-based key format."""
        from app.core.services.rate_limit import format_rate_limit_key

        key = format_rate_limit_key("user", "user-123", "/api/test")
        assert key == "rate_limit:user:user-123:/api/test"

    def test_key_format_endpoint(self):
        """Test endpoint-based key format."""
        from app.core.services.rate_limit import format_rate_limit_key

        key = format_rate_limit_key("endpoint", "/api/test", "/api/test")
        assert key == "rate_limit:endpoint:/api/test:/api/test"


# ============================================================================
# Tests for Stacking Rate Limiters
# ============================================================================


class TestStackingRateLimiters:
    """Test suite for stacking multiple rate limiters."""

    @pytest.mark.asyncio
    async def test_stacking_ip_and_endpoint(self):
        """Test stacking IP and endpoint rate limiters."""
        from app.core.services.rate_limit import (
            rate_limit_by_ip,
            rate_limit_by_endpoint,
        )

        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "192.168.1.1"
        mock_request.url.path = "/api/test"

        with patch("app.core.services.rate_limit.RateLimiter") as mock_limiter_class:
            mock_limiter = MagicMock()
            mock_limiter.check = AsyncMock(
                return_value=MagicMock(allowed=True, remaining=9, limit=10)
            )
            mock_limiter_class.return_value = mock_limiter

            # Both should pass
            ip_dep = rate_limit_by_ip(limit=100, window=60)
            endpoint_dep = rate_limit_by_endpoint(limit=10, window=60)

            ip_result = await ip_dep(mock_request)
            endpoint_result = await endpoint_dep(mock_request)

            assert ip_result.allowed is True
            assert endpoint_result.allowed is True
            assert mock_limiter.check.call_count == 2
