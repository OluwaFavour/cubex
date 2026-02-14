"""
Test suite for QuotaCacheService.

Run tests:
    pytest tests/apps/cubex_api/services/test_quota_cache.py -v

Run with coverage:
    pytest tests/apps/cubex_api/services/test_quota_cache.py --cov=app.apps.cubex_api.services.quota_cache --cov-report=term-missing -v
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.apps.cubex_api.services.quota_cache import (
    MemoryBackend,
    QuotaCacheService,
    RedisBackend,
)


class TestMemoryBackend:
    """Test suite for MemoryBackend class."""

    @pytest.fixture
    def backend(self):
        """Create a fresh memory backend for each test."""
        return MemoryBackend()

    async def test_set_and_get_endpoint_cost(self, backend: MemoryBackend):
        """Test setting and getting endpoint costs."""
        await backend.set_endpoint_cost("/api/v1/analyze", Decimal("2.5"))

        result = await backend.get_endpoint_cost("/api/v1/analyze")
        assert result == Decimal("2.5")

    async def test_get_nonexistent_endpoint_cost_returns_none(
        self, backend: MemoryBackend
    ):
        """Test that getting a non-existent endpoint returns None."""
        result = await backend.get_endpoint_cost("/nonexistent")
        assert result is None

    async def test_delete_endpoint_cost(self, backend: MemoryBackend):
        """Test deleting an endpoint cost."""
        await backend.set_endpoint_cost("/api/v1/test", Decimal("1.0"))
        await backend.delete_endpoint_cost("/api/v1/test")

        result = await backend.get_endpoint_cost("/api/v1/test")
        assert result is None

    async def test_delete_nonexistent_endpoint_no_error(self, backend: MemoryBackend):
        """Test that deleting a non-existent endpoint doesn't raise error."""
        await backend.delete_endpoint_cost("/nonexistent")  # Should not raise

    async def test_set_and_get_plan_multiplier(self, backend: MemoryBackend):
        """Test setting and getting plan multipliers."""
        plan_id = uuid4()
        await backend.set_plan_multiplier(plan_id, Decimal("0.8"))

        result = await backend.get_plan_multiplier(plan_id)
        assert result == Decimal("0.8")

    async def test_get_nonexistent_plan_multiplier_returns_none(
        self, backend: MemoryBackend
    ):
        """Test that getting a non-existent plan multiplier returns None."""
        result = await backend.get_plan_multiplier(uuid4())
        assert result is None

    async def test_delete_plan_multiplier(self, backend: MemoryBackend):
        """Test deleting a plan multiplier."""
        plan_id = uuid4()
        await backend.set_plan_multiplier(plan_id, Decimal("1.5"))
        await backend.delete_plan_multiplier(plan_id)

        result = await backend.get_plan_multiplier(plan_id)
        assert result is None

    async def test_clear_clears_all_data(self, backend: MemoryBackend):
        """Test that clear removes all cached data."""
        plan_id = uuid4()
        await backend.set_endpoint_cost("/api/v1/test", Decimal("1.0"))
        await backend.set_plan_multiplier(plan_id, Decimal("1.5"))
        await backend.set_plan_credits_allocation(plan_id, Decimal("5000.0"))
        await backend.set_plan_rate_limit(plan_id, 30)

        await backend.clear()

        assert await backend.get_endpoint_cost("/api/v1/test") is None
        assert await backend.get_plan_multiplier(plan_id) is None
        assert await backend.get_plan_credits_allocation(plan_id) is None
        assert await backend.get_plan_rate_limit(plan_id) is None

    # Plan credits allocation tests
    async def test_set_and_get_plan_credits_allocation(self, backend: MemoryBackend):
        """Test setting and getting plan credits allocation."""
        plan_id = uuid4()
        await backend.set_plan_credits_allocation(plan_id, Decimal("10000.0"))

        result = await backend.get_plan_credits_allocation(plan_id)
        assert result == Decimal("10000.0")

    async def test_get_nonexistent_plan_credits_allocation_returns_none(
        self, backend: MemoryBackend
    ):
        """Test that getting a non-existent plan credits allocation returns None."""
        result = await backend.get_plan_credits_allocation(uuid4())
        assert result is None

    async def test_delete_plan_credits_allocation(self, backend: MemoryBackend):
        """Test deleting a plan credits allocation."""
        plan_id = uuid4()
        await backend.set_plan_credits_allocation(plan_id, Decimal("5000.0"))
        await backend.delete_plan_credits_allocation(plan_id)

        result = await backend.get_plan_credits_allocation(plan_id)
        assert result is None

    async def test_delete_nonexistent_plan_credits_allocation_no_error(
        self, backend: MemoryBackend
    ):
        """Test that deleting a non-existent plan credits allocation doesn't raise error."""
        await backend.delete_plan_credits_allocation(uuid4())  # Should not raise

    # Plan rate limit tests
    async def test_set_and_get_plan_rate_limit(self, backend: MemoryBackend):
        """Test setting and getting plan rate limit."""
        plan_id = uuid4()
        await backend.set_plan_rate_limit(plan_id, 100)

        result = await backend.get_plan_rate_limit(plan_id)
        assert result == 100

    async def test_get_nonexistent_plan_rate_limit_returns_none(
        self, backend: MemoryBackend
    ):
        """Test that getting a non-existent plan rate limit returns None."""
        result = await backend.get_plan_rate_limit(uuid4())
        assert result is None

    async def test_delete_plan_rate_limit(self, backend: MemoryBackend):
        """Test deleting a plan rate limit."""
        plan_id = uuid4()
        await backend.set_plan_rate_limit(plan_id, 50)
        await backend.delete_plan_rate_limit(plan_id)

        result = await backend.get_plan_rate_limit(plan_id)
        assert result is None

    async def test_delete_nonexistent_plan_rate_limit_no_error(
        self, backend: MemoryBackend
    ):
        """Test that deleting a non-existent plan rate limit doesn't raise error."""
        await backend.delete_plan_rate_limit(uuid4())  # Should not raise


