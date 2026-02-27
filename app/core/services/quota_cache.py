"""
Quota Cache Service for O(1) cost lookups.

"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import app_logger
from app.core.enums import FeatureKey
from app.core.services.redis_service import RedisService

if TYPE_CHECKING:
    from app.core.db.models.quota import FeatureCostConfig, PlanPricingRule


class QuotaCacheBackend(ABC):
    """
    Abstract base class for quota cache backends.

    Implementations must provide methods for getting and setting
    feature costs and plan multipliers.
    """

    @abstractmethod
    async def get_feature_cost(self, feature_key: FeatureKey) -> Decimal | None:
        """Get cached feature cost."""
        pass

    @abstractmethod
    async def set_feature_cost(self, feature_key: FeatureKey, cost: Decimal) -> None:
        """Set feature cost in cache."""
        pass

    @abstractmethod
    async def delete_feature_cost(self, feature_key: FeatureKey) -> None:
        """Remove feature cost from cache."""
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
    async def get_plan_rate_day_limit(self, plan_id: UUID) -> int | None:
        """Get cached plan rate limit per day."""
        pass

    @abstractmethod
    async def set_plan_rate_day_limit(self, plan_id: UUID, rate_limit: int) -> None:
        """Set plan rate limit in cache."""
        pass

    @abstractmethod
    async def delete_plan_rate_day_limit(self, plan_id: UUID) -> None:
        """Remove plan rate limit from cache."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all cached data."""
        pass


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
        self._feature_costs: dict[str, Decimal] = {}
        self._plan_multipliers: dict[UUID, Decimal] = {}
        self._plan_credits: dict[UUID, Decimal] = {}
        self._plan_rate_limits: dict[UUID, int] = {}
        self._plan_rate_day_limit: dict[UUID, int] = {}

    async def get_feature_cost(self, feature_key: FeatureKey) -> Decimal | None:
        """Get cached feature cost."""
        return self._feature_costs.get(feature_key)

    async def set_feature_cost(self, feature_key: FeatureKey, cost: Decimal) -> None:
        """Set feature cost in cache."""
        self._feature_costs[feature_key] = cost

    async def delete_feature_cost(self, feature_key: FeatureKey) -> None:
        """Remove feature cost from cache."""
        self._feature_costs.pop(feature_key, None)

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

    async def get_plan_rate_day_limit(self, plan_id: UUID) -> int | None:
        """Get cached plan rate limit per minute."""
        return self._plan_rate_day_limit.get(plan_id)

    async def set_plan_rate_day_limit(self, plan_id: UUID, rate_limit: int) -> None:
        """Set plan rate limit in cache."""
        self._plan_rate_day_limit[plan_id] = rate_limit

    async def delete_plan_rate_day_limit(self, plan_id: UUID) -> None:
        """Remove plan rate limit from cache."""
        self._plan_rate_day_limit.pop(plan_id, None)

    async def clear(self) -> None:
        """Clear all cached data."""
        self._feature_costs.clear()
        self._plan_multipliers.clear()
        self._plan_credits.clear()
        self._plan_rate_limits.clear()
        self._plan_rate_day_limit.clear()


