"""
Unit tests for RedisService.

"""

from unittest.mock import AsyncMock, patch

import pytest


class TestRedisServiceInit:

    @pytest.mark.asyncio
    async def test_init_success(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")

            mock_redis_class.from_url.assert_called_once()
            assert RedisService._client is not None

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_init_with_default_url(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init()

            mock_redis_class.from_url.assert_called_once()

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_init_closes_existing_connection(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            await RedisService.init("redis://localhost:6379/1")

            assert mock_redis_class.from_url.call_count == 2

        await RedisService.aclose()


class TestRedisServiceAclose:

    @pytest.mark.asyncio
    async def test_aclose_success(self):
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
        from app.core.services.redis_service import RedisService

        RedisService._client = None

        await RedisService.aclose()


class TestRedisServicePing:

    @pytest.mark.asyncio
    async def test_ping_success(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.ping.return_value = True
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.ping()

            assert result is True
            mock_client.ping.assert_called_once()

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_ping_failure(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.ping.side_effect = Exception("Connection refused")
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.ping()

            assert result is False

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_ping_when_not_initialized(self):
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.ping()

        assert result is False


class TestRedisServiceGet:

    @pytest.mark.asyncio
    async def test_get_existing_key(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = b"test_value"
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.get("test_key")

            assert result == "test_value"
            mock_client.get.assert_called_once_with("test_key")

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_get_non_existing_key(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = None
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.get("non_existing_key")

            assert result is None

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_get_when_not_initialized(self):
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.get("test_key")

        assert result is None


class TestRedisServiceSet:

    @pytest.mark.asyncio
    async def test_set_without_ttl(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.set.return_value = True
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.set("test_key", "test_value")

            assert result is True
            mock_client.set.assert_called_once_with("test_key", "test_value", ex=None)

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_set_with_ttl(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.set.return_value = True
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.set("test_key", "test_value", ttl=60)

            assert result is True
            mock_client.set.assert_called_once_with("test_key", "test_value", ex=60)

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_set_when_not_initialized(self):
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.set("test_key", "test_value")

        assert result is False


class TestRedisServiceIncr:

    @pytest.mark.asyncio
    async def test_incr_success(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.incr.return_value = 5
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.incr("counter_key")

            assert result == 5
            mock_client.incr.assert_called_once_with("counter_key")

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_incr_when_not_initialized(self):
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.incr("counter_key")

        assert result is None


class TestRedisServiceExpire:

    @pytest.mark.asyncio
    async def test_expire_success(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.expire.return_value = True
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.expire("test_key", 60)

            assert result is True
            mock_client.expire.assert_called_once_with("test_key", 60)

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_expire_when_not_initialized(self):
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.expire("test_key", 60)

        assert result is False


class TestRedisServiceDelete:

    @pytest.mark.asyncio
    async def test_delete_success(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.delete.return_value = 1
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.delete("test_key")

            assert result is True
            mock_client.delete.assert_called_once_with("test_key")

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_delete_non_existing_key(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.delete.return_value = 0
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.delete("non_existing_key")

            assert result is False

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_delete_when_not_initialized(self):
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.delete("test_key")

        assert result is False


class TestRedisServiceExists:

    @pytest.mark.asyncio
    async def test_exists_true(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.exists.return_value = 1
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.exists("test_key")

            assert result is True
            mock_client.exists.assert_called_once_with("test_key")

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_exists_false(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.exists.return_value = 0
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.exists("non_existing_key")

            assert result is False

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_exists_when_not_initialized(self):
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.exists("test_key")

        assert result is False


class TestRedisServiceTTL:

    @pytest.mark.asyncio
    async def test_ttl_success(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.ttl.return_value = 60
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.ttl("test_key")

            assert result == 60
            mock_client.ttl.assert_called_once_with("test_key")

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_ttl_no_expiry(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.ttl.return_value = -1  # No expiry
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.ttl("test_key")

            assert result == -1

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_ttl_when_not_initialized(self):
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.ttl("test_key")

        assert result is None


class TestRedisServiceSetNX:

    @pytest.mark.asyncio
    async def test_setnx_success(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.setnx.return_value = True
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.setnx("test_key", "test_value")

            assert result is True
            mock_client.setnx.assert_called_once_with("test_key", "test_value")

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_setnx_key_exists(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_client.setnx.return_value = False
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")
            result = await RedisService.setnx("existing_key", "test_value")

            assert result is False

        await RedisService.aclose()

    @pytest.mark.asyncio
    async def test_setnx_when_not_initialized(self):
        from app.core.services.redis_service import RedisService

        RedisService._client = None
        result = await RedisService.setnx("test_key", "test_value")

        assert result is False


class TestRedisServiceIsConnected:

    @pytest.mark.asyncio
    async def test_is_connected_true(self):
        from app.core.services.redis_service import RedisService

        with patch("app.core.services.redis_service.Redis") as mock_redis_class:
            mock_client = AsyncMock()
            mock_redis_class.from_url.return_value = mock_client

            await RedisService.init("redis://localhost:6379/0")

            assert RedisService.is_connected() is True

        await RedisService.aclose()

    def test_is_connected_false(self):
        from app.core.services.redis_service import RedisService

        RedisService._client = None

        assert RedisService.is_connected() is False

