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
    MemoryBackend,
    QuotaCacheService,
    RedisBackend,
)


class TestMemoryBackend:

    @pytest.fixture
    def backend(self):
        """Create a fresh memory backend for each test."""
        return MemoryBackend()

    async def test_set_and_get_feature_cost(self, backend: MemoryBackend):
        await backend.set_feature_cost(FeatureKey.API_EXTRACT_CUES_RESUME, Decimal("2.5"))

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
        await backend.delete_feature_cost(FeatureKey.API_CAREER_PATH)  # Should not raise

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
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value="2.5")

            result = await backend.get_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS)

            mock_redis.get.assert_called_once_with(f"quota:feature_cost:{FeatureKey.API_EXTRACT_KEYWORDS}")
            assert result == Decimal("2.5")

    async def test_get_feature_cost_returns_none_when_not_found(
        self, backend: RedisBackend
    ):
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            result = await backend.get_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS)
            assert result is None

    async def test_set_feature_cost_calls_redis(self, backend: RedisBackend):
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.set = AsyncMock()

            await backend.set_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS, Decimal("3.5"))

            mock_redis.set.assert_called_once_with(
                f"quota:feature_cost:{FeatureKey.API_EXTRACT_KEYWORDS}", "3.5"
            )

    async def test_delete_feature_cost_calls_redis(self, backend: RedisBackend):
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.delete = AsyncMock()

            await backend.delete_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS)

            mock_redis.delete.assert_called_once_with(
                f"quota:feature_cost:{FeatureKey.API_EXTRACT_KEYWORDS}"
            )

    async def test_get_plan_multiplier_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value="0.75")

            result = await backend.get_plan_multiplier(plan_id)

            mock_redis.get.assert_called_once_with(f"quota:plan_multiplier:{plan_id}")
            assert result == Decimal("0.75")

    async def test_set_plan_multiplier_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.set = AsyncMock()

            await backend.set_plan_multiplier(plan_id, Decimal("1.25"))

            mock_redis.set.assert_called_once_with(
                f"quota:plan_multiplier:{plan_id}", "1.25"
            )

    async def test_delete_plan_multiplier_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.delete = AsyncMock()

            await backend.delete_plan_multiplier(plan_id)

            mock_redis.delete.assert_called_once_with(
                f"quota:plan_multiplier:{plan_id}"
            )

    async def test_clear_calls_redis_delete_pattern(self, backend: RedisBackend):
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
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
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value="10000.0")

            result = await backend.get_plan_credits_allocation(plan_id)

            mock_redis.get.assert_called_once_with(f"quota:plan_credits:{plan_id}")
            assert result == Decimal("10000.0")

    async def test_get_plan_credits_allocation_returns_none_when_not_found(
        self, backend: RedisBackend
    ):
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            result = await backend.get_plan_credits_allocation(uuid4())
            assert result is None

    async def test_set_plan_credits_allocation_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.set = AsyncMock()

            await backend.set_plan_credits_allocation(plan_id, Decimal("7500.0"))

            mock_redis.set.assert_called_once_with(
                f"quota:plan_credits:{plan_id}", "7500.0"
            )

    async def test_delete_plan_credits_allocation_calls_redis(
        self, backend: RedisBackend
    ):
        plan_id = uuid4()
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.delete = AsyncMock()

            await backend.delete_plan_credits_allocation(plan_id)

            mock_redis.delete.assert_called_once_with(f"quota:plan_credits:{plan_id}")

    # Plan rate limit tests
    async def test_get_plan_rate_limit_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value="100")

            result = await backend.get_plan_rate_limit(plan_id)

            mock_redis.get.assert_called_once_with(f"quota:plan_rate_limit:{plan_id}")
            assert result == 100

    async def test_get_plan_rate_limit_returns_none_when_not_found(
        self, backend: RedisBackend
    ):
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            result = await backend.get_plan_rate_limit(uuid4())
            assert result is None

    async def test_set_plan_rate_limit_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
            mock_redis.set = AsyncMock()

            await backend.set_plan_rate_limit(plan_id, 50)

            mock_redis.set.assert_called_once_with(
                f"quota:plan_rate_limit:{plan_id}", "50"
            )

    async def test_delete_plan_rate_limit_calls_redis(self, backend: RedisBackend):
        plan_id = uuid4()
        with patch(
            "app.core.services.quota_cache.RedisService"
        ) as mock_redis:
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

        result = await QuotaCacheService.get_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS)
        assert result == Decimal("2.5")

    async def test_init_loads_pricing_rules(self):
        mock_session = AsyncMock()
        plan_id = uuid4()

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

        with patch("app.core.services.quota_cache.event"):
            await QuotaCacheService.init(mock_session, backend="memory")

        assert await QuotaCacheService.get_plan_multiplier(plan_id) == Decimal("0.8")
        assert await QuotaCacheService.get_plan_credits_allocation(plan_id) == Decimal(
            "10000.0"
        )
        assert await QuotaCacheService.get_plan_rate_limit(plan_id) == 100


