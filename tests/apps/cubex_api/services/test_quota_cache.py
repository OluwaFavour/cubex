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

from app.core.enums import FeatureKey
from app.core.services.quota_cache import (
    FeatureConfig,
    MemoryBackend,
    PlanConfig,
    QuotaCacheService,
    RedisBackend,
    _UNLIMITED,
)


class TestMemoryBackend:

    @pytest.fixture
    def backend(self):
        """Create a fresh memory backend for each test."""
        return MemoryBackend()

    async def test_set_and_get_feature_cost(self, backend: MemoryBackend):
        await backend.set_feature_cost(
            FeatureKey.API_EXTRACT_CUES_RESUME, Decimal("2.5")
        )

        result = await backend.get_feature_cost(FeatureKey.API_EXTRACT_CUES_RESUME)
        assert result == Decimal("2.5")

    async def test_get_nonexistent_feature_cost_returns_none(
        self, backend: MemoryBackend
    ):
        result = await backend.get_feature_cost(FeatureKey.API_CAREER_PATH)
        assert result is None

    async def test_delete_feature_cost(self, backend: MemoryBackend):
        await backend.set_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS, Decimal("1.0"))
        await backend.delete_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS)

        result = await backend.get_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS)
        assert result is None

    async def test_delete_nonexistent_feature_no_error(self, backend: MemoryBackend):
        await backend.delete_feature_cost(
            FeatureKey.API_CAREER_PATH
        )  # Should not raise

    async def test_set_and_get_plan_multiplier(self, backend: MemoryBackend):
        plan_id = uuid4()
        await backend.set_plan_multiplier(plan_id, Decimal("0.8"))

        result = await backend.get_plan_multiplier(plan_id)
        assert result == Decimal("0.8")

    async def test_get_nonexistent_plan_multiplier_returns_none(
        self, backend: MemoryBackend
    ):
        result = await backend.get_plan_multiplier(uuid4())
        assert result is None

    async def test_delete_plan_multiplier(self, backend: MemoryBackend):
        plan_id = uuid4()
        await backend.set_plan_multiplier(plan_id, Decimal("1.5"))
        await backend.delete_plan_multiplier(plan_id)

        result = await backend.get_plan_multiplier(plan_id)
        assert result is None

    async def test_clear_clears_all_data(self, backend: MemoryBackend):
        plan_id = uuid4()
        await backend.set_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS, Decimal("1.0"))
        await backend.set_plan_multiplier(plan_id, Decimal("1.5"))
        await backend.set_plan_credits_allocation(plan_id, Decimal("5000.0"))
        await backend.set_plan_rate_limit(plan_id, 30)

        await backend.clear()

        assert await backend.get_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS) is None
        assert await backend.get_plan_multiplier(plan_id) is None
        assert await backend.get_plan_credits_allocation(plan_id) is None
        assert await backend.get_plan_rate_limit(plan_id) is None

    # Plan credits allocation tests
    async def test_set_and_get_plan_credits_allocation(self, backend: MemoryBackend):
        plan_id = uuid4()
        await backend.set_plan_credits_allocation(plan_id, Decimal("10000.0"))

        result = await backend.get_plan_credits_allocation(plan_id)
        assert result == Decimal("10000.0")

    async def test_get_nonexistent_plan_credits_allocation_returns_none(
        self, backend: MemoryBackend
    ):
        result = await backend.get_plan_credits_allocation(uuid4())
        assert result is None

    async def test_delete_plan_credits_allocation(self, backend: MemoryBackend):
        plan_id = uuid4()
        await backend.set_plan_credits_allocation(plan_id, Decimal("5000.0"))
        await backend.delete_plan_credits_allocation(plan_id)

        result = await backend.get_plan_credits_allocation(plan_id)
        assert result is None

    async def test_delete_nonexistent_plan_credits_allocation_no_error(
        self, backend: MemoryBackend
    ):
        await backend.delete_plan_credits_allocation(uuid4())  # Should not raise

    # Plan rate limit tests
    async def test_set_and_get_plan_rate_limit(self, backend: MemoryBackend):
        plan_id = uuid4()
        await backend.set_plan_rate_limit(plan_id, 100)

        result = await backend.get_plan_rate_limit(plan_id)
        assert result == 100

    async def test_get_nonexistent_plan_rate_limit_returns_none(
        self, backend: MemoryBackend
    ):
        result = await backend.get_plan_rate_limit(uuid4())
        assert result is None

    async def test_delete_plan_rate_limit(self, backend: MemoryBackend):
        plan_id = uuid4()
        await backend.set_plan_rate_limit(plan_id, 50)
        await backend.delete_plan_rate_limit(plan_id)

        result = await backend.get_plan_rate_limit(plan_id)
        assert result is None

    async def test_delete_nonexistent_plan_rate_limit_no_error(
        self, backend: MemoryBackend
    ):
        await backend.delete_plan_rate_limit(uuid4())  # Should not raise