class TestRedisBackend:
    """Test suite for RedisBackend class."""

    @pytest.fixture
    def backend(self):
        """Create a Redis backend instance."""
        return RedisBackend()

    async def test_get_endpoint_cost_calls_redis(self, backend: RedisBackend):
        """Test that get_endpoint_cost calls RedisService."""
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value="2.5")

            result = await backend.get_endpoint_cost("/api/v1/test")

            mock_redis.get.assert_called_once_with("quota:endpoint_cost:/api/v1/test")
            assert result == Decimal("2.5")

    async def test_get_endpoint_cost_returns_none_when_not_found(
        self, backend: RedisBackend
    ):
        """Test that get_endpoint_cost returns None when key doesn't exist."""
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            result = await backend.get_endpoint_cost("/api/v1/test")
            assert result is None

    async def test_set_endpoint_cost_calls_redis(self, backend: RedisBackend):
        """Test that set_endpoint_cost calls RedisService.set."""
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.set = AsyncMock()

            await backend.set_endpoint_cost("/api/v1/test", Decimal("3.5"))

            mock_redis.set.assert_called_once_with(
                "quota:endpoint_cost:/api/v1/test", "3.5"
            )

    async def test_delete_endpoint_cost_calls_redis(self, backend: RedisBackend):
        """Test that delete_endpoint_cost calls RedisService.delete."""
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.delete = AsyncMock()

            await backend.delete_endpoint_cost("/api/v1/test")

            mock_redis.delete.assert_called_once_with(
                "quota:endpoint_cost:/api/v1/test"
            )

    async def test_get_plan_multiplier_calls_redis(self, backend: RedisBackend):
        """Test that get_plan_multiplier calls RedisService."""
        plan_id = uuid4()
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value="0.75")

            result = await backend.get_plan_multiplier(plan_id)

            mock_redis.get.assert_called_once_with(f"quota:plan_multiplier:{plan_id}")
            assert result == Decimal("0.75")

    async def test_set_plan_multiplier_calls_redis(self, backend: RedisBackend):
        """Test that set_plan_multiplier calls RedisService.set."""
        plan_id = uuid4()
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.set = AsyncMock()

            await backend.set_plan_multiplier(plan_id, Decimal("1.25"))

            mock_redis.set.assert_called_once_with(
                f"quota:plan_multiplier:{plan_id}", "1.25"
            )

    async def test_delete_plan_multiplier_calls_redis(self, backend: RedisBackend):
        """Test that delete_plan_multiplier calls RedisService.delete."""
        plan_id = uuid4()
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.delete = AsyncMock()

            await backend.delete_plan_multiplier(plan_id)

            mock_redis.delete.assert_called_once_with(
                f"quota:plan_multiplier:{plan_id}"
            )

    async def test_clear_calls_redis_delete_pattern(self, backend: RedisBackend):
        """Test that clear calls RedisService.delete_pattern for all prefixes."""
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.delete_pattern = AsyncMock()

            await backend.clear()

            assert mock_redis.delete_pattern.call_count == 4
            mock_redis.delete_pattern.assert_any_call("quota:endpoint_cost:*")
            mock_redis.delete_pattern.assert_any_call("quota:plan_multiplier:*")
            mock_redis.delete_pattern.assert_any_call("quota:plan_credits:*")
            mock_redis.delete_pattern.assert_any_call("quota:plan_rate_limit:*")

    # Plan credits allocation tests
    async def test_get_plan_credits_allocation_calls_redis(self, backend: RedisBackend):
        """Test that get_plan_credits_allocation calls RedisService."""
        plan_id = uuid4()
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value="10000.0")

            result = await backend.get_plan_credits_allocation(plan_id)

            mock_redis.get.assert_called_once_with(f"quota:plan_credits:{plan_id}")
            assert result == Decimal("10000.0")

    async def test_get_plan_credits_allocation_returns_none_when_not_found(
        self, backend: RedisBackend
    ):
        """Test that get_plan_credits_allocation returns None when key doesn't exist."""
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            result = await backend.get_plan_credits_allocation(uuid4())
            assert result is None

    async def test_set_plan_credits_allocation_calls_redis(self, backend: RedisBackend):
        """Test that set_plan_credits_allocation calls RedisService.set."""
        plan_id = uuid4()
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.set = AsyncMock()

            await backend.set_plan_credits_allocation(plan_id, Decimal("7500.0"))

            mock_redis.set.assert_called_once_with(
                f"quota:plan_credits:{plan_id}", "7500.0"
            )

    async def test_delete_plan_credits_allocation_calls_redis(
        self, backend: RedisBackend
    ):
        """Test that delete_plan_credits_allocation calls RedisService.delete."""
        plan_id = uuid4()
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.delete = AsyncMock()

            await backend.delete_plan_credits_allocation(plan_id)

            mock_redis.delete.assert_called_once_with(f"quota:plan_credits:{plan_id}")

    # Plan rate limit tests
    async def test_get_plan_rate_limit_calls_redis(self, backend: RedisBackend):
        """Test that get_plan_rate_limit calls RedisService."""
        plan_id = uuid4()
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value="100")

            result = await backend.get_plan_rate_limit(plan_id)

            mock_redis.get.assert_called_once_with(f"quota:plan_rate_limit:{plan_id}")
            assert result == 100

    async def test_get_plan_rate_limit_returns_none_when_not_found(
        self, backend: RedisBackend
    ):
        """Test that get_plan_rate_limit returns None when key doesn't exist."""
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            result = await backend.get_plan_rate_limit(uuid4())
            assert result is None

    async def test_set_plan_rate_limit_calls_redis(self, backend: RedisBackend):
        """Test that set_plan_rate_limit calls RedisService.set."""
        plan_id = uuid4()
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.set = AsyncMock()

            await backend.set_plan_rate_limit(plan_id, 50)

            mock_redis.set.assert_called_once_with(
                f"quota:plan_rate_limit:{plan_id}", "50"
            )

    async def test_delete_plan_rate_limit_calls_redis(self, backend: RedisBackend):
        """Test that delete_plan_rate_limit calls RedisService.delete."""
        plan_id = uuid4()
        with patch(
            "app.apps.cubex_api.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.delete = AsyncMock()

            await backend.delete_plan_rate_limit(plan_id)

            mock_redis.delete.assert_called_once_with(
                f"quota:plan_rate_limit:{plan_id}"
            )


class TestQuotaCacheServiceInit:
    """Test suite for QuotaCacheService initialization."""

    @pytest.fixture(autouse=True)
    def reset_service(self):
        """Reset the singleton state before each test."""
        QuotaCacheService._initialized = False
        QuotaCacheService._backend = None
        QuotaCacheService._events_registered = False
        yield
        QuotaCacheService._initialized = False
        QuotaCacheService._backend = None
        QuotaCacheService._events_registered = False

    async def test_init_with_memory_backend(self):
        """Test initialization with memory backend."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        # Mock empty results
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        with patch(
            "app.apps.cubex_api.services.quota_cache.event"
        ):  # Don't actually register events
            await QuotaCacheService.init(mock_session, backend="memory")

        assert QuotaCacheService.is_initialized() is True
        assert isinstance(QuotaCacheService._backend, MemoryBackend)

    async def test_init_with_redis_backend(self):
        """Test initialization with redis backend."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        with patch("app.apps.cubex_api.services.quota_cache.event"):
            await QuotaCacheService.init(mock_session, backend="redis")

        assert QuotaCacheService.is_initialized() is True
        assert isinstance(QuotaCacheService._backend, RedisBackend)

    async def test_init_skips_if_already_initialized(self):
        """Test that init is skipped if already initialized."""
        QuotaCacheService._initialized = True
        QuotaCacheService._backend = MemoryBackend()

        mock_session = AsyncMock()
        await QuotaCacheService.init(mock_session)

        # Session should not be used if already initialized
        mock_session.execute.assert_not_called()

    async def test_init_loads_endpoint_configs(self):
        """Test that init loads endpoint configs from database."""
        mock_session = AsyncMock()

        # Create mock endpoint config
        mock_config = MagicMock()
        mock_config.endpoint = "/api/v1/test"
        mock_config.internal_cost_credits = Decimal("2.5")

        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.all.return_value = [mock_config]
        mock_result2 = MagicMock()
        mock_result2.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        with patch("app.apps.cubex_api.services.quota_cache.event"):
            await QuotaCacheService.init(mock_session, backend="memory")

        # Verify the endpoint cost was cached
        result = await QuotaCacheService.get_endpoint_cost("/api/v1/test")
        assert result == Decimal("2.5")

    async def test_init_loads_pricing_rules(self):
        """Test that init loads pricing rules from database."""
        mock_session = AsyncMock()
        plan_id = uuid4()

        # Create mock pricing rule with all fields
        mock_rule = MagicMock()
        mock_rule.plan_id = plan_id
        mock_rule.multiplier = Decimal("0.8")
        mock_rule.credits_allocation = Decimal("10000.0")
        mock_rule.rate_limit_per_minute = 100

        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.all.return_value = []
        mock_result2 = MagicMock()
        mock_result2.scalars.return_value.all.return_value = [mock_rule]

        mock_session.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        with patch("app.apps.cubex_api.services.quota_cache.event"):
            await QuotaCacheService.init(mock_session, backend="memory")

        # Verify all pricing rule fields were cached
        assert await QuotaCacheService.get_plan_multiplier(plan_id) == Decimal("0.8")
        assert await QuotaCacheService.get_plan_credits_allocation(plan_id) == Decimal(
            "10000.0"
        )
        assert await QuotaCacheService.get_plan_rate_limit(plan_id) == 100


class TestQuotaCacheServiceLookups:
    """Test suite for QuotaCacheService O(1) lookup methods."""

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Set up service with memory backend for each test."""
        QuotaCacheService._initialized = True
        QuotaCacheService._backend = MemoryBackend()
        yield
        QuotaCacheService._initialized = False
        QuotaCacheService._backend = None

    async def test_get_endpoint_cost_returns_cached_value(self):
        """Test that get_endpoint_cost returns the cached value."""
        await QuotaCacheService._backend.set_endpoint_cost(
            "/api/v1/test", Decimal("5.0")
        )

        result = await QuotaCacheService.get_endpoint_cost("/api/v1/test")
        assert result == Decimal("5.0")

    async def test_get_endpoint_cost_returns_default_when_not_found(self):
        """Test that get_endpoint_cost returns default when not cached."""
        result = await QuotaCacheService.get_endpoint_cost("/nonexistent")
        assert result == QuotaCacheService.DEFAULT_ENDPOINT_COST

    async def test_get_endpoint_cost_returns_default_when_no_backend(self):
        """Test that get_endpoint_cost returns default when backend is None."""
        QuotaCacheService._backend = None

        result = await QuotaCacheService.get_endpoint_cost("/any")
        assert result == QuotaCacheService.DEFAULT_ENDPOINT_COST

    async def test_get_plan_multiplier_returns_cached_value(self):
        """Test that get_plan_multiplier returns the cached value."""
        plan_id = uuid4()
        await QuotaCacheService._backend.set_plan_multiplier(plan_id, Decimal("1.5"))

        result = await QuotaCacheService.get_plan_multiplier(plan_id)
        assert result == Decimal("1.5")

    async def test_get_plan_multiplier_returns_default_when_not_found(self):
        """Test that get_plan_multiplier returns default when not cached."""
        result = await QuotaCacheService.get_plan_multiplier(uuid4())
        assert result == QuotaCacheService.DEFAULT_PLAN_MULTIPLIER

    async def test_get_plan_multiplier_returns_default_when_no_backend(self):
        """Test that get_plan_multiplier returns default when backend is None."""
        QuotaCacheService._backend = None

        result = await QuotaCacheService.get_plan_multiplier(uuid4())
        assert result == QuotaCacheService.DEFAULT_PLAN_MULTIPLIER

    async def test_calculate_billable_cost(self):
        """Test billable cost calculation."""
        plan_id = uuid4()
        await QuotaCacheService._backend.set_endpoint_cost(
            "/api/v1/analyze", Decimal("10.0")
        )
        await QuotaCacheService._backend.set_plan_multiplier(plan_id, Decimal("0.5"))

        result = await QuotaCacheService.calculate_billable_cost(
            "/api/v1/analyze", plan_id
        )
        assert result == Decimal("5.0")  # 10.0 * 0.5

    async def test_calculate_billable_cost_uses_defaults(self):
        """Test billable cost uses defaults when values not cached."""
        result = await QuotaCacheService.calculate_billable_cost(
            "/nonexistent", uuid4()
        )
        expected = (
            QuotaCacheService.DEFAULT_ENDPOINT_COST
            * QuotaCacheService.DEFAULT_PLAN_MULTIPLIER
        )
        assert result == expected

    # Plan credits allocation tests
    async def test_get_plan_credits_allocation_returns_cached_value(self):
        """Test that get_plan_credits_allocation returns the cached value."""
        plan_id = uuid4()
        await QuotaCacheService._backend.set_plan_credits_allocation(
            plan_id, Decimal("10000.0")
        )

        result = await QuotaCacheService.get_plan_credits_allocation(plan_id)
        assert result == Decimal("10000.0")

    async def test_get_plan_credits_allocation_returns_default_when_not_found(self):
        """Test that get_plan_credits_allocation returns default when not cached."""
        result = await QuotaCacheService.get_plan_credits_allocation(uuid4())
        assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

    async def test_get_plan_credits_allocation_returns_default_when_no_backend(self):
        """Test that get_plan_credits_allocation returns default when backend is None."""
        QuotaCacheService._backend = None

        result = await QuotaCacheService.get_plan_credits_allocation(uuid4())
        assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

    async def test_get_plan_credits_allocation_returns_default_when_plan_id_none(self):
        """Test that get_plan_credits_allocation returns default when plan_id is None."""
        result = await QuotaCacheService.get_plan_credits_allocation(None)
        assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

    # Plan rate limit tests
    async def test_get_plan_rate_limit_returns_cached_value(self):
        """Test that get_plan_rate_limit returns the cached value."""
        plan_id = uuid4()
        await QuotaCacheService._backend.set_plan_rate_limit(plan_id, 100)

        result = await QuotaCacheService.get_plan_rate_limit(plan_id)
        assert result == 100

    async def test_get_plan_rate_limit_returns_default_when_not_found(self):
        """Test that get_plan_rate_limit returns default when not cached."""
        result = await QuotaCacheService.get_plan_rate_limit(uuid4())
        assert result == QuotaCacheService.DEFAULT_RATE_LIMIT_PER_MINUTE

    async def test_get_plan_rate_limit_returns_default_when_no_backend(self):
        """Test that get_plan_rate_limit returns default when backend is None."""
        QuotaCacheService._backend = None

        result = await QuotaCacheService.get_plan_rate_limit(uuid4())
        assert result == QuotaCacheService.DEFAULT_RATE_LIMIT_PER_MINUTE

    async def test_get_plan_rate_limit_returns_default_when_plan_id_none(self):
        """Test that get_plan_rate_limit returns default when plan_id is None."""
        result = await QuotaCacheService.get_plan_rate_limit(None)
        assert result == QuotaCacheService.DEFAULT_RATE_LIMIT_PER_MINUTE


class TestQuotaCacheServiceClear:
    """Test suite for QuotaCacheService clear and refresh methods."""

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Set up service with memory backend for each test."""
        QuotaCacheService._initialized = True
        QuotaCacheService._backend = MemoryBackend()
        yield
        QuotaCacheService._initialized = False
        QuotaCacheService._backend = None

    async def test_clear_clears_backend_and_resets_state(self):
        """Test that clear clears the backend and resets initialized state."""
        await QuotaCacheService._backend.set_endpoint_cost("/test", Decimal("1.0"))

        await QuotaCacheService.clear()

        assert QuotaCacheService._initialized is False
        # Backend should still exist but be empty
        assert await QuotaCacheService._backend.get_endpoint_cost("/test") is None

    async def test_is_initialized_returns_correct_state(self):
        """Test is_initialized returns the correct state."""
        assert QuotaCacheService.is_initialized() is True

        await QuotaCacheService.clear()
        assert QuotaCacheService.is_initialized() is False


class TestQuotaCacheServiceConstants:
    """Test suite for QuotaCacheService constants."""

    def test_default_endpoint_cost(self):
        """Test default endpoint cost constant."""
        assert QuotaCacheService.DEFAULT_ENDPOINT_COST == Decimal("6.0")

    def test_default_plan_multiplier(self):
        """Test default plan multiplier constant."""
        assert QuotaCacheService.DEFAULT_PLAN_MULTIPLIER == Decimal("3.0")

    def test_default_plan_credits(self):
        """Test default plan credits constant."""
        assert QuotaCacheService.DEFAULT_PLAN_CREDITS == Decimal("5000.0")

    def test_default_rate_limit_per_minute(self):
        """Test default rate limit per minute constant."""
        assert QuotaCacheService.DEFAULT_RATE_LIMIT_PER_MINUTE == 20


class TestQuotaCacheServiceFallbackMethod:
    """Test suite for get_plan_credits_allocation_with_fallback."""

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Set up service with memory backend for each test."""
        QuotaCacheService._initialized = True
        QuotaCacheService._backend = MemoryBackend()
        yield
        QuotaCacheService._initialized = False
        QuotaCacheService._backend = None

    async def test_returns_default_when_plan_id_is_none(self):
        """Test that default is returned when plan_id is None."""
        result = await QuotaCacheService.get_plan_credits_allocation_with_fallback(
            session=MagicMock(),
            plan_id=None,
        )
        assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

    async def test_returns_cached_value_when_available(self):
        """Test that cached value is returned when available."""
        plan_id = uuid4()
        await QuotaCacheService._backend.set_plan_credits_allocation(
            plan_id, Decimal("10000.0")
        )

        result = await QuotaCacheService.get_plan_credits_allocation_with_fallback(
            session=MagicMock(),
            plan_id=plan_id,
        )
        assert result == Decimal("10000.0")

    async def test_falls_back_to_db_when_cache_miss(self):
        """Test that DB is queried when cache misses."""
        plan_id = uuid4()
        mock_session = AsyncMock()
        mock_rule = MagicMock()
        mock_rule.credits_allocation = Decimal("7500.0")

        with patch("app.apps.cubex_api.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=mock_rule)

            result = await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session=mock_session,
                plan_id=plan_id,
            )

            assert result == Decimal("7500.0")
            mock_db.get_by_plan_id.assert_called_once_with(mock_session, plan_id)

    async def test_updates_cache_after_db_fallback(self):
        """Test that cache is updated after successful DB fallback."""
        plan_id = uuid4()
        mock_session = AsyncMock()
        mock_rule = MagicMock()
        mock_rule.credits_allocation = Decimal("7500.0")

        with patch("app.apps.cubex_api.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=mock_rule)

            await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session=mock_session,
                plan_id=plan_id,
            )

            # Verify cache was updated
            cached = await QuotaCacheService._backend.get_plan_credits_allocation(
                plan_id
            )
            assert cached == Decimal("7500.0")

    async def test_returns_default_when_db_returns_none(self):
        """Test that default is returned when DB returns None."""
        plan_id = uuid4()
        mock_session = AsyncMock()

        with patch("app.apps.cubex_api.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=None)

            result = await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session=mock_session,
                plan_id=plan_id,
            )

            assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

    async def test_returns_default_when_cache_and_db_fail(self):
        """Test that default is returned when both cache and DB fail."""
        plan_id = uuid4()
        mock_session = AsyncMock()

        # Make cache raise an exception
        QuotaCacheService._backend.get_plan_credits_allocation = AsyncMock(
            side_effect=Exception("Cache error")
        )

        with patch("app.apps.cubex_api.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(side_effect=Exception("DB error"))

            result = await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session=mock_session,
                plan_id=plan_id,
            )

            assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

    async def test_returns_default_when_no_backend(self):
        """Test that default is returned when backend is None."""
        QuotaCacheService._backend = None
        plan_id = uuid4()
        mock_session = AsyncMock()

        with patch("app.apps.cubex_api.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=None)

            result = await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session=mock_session,
                plan_id=plan_id,
            )

            assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS
