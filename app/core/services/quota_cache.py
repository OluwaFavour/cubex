"""
Quota Cache Service for O(1) cost lookups.

"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import app_logger
from app.core.enums import FeatureKey
from app.core.services.base import SingletonService
from app.core.services.redis_service import RedisService

if TYPE_CHECKING:
    from app.core.db.models.quota import FeatureCostConfig, PlanPricingRule


# ---------------------------------------------------------------------------
# Public dataclasses returned by cache getters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanConfig:
    """Cached plan pricing configuration.

    Represents one PlanPricingRule row.  A ``None`` return from
    ``get_plan_config`` means no row exists — the caller should deny
    the request (HTTP 500).

    Attributes:
        multiplier: Pricing multiplier for billable cost calculation.
        credits_allocation: Total credits per billing period.
        rate_limit_per_minute: Max requests/minute, or ``None`` if unlimited.
        rate_limit_per_day: Max requests/day, or ``None`` if unlimited.
    """

    multiplier: Decimal
    credits_allocation: Decimal
    rate_limit_per_minute: int | None
    rate_limit_per_day: int | None


@dataclass(frozen=True)
class FeatureConfig:
    """Cached feature cost configuration.

    Represents one FeatureCostConfig row.  A ``None`` return from
    ``get_feature_config`` means no row exists — the caller should deny
    the request (HTTP 500).

    Attributes:
        internal_cost_credits: Base credit cost for one call to this feature.
    """

    internal_cost_credits: Decimal


# Sentinel stored in cache backends for "rate limit is intentionally unlimited".
# The backends only store ``int``; ``None`` means "not cached".
_UNLIMITED: int = -1


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
        """Set plan rate limit per day in cache."""
        pass

    @abstractmethod
    async def delete_plan_rate_day_limit(self, plan_id: UUID) -> None:
        """Remove plan rate limit per day from cache."""
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
        """Get cached plan rate limit per day."""
        return self._plan_rate_day_limit.get(plan_id)

    async def set_plan_rate_day_limit(self, plan_id: UUID, rate_limit: int) -> None:
        """Set plan rate limit per day in cache."""
        self._plan_rate_day_limit[plan_id] = rate_limit

    async def delete_plan_rate_day_limit(self, plan_id: UUID) -> None:
        """Remove plan rate limit per day from cache."""
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
        """Get cached plan rate limit per day from Redis."""
        key = f"{self.PLAN_RATE_DAY_LIMIT_PREFIX}{plan_id}"
        value = await RedisService.get(key)
        if value is not None:
            return int(value)
        return None

    async def set_plan_rate_day_limit(self, plan_id: UUID, rate_limit: int) -> None:
        """Set plan rate limit per day in Redis (no TTL - permanent until updated)."""
        key = f"{self.PLAN_RATE_DAY_LIMIT_PREFIX}{plan_id}"
        await RedisService.set(key, str(rate_limit))

    async def delete_plan_rate_day_limit(self, plan_id: UUID) -> None:
        """Remove plan rate limit per day from Redis."""
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


class QuotaCacheService(SingletonService):
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

    _backend: QuotaCacheBackend | None = None
    _events_registered: bool = False

    @classmethod
    def _reset(cls) -> None:
        """Reset all singleton state — intended for test teardown only."""
        super()._reset()
        cls._backend = None
        cls._events_registered = False

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
                (
                    rule.rate_limit_per_minute
                    if rule.rate_limit_per_minute is not None
                    else _UNLIMITED
                ),
            )
            await cls._backend.set_plan_rate_day_limit(
                rule.plan_id,
                (
                    rule.rate_limit_per_day
                    if rule.rate_limit_per_day is not None
                    else _UNLIMITED
                ),
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
                    (
                        target.rate_limit_per_minute
                        if target.rate_limit_per_minute is not None
                        else _UNLIMITED
                    ),
                )
                await backend.set_plan_rate_day_limit(
                    target.plan_id,
                    (
                        target.rate_limit_per_day
                        if target.rate_limit_per_day is not None
                        else _UNLIMITED
                    ),
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

    # ------------------------------------------------------------------
    # Public getters  (cache → DB → None)
    # ------------------------------------------------------------------

    @classmethod
    async def get_plan_config(
        cls,
        session: AsyncSession,
        plan_id: UUID | None,
    ) -> PlanConfig | None:
        """
        Get the full pricing configuration for a plan.

        Lookup order: cache → database → ``None``.

        Args:
            session: Database session (used on cache miss).
            plan_id: The plan UUID, or ``None``.

        Returns:
            A :class:`PlanConfig` if a row exists, otherwise ``None``
            (meaning the caller should deny the request).
        """
        if plan_id is None:
            return None

        # --- 1. Try cache ---------------------------------------------------
        if cls._backend is not None:
            try:
                multiplier = await cls._backend.get_plan_multiplier(plan_id)
                credits = await cls._backend.get_plan_credits_allocation(plan_id)
                rate_min = await cls._backend.get_plan_rate_limit(plan_id)
                rate_day = await cls._backend.get_plan_rate_day_limit(plan_id)

                if (
                    multiplier is not None
                    and credits is not None
                    and rate_min is not None
                    and rate_day is not None
                ):
                    return PlanConfig(
                        multiplier=multiplier,
                        credits_allocation=credits,
                        rate_limit_per_minute=(
                            rate_min if rate_min != _UNLIMITED else None
                        ),
                        rate_limit_per_day=(
                            rate_day if rate_day != _UNLIMITED else None
                        ),
                    )
            except Exception as e:
                app_logger.warning(
                    f"Cache lookup failed for plan config {plan_id}, "
                    f"falling back to DB: {e}"
                )

        # --- 2. Fallback to DB ----------------------------------------------
        try:
            from app.core.db.crud.quota import plan_pricing_rule_db

            rule = await plan_pricing_rule_db.get_by_plan_id(session, plan_id)
            if rule is None:
                return None

            # Populate cache for next time (best effort)
            if cls._backend is not None:
                try:
                    await cls._backend.set_plan_multiplier(plan_id, rule.multiplier)
                    await cls._backend.set_plan_credits_allocation(
                        plan_id, rule.credits_allocation
                    )
                    await cls._backend.set_plan_rate_limit(
                        plan_id,
                        (
                            rule.rate_limit_per_minute
                            if rule.rate_limit_per_minute is not None
                            else _UNLIMITED
                        ),
                    )
                    await cls._backend.set_plan_rate_day_limit(
                        plan_id,
                        (
                            rule.rate_limit_per_day
                            if rule.rate_limit_per_day is not None
                            else _UNLIMITED
                        ),
                    )
                except Exception:
                    pass  # Cache update is best-effort

            return PlanConfig(
                multiplier=rule.multiplier,
                credits_allocation=rule.credits_allocation,
                rate_limit_per_minute=rule.rate_limit_per_minute,
                rate_limit_per_day=rule.rate_limit_per_day,
            )
        except Exception as e:
            app_logger.warning(f"DB fallback failed for plan config {plan_id}: {e}")
            return None

    @classmethod
    async def get_feature_config(
        cls,
        session: AsyncSession,
        feature_key: FeatureKey,
    ) -> FeatureConfig | None:
        """
        Get the cost configuration for a feature.

        Lookup order: cache → database → ``None``.

        Args:
            session: Database session (used on cache miss).
            feature_key: The feature key to look up.

        Returns:
            A :class:`FeatureConfig` if a row exists, otherwise ``None``
            (meaning the caller should deny the request).
        """
        # --- 1. Try cache ---------------------------------------------------
        if cls._backend is not None:
            try:
                cost = await cls._backend.get_feature_cost(feature_key)
                if cost is not None:
                    return FeatureConfig(internal_cost_credits=cost)
            except Exception as e:
                app_logger.warning(
                    f"Cache lookup failed for feature config '{feature_key}', "
                    f"falling back to DB: {e}"
                )

        # --- 2. Fallback to DB ----------------------------------------------
        try:
            from app.core.db.crud.quota import feature_cost_config_db

            config = await feature_cost_config_db.get_by_feature_key(
                session, feature_key
            )
            if config is None:
                return None

            # Populate cache for next time (best effort)
            if cls._backend is not None:
                try:
                    await cls._backend.set_feature_cost(
                        feature_key, config.internal_cost_credits
                    )
                except Exception:
                    pass

            return FeatureConfig(internal_cost_credits=config.internal_cost_credits)
        except Exception as e:
            app_logger.warning(
                f"DB fallback failed for feature config '{feature_key}': {e}"
            )
            return None

    @classmethod
    async def calculate_billable_cost(
        cls,
        session: AsyncSession,
        feature_key: FeatureKey,
        plan_id: UUID | None,
    ) -> Decimal | None:
        """
        Calculate the billable cost for a feature call.

        Formula: ``internal_cost_credits * multiplier``

        Returns ``None`` if either the feature or plan configuration is
        missing — the caller should deny the request.

        Args:
            session: Database session (used on cache miss).
            feature_key: The feature key.
            plan_id: The plan UUID, or ``None``.

        Returns:
            The billable cost in credits, or ``None``.
        """
        feature_cfg = await cls.get_feature_config(session, feature_key)
        plan_cfg = await cls.get_plan_config(session, plan_id)
        if feature_cfg is None or plan_cfg is None:
            return None
        return feature_cfg.internal_cost_credits * plan_cfg.multiplier

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


__all__ = [
    "QuotaCacheService",
    "QuotaCacheBackend",
    "MemoryBackend",
    "RedisBackend",
    "PlanConfig",
    "FeatureConfig",
]
