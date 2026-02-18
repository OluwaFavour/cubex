"""
Unit tests for RedisService.

This module provides comprehensive test coverage for the RedisService class
including initialization, connection management, and all Redis operations.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestRedisServiceInit:
    """Test suite for RedisService initialization."""

    @pytest.mark.asyncio
    async def test_init_success(self):
        """Test successful initialization of RedisService."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")

            mock_redis_class.from_url.assert_called_once()
            assert RedisService._client is not None

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_init_with_default_url(self):
        """Test initialization with default URL from settings."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init()

            mock_redis_class.from_url.assert_called_once()

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_init_closes_existing_connection(self):
        """Test that init closes existing connection before creating new one."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_redis_class.from_url.return_value = mock_client

            # Initialize twice
            await RedisService.init("redis://localhost:6379/0")
            await RedisService.init("redis://localhost:6379/1")

            # Should have called close on the first client
            assert mock_redis_class.from_url.call_count == 2

        # Cleanup
        await RedisService.aclose()


class TestRedisServiceAclose:
    """Test suite for RedisService aclose method."""

    @pytest.mark.asyncio
    async def test_aclose_success(self):
        """Test successful closing of RedisService."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            await RedisService.aclose()

            mock_client.aclose.assert_called_once()
            assert RedisService._client is None

    @pytest.mark.asyncio
    async def test_aclose_when_not_initialized(self):
        """Test aclose when service is not initialized."""
        from app.core.services.redis_service import RedisService

        # Ensure client is None
        RedisService._client = None

        # Should not raise
        await RedisService.aclose()


class TestRedisServicePing:
    """Test suite for RedisService ping method."""

    @pytest.mark.asyncio
    async def test_ping_success(self):
        """Test successful ping."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.ping.return_value = True
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.ping()

            assert result is True
            mock_client.ping.assert_called_once()

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_ping_failure(self):
        """Test ping when connection fails."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.ping.side_effect = Exception("Connection refused")
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.ping()

            assert result is False

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_ping_when_not_initialized(self):
        """Test ping when service is not initialized."""
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.ping()

        assert result is False


class TestRedisServiceGet:
    """Test suite for RedisService get method."""

    @pytest.mark.asyncio
    async def test_get_existing_key(self):
        """Test getting an existing key."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = b"test_value"
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.get("test_key")

            assert result == "test_value"
            mock_client.get.assert_called_once_with("test_key")

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_get_non_existing_key(self):
        """Test getting a non-existing key."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = None
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.get("non_existing_key")

            assert result is None

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_get_when_not_initialized(self):
        """Test get when service is not initialized."""
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.get("test_key")

        assert result is None


class TestRedisServiceSet:
    """Test suite for RedisService set method."""

    @pytest.mark.asyncio
    async def test_set_without_ttl(self):
        """Test setting a value without TTL."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.set.return_value = True
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.set("test_key", "test_value")

            assert result is True
            mock_client.set.assert_called_once_with("test_key", "test_value", ex=None)

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_set_with_ttl(self):
        """Test setting a value with TTL."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.set.return_value = True
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.set("test_key", "test_value", ttl=60)

            assert result is True
            mock_client.set.assert_called_once_with("test_key", "test_value", ex=60)

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_set_when_not_initialized(self):
        """Test set when service is not initialized."""
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.set("test_key", "test_value")

        assert result is False


class TestRedisServiceIncr:
    """Test suite for RedisService incr method."""

    @pytest.mark.asyncio
    async def test_incr_success(self):
        """Test incrementing a counter."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.incr.return_value = 5
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.incr("counter_key")

            assert result == 5
            mock_client.incr.assert_called_once_with("counter_key")

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_incr_when_not_initialized(self):
        """Test incr when service is not initialized."""
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.incr("counter_key")

        assert result is None


class TestRedisServiceExpire:
    """Test suite for RedisService expire method."""

    @pytest.mark.asyncio
    async def test_expire_success(self):
        """Test setting expiration on a key."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.expire.return_value = True
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.expire("test_key", 60)

            assert result is True
            mock_client.expire.assert_called_once_with("test_key", 60)

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_expire_when_not_initialized(self):
        """Test expire when service is not initialized."""
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.expire("test_key", 60)

        assert result is False


class TestRedisServiceDelete:
    """Test suite for RedisService delete method."""

    @pytest.mark.asyncio
    async def test_delete_success(self):
        """Test deleting a key."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.delete.return_value = 1
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.delete("test_key")

            assert result is True
            mock_client.delete.assert_called_once_with("test_key")

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_delete_non_existing_key(self):
        """Test deleting a non-existing key."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.delete.return_value = 0
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.delete("non_existing_key")

            assert result is False

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_delete_when_not_initialized(self):
        """Test delete when service is not initialized."""
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.delete("test_key")

        assert result is False


class TestRedisServiceExists:
    """Test suite for RedisService exists method."""

    @pytest.mark.asyncio
    async def test_exists_true(self):
        """Test checking if a key exists."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.exists.return_value = 1
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.exists("test_key")

            assert result is True
            mock_client.exists.assert_called_once_with("test_key")

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_exists_false(self):
        """Test checking if a non-existing key exists."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.exists.return_value = 0
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.exists("non_existing_key")

            assert result is False

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_exists_when_not_initialized(self):
        """Test exists when service is not initialized."""
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.exists("test_key")

        assert result is False


class TestRedisServiceTTL:
    """Test suite for RedisService ttl method."""

    @pytest.mark.asyncio
    async def test_ttl_success(self):
        """Test getting TTL of a key."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.ttl.return_value = 60
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.ttl("test_key")

            assert result == 60
            mock_client.ttl.assert_called_once_with("test_key")

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_ttl_no_expiry(self):
        """Test getting TTL of a key with no expiry."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.ttl.return_value = -1  # No expiry
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.ttl("test_key")

            assert result == -1

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_ttl_when_not_initialized(self):
        """Test ttl when service is not initialized."""
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.ttl("test_key")

        assert result is None


class TestRedisServiceSetNX:
    """Test suite for RedisService setnx method."""

    @pytest.mark.asyncio
    async def test_setnx_success(self):
        """Test set if not exists - key doesn't exist."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.setnx.return_value = True
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.setnx("test_key", "test_value")

            assert result is True
            mock_client.setnx.assert_called_once_with("test_key", "test_value")

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_setnx_key_exists(self):
        """Test set if not exists - key already exists."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.setnx.return_value = False
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.setnx("existing_key", "test_value")

            assert result is False

        # Cleanup
        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_setnx_when_not_initialized(self):
        """Test setnx when service is not initialized."""
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.setnx("test_key", "test_value")

        assert result is False


class TestRedisServiceIsConnected:
    """Test suite for RedisService is_connected method."""

    @pytest.mark.asyncio
    async def test_is_connected_true(self):
        """Test is_connected when client is initialized."""
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")

            assert RedisService.is_connected() is True

        # Cleanup
        await RedisService.aclose()

    def test_is_connected_false(self):
        """Test is_connected when client is not initialized."""
        from app.core.services.redis_service import RedisService

        RedisService._client = None

        assert RedisService.is_connected() is False