class TestRedisBackend:

    @pytest.fixture
    def backend(self):
        """Create a Redis backend instance."""
        return RedisBackend()

    async def test_get_feature_cost_calls_redis(self, backend: RedisBackend):
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.get = AsyncMock(return_value="2.5")

            result = await backend.get_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS)

            mock_redis.get.assert_called_once_with(
                f"quota:feature_cost:{FeatureKey.API_EXTRACT_KEYWORDS}"
            )
            assert result == Decimal("2.5")

    async def test_get_feature_cost_returns_none_when_not_found(
        self, backend: RedisBackend
    ):
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            result = await backend.get_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS)
            assert result is None

    async def test_set_feature_cost_calls_redis(self, backend: RedisBackend):
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.set = AsyncMock()

            await backend.set_feature_cost(
                FeatureKey.API_EXTRACT_KEYWORDS, Decimal("3.5")
            )

            mock_redis.set.assert_called_once_with(
                f"quota:feature_cost:{FeatureKey.API_EXTRACT_KEYWORDS}", "3.5"
            )

    async def test_delete_feature_cost_calls_redis(self, backend: RedisBackend):
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.delete = AsyncMock()

            await backend.delete_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS)

            mock_redis.delete.assert_called_once_with(
                f"quota:feature_cost:{FeatureKey.API_EXTRACT_KEYWORDS}"
            )

    async def test_get_plan_multiplier_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.get = AsyncMock(return_value="0.75")

            result = await backend.get_plan_multiplier(plan_id)

            mock_redis.get.assert_called_once_with(f"quota:plan_multiplier:{plan_id}")
            assert result == Decimal("0.75")

    async def test_set_plan_multiplier_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.set = AsyncMock()

            await backend.set_plan_multiplier(plan_id, Decimal("1.25"))

            mock_redis.set.assert_called_once_with(
                f"quota:plan_multiplier:{plan_id}", "1.25"
            )

    async def test_delete_plan_multiplier_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.delete = AsyncMock()

            await backend.delete_plan_multiplier(plan_id)

            mock_redis.delete.assert_called_once_with(
                f"quota:plan_multiplier:{plan_id}"
            )

    async def test_clear_calls_redis_delete_pattern(self, backend: RedisBackend):
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.delete_pattern = AsyncMock()

            await backend.clear()

            assert mock_redis.delete_pattern.call_count == 5
            mock_redis.delete_pattern.assert_any_call("quota:feature_cost:*")
            mock_redis.delete_pattern.assert_any_call("quota:plan_multiplier:*")
            mock_redis.delete_pattern.assert_any_call("quota:plan_credits:*")
            mock_redis.delete_pattern.assert_any_call("quota:plan_rate_limit:*")
            mock_redis.delete_pattern.assert_any_call("quota:plan_rate_day_limit:*")

    # Plan credits allocation tests
    async def test_get_plan_credits_allocation_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.get = AsyncMock(return_value="10000.0")

            result = await backend.get_plan_credits_allocation(plan_id)

            mock_redis.get.assert_called_once_with(f"quota:plan_credits:{plan_id}")
            assert result == Decimal("10000.0")

    async def test_get_plan_credits_allocation_returns_none_when_not_found(
        self, backend: RedisBackend
    ):
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            result = await backend.get_plan_credits_allocation(uuid4())
            assert result is None

    async def test_set_plan_credits_allocation_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.set = AsyncMock()

            await backend.set_plan_credits_allocation(plan_id, Decimal("7500.0"))

            mock_redis.set.assert_called_once_with(
                f"quota:plan_credits:{plan_id}", "7500.0"
            )

    async def test_delete_plan_credits_allocation_calls_redis(
        self, backend: RedisBackend
    ):
        plan_id = uuid4()
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.delete = AsyncMock()

            await backend.delete_plan_credits_allocation(plan_id)

            mock_redis.delete.assert_called_once_with(f"quota:plan_credits:{plan_id}")

    # Plan rate limit tests
    async def test_get_plan_rate_limit_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.get = AsyncMock(return_value="100")

            result = await backend.get_plan_rate_limit(plan_id)

            mock_redis.get.assert_called_once_with(f"quota:plan_rate_limit:{plan_id}")
            assert result == 100

    async def test_get_plan_rate_limit_returns_none_when_not_found(
        self, backend: RedisBackend
    ):
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            result = await backend.get_plan_rate_limit(uuid4())
            assert result is None

    async def test_set_plan_rate_limit_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.set = AsyncMock()

            await backend.set_plan_rate_limit(plan_id, 50)

            mock_redis.set.assert_called_once_with(
                f"quota:plan_rate_limit:{plan_id}", "50"
            )

    async def test_delete_plan_rate_limit_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch("app.core.services.quota_cache.RedisService") as mock_redis:
            mock_redis.delete = AsyncMock()

            await backend.delete_plan_rate_limit(plan_id)

            mock_redis.delete.assert_called_once_with(
                f"quota:plan_rate_limit:{plan_id}"
            )