class RedisBackend(QuotaCacheBackend):
    """
    Redis-based quota cache backend.

    Suitable for distributed systems where multiple instances need
    to share cache state. Uses Redis GET/SET operations.
    """

    # Key prefixes for namespacing
    FEATURE_COST_PREFIX = "quota:feature_cost:"
    PLAN_MULTIPLIER_PREFIX = "quota:plan_multiplier:"
    PLAN_CREDITS_PREFIX = "quota:plan_credits:"
    PLAN_RATE_LIMIT_PREFIX = "quota:plan_rate_limit:"
    PLAN_RATE_DAY_LIMIT_PREFIX = "quota:plan_rate_day_limit:"

    async def get_feature_cost(self, feature_key: FeatureKey) -> Decimal | None:
        """Get cached feature cost from Redis."""
        key = f"{self.FEATURE_COST_PREFIX}{feature_key}"
        value = await RedisService.get(key)
        if value is not None:
            return Decimal(value)
        return None

    async def set_feature_cost(self, feature_key: FeatureKey, cost: Decimal) -> None:
        """Set feature cost in Redis (no TTL - permanent until updated)."""
        key = f"{self.FEATURE_COST_PREFIX}{feature_key}"
        await RedisService.set(key, str(cost))

    async def delete_feature_cost(self, feature_key: FeatureKey) -> None:
        """Remove feature cost from Redis."""
        key = f"{self.FEATURE_COST_PREFIX}{feature_key}"
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

    async def get_plan_rate_day_limit(self, plan_id: UUID) -> int | None:
        """Get cached plan rate limit from Redis."""
        key = f"{self.PLAN_RATE_DAY_LIMIT_PREFIX}{plan_id}"
        value = await RedisService.get(key)
        if value is not None:
            return int(value)
        return None

    async def set_plan_rate_day_limit(self, plan_id: UUID, rate_limit: int) -> None:
        """Set plan rate limit in Redis (no TTL - permanent until updated)."""
        key = f"{self.PLAN_RATE_DAY_LIMIT_PREFIX}{plan_id}"
        await RedisService.set(key, str(rate_limit))

    async def delete_plan_rate_day_limit(self, plan_id: UUID) -> None:
        """Remove plan rate limit from Redis."""
        key = f"{self.PLAN_RATE_DAY_LIMIT_PREFIX}{plan_id}"
        await RedisService.delete(key)

    async def clear(self) -> None:
        """
        Clear all quota cache data from Redis.

        Note: This uses SCAN to find keys by pattern, which is safe
        but may be slow for large datasets.
        """
        await RedisService.delete_pattern(f"{self.FEATURE_COST_PREFIX}*")
        await RedisService.delete_pattern(f"{self.PLAN_MULTIPLIER_PREFIX}*")
        await RedisService.delete_pattern(f"{self.PLAN_CREDITS_PREFIX}*")
        await RedisService.delete_pattern(f"{self.PLAN_RATE_LIMIT_PREFIX}*")
        await RedisService.delete_pattern(f"{self.PLAN_RATE_DAY_LIMIT_PREFIX}*")


