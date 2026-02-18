"""
Redis service for caching and rate limiting.

This module provides a singleton Redis client for async operations
including caching, rate limiting counters, and distributed state management.
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import redis_logger, settings


class RedisService:
    """
    Singleton Redis service for async Redis operations.

    This service provides a centralized Redis client for the application,
    supporting common operations like get, set, increment, and key management.
    It follows the same pattern as other services (BrevoService, CloudinaryService).

    Attributes:
        _client: The async Redis client instance.
        _url: The Redis connection URL.

    Example:
        >>> await RedisService.init("redis://localhost:6379/0")
        >>> await RedisService.set("key", "value", ttl=60)
        >>> value = await RedisService.get("key")
        >>> await RedisService.aclose()
    """

    _client: Redis | None = None
    _url: str = settings.REDIS_URL

    @classmethod
    async def init(cls, url: str | None = None) -> None:
        """
        Initialize the Redis service with the given URL.

        This method creates an async Redis client connection. If a client
        already exists, it will be closed before creating a new one.

        Args:
            url: The Redis connection URL. If None, uses settings.REDIS_URL.

        Returns:
            None

        Example:
            >>> await RedisService.init("redis://localhost:6379/0")
        """
        if url is not None:
            cls._url = url

        # Close existing connection if any
        await cls.aclose()

        try:
            cls._client = Redis.from_url(
                cls._url,
                encoding="utf-8",
                decode_responses=False,  # We handle decoding manually
            )
            redis_logger.info(f"Redis client initialized with URL: {cls._url}")
        except Exception as e:
            redis_logger.error(f"Failed to initialize Redis client: {str(e)}")
            raise

    @classmethod
    async def aclose(cls) -> None:
        """
        Close the Redis client connection.

        This method safely closes the Redis client and sets it to None.
        Safe to call even if the client is not initialized.

        Returns:
            None
        """
        if cls._client is not None:
            try:
                await cls._client.aclose()
                redis_logger.info("Redis client closed successfully")
            except Exception as e:
                redis_logger.warning(f"Error closing Redis client: {str(e)}")
            finally:
                cls._client = None

    @classmethod
    def is_connected(cls) -> bool:
        """
        Check if the Redis client is initialized.

        Returns:
            bool: True if client is initialized, False otherwise.
        """
        return cls._client is not None

    @classmethod
    async def ping(cls) -> bool:
        """
        Ping the Redis server to check connectivity.

        Returns:
            bool: True if ping succeeds, False otherwise.
        """
        if cls._client is None:
            redis_logger.warning("Redis ping attempted but client not initialized")
            return False

        try:
            result = await cls._client.ping()  # type: ignore[misc]
            redis_logger.debug("Redis ping successful")
            return bool(result)
        except Exception as e:
            redis_logger.error(f"Redis ping failed: {str(e)}")
            return False

    @classmethod
    async def get(cls, key: str) -> str | None:
        """
        Get a value from Redis by key.

        Args:
            key: The key to retrieve.

        Returns:
            The value as a string if found, None otherwise.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis get({key}) attempted but client not initialized"
            )
            return None

        try:
            value = await cls._client.get(key)
            if value is not None:
                # Decode bytes to string
                return value.decode("utf-8") if isinstance(value, bytes) else value
            return None
        except Exception as e:
            redis_logger.error(f"Redis get({key}) failed: {str(e)}")
            return None

    @classmethod
    async def set(
        cls,
        key: str,
        value: str,
        ttl: int | None = None,
    ) -> bool:
        """
        Set a value in Redis.

        Args:
            key: The key to set.
            value: The value to store.
            ttl: Optional time-to-live in seconds.

        Returns:
            bool: True if set succeeds, False otherwise.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis set({key}) attempted but client not initialized"
            )
            return False

        try:
            await cls._client.set(key, value, ex=ttl)
            redis_logger.debug(f"Redis set({key}) successful, TTL: {ttl}")
            return True
        except Exception as e:
            redis_logger.error(f"Redis set({key}) failed: {str(e)}")
            return False

    @classmethod
    async def setnx(cls, key: str, value: str) -> bool:
        """
        Set a value in Redis only if the key does not exist.

        Args:
            key: The key to set.
            value: The value to store.

        Returns:
            bool: True if set succeeds (key didn't exist), False otherwise.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis setnx({key}) attempted but client not initialized"
            )
            return False

        try:
            result = await cls._client.setnx(key, value)
            redis_logger.debug(f"Redis setnx({key}) result: {result}")
            return bool(result)
        except Exception as e:
            redis_logger.error(f"Redis setnx({key}) failed: {str(e)}")
            return False

    @classmethod
    async def incr(cls, key: str) -> int | None:
        """
        Increment a counter in Redis.

        If the key doesn't exist, it will be created with value 1.

        Args:
            key: The key to increment.

        Returns:
            The new value after increment, or None on failure.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis incr({key}) attempted but client not initialized"
            )
            return None

        try:
            value = await cls._client.incr(key)
            redis_logger.debug(f"Redis incr({key}) new value: {value}")
            return value
        except Exception as e:
            redis_logger.error(f"Redis incr({key}) failed: {str(e)}")
            return None

    @classmethod
    async def expire(cls, key: str, ttl: int) -> bool:
        """
        Set expiration time on a key.

        Args:
            key: The key to set expiration on.
            ttl: Time-to-live in seconds.

        Returns:
            bool: True if expiration was set, False otherwise.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis expire({key}) attempted but client not initialized"
            )
            return False

        try:
            result = await cls._client.expire(key, ttl)
            redis_logger.debug(f"Redis expire({key}, {ttl}) result: {result}")
            return bool(result)
        except Exception as e:
            redis_logger.error(f"Redis expire({key}) failed: {str(e)}")
            return False

    @classmethod
    async def ttl(cls, key: str) -> int | None:
        """
        Get the remaining time-to-live of a key.

        Args:
            key: The key to check.

        Returns:
            TTL in seconds, -1 if no expiry, -2 if key doesn't exist, None on error.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis ttl({key}) attempted but client not initialized"
            )
            return None

        try:
            value = await cls._client.ttl(key)
            return value
        except Exception as e:
            redis_logger.error(f"Redis ttl({key}) failed: {str(e)}")
            return None

    @classmethod
    async def delete(cls, key: str) -> bool:
        """
        Delete a key from Redis.

        Args:
            key: The key to delete.

        Returns:
            bool: True if key was deleted, False if key didn't exist or error.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis delete({key}) attempted but client not initialized"
            )
            return False

        try:
            result = await cls._client.delete(key)
            deleted = result > 0
            redis_logger.debug(f"Redis delete({key}) result: {deleted}")
            return deleted
        except Exception as e:
            redis_logger.error(f"Redis delete({key}) failed: {str(e)}")
            return False

    @classmethod
    async def exists(cls, key: str) -> bool:
        """
        Check if a key exists in Redis.

        Args:
            key: The key to check.

        Returns:
            bool: True if key exists, False otherwise.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis exists({key}) attempted but client not initialized"
            )
            return False

        try:
            result = await cls._client.exists(key)
            exists = result > 0
            redis_logger.debug(f"Redis exists({key}) result: {exists}")
            return exists
        except Exception as e:
            redis_logger.error(f"Redis exists({key}) failed: {str(e)}")
            return False

    @classmethod
    async def set_if_not_exists(
        cls,
        key: str,
        value: str = "1",
        ttl: int = 48 * 3600,
    ) -> bool:
        """
        Atomically set a value only if the key does not exist, with TTL.

        Uses Redis SET NX EX command for atomic check-and-set with expiration.
        Ideal for implementing idempotency checks (e.g., Stripe event deduplication).

        Args:
            key: The key to set.
            value: The value to store. Defaults to "1".
            ttl: Time-to-live in seconds. Defaults to 48 hours.

        Returns:
            bool: True if the key was set (didn't exist), False if key already existed.

        Example:
            >>> is_new = await RedisService.set_if_not_exists(f"stripe_event:{event_id}")
            >>> if not is_new:
            ...     return  # Already processed
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis set_if_not_exists({key}) attempted but client not initialized"
            )
            return False

        try:
            # SET key value NX EX ttl - atomically set if not exists with expiry
            result = await cls._client.set(key, value, nx=True, ex=ttl)
            was_set = result is not None
            redis_logger.debug(
                f"Redis set_if_not_exists({key}) result: {was_set}, TTL: {ttl}s"
            )
            return was_set
        except Exception as e:
            redis_logger.error(f"Redis set_if_not_exists({key}) failed: {str(e)}")
            return False

    @classmethod
    async def delete_pattern(cls, pattern: str) -> int:
        """
        Delete all keys matching a pattern.

        Uses SCAN to safely iterate through keys matching the pattern,
        then deletes them in batches. This is safe for production use
        unlike KEYS which can block Redis.

        Args:
            pattern: The pattern to match (e.g., "quota:endpoint_cost:*").

        Returns:
            int: Number of keys deleted.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis delete_pattern({pattern}) attempted but client not initialized"
            )
            return 0

        try:
            deleted_count = 0
            cursor = 0

            while True:
                cursor, keys = await cls._client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                if keys:
                    deleted_count += await cls._client.delete(*keys)
                if cursor == 0:
                    break

            redis_logger.debug(
                f"Redis delete_pattern({pattern}) deleted {deleted_count} keys"
            )
            return deleted_count
        except Exception as e:
            redis_logger.error(f"Redis delete_pattern({pattern}) failed: {str(e)}")
            return 0

    # Lua script for atomic rate limiting: INCR + conditional EXPIRE + TTL
    # Returns: [count, ttl]
    _RATE_LIMIT_SCRIPT = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    local ttl = redis.call('TTL', KEYS[1])
    return {count, ttl}
    """

    @classmethod
    async def rate_limit_incr(
        cls, key: str, window_seconds: int = 60
    ) -> tuple[int, int] | None:
        """
        Atomically increment rate limit counter and get TTL in one round trip.

        Uses a Lua script to:
        1. Increment the counter (creates with value 1 if not exists)
        2. Set expiration only if this is the first request in the window
        3. Get the remaining TTL

        This is much faster than separate INCR + EXPIRE + TTL calls.

        Args:
            key: The rate limit key (e.g., "rate_limit:{workspace_id}").
            window_seconds: The rate limit window in seconds. Defaults to 60.

        Returns:
            Tuple of (count, ttl) or None if Redis is unavailable.
            - count: Current request count in the window
            - ttl: Seconds remaining until window resets
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis rate_limit_incr({key}) attempted but client not initialized"
            )
            return None

        try:
            result = await cls._client.eval(  # type: ignore[misc]
                cls._RATE_LIMIT_SCRIPT,
                1,  # number of keys
                key,  # KEYS[1]
                str(window_seconds),  # ARGV[1]
            )
            count, ttl = int(result[0]), int(result[1])
            redis_logger.debug(f"Redis rate_limit_incr({key}) count={count}, ttl={ttl}")
            return (count, ttl)
        except Exception as e:
            redis_logger.error(f"Redis rate_limit_incr({key}) failed: {str(e)}")
            return None

    @classmethod
    async def hset(
        cls, key: str, field: str, value: str, ttl: int | None = None
    ) -> bool:
        """
        Set a field in a hash.

        Args:
            key: The hash key.
            field: The field name.
            value: The value to store.
            ttl: Optional TTL in seconds (applies to entire hash key).

        Returns:
            bool: True if successful, False otherwise.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis hset({key}, {field}) attempted but client not initialized"
            )
            return False

        try:
            await cls._client.hset(key, field, value)  # type: ignore[misc]
            if ttl is not None:
                await cls._client.expire(key, ttl)
            redis_logger.debug(f"Redis hset({key}, {field}) successful")
            return True
        except Exception as e:
            redis_logger.error(f"Redis hset({key}, {field}) failed: {str(e)}")
            return False

    @classmethod
    async def hget(cls, key: str, field: str) -> str | None:
        """
        Get a field from a hash.

        Args:
            key: The hash key.
            field: The field name.

        Returns:
            The value as string if found, None otherwise.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis hget({key}, {field}) attempted but client not initialized"
            )
            return None

        try:
            value = await cls._client.hget(key, field)  # type: ignore[misc]
            if value is not None:
                return value.decode("utf-8") if isinstance(value, bytes) else value
            return None
        except Exception as e:
            redis_logger.error(f"Redis hget({key}, {field}) failed: {str(e)}")
            return None

    @classmethod
    async def hgetall(cls, key: str) -> dict[str, str] | None:
        """
        Get all fields from a hash.

        Args:
            key: The hash key.

        Returns:
            Dict of field -> value if found, None on error.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis hgetall({key}) attempted but client not initialized"
            )
            return None

        try:
            result = await cls._client.hgetall(key)  # type: ignore[misc]
            if result:
                return {
                    (k.decode("utf-8") if isinstance(k, bytes) else k): (
                        v.decode("utf-8") if isinstance(v, bytes) else v
                    )
                    for k, v in result.items()
                }
            return {}
        except Exception as e:
            redis_logger.error(f"Redis hgetall({key}) failed: {str(e)}")
            return None

    @classmethod
    async def sadd(cls, key: str, *members: str) -> int | None:
        """
        Add members to a set.

        Args:
            key: The set key.
            members: Values to add to the set.

        Returns:
            Number of elements added, or None on error.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis sadd({key}) attempted but client not initialized"
            )
            return None

        try:
            result = await cls._client.sadd(key, *members)  # type: ignore[misc]
            redis_logger.debug(f"Redis sadd({key}) added {result} members")
            return result
        except Exception as e:
            redis_logger.error(f"Redis sadd({key}) failed: {str(e)}")
            return None

    @classmethod
    async def smembers(cls, key: str) -> set[str] | None:
        """
        Get all members of a set.

        Args:
            key: The set key.

        Returns:
            Set of members, or None on error.
        """
        if cls._client is None:
            redis_logger.warning(
                f"Redis smembers({key}) attempted but client not initialized"
            )
            return None

        try:
            result = await cls._client.smembers(key)  # type: ignore[misc]
            return {m.decode("utf-8") if isinstance(m, bytes) else m for m in result}
        except Exception as e:
            redis_logger.error(f"Redis smembers({key}) failed: {str(e)}")
            return None


__all__ = ["RedisService"]