class TestQuotaCacheServiceInit:

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
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        # Mock empty results
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        with patch(
            "app.core.services.quota_cache.event"
        ):  # Don't actually register events
            await QuotaCacheService.init(mock_session, backend="memory")

        assert QuotaCacheService.is_initialized() is True
        assert isinstance(QuotaCacheService._backend, MemoryBackend)

    async def test_init_with_redis_backend(self):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        with patch("app.core.services.quota_cache.event"):
            await QuotaCacheService.init(mock_session, backend="redis")

        assert QuotaCacheService.is_initialized() is True
        assert isinstance(QuotaCacheService._backend, RedisBackend)

    async def test_init_skips_if_already_initialized(self):
        QuotaCacheService._initialized = True
        QuotaCacheService._backend = MemoryBackend()

        mock_session = AsyncMock()
        await QuotaCacheService.init(mock_session)

        # Session should not be used if already initialized
        mock_session.execute.assert_not_called()

    async def test_init_loads_feature_configs(self):
        mock_session = AsyncMock()

        mock_config = MagicMock()
        mock_config.feature_key = FeatureKey.API_EXTRACT_KEYWORDS
        mock_config.internal_cost_credits = Decimal("2.5")

        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.all.return_value = [mock_config]
        mock_result2 = MagicMock()
        mock_result2.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        with patch("app.core.services.quota_cache.event"):
            await QuotaCacheService.init(mock_session, backend="memory")

        result = await QuotaCacheService._backend.get_feature_cost(
            FeatureKey.API_EXTRACT_KEYWORDS
        )
        assert result == Decimal("2.5")

    async def test_init_loads_pricing_rules(self):
        mock_session = AsyncMock()
        plan_id = uuid4()

        mock_rule = MagicMock()
        mock_rule.plan_id = plan_id
        mock_rule.multiplier = Decimal("0.8")
        mock_rule.credits_allocation = Decimal("10000.0")
        mock_rule.rate_limit_per_minute = 100
        mock_rule.rate_limit_per_day = 5000

        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.all.return_value = []
        mock_result2 = MagicMock()
        mock_result2.scalars.return_value.all.return_value = [mock_rule]

        mock_session.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        with patch("app.core.services.quota_cache.event"):
            await QuotaCacheService.init(mock_session, backend="memory")

        assert await QuotaCacheService._backend.get_plan_multiplier(plan_id) == Decimal(
            "0.8"
        )
        assert await QuotaCacheService._backend.get_plan_credits_allocation(
            plan_id
        ) == Decimal("10000.0")
        assert await QuotaCacheService._backend.get_plan_rate_limit(plan_id) == 100
        assert await QuotaCacheService._backend.get_plan_rate_day_limit(plan_id) == 5000