class QuotaCacheService:
    """
    Singleton service for O(1) cost lookups.

    Maintains cached mappings for:
    - feature → internal_cost_credits
    - plan_id → multiplier
    - plan_id → credits_allocation
    - plan_id → rate_limit_per_minute
    - plan_id → rate_limit_per_day

    The cache is populated at startup and kept in sync with the database
    via SQLAlchemy event listeners.

    Supports both memory and Redis backends (configurable).
    """

    _initialized: bool = False
    _backend: QuotaCacheBackend | None = None
    _events_registered: bool = False

    # Default values when no config exists
    DEFAULT_FEATURE_COST: Decimal = Decimal("6.0")
    DEFAULT_PLAN_MULTIPLIER: Decimal = Decimal("3.0")
    DEFAULT_PLAN_CREDITS: Decimal = Decimal("5000.0")
    DEFAULT_RATE_LIMIT_PER_MINUTE: int = 20
    DEFAULT_RATE_LIMIT_PER_DAY: int = 20

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

        if backend == "redis":
            cls._backend = RedisBackend()
        else:
            cls._backend = MemoryBackend()

        # Import here to avoid circular imports
        from sqlalchemy import select

        from app.core.db.models.quota import (
            FeatureCostConfig,
            PlanPricingRule,
        )

        result = await session.execute(
            select(FeatureCostConfig).where(
                FeatureCostConfig.is_deleted == False  # noqa: E712
            )
        )
        feature_configs = result.scalars().all()
        for config in feature_configs:
            await cls._backend.set_feature_cost(
                config.feature_key, config.internal_cost_credits
            )
        app_logger.info(f"Loaded {len(feature_configs)} feature cost configs.")

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
                rule.plan_id,
                rule.rate_limit_per_minute or cls.DEFAULT_RATE_LIMIT_PER_MINUTE,
            )
            await cls._backend.set_plan_rate_day_limit(
                rule.plan_id, rule.rate_limit_per_day or cls.DEFAULT_RATE_LIMIT_PER_DAY
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
        from app.core.db.models.quota import (
            FeatureCostConfig,
            PlanPricingRule,
        )

        # Feature cost events
        event.listen(FeatureCostConfig, "after_insert", cls._on_feature_change)
        event.listen(FeatureCostConfig, "after_update", cls._on_feature_change)
        event.listen(FeatureCostConfig, "after_delete", cls._on_feature_delete)

        # Plan pricing rule events
        event.listen(PlanPricingRule, "after_insert", cls._on_pricing_change)
        event.listen(PlanPricingRule, "after_update", cls._on_pricing_change)
        event.listen(PlanPricingRule, "after_delete", cls._on_pricing_delete)

        app_logger.debug("SQLAlchemy event listeners registered for quota cache.")


    @classmethod
    def _on_feature_change(
        cls, mapper, connection, target: "FeatureCostConfig"
    ) -> None:
        """Handle feature config insert/update."""
        import asyncio

        backend = cls._backend
        if backend is None:
            return

        async def _update():
            if target.is_deleted:
                await backend.delete_feature_cost(target.feature_key)
                app_logger.debug(
                    f"Cache: Removed feature cost for '{target.feature_key}'"
                )
            else:
                await backend.set_feature_cost(
                    target.feature_key, target.internal_cost_credits
                )
                app_logger.debug(
                    f"Cache: Updated feature cost for '{target.feature_key}'"
                )

        # Run async operation in the event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_update())
        except RuntimeError:
            # No running loop, run synchronously
            asyncio.run(_update())

    @classmethod
    def _on_feature_delete(
        cls, mapper, connection, target: "FeatureCostConfig"
    ) -> None:
        """Handle feature config hard delete."""
        import asyncio

        backend = cls._backend
        if backend is None:
            return

        async def _delete():
            await backend.delete_feature_cost(target.feature_key)
            app_logger.debug(f"Cache: Removed feature cost for '{target.feature_key}'")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_delete())
        except RuntimeError:
            asyncio.run(_delete())


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
                await backend.delete_plan_rate_day_limit(target.plan_id)
                app_logger.debug(
                    f"Cache: Removed pricing rule for plan '{target.plan_id}'"
                )
            else:
                await backend.set_plan_multiplier(target.plan_id, target.multiplier)
                await backend.set_plan_credits_allocation(
                    target.plan_id, target.credits_allocation
                )
                await backend.set_plan_rate_limit(
                    target.plan_id,
                    target.rate_limit_per_minute or cls.DEFAULT_RATE_LIMIT_PER_MINUTE,
                )
                await backend.set_plan_rate_day_limit(
                    target.plan_id,
                    target.rate_limit_per_day or cls.DEFAULT_RATE_LIMIT_PER_DAY,
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
            await backend.delete_plan_rate_day_limit(target.plan_id)
            app_logger.debug(f"Cache: Removed pricing rule for plan '{target.plan_id}'")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_delete())
        except RuntimeError:
            asyncio.run(_delete())


    @classmethod
    async def get_feature_cost(cls, feature_key: FeatureKey) -> Decimal:
        """
        Get the internal credit cost for an feature.

        Args:
            feature: The API feature path (will be normalized to lowercase).

        Returns:
            The internal credit cost, or DEFAULT_FEATURE_COST if not configured.
        """
        if cls._backend is None:
            return cls.DEFAULT_FEATURE_COST
        cost = await cls._backend.get_feature_cost(feature_key)
        return cost if cost is not None else cls.DEFAULT_FEATURE_COST

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
            from app.core.db.crud.quota import plan_pricing_rule_db

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
    async def get_plan_rate_day_limit(cls, plan_id: UUID | None) -> int:
        """
        Get the rate limit per day for a plan.

        Args:
            plan_id: The plan UUID or None.

        Returns:
            The rate limit per day, or DEFAULT_RATE_LIMIT_PER_DAY if not configured.
        """
        if cls._backend is None or plan_id is None:
            return cls.DEFAULT_RATE_LIMIT_PER_DAY
        rate_limit = await cls._backend.get_plan_rate_day_limit(plan_id)
        return rate_limit if rate_limit is not None else cls.DEFAULT_RATE_LIMIT_PER_DAY

    @classmethod
    async def calculate_billable_cost(
        cls, feature_key: FeatureKey, plan_id: UUID | None
    ) -> Decimal:
        """
        Calculate the billable cost for an feature call.

        Formula: internal_cost_credits * multiplier

        Args:
            feature: The API feature path.
            plan_id: The plan UUID or None.

        Returns:
            The billable cost in credits.
        """
        base_cost = await cls.get_feature_cost(feature_key)
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


__all__ = ["QuotaCacheService", "QuotaCacheBackend", "MemoryBackend", "RedisBackend"]

