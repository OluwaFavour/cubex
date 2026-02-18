"""
Quota Cache Service for O(1) cost lookups.

This module provides caching for endpoint costs and plan pricing
multipliers with support for both in-memory and Redis backends.
The cache is populated at startup and updated via SQLAlchemy
event listeners when the underlying tables are modified.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import app_logger
from app.core.services.redis_service import RedisService

if TYPE_CHECKING:
    from app.apps.cubex_api.db.models.quota import EndpointCostConfig, PlanPricingRule


# =============================================================================
# Backend Abstract Base Class
# =============================================================================


class QuotaCacheBackend(ABC):
    """
    Abstract base class for quota cache backends.

    Implementations must provide methods for getting and setting
    endpoint costs and plan multipliers.
    """

    @abstractmethod
    async def get_endpoint_cost(self, endpoint: str) -> Decimal | None:
        """Get cached endpoint cost."""
        pass

    @abstractmethod
    async def set_endpoint_cost(self, endpoint: str, cost: Decimal) -> None:
        """Set endpoint cost in cache."""
        pass

    @abstractmethod
    async def delete_endpoint_cost(self, endpoint: str) -> None:
        """Remove endpoint cost from cache."""
        pass

    @abstractmethod
    async def get_plan_multiplier(self, plan_id: UUID) -> Decimal | None:
        """Get cached plan multiplier."""
        pass

    @abstractmethod
    async def set_plan_multiplier(self, plan_id: UUID, multiplier: Decimal) -> None:
        """Set plan multiplier in cache."""
        pass

    @abstractmethod
    async def delete_plan_multiplier(self, plan_id: UUID) -> None:
        """Remove plan multiplier from cache."""
        pass

    @abstractmethod
    async def get_plan_credits_allocation(self, plan_id: UUID) -> Decimal | None:
        """Get cached plan credits allocation."""
        pass

    @abstractmethod
    async def set_plan_credits_allocation(
        self, plan_id: UUID, credits: Decimal
    ) -> None:
        """Set plan credits allocation in cache."""
        pass

    @abstractmethod
    async def delete_plan_credits_allocation(self, plan_id: UUID) -> None:
        """Remove plan credits allocation from cache."""
        pass

    @abstractmethod
    async def get_plan_rate_limit(self, plan_id: UUID) -> int | None:
        """Get cached plan rate limit per minute."""
        pass

    @abstractmethod
    async def set_plan_rate_limit(self, plan_id: UUID, rate_limit: int) -> None:
        """Set plan rate limit in cache."""
        pass

    @abstractmethod
    async def delete_plan_rate_limit(self, plan_id: UUID) -> None:
        """Remove plan rate limit from cache."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all cached data."""
        pass


# =============================================================================
# Memory Backend
# =============================================================================