class TestQuotaCacheServiceLookups:

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Set up service with memory backend for each test."""
        QuotaCacheService._initialized = True
        QuotaCacheService._backend = MemoryBackend()
        yield
        QuotaCacheService._initialized = False
        QuotaCacheService._backend = None

    # --- get_plan_config (cache hit) ----------------------------------------

    async def test_get_plan_config_returns_cached_value(self):
        plan_id = uuid4()
        session = AsyncMock()
        await QuotaCacheService._backend.set_plan_multiplier(plan_id, Decimal("1.5"))
        await QuotaCacheService._backend.set_plan_credits_allocation(
            plan_id, Decimal("10000.0")
        )
        await QuotaCacheService._backend.set_plan_rate_limit(plan_id, 100)
        await QuotaCacheService._backend.set_plan_rate_day_limit(plan_id, 5000)

        result = await QuotaCacheService.get_plan_config(session, plan_id)
        assert result == PlanConfig(
            multiplier=Decimal("1.5"),
            credits_allocation=Decimal("10000.0"),
            rate_limit_per_minute=100,
            rate_limit_per_day=5000,
        )

    async def test_get_plan_config_translates_unlimited_sentinel(self):
        plan_id = uuid4()
        session = AsyncMock()
        await QuotaCacheService._backend.set_plan_multiplier(plan_id, Decimal("1.0"))
        await QuotaCacheService._backend.set_plan_credits_allocation(
            plan_id, Decimal("5000.0")
        )
        await QuotaCacheService._backend.set_plan_rate_limit(plan_id, _UNLIMITED)
        await QuotaCacheService._backend.set_plan_rate_day_limit(plan_id, _UNLIMITED)

        result = await QuotaCacheService.get_plan_config(session, plan_id)
        assert result is not None
        assert result.rate_limit_per_minute is None
        assert result.rate_limit_per_day is None

    async def test_get_plan_config_returns_none_when_plan_id_is_none(self):
        session = AsyncMock()
        result = await QuotaCacheService.get_plan_config(session, None)
        assert result is None

    async def test_get_plan_config_returns_none_when_no_backend_and_db_miss(self):
        QuotaCacheService._backend = None
        session = AsyncMock()

        with patch("app.core.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=None)
            result = await QuotaCacheService.get_plan_config(session, uuid4())

        assert result is None

    # --- get_feature_config (cache hit) -------------------------------------

    async def test_get_feature_config_returns_cached_value(self):
        session = AsyncMock()
        await QuotaCacheService._backend.set_feature_cost(
            FeatureKey.API_EXTRACT_KEYWORDS, Decimal("5.0")
        )

        result = await QuotaCacheService.get_feature_config(
            session, FeatureKey.API_EXTRACT_KEYWORDS
        )
        assert result == FeatureConfig(internal_cost_credits=Decimal("5.0"))

    async def test_get_feature_config_returns_none_when_not_cached_and_db_miss(self):
        session = AsyncMock()

        with patch("app.core.db.crud.quota.feature_cost_config_db") as mock_db:
            mock_db.get_by_feature_key = AsyncMock(return_value=None)
            result = await QuotaCacheService.get_feature_config(
                session, FeatureKey.API_CAREER_PATH
            )

        assert result is None

    async def test_get_feature_config_returns_none_when_no_backend_and_db_miss(self):
        QuotaCacheService._backend = None
        session = AsyncMock()

        with patch("app.core.db.crud.quota.feature_cost_config_db") as mock_db:
            mock_db.get_by_feature_key = AsyncMock(return_value=None)
            result = await QuotaCacheService.get_feature_config(
                session, FeatureKey.API_CAREER_PATH
            )

        assert result is None

    # --- calculate_billable_cost --------------------------------------------

    async def test_calculate_billable_cost_from_cache(self):
        plan_id = uuid4()
        session = AsyncMock()
        await QuotaCacheService._backend.set_feature_cost(
            FeatureKey.API_EXTRACT_CUES_RESUME, Decimal("10.0")
        )
        await QuotaCacheService._backend.set_plan_multiplier(plan_id, Decimal("0.5"))
        await QuotaCacheService._backend.set_plan_credits_allocation(
            plan_id, Decimal("5000.0")
        )
        await QuotaCacheService._backend.set_plan_rate_limit(plan_id, _UNLIMITED)
        await QuotaCacheService._backend.set_plan_rate_day_limit(plan_id, _UNLIMITED)

        result = await QuotaCacheService.calculate_billable_cost(
            session, FeatureKey.API_EXTRACT_CUES_RESUME, plan_id
        )
        assert result == Decimal("5.0")  # 10.0 * 0.5

    async def test_calculate_billable_cost_returns_none_when_missing_config(self):
        session = AsyncMock()
        with patch("app.core.db.crud.quota.feature_cost_config_db") as mock_fc, patch(
            "app.core.db.crud.quota.plan_pricing_rule_db"
        ) as mock_pp:
            mock_fc.get_by_feature_key = AsyncMock(return_value=None)
            mock_pp.get_by_plan_id = AsyncMock(return_value=None)

            result = await QuotaCacheService.calculate_billable_cost(
                session, FeatureKey.API_CAREER_PATH, uuid4()
            )
        assert result is None


class TestQuotaCacheServiceClear:

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Set up service with memory backend for each test."""
        QuotaCacheService._initialized = True
        QuotaCacheService._backend = MemoryBackend()
        yield
        QuotaCacheService._initialized = False
        QuotaCacheService._backend = None

    async def test_clear_clears_backend_and_resets_state(self):
        await QuotaCacheService._backend.set_feature_cost(
            FeatureKey.API_EXTRACT_KEYWORDS, Decimal("1.0")
        )

        await QuotaCacheService.clear()

        assert QuotaCacheService._initialized is False
        # Backend should still exist but be empty
        assert (
            await QuotaCacheService._backend.get_feature_cost(
                FeatureKey.API_EXTRACT_KEYWORDS
            )
            is None
        )

    async def test_is_initialized_returns_correct_state(self):
        assert QuotaCacheService.is_initialized() is True

        await QuotaCacheService.clear()
        assert QuotaCacheService.is_initialized() is False