class TestQuotaCacheServiceLookups:

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Set up service with memory backend for each test."""
        QuotaCacheService._initialized = True
        QuotaCacheService._backend = MemoryBackend()
        yield
        QuotaCacheService._initialized = False
        QuotaCacheService._backend = None

    async def test_get_feature_cost_returns_cached_value(self):
        await QuotaCacheService._backend.set_feature_cost(
            FeatureKey.API_EXTRACT_KEYWORDS, Decimal("5.0")
        )

        result = await QuotaCacheService.get_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS)
        assert result == Decimal("5.0")

    async def test_get_feature_cost_returns_default_when_not_found(self):
        result = await QuotaCacheService.get_feature_cost(FeatureKey.API_CAREER_PATH)
        assert result == QuotaCacheService.DEFAULT_FEATURE_COST

    async def test_get_feature_cost_returns_default_when_no_backend(self):
        QuotaCacheService._backend = None

        result = await QuotaCacheService.get_feature_cost(FeatureKey.API_CAREER_PATH)
        assert result == QuotaCacheService.DEFAULT_FEATURE_COST

    async def test_get_plan_multiplier_returns_cached_value(self):
        plan_id = uuid4()
        await QuotaCacheService._backend.set_plan_multiplier(plan_id, Decimal("1.5"))

        result = await QuotaCacheService.get_plan_multiplier(plan_id)
        assert result == Decimal("1.5")

    async def test_get_plan_multiplier_returns_default_when_not_found(self):
        result = await QuotaCacheService.get_plan_multiplier(uuid4())
        assert result == QuotaCacheService.DEFAULT_PLAN_MULTIPLIER

    async def test_get_plan_multiplier_returns_default_when_no_backend(self):
        QuotaCacheService._backend = None

        result = await QuotaCacheService.get_plan_multiplier(uuid4())
        assert result == QuotaCacheService.DEFAULT_PLAN_MULTIPLIER

    async def test_calculate_billable_cost(self):
        plan_id = uuid4()
        await QuotaCacheService._backend.set_feature_cost(
            FeatureKey.API_EXTRACT_CUES_RESUME, Decimal("10.0")
        )
        await QuotaCacheService._backend.set_plan_multiplier(plan_id, Decimal("0.5"))

        result = await QuotaCacheService.calculate_billable_cost(
            FeatureKey.API_EXTRACT_CUES_RESUME, plan_id
        )
        assert result == Decimal("5.0")  # 10.0 * 0.5

    async def test_calculate_billable_cost_uses_defaults(self):
        result = await QuotaCacheService.calculate_billable_cost(
            FeatureKey.API_CAREER_PATH, uuid4()
        )
        expected = (
            QuotaCacheService.DEFAULT_FEATURE_COST
            * QuotaCacheService.DEFAULT_PLAN_MULTIPLIER
        )
        assert result == expected

    # Plan credits allocation tests
    async def test_get_plan_credits_allocation_returns_cached_value(self):
        plan_id = uuid4()
        await QuotaCacheService._backend.set_plan_credits_allocation(
            plan_id, Decimal("10000.0")
        )

        result = await QuotaCacheService.get_plan_credits_allocation(plan_id)
        assert result == Decimal("10000.0")

    async def test_get_plan_credits_allocation_returns_default_when_not_found(self):
        result = await QuotaCacheService.get_plan_credits_allocation(uuid4())
        assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

    async def test_get_plan_credits_allocation_returns_default_when_no_backend(self):
        QuotaCacheService._backend = None

        result = await QuotaCacheService.get_plan_credits_allocation(uuid4())
        assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

    async def test_get_plan_credits_allocation_returns_default_when_plan_id_none(self):
        result = await QuotaCacheService.get_plan_credits_allocation(None)
        assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

    # Plan rate limit tests
    async def test_get_plan_rate_limit_returns_cached_value(self):
        plan_id = uuid4()
        await QuotaCacheService._backend.set_plan_rate_limit(plan_id, 100)

        result = await QuotaCacheService.get_plan_rate_limit(plan_id)
        assert result == 100

    async def test_get_plan_rate_limit_returns_default_when_not_found(self):
        result = await QuotaCacheService.get_plan_rate_limit(uuid4())
        assert result == QuotaCacheService.DEFAULT_RATE_LIMIT_PER_MINUTE

    async def test_get_plan_rate_limit_returns_default_when_no_backend(self):
        QuotaCacheService._backend = None

        result = await QuotaCacheService.get_plan_rate_limit(uuid4())
        assert result == QuotaCacheService.DEFAULT_RATE_LIMIT_PER_MINUTE

    async def test_get_plan_rate_limit_returns_default_when_plan_id_none(self):
        result = await QuotaCacheService.get_plan_rate_limit(None)
        assert result == QuotaCacheService.DEFAULT_RATE_LIMIT_PER_MINUTE


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
        await QuotaCacheService._backend.set_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS, Decimal("1.0"))

        await QuotaCacheService.clear()

        assert QuotaCacheService._initialized is False
        # Backend should still exist but be empty
        assert await QuotaCacheService._backend.get_feature_cost(FeatureKey.API_EXTRACT_KEYWORDS) is None

    async def test_is_initialized_returns_correct_state(self):
        assert QuotaCacheService.is_initialized() is True

        await QuotaCacheService.clear()
        assert QuotaCacheService.is_initialized() is False


class TestQuotaCacheServiceConstants:

    def test_default_feature_cost(self):
        assert QuotaCacheService.DEFAULT_FEATURE_COST == Decimal("6.0")

    def test_default_plan_multiplier(self):
        assert QuotaCacheService.DEFAULT_PLAN_MULTIPLIER == Decimal("3.0")

    def test_default_plan_credits(self):
        assert QuotaCacheService.DEFAULT_PLAN_CREDITS == Decimal("5000.0")

    def test_default_rate_limit_per_minute(self):
        assert QuotaCacheService.DEFAULT_RATE_LIMIT_PER_MINUTE == 20


class TestQuotaCacheServiceFallbackMethod:

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Set up service with memory backend for each test."""
        QuotaCacheService._initialized = True
        QuotaCacheService._backend = MemoryBackend()
        yield
        QuotaCacheService._initialized = False
        QuotaCacheService._backend = None

    async def test_returns_default_when_plan_id_is_none(self):
        result = await QuotaCacheService.get_plan_credits_allocation_with_fallback(
            session=MagicMock(),
            plan_id=None,
        )
        assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

    async def test_returns_cached_value_when_available(self):
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
        plan_id = uuid4()
        mock_session = AsyncMock()
        mock_rule = MagicMock()
        mock_rule.credits_allocation = Decimal("7500.0")

        with patch("app.core.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=mock_rule)

            result = await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session=mock_session,
                plan_id=plan_id,
            )

            assert result == Decimal("7500.0")
            mock_db.get_by_plan_id.assert_called_once_with(mock_session, plan_id)

    async def test_updates_cache_after_db_fallback(self):
        plan_id = uuid4()
        mock_session = AsyncMock()
        mock_rule = MagicMock()
        mock_rule.credits_allocation = Decimal("7500.0")

        with patch("app.core.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=mock_rule)

            await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session=mock_session,
                plan_id=plan_id,
            )

            cached = await QuotaCacheService._backend.get_plan_credits_allocation(
                plan_id
            )
            assert cached == Decimal("7500.0")

    async def test_returns_default_when_db_returns_none(self):
        plan_id = uuid4()
        mock_session = AsyncMock()

        with patch("app.core.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=None)

            result = await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session=mock_session,
                plan_id=plan_id,
            )

            assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

    async def test_returns_default_when_cache_and_db_fail(self):
        plan_id = uuid4()
        mock_session = AsyncMock()

        # Make cache raise an exception
        QuotaCacheService._backend.get_plan_credits_allocation = AsyncMock(
            side_effect=Exception("Cache error")
        )

        with patch("app.core.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(side_effect=Exception("DB error"))

            result = await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session=mock_session,
                plan_id=plan_id,
            )

            assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

    async def test_returns_default_when_no_backend(self):
        QuotaCacheService._backend = None
        plan_id = uuid4()
        mock_session = AsyncMock()

        with patch("app.core.db.crud.quota.plan_pricing_rule_db") as mock_db:
            mock_db.get_by_plan_id = AsyncMock(return_value=None)

            result = await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session=mock_session,
                plan_id=plan_id,
            )

            assert result == QuotaCacheService.DEFAULT_PLAN_CREDITS

