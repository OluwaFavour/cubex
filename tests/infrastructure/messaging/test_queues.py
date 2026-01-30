"""
Test suite for RabbitMQ queue configurations.

Run tests:
    pytest app/tests/infrastructure/messaging/test_queues.py -v

Run with coverage:
    pytest app/tests/infrastructure/messaging/test_queues.py --cov=app.infrastructure.messaging.queues --cov-report=term-missing -v
"""

import pytest
from pydantic import ValidationError

from app.infrastructure.messaging.queues import (
    QueueConfig,
    RetryQueue,
    get_queue_configs,
)


class TestRetryQueue:
    """Test suite for RetryQueue model."""

    def test_retry_queue_creation(self):
        """Test creating a RetryQueue with valid data."""
        retry_queue = RetryQueue(name="test_retry", ttl=30000)

        assert retry_queue.name == "test_retry"
        assert retry_queue.ttl == 30000

    def test_retry_queue_ttl_must_be_positive(self):
        """Test that TTL must be greater than 0."""
        with pytest.raises(ValidationError) as exc_info:
            RetryQueue(name="test", ttl=0)

        assert "greater than 0" in str(exc_info.value).lower()

    def test_retry_queue_ttl_negative_rejected(self):
        """Test that negative TTL is rejected."""
        with pytest.raises(ValidationError):
            RetryQueue(name="test", ttl=-1000)


class TestQueueConfig:
    """Test suite for QueueConfig model."""

    def test_queue_config_minimal(self):
        """Test creating QueueConfig with minimal required fields."""

        def sample_handler(msg):
            pass

        config = QueueConfig(name="test_queue", handler=sample_handler)

        assert config.name == "test_queue"
        assert config.handler == sample_handler
        assert config.retry_queue is None
        assert config.retry_queues is None
        assert config.retry_ttl is None
        assert config.max_retries is None
        assert config.dead_letter_queue is None

    def test_queue_config_with_single_retry(self):
        """Test QueueConfig with single retry queue."""

        def sample_handler(msg):
            pass

        config = QueueConfig(
            name="test_queue",
            handler=sample_handler,
            retry_queue="test_retry",
            retry_ttl=60000,
            max_retries=5,
            dead_letter_queue="test_dead",
        )

        assert config.name == "test_queue"
        assert config.retry_queue == "test_retry"
        assert config.retry_ttl == 60000
        assert config.max_retries == 5
        assert config.dead_letter_queue == "test_dead"

    def test_queue_config_with_multiple_retries(self):
        """Test QueueConfig with multiple retry queues."""

        def sample_handler(msg):
            pass

        retry_queues = [
            RetryQueue(name="retry_30s", ttl=30000),
            RetryQueue(name="retry_5m", ttl=300000),
        ]

        config = QueueConfig(
            name="test_queue",
            handler=sample_handler,
            retry_queues=retry_queues,
            dead_letter_queue="test_dead",
        )

        assert config.name == "test_queue"
        assert len(config.retry_queues) == 2
        assert config.retry_queues[0].name == "retry_30s"
        assert config.retry_queues[1].ttl == 300000

    def test_queue_config_both_retry_types_raises_error(self):
        """Test that using both retry_queue and retry_queues raises ValueError."""

        def sample_handler(msg):
            pass

        with pytest.raises(ValidationError) as exc_info:
            QueueConfig(
                name="test_queue",
                handler=sample_handler,
                retry_queue="single_retry",
                retry_queues=[RetryQueue(name="multi_retry", ttl=30000)],
            )

        error_msg = str(exc_info.value).lower()
        assert "retry_queue" in error_msg or "retry_queues" in error_msg

    def test_queue_config_retry_queue_without_ttl_raises_error(self):
        """Test that retry_queue without retry_ttl raises ValueError."""

        def sample_handler(msg):
            pass

        with pytest.raises(ValidationError) as exc_info:
            QueueConfig(
                name="test_queue",
                handler=sample_handler,
                retry_queue="test_retry",
                # Missing retry_ttl
            )

        error_msg = str(exc_info.value).lower()
        assert "retry_ttl" in error_msg

    def test_queue_config_empty_retry_queues_raises_error(self):
        """Test that empty retry_queues list raises ValueError."""

        def sample_handler(msg):
            pass

        with pytest.raises(ValidationError) as exc_info:
            QueueConfig(name="test_queue", handler=sample_handler, retry_queues=[])

        error_msg = str(exc_info.value).lower()
        assert "retry_queues" in error_msg or "at least one" in error_msg

    def test_queue_config_max_retries_must_be_positive(self):
        """Test that max_retries must be greater than 0."""

        def sample_handler(msg):
            pass

        with pytest.raises(ValidationError):
            QueueConfig(
                name="test_queue",
                handler=sample_handler,
                retry_queue="test_retry",
                retry_ttl=30000,
                max_retries=0,
            )

    def test_queue_config_retry_ttl_must_be_positive(self):
        """Test that retry_ttl must be greater than 0."""

        def sample_handler(msg):
            pass

        with pytest.raises(ValidationError):
            QueueConfig(
                name="test_queue",
                handler=sample_handler,
                retry_queue="test_retry",
                retry_ttl=-1000,
            )


class TestGetQueueConfigs:
    """Test suite for get_queue_configs function."""

    def test_get_queue_configs_returns_list(self):
        """Test that get_queue_configs returns a list."""
        configs = get_queue_configs()

        assert isinstance(configs, list)

    def test_get_queue_configs_returns_empty_by_default(self):
        """Test that get_queue_configs returns empty list when no queues configured."""
        # Since QUEUE_CONFIG is empty by default
        configs = get_queue_configs()

        assert len(configs) == 0

    def test_get_queue_configs_cached(self):
        """Test that get_queue_configs uses lru_cache."""
        # Call twice and check they return the same object
        configs1 = get_queue_configs()
        configs2 = get_queue_configs()

        # Should be same instance due to caching
        assert configs1 is configs2

    def test_get_queue_configs_with_data(self):
        """Test get_queue_configs with actual queue configurations."""
        from app.infrastructure.messaging import queues as queues_module

        def test_handler(msg):
            pass

        # Temporarily modify QUEUE_CONFIG
        original_config = queues_module.QUEUE_CONFIG.copy()
        try:
            queues_module.QUEUE_CONFIG.clear()
            queues_module.QUEUE_CONFIG.append(
                {
                    "name": "test_queue",
                    "handler": test_handler,
                    "retry_queue": "test_retry",
                    "retry_ttl": 60000,
                    "max_retries": 3,
                }
            )

            # Clear cache
            get_queue_configs.cache_clear()

            configs = get_queue_configs()

            assert len(configs) == 1
            assert isinstance(configs[0], QueueConfig)
            assert configs[0].name == "test_queue"
            assert configs[0].max_retries == 3
        finally:
            # Restore original config
            queues_module.QUEUE_CONFIG.clear()
            queues_module.QUEUE_CONFIG.extend(original_config)
            get_queue_configs.cache_clear()

    def test_queue_config_model_validate_with_dict(self):
        """Test that QueueConfig can be validated from a dictionary."""

        def test_handler(msg):
            pass

        config_dict = {
            "name": "test_queue",
            "handler": test_handler,
            "dead_letter_queue": "test_dead",
        }

        config = QueueConfig.model_validate(config_dict, from_attributes=True)

        assert config.name == "test_queue"
        assert config.handler == test_handler
        assert config.dead_letter_queue == "test_dead"
