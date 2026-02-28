from app.core.services import QuotaCacheService, RedisService


class APIQuotaCacheService(QuotaCacheService):

    # Cache key prefix and TTL for API keys
    API_KEY_CACHE_PREFIX = "api_key:"
    API_KEY_CACHE_TTL = 15  # 15 seconds (short TTL to limit stale auth window)

    @classmethod
    async def get_cached_api_key_info(cls, key_hash: str) -> dict[str, str] | None:
        """
        Get cached API key information from Redis.

        Args:
            key_hash: The HMAC-SHA256 hash of the API key.

        Returns:
            Dict with cached key info (id, workspace_id, is_test_key, plan_id),
            or None if not cached.
        """
        cache_key = f"{cls.API_KEY_CACHE_PREFIX}{key_hash}"
        cached = await RedisService.hgetall(cache_key)
        if cached and cached.get("id"):
            return cached
        return None

    @classmethod
    async def cache_api_key_info(
        cls,
        key_hash: str,
        api_key_id: str,
        workspace_id: str,
        is_test_key: bool,
        plan_id: str | None,
    ) -> None:
        """
        Cache API key information in Redis with TTL.

        Args:
            key_hash: The HMAC-SHA256 hash of the API key.
            api_key_id: The API key's UUID as string.
            workspace_id: The workspace UUID as string.
            is_test_key: Whether this is a test key.
            plan_id: The plan UUID as string, or None.
        """
        cache_key = f"{cls.API_KEY_CACHE_PREFIX}{key_hash}"
        # Store as hash for structured access
        await RedisService.hset(cache_key, "id", api_key_id, ttl=cls.API_KEY_CACHE_TTL)
        await RedisService.hset(cache_key, "workspace_id", workspace_id)
        await RedisService.hset(cache_key, "is_test_key", "1" if is_test_key else "0")
        await RedisService.hset(cache_key, "plan_id", plan_id or "")

    @classmethod
    async def invalidate_api_key_cache(cls, key_hash: str) -> None:
        """
        Invalidate cached API key information.

        Called when an API key is revoked, deleted, or modified.

        Args:
            key_hash: The HMAC-SHA256 hash of the API key.
        """
        cache_key = f"{cls.API_KEY_CACHE_PREFIX}{key_hash}"
        await RedisService.delete(cache_key)


api_quota_cache_service = APIQuotaCacheService()