class TestQuotaCacheServicePlanConfigFallback:
    """Test cache-miss → DB → None fallback in get_plan_config."""

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Set up service with memory backend for each test."""
        QuotaCacheService._initialized = True
        QuotaCacheService._backend = MemoryBackend()
        yield
        QuotaCacheService._initialized = False
        QuotaCacheService._backend = None

    async def test_returns_none_when_plan_id_is_none(self):
        result = await QuotaCacheService.get_plan_config(
            session=AsyncMock(),
            plan_id=None,
        )
        assert result is None

    async def test_returns_cached_value_when_available(self):
        plan_id = uuid4()
        await QuotaCacheService._backend.set_plan_multiplier(plan_id, Decimal("0.8"))
        await QuotaCacheService._backend.set_plan_credits_allocation(
            plan_id, Decimal("10000.0")
        )
        await QuotaCacheService._backend.set_plan_rate_limit(plan_id, 100)
        await QuotaCacheService._backend.set_plan_rate_day_limit(plan_id, 5000)

        result = await QuotaCacheService.get_plan_config(
            session=AsyncMock(),
            plan_id=plan_id,
        )
        assert result == PlanConfig(
            multiplier=Decimal("0.8"),
            credits_allocation=Decimal("10000.0"),
            rate_limit_per_minute=100,
            rate_limit_per_day=5000,
        )

    async def test_falls_back_to_db_when_cache_miss(self):
        plan_id = uuid4()
        mock_session = AsyncMock()
        mock_rule = MagicMock()
        mock_rule.multiplier = Decimal("1.2")
        mock_rule.credits_allocation = Decimal("7500.0")
        mock_rule.rate_limit_per_minute = 50
        mock_rule.rate_limit_per_day = 2000

        with patch("app.core.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=mock_rule)

            result = await QuotaCacheService.get_plan_config(
                session=mock_session,
                plan_id=plan_id,
            )

            assert result == PlanConfig(
                multiplier=Decimal("1.2"),
                credits_allocation=Decimal("7500.0"),
                rate_limit_per_minute=50,
                rate_limit_per_day=2000,
            )
            mock_db.get_by_plan_id.assert_called_once_with(mock_session, plan_id)

    async def test_updates_cache_after_db_fallback(self):
        plan_id = uuid4()
        mock_session = AsyncMock()
        mock_rule = MagicMock()
        mock_rule.multiplier = Decimal("1.0")
        mock_rule.credits_allocation = Decimal("7500.0")
        mock_rule.rate_limit_per_minute = None
        mock_rule.rate_limit_per_day = 3000

        with patch("app.core.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=mock_rule)

            await QuotaCacheService.get_plan_config(
                session=mock_session,
                plan_id=plan_id,
            )

            cached_credits = (
                await QuotaCacheService._backend.get_plan_credits_allocation(plan_id)
            )
            assert cached_credits == Decimal("7500.0")
            # None rate limit should be stored as _UNLIMITED sentinel
            cached_rate_min = await QuotaCacheService._backend.get_plan_rate_limit(
                plan_id
            )
            assert cached_rate_min == _UNLIMITED
            cached_rate_day = await QuotaCacheService._backend.get_plan_rate_day_limit(
                plan_id
            )
            assert cached_rate_day == 3000

    async def test_returns_none_when_db_returns_none(self):
        plan_id = uuid4()
        mock_session = AsyncMock()

        with patch("app.core.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=None)

            result = await QuotaCacheService.get_plan_config(
                session=mock_session,
                plan_id=plan_id,
            )

            assert result is None

    async def test_returns_none_when_cache_and_db_fail(self):
        plan_id = uuid4()
        mock_session = AsyncMock()

        # Make cache raise an exception
        QuotaCacheService._backend.get_plan_multiplier = AsyncMock(
            side_effect=Exception("Cache error")
        )

        with patch("app.core.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(side_effect=Exception("DB error"))

            result = await QuotaCacheService.get_plan_config(
                session=mock_session,
                plan_id=plan_id,
            )

            assert result is None

    async def test_returns_none_when_no_backend_and_db_miss(self):
        QuotaCacheService._backend = None
        plan_id = uuid4()
        mock_session = AsyncMock()

        with patch("app.core.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=None)

            result = await QuotaCacheService.get_plan_config(
                session=mock_session,
                plan_id=plan_id,
            )

            assert result is None


class TestQuotaCacheServiceFeatureConfigFallback:
    """Test cache-miss → DB → None fallback in get_feature_config."""

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Set up service with memory backend for each test."""
        QuotaCacheService._initialized = True
        QuotaCacheService._backend = MemoryBackend()
        yield
        QuotaCacheService._initialized = False
        QuotaCacheService._backend = None

    async def test_returns_cached_value(self):
        session = AsyncMock()
        await QuotaCacheService._backend.set_feature_cost(
            FeatureKey.API_EXTRACT_KEYWORDS, Decimal("2.5")
        )

        result = await QuotaCacheService.get_feature_config(
            session, FeatureKey.API_EXTRACT_KEYWORDS
        )
        assert result == FeatureConfig(internal_cost_credits=Decimal("2.5"))

    async def test_falls_back_to_db(self):
        mock_session = AsyncMock()
        mock_config = MagicMock()
        mock_config.internal_cost_credits = Decimal("8.0")

        with patch("app.core.db.crud.quota.feature_cost_config_db") as mock_db:
            mock_db.get_by_feature_key = AsyncMock(return_value=mock_config)

            result = await QuotaCacheService.get_feature_config(
                mock_session, FeatureKey.API_EXTRACT_KEYWORDS
            )

            assert result == FeatureConfig(internal_cost_credits=Decimal("8.0"))

    async def test_returns_none_when_db_returns_none(self):
        mock_session = AsyncMock()

        with patch("app.core.db.crud.quota.feature_cost_config_db") as mock_db:
            mock_db.get_by_feature_key = AsyncMock(return_value=None)

            result = await QuotaCacheService.get_feature_config(
                mock_session, FeatureKey.API_EXTRACT_KEYWORDS
            )

            assert result is None

    async def test_returns_none_when_cache_and_db_fail(self):
        mock_session = AsyncMock()

        QuotaCacheService._backend.get_feature_cost = AsyncMock(
            side_effect=Exception("Cache error")
        )

        with patch("app.core.db.crud.quota.feature_cost_config_db") as mock_db:
            mock_db.get_by_feature_key = AsyncMock(side_effect=Exception("DB error"))

            result = await QuotaCacheService.get_feature_config(
                mock_session, FeatureKey.API_EXTRACT_KEYWORDS
            )

            assert result is None