class MemoryBackend(QuotaCacheBackend):
    """
    In-memory quota cache backend using dictionaries.

    Suitable for single-instance deployments or development.
    Data is lost on application restart.

    Note:
        Not suitable for multi-process or multi-instance deployments.
    """

    def __init__(self) -> None:
        """Initialize the memory backend with empty stores."""
        self._endpoint_costs: dict[str, Decimal] = {}
        self._plan_multipliers: dict[UUID, Decimal] = {}
        self._plan_credits: dict[UUID, Decimal] = {}
        self._plan_rate_limits: dict[UUID, int] = {}

    async def get_endpoint_cost(self, endpoint: str) -> Decimal | None:
        """Get cached endpoint cost."""
        return self._endpoint_costs.get(endpoint)

    async def set_endpoint_cost(self, endpoint: str, cost: Decimal) -> None:
        """Set endpoint cost in cache."""
        self._endpoint_costs[endpoint] = cost

    async def delete_endpoint_cost(self, endpoint: str) -> None:
        """Remove endpoint cost from cache."""
        self._endpoint_costs.pop(endpoint, None)

    async def get_plan_multiplier(self, plan_id: UUID) -> Decimal | None:
        """Get cached plan multiplier."""
        return self._plan_multipliers.get(plan_id)

    async def set_plan_multiplier(self, plan_id: UUID, multiplier: Decimal) -> None:
        """Set plan multiplier in cache."""
        self._plan_multipliers[plan_id] = multiplier

    async def delete_plan_multiplier(self, plan_id: UUID) -> None:
        """Remove plan multiplier from cache."""
        self._plan_multipliers.pop(plan_id, None)

    async def get_plan_credits_allocation(self, plan_id: UUID) -> Decimal | None:
        """Get cached plan credits allocation."""
        return self._plan_credits.get(plan_id)

    async def set_plan_credits_allocation(
        self, plan_id: UUID, credits: Decimal
    ) -> None:
        """Set plan credits allocation in cache."""
        self._plan_credits[plan_id] = credits

    async def delete_plan_credits_allocation(self, plan_id: UUID) -> None:
        """Remove plan credits allocation from cache."""
        self._plan_credits.pop(plan_id, None)

    async def get_plan_rate_limit(self, plan_id: UUID) -> int | None:
        """Get cached plan rate limit per minute."""
        return self._plan_rate_limits.get(plan_id)

    async def set_plan_rate_limit(self, plan_id: UUID, rate_limit: int) -> None:
        """Set plan rate limit in cache."""
        self._plan_rate_limits[plan_id] = rate_limit

    async def delete_plan_rate_limit(self, plan_id: UUID) -> None:
        """Remove plan rate limit from cache."""
        self._plan_rate_limits.pop(plan_id, None)

    async def clear(self) -> None:
        """Clear all cached data."""
        self._endpoint_costs.clear()
        self._plan_multipliers.clear()
        self._plan_credits.clear()
        self._plan_rate_limits.clear()


# =============================================================================
# Redis Backend
# =============================================================================


class RedisBackend(QuotaCacheBackend):
    """
    Redis-based quota cache backend.

    Suitable for distributed systems where multiple instances need
    to share cache state. Uses Redis GET/SET operations.
    """

    # Key prefixes for namespacing
    ENDPOINT_COST_PREFIX = "quota:endpoint_cost:"
    PLAN_MULTIPLIER_PREFIX = "quota:plan_multiplier:"
    PLAN_CREDITS_PREFIX = "quota:plan_credits:"
    PLAN_RATE_LIMIT_PREFIX = "quota:plan_rate_limit:"

    async def get_endpoint_cost(self, endpoint: str) -> Decimal | None:
        """Get cached endpoint cost from Redis."""
        key = f"{self.ENDPOINT_COST_PREFIX}{endpoint}"
        value = await RedisService.get(key)
        if value is not None:
            return Decimal(value)
        return None

    async def set_endpoint_cost(self, endpoint: str, cost: Decimal) -> None:
        """Set endpoint cost in Redis (no TTL - permanent until updated)."""
        key = f"{self.ENDPOINT_COST_PREFIX}{endpoint}"
        await RedisService.set(key, str(cost))

    async def delete_endpoint_cost(self, endpoint: str) -> None:
        """Remove endpoint cost from Redis."""
        key = f"{self.ENDPOINT_COST_PREFIX}{endpoint}"
        await RedisService.delete(key)

    async def get_plan_multiplier(self, plan_id: UUID) -> Decimal | None:
        """Get cached plan multiplier from Redis."""
        key = f"{self.PLAN_MULTIPLIER_PREFIX}{plan_id}"
        value = await RedisService.get(key)
        if value is not None:
            return Decimal(value)
        return None

    async def set_plan_multiplier(self, plan_id: UUID, multiplier: Decimal) -> None:
        """Set plan multiplier in Redis (no TTL - permanent until updated)."""
        key = f"{self.PLAN_MULTIPLIER_PREFIX}{plan_id}"
        await RedisService.set(key, str(multiplier))

    async def delete_plan_multiplier(self, plan_id: UUID) -> None:
        """Remove plan multiplier from Redis."""
        key = f"{self.PLAN_MULTIPLIER_PREFIX}{plan_id}"
        await RedisService.delete(key)

    async def get_plan_credits_allocation(self, plan_id: UUID) -> Decimal | None:
        """Get cached plan credits allocation from Redis."""
        key = f"{self.PLAN_CREDITS_PREFIX}{plan_id}"
        value = await RedisService.get(key)
        if value is not None:
            return Decimal(value)
        return None

    async def set_plan_credits_allocation(
        self, plan_id: UUID, credits: Decimal
    ) -> None:
        """Set plan credits allocation in Redis (no TTL - permanent until updated)."""
        key = f"{self.PLAN_CREDITS_PREFIX}{plan_id}"
        await RedisService.set(key, str(credits))

    async def delete_plan_credits_allocation(self, plan_id: UUID) -> None:
        """Remove plan credits allocation from Redis."""
        key = f"{self.PLAN_CREDITS_PREFIX}{plan_id}"
        await RedisService.delete(key)

    async def get_plan_rate_limit(self, plan_id: UUID) -> int | None:
        """Get cached plan rate limit from Redis."""
        key = f"{self.PLAN_RATE_LIMIT_PREFIX}{plan_id}"
        value = await RedisService.get(key)
        if value is not None:
            return int(value)
        return None

    async def set_plan_rate_limit(self, plan_id: UUID, rate_limit: int) -> None:
        """Set plan rate limit in Redis (no TTL - permanent until updated)."""
        key = f"{self.PLAN_RATE_LIMIT_PREFIX}{plan_id}"
        await RedisService.set(key, str(rate_limit))

    async def delete_plan_rate_limit(self, plan_id: UUID) -> None:
        """Remove plan rate limit from Redis."""
        key = f"{self.PLAN_RATE_LIMIT_PREFIX}{plan_id}"
        await RedisService.delete(key)

    async def clear(self) -> None:
        """
        Clear all quota cache data from Redis.

        Note: This uses SCAN to find keys by pattern, which is safe
        but may be slow for large datasets.
        """
        # Delete all endpoint cost keys
        await RedisService.delete_pattern(f"{self.ENDPOINT_COST_PREFIX}*")
        # Delete all plan multiplier keys
        await RedisService.delete_pattern(f"{self.PLAN_MULTIPLIER_PREFIX}*")
        # Delete all plan credits keys
        await RedisService.delete_pattern(f"{self.PLAN_CREDITS_PREFIX}*")
        # Delete all plan rate limit keys
        await RedisService.delete_pattern(f"{self.PLAN_RATE_LIMIT_PREFIX}*")


# =============================================================================
# Quota Cache Service
# =============================================================================


class QuotaCacheService:
    """
    Singleton service for O(1) cost lookups.

    Maintains cached mappings for:
    - endpoint → internal_cost_credits
    - plan_id → multiplier
    - plan_id → credits_allocation
    - plan_id → rate_limit_per_minute

    The cache is populated at startup and kept in sync with the database
    via SQLAlchemy event listeners.

    Supports both memory and Redis backends (configurable).
    """

    _initialized: bool = False
    _backend: QuotaCacheBackend | None = None
    _events_registered: bool = False

    # Default values when no config exists
    DEFAULT_ENDPOINT_COST: Decimal = Decimal("6.0")
    DEFAULT_PLAN_MULTIPLIER: Decimal = Decimal("3.0")
    DEFAULT_PLAN_CREDITS: Decimal = Decimal("5000.0")
    DEFAULT_RATE_LIMIT_PER_MINUTE: int = 20

    @classmethod
    async def init(
        cls,
        session: AsyncSession,
        backend: Literal["memory", "redis"] = "memory",
    ) -> None:
        """
        Initialize the cache by loading all configs from database.

        Args:
            session: SQLAlchemy async session for database queries.
            backend: Cache backend to use ("memory" or "redis").
        """
        if cls._initialized:
            app_logger.debug("QuotaCacheService already initialized, skipping.")
            return

        app_logger.info(f"Initializing QuotaCacheService with {backend} backend...")

        # Initialize backend
        if backend == "redis":
            cls._backend = RedisBackend()
        else:
            cls._backend = MemoryBackend()

        # Import here to avoid circular imports
        from sqlalchemy import select

        from app.apps.cubex_api.db.models.quota import (
            EndpointCostConfig,
            PlanPricingRule,
        )

        # Load endpoint costs
        result = await session.execute(
            select(EndpointCostConfig).where(
                EndpointCostConfig.is_deleted == False  # noqa: E712
            )
        )
        endpoint_configs = result.scalars().all()
        for config in endpoint_configs:
            await cls._backend.set_endpoint_cost(
                config.endpoint, config.internal_cost_credits
            )
        app_logger.info(f"Loaded {len(endpoint_configs)} endpoint cost configs.")

        # Load plan pricing rules (multiplier, credits, rate limit)
        result = await session.execute(
            select(PlanPricingRule).where(
                PlanPricingRule.is_deleted == False  # noqa: E712
            )
        )
        pricing_rules = result.scalars().all()
        for rule in pricing_rules:
            await cls._backend.set_plan_multiplier(rule.plan_id, rule.multiplier)
            await cls._backend.set_plan_credits_allocation(
                rule.plan_id, rule.credits_allocation
            )
            await cls._backend.set_plan_rate_limit(
                rule.plan_id, rule.rate_limit_per_minute
            )
        app_logger.info(f"Loaded {len(pricing_rules)} plan pricing rules.")

        # Register event listeners (only once)
        if not cls._events_registered:
            cls._register_event_listeners()
            cls._events_registered = True

        cls._initialized = True
        app_logger.info("QuotaCacheService initialized successfully.")

    @classmethod
    def _register_event_listeners(cls) -> None:
        """Register SQLAlchemy event listeners for cache invalidation."""
        from app.apps.cubex_api.db.models.quota import (
            EndpointCostConfig,
            PlanPricingRule,
        )

        # Endpoint cost events
        event.listen(EndpointCostConfig, "after_insert", cls._on_endpoint_change)
        event.listen(EndpointCostConfig, "after_update", cls._on_endpoint_change)
        event.listen(EndpointCostConfig, "after_delete", cls._on_endpoint_delete)

        # Plan pricing rule events
        event.listen(PlanPricingRule, "after_insert", cls._on_pricing_change)
        event.listen(PlanPricingRule, "after_update", cls._on_pricing_change)
        event.listen(PlanPricingRule, "after_delete", cls._on_pricing_delete)

        app_logger.debug("SQLAlchemy event listeners registered for quota cache.")

    # =========================================================================
    # Endpoint Cost Event Handlers
    # =========================================================================

    @classmethod
    def _on_endpoint_change(
        cls, mapper, connection, target: "EndpointCostConfig"
    ) -> None:
        """Handle endpoint config insert/update."""
        import asyncio

        backend = cls._backend
        if backend is None:
            return

        async def _update():
            if target.is_deleted:
                await backend.delete_endpoint_cost(target.endpoint)
                app_logger.debug(
                    f"Cache: Removed endpoint cost for '{target.endpoint}'"
                )
            else:
                await backend.set_endpoint_cost(
                    target.endpoint, target.internal_cost_credits
                )
                app_logger.debug(
                    f"Cache: Updated endpoint cost for '{target.endpoint}'"
                )

        # Run async operation in the event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_update())
        except RuntimeError:
            # No running loop, run synchronously
            asyncio.run(_update())

    @classmethod
    def _on_endpoint_delete(
        cls, mapper, connection, target: "EndpointCostConfig"
    ) -> None:
        """Handle endpoint config hard delete."""
        import asyncio

        backend = cls._backend
        if backend is None:
            return

        async def _delete():
            await backend.delete_endpoint_cost(target.endpoint)
            app_logger.debug(f"Cache: Removed endpoint cost for '{target.endpoint}'")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_delete())
        except RuntimeError:
            asyncio.run(_delete())

    # =========================================================================
    # Plan Pricing Rule Event Handlers
    # =========================================================================

    @classmethod
    def _on_pricing_change(cls, mapper, connection, target: "PlanPricingRule") -> None:
        """Handle pricing rule insert/update."""
        import asyncio

        backend = cls._backend
        if backend is None:
            return

        async def _update():
            if target.is_deleted:
                await backend.delete_plan_multiplier(target.plan_id)
                await backend.delete_plan_credits_allocation(target.plan_id)
                await backend.delete_plan_rate_limit(target.plan_id)
                app_logger.debug(
                    f"Cache: Removed pricing rule for plan '{target.plan_id}'"
                )
            else:
                await backend.set_plan_multiplier(target.plan_id, target.multiplier)
                await backend.set_plan_credits_allocation(
                    target.plan_id, target.credits_allocation
                )
                await backend.set_plan_rate_limit(
                    target.plan_id, target.rate_limit_per_minute
                )
                app_logger.debug(
                    f"Cache: Updated pricing rule for plan '{target.plan_id}'"
                )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_update())
        except RuntimeError:
            asyncio.run(_update())

    @classmethod
    def _on_pricing_delete(cls, mapper, connection, target: "PlanPricingRule") -> None:
        """Handle pricing rule hard delete."""
        import asyncio

        backend = cls._backend
        if backend is None:
            return

        async def _delete():
            await backend.delete_plan_multiplier(target.plan_id)
            await backend.delete_plan_credits_allocation(target.plan_id)
            await backend.delete_plan_rate_limit(target.plan_id)
            app_logger.debug(f"Cache: Removed pricing rule for plan '{target.plan_id}'")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_delete())
        except RuntimeError:
            asyncio.run(_delete())

    # =========================================================================
    # Public API - O(1) Lookups
    # =========================================================================

    @classmethod
    async def get_endpoint_cost(cls, endpoint: str) -> Decimal:
        """
        Get the internal credit cost for an endpoint.

        Args:
            endpoint: The API endpoint path (will be normalized to lowercase).

        Returns:
            The internal credit cost, or DEFAULT_ENDPOINT_COST if not configured.
        """
        if cls._backend is None:
            return cls.DEFAULT_ENDPOINT_COST
        # Normalize endpoint to lowercase for consistent lookups
        normalized_endpoint = endpoint.lower()
        cost = await cls._backend.get_endpoint_cost(normalized_endpoint)
        return cost if cost is not None else cls.DEFAULT_ENDPOINT_COST

    @classmethod
    async def get_plan_multiplier(cls, plan_id: UUID | None) -> Decimal:
        """
        Get the pricing multiplier for a plan.

        Args:
            plan_id: The plan UUID or None.

        Returns:
            The pricing multiplier, or DEFAULT_PLAN_MULTIPLIER if not configured.
        """
        if cls._backend is None or plan_id is None:
            return cls.DEFAULT_PLAN_MULTIPLIER
        multiplier = await cls._backend.get_plan_multiplier(plan_id)
        return multiplier if multiplier is not None else cls.DEFAULT_PLAN_MULTIPLIER

    @classmethod
    async def get_plan_credits_allocation(cls, plan_id: UUID | None) -> Decimal:
        """
        Get the credits allocation for a plan.

        Args:
            plan_id: The plan UUID or None.

        Returns:
            The credits allocation, or DEFAULT_PLAN_CREDITS if not configured.
        """
        if cls._backend is None or plan_id is None:
            return cls.DEFAULT_PLAN_CREDITS
        credits = await cls._backend.get_plan_credits_allocation(plan_id)
        return credits if credits is not None else cls.DEFAULT_PLAN_CREDITS

    @classmethod
    async def get_plan_credits_allocation_with_fallback(
        cls,
        session: AsyncSession,
        plan_id: UUID | None,
    ) -> Decimal:
        """
        Get the credits allocation for a plan, with DB fallback if cache unavailable.

        Tries cache first. If cache miss or cache unavailable, falls back to
        querying the database directly via PlanPricingRuleDB.

        Args:
            session: Database session for fallback query.
            plan_id: The plan UUID or None.

        Returns:
            The credits allocation, or DEFAULT_PLAN_CREDITS if not configured.
        """
        if plan_id is None:
            return cls.DEFAULT_PLAN_CREDITS

        # Try cache first
        try:
            if cls._backend is not None:
                credits = await cls._backend.get_plan_credits_allocation(plan_id)
                if credits is not None:
                    return credits
        except Exception as e:
            app_logger.warning(
                f"Cache lookup failed for plan credits allocation {plan_id}, "
                f"falling back to DB: {e}"
            )

        # Fallback to database query
        try:
            from app.apps.cubex_api.db.crud.quota import plan_pricing_rule_db

            rule = await plan_pricing_rule_db.get_by_plan_id(session, plan_id)
            if rule is not None:
                # Update cache for next time (best effort)
                if cls._backend is not None:
                    try:
                        await cls._backend.set_plan_credits_allocation(
                            plan_id, rule.credits_allocation
                        )
                    except Exception:
                        pass  # Cache update is best-effort
                return rule.credits_allocation
        except Exception as e:
            app_logger.warning(
                f"DB fallback failed for plan credits allocation {plan_id}: {e}"
            )

        return cls.DEFAULT_PLAN_CREDITS

    @classmethod
    async def get_plan_rate_limit(cls, plan_id: UUID | None) -> int:
        """
        Get the rate limit per minute for a plan.

        Args:
            plan_id: The plan UUID or None.

        Returns:
            The rate limit per minute, or DEFAULT_RATE_LIMIT_PER_MINUTE if not configured.
        """
        if cls._backend is None or plan_id is None:
            return cls.DEFAULT_RATE_LIMIT_PER_MINUTE
        rate_limit = await cls._backend.get_plan_rate_limit(plan_id)
        return (
            rate_limit if rate_limit is not None else cls.DEFAULT_RATE_LIMIT_PER_MINUTE
        )

    @classmethod
    async def calculate_billable_cost(
        cls, endpoint: str, plan_id: UUID | None
    ) -> Decimal:
        """
        Calculate the billable cost for an endpoint call.

        Formula: internal_cost_credits * multiplier

        Args:
            endpoint: The API endpoint path.
            plan_id: The plan UUID or None.

        Returns:
            The billable cost in credits.
        """
        base_cost = await cls.get_endpoint_cost(endpoint)
        multiplier = await cls.get_plan_multiplier(plan_id)
        return base_cost * multiplier

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if the cache has been initialized."""
        return cls._initialized

    @classmethod
    async def clear(cls) -> None:
        """
        Clear the cache.

        Useful for testing or forced refresh scenarios.
        """
        if cls._backend:
            await cls._backend.clear()
        cls._initialized = False
        app_logger.info("QuotaCacheService cache cleared.")

    @classmethod
    async def refresh(cls, session: AsyncSession) -> None:
        """
        Force refresh the cache from database.

        Args:
            session: SQLAlchemy async session for database queries.
        """
        backend_type: Literal["memory", "redis"] = "memory"
        if isinstance(cls._backend, RedisBackend):
            backend_type = "redis"

        await cls.clear()
        cls._initialized = False
        await cls.init(session, backend=backend_type)

    # =========================================================================
    # API Key Caching (for hot path optimization)
    # =========================================================================

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


__all__ = ["QuotaCacheService", "QuotaCacheBackend", "MemoryBackend", "RedisBackend"]
