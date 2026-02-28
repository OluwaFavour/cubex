"""
Test suite for RabbitMQ consumer startup and queue management.

Run tests:
    pytest app/tests/infrastructure/messaging/test_main.py -v

Run with coverage:
    pytest app/tests/infrastructure/messaging/test_main.py --cov=app.infrastructure.messaging.main --cov-report=term-missing -v
"""

import asyncio
from functools import partial
from unittest.mock import AsyncMock, patch

import pytest
import aio_pika

from app.infrastructure.messaging.main import start_consumers
from app.infrastructure.messaging.queues import QueueConfig, RetryQueue


class TestStartConsumers:

    @pytest.mark.asyncio
    async def test_start_consumers_basic_setup(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_queue = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.set_qos = AsyncMock()
        mock_channel.declare_queue = AsyncMock(return_value=mock_queue)
        mock_queue.consume = AsyncMock()

        def sample_handler(msg):
            pass

        queue_config = QueueConfig(name="test_queue", handler=sample_handler)

        with (
            patch(
                "app.infrastructure.messaging.main.get_connection",
                new_callable=AsyncMock,
            ) as mock_get_conn,
            patch(
                "app.infrastructure.messaging.main.get_queue_configs"
            ) as mock_get_configs,
        ):
            mock_get_conn.return_value = mock_connection
            mock_get_configs.return_value = [queue_config]

            # Test with keep_alive=False to return immediately
            result = await start_consumers(keep_alive=False)

            mock_get_conn.assert_called_once()
            mock_connection.channel.assert_called_once()
            mock_channel.set_qos.assert_called_once_with(prefetch_count=10)

            mock_channel.declare_queue.assert_called_once_with(
                "test_queue", durable=True
            )

            mock_queue.consume.assert_called_once()
            consume_args = mock_queue.consume.call_args
            assert consume_args.kwargs["no_ack"] is False

            assert result == mock_connection

    @pytest.mark.asyncio
    async def test_start_consumers_with_single_retry_queue(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_main_queue = AsyncMock()
        mock_retry_queue = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.set_qos = AsyncMock()

        # Return different mocks for main and retry queue
        queue_returns = [mock_main_queue, mock_retry_queue]
        mock_channel.declare_queue = AsyncMock(side_effect=queue_returns)
        mock_main_queue.consume = AsyncMock()

        def sample_handler(msg):
            pass

        queue_config = QueueConfig(
            name="test_queue",
            handler=sample_handler,
            retry_queue="test_queue_retry",
            retry_ttl=30000,
            max_retries=3,
        )

        with (
            patch(
                "app.infrastructure.messaging.main.get_connection",
                new_callable=AsyncMock,
            ) as mock_get_conn,
            patch(
                "app.infrastructure.messaging.main.get_queue_configs"
            ) as mock_get_configs,
        ):
            mock_get_conn.return_value = mock_connection
            mock_get_configs.return_value = [queue_config]

            result = await start_consumers(keep_alive=False)

            assert mock_channel.declare_queue.call_count == 2

            main_call = mock_channel.declare_queue.call_args_list[0]
            assert main_call.args[0] == "test_queue"
            assert main_call.kwargs["durable"] is True

            retry_call = mock_channel.declare_queue.call_args_list[1]
            assert retry_call.args[0] == "test_queue_retry"
            assert retry_call.kwargs["durable"] is True
            assert retry_call.kwargs["arguments"]["x-message-ttl"] == 30000
            assert retry_call.kwargs["arguments"]["x-dead-letter-exchange"] == ""
            assert (
                retry_call.kwargs["arguments"]["x-dead-letter-routing-key"]
                == "test_queue"
            )

            assert result == mock_connection

    @pytest.mark.asyncio
    async def test_start_consumers_with_multiple_retry_queues(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_main_queue = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.set_qos = AsyncMock()

        # Return mock queues for main + 3 retry queues
        queue_returns = [mock_main_queue, AsyncMock(), AsyncMock(), AsyncMock()]
        mock_channel.declare_queue = AsyncMock(side_effect=queue_returns)
        mock_main_queue.consume = AsyncMock()

        def sample_handler(msg):
            pass

        queue_config = QueueConfig(
            name="test_queue",
            handler=sample_handler,
            retry_queues=[
                RetryQueue(name="test_retry_30s", ttl=30000),
                RetryQueue(name="test_retry_5m", ttl=300000),
                RetryQueue(name="test_retry_1h", ttl=3600000),
            ],
        )

        with (
            patch(
                "app.infrastructure.messaging.main.get_connection",
                new_callable=AsyncMock,
            ) as mock_get_conn,
            patch(
                "app.infrastructure.messaging.main.get_queue_configs"
            ) as mock_get_configs,
        ):
            mock_get_conn.return_value = mock_connection
            mock_get_configs.return_value = [queue_config]

            result = await start_consumers(keep_alive=False)

            assert mock_channel.declare_queue.call_count == 4

            main_call = mock_channel.declare_queue.call_args_list[0]
            assert main_call.args[0] == "test_queue"

            # Verify first retry queue (30s)
            retry1_call = mock_channel.declare_queue.call_args_list[1]
            assert retry1_call.args[0] == "test_retry_30s"
            assert retry1_call.kwargs["arguments"]["x-message-ttl"] == 30000
            assert (
                retry1_call.kwargs["arguments"]["x-dead-letter-routing-key"]
                == "test_queue"
            )

            # Verify second retry queue (5m)
            retry2_call = mock_channel.declare_queue.call_args_list[2]
            assert retry2_call.args[0] == "test_retry_5m"
            assert retry2_call.kwargs["arguments"]["x-message-ttl"] == 300000

            # Verify third retry queue (1h)
            retry3_call = mock_channel.declare_queue.call_args_list[3]
            assert retry3_call.args[0] == "test_retry_1h"
            assert retry3_call.kwargs["arguments"]["x-message-ttl"] == 3600000

            assert result == mock_connection

    @pytest.mark.asyncio
    async def test_start_consumers_with_dead_letter_queue(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_main_queue = AsyncMock()
        mock_dlx_queue = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.set_qos = AsyncMock()

        queue_returns = [mock_main_queue, mock_dlx_queue]
        mock_channel.declare_queue = AsyncMock(side_effect=queue_returns)
        mock_main_queue.consume = AsyncMock()

        def sample_handler(msg):
            pass

        queue_config = QueueConfig(
            name="test_queue",
            handler=sample_handler,
            dead_letter_queue="test_queue_dead",
        )

        with (
            patch(
                "app.infrastructure.messaging.main.get_connection",
                new_callable=AsyncMock,
            ) as mock_get_conn,
            patch(
                "app.infrastructure.messaging.main.get_queue_configs"
            ) as mock_get_configs,
        ):
            mock_get_conn.return_value = mock_connection
            mock_get_configs.return_value = [queue_config]

            result = await start_consumers(keep_alive=False)

            assert mock_channel.declare_queue.call_count == 2

            dlx_call = mock_channel.declare_queue.call_args_list[1]
            assert dlx_call.args[0] == "test_queue_dead"
            assert dlx_call.kwargs["durable"] is True
            # No special arguments for DLX queue
            assert "arguments" not in dlx_call.kwargs

            assert result == mock_connection

    @pytest.mark.asyncio
    async def test_start_consumers_registers_consumer_with_correct_handler(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_main_queue = AsyncMock()
        mock_dlq_queue = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.set_qos = AsyncMock()

        # Return different mock queues for main vs dead-letter declarations
        queue_mocks = {
            "test_queue": mock_main_queue,
            "test_dead": mock_dlq_queue,
        }
        mock_channel.declare_queue = AsyncMock(
            side_effect=lambda name, **kw: queue_mocks.get(name, AsyncMock())
        )

        def sample_handler(msg):
            pass

        queue_config = QueueConfig(
            name="test_queue",
            handler=sample_handler,
            retry_queue="test_retry",
            retry_ttl=60000,
            max_retries=5,
            dead_letter_queue="test_dead",
        )

        with (
            patch(
                "app.infrastructure.messaging.main.get_connection",
                new_callable=AsyncMock,
            ) as mock_get_conn,
            patch(
                "app.infrastructure.messaging.main.get_queue_configs"
            ) as mock_get_configs,
        ):
            mock_get_conn.return_value = mock_connection
            mock_get_configs.return_value = [queue_config]

            result = await start_consumers(keep_alive=False)

            # Main queue consumer
            mock_main_queue.consume.assert_called_once()
            consume_call = mock_main_queue.consume.call_args

            consumer_callback = consume_call.args[0]
            assert isinstance(consumer_callback, partial)

            assert consumer_callback.func.__name__ == "process_message"
            assert consumer_callback.keywords["handler"] == sample_handler
            assert consumer_callback.keywords["channel"] == mock_channel
            assert consumer_callback.keywords["retry_queue"] == "test_retry"
            assert consumer_callback.keywords["retry_queues"] is None
            assert consumer_callback.keywords["max_retries"] == 5
            assert consumer_callback.keywords["dead_letter_queue"] == "test_dead"

            assert consume_call.kwargs["no_ack"] is False

            # DLQ consumer
            mock_dlq_queue.consume.assert_called_once()
            dlq_call = mock_dlq_queue.consume.call_args
            dlq_callback = dlq_call.args[0]
            assert isinstance(dlq_callback, partial)
            assert dlq_callback.func.__name__ == "handle_dlq_message"
            assert dlq_callback.keywords["queue_name"] == "test_dead"
            assert dlq_call.kwargs["no_ack"] is False

            assert result == mock_connection

    @pytest.mark.asyncio
    async def test_start_consumers_multiple_queues(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.set_qos = AsyncMock()

        mock_queue1 = AsyncMock()
        mock_queue2 = AsyncMock()
        queue_returns = [mock_queue1, mock_queue2]
        mock_channel.declare_queue = AsyncMock(side_effect=queue_returns)
        mock_queue1.consume = AsyncMock()
        mock_queue2.consume = AsyncMock()

        def handler1(msg):
            pass

        def handler2(msg):
            pass

        queue_configs = [
            QueueConfig(name="queue1", handler=handler1),
            QueueConfig(name="queue2", handler=handler2),
        ]

        with (
            patch(
                "app.infrastructure.messaging.main.get_connection",
                new_callable=AsyncMock,
            ) as mock_get_conn,
            patch(
                "app.infrastructure.messaging.main.get_queue_configs"
            ) as mock_get_configs,
        ):
            mock_get_conn.return_value = mock_connection
            mock_get_configs.return_value = queue_configs

            result = await start_consumers(keep_alive=False)

            assert mock_channel.declare_queue.call_count == 2
            assert mock_channel.declare_queue.call_args_list[0].args[0] == "queue1"
            assert mock_channel.declare_queue.call_args_list[1].args[0] == "queue2"

            mock_queue1.consume.assert_called_once()
            mock_queue2.consume.assert_called_once()

            assert result == mock_connection

    @pytest.mark.asyncio
    async def test_start_consumers_qos_setting(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_queue = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.set_qos = AsyncMock()
        mock_channel.declare_queue = AsyncMock(return_value=mock_queue)
        mock_queue.consume = AsyncMock()

        def sample_handler(msg):
            pass

        queue_config = QueueConfig(name="test_queue", handler=sample_handler)

        with (
            patch(
                "app.infrastructure.messaging.main.get_connection",
                new_callable=AsyncMock,
            ) as mock_get_conn,
            patch(
                "app.infrastructure.messaging.main.get_queue_configs"
            ) as mock_get_configs,
        ):
            mock_get_conn.return_value = mock_connection
            mock_get_configs.return_value = [queue_config]

            await start_consumers(keep_alive=False)

            mock_channel.set_qos.assert_called_once_with(prefetch_count=10)

    @pytest.mark.asyncio
    async def test_start_consumers_keep_alive_true_runs_forever(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_queue = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.set_qos = AsyncMock()
        mock_channel.declare_queue = AsyncMock(return_value=mock_queue)
        mock_queue.consume = AsyncMock()
        mock_connection.close = AsyncMock()

        def sample_handler(msg):
            pass

        queue_config = QueueConfig(name="test_queue", handler=sample_handler)

        future = asyncio.Future()

        async def cancel_future():
            await asyncio.sleep(0.1)
            future.cancel()

        with (
            patch(
                "app.infrastructure.messaging.main.get_connection",
                new_callable=AsyncMock,
            ) as mock_get_conn,
            patch(
                "app.infrastructure.messaging.main.get_queue_configs"
            ) as mock_get_configs,
            patch("asyncio.Future", return_value=future),
        ):
            mock_get_conn.return_value = mock_connection
            mock_get_configs.return_value = [queue_config]

            # Start the cancellation in background
            asyncio.create_task(cancel_future())

            # This should run forever but be cancelled
            with pytest.raises(asyncio.CancelledError):
                await start_consumers(keep_alive=True)

            mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_consumers_retry_queues_converted_to_dict(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_queue = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.set_qos = AsyncMock()

        # Return mocks for main + 2 retry queues
        queue_returns = [mock_queue, AsyncMock(), AsyncMock()]
        mock_channel.declare_queue = AsyncMock(side_effect=queue_returns)
        mock_queue.consume = AsyncMock()

        def sample_handler(msg):
            pass

        queue_config = QueueConfig(
            name="test_queue",
            handler=sample_handler,
            retry_queues=[
                RetryQueue(name="retry1", ttl=30000),
                RetryQueue(name="retry2", ttl=60000),
            ],
        )

        with (
            patch(
                "app.infrastructure.messaging.main.get_connection",
                new_callable=AsyncMock,
            ) as mock_get_conn,
            patch(
                "app.infrastructure.messaging.main.get_queue_configs"
            ) as mock_get_configs,
        ):
            mock_get_conn.return_value = mock_connection
            mock_get_configs.return_value = [queue_config]

            await start_consumers(keep_alive=False)

            mock_queue.consume.assert_called_once()
            consumer_callback = mock_queue.consume.call_args.args[0]

            retry_queues = consumer_callback.keywords["retry_queues"]
            assert retry_queues == [
                {"name": "retry1", "ttl": 30000},
                {"name": "retry2", "ttl": 60000},
            ]

    @pytest.mark.asyncio
    async def test_start_consumers_complete_configuration(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.set_qos = AsyncMock()

        # Main + 2 retry + DLX = 4 queues
        queue_returns = [AsyncMock() for _ in range(4)]
        mock_channel.declare_queue = AsyncMock(side_effect=queue_returns)
        queue_returns[0].consume = AsyncMock()

        def sample_handler(msg):
            pass

        queue_config = QueueConfig(
            name="main_queue",
            handler=sample_handler,
            retry_queues=[
                RetryQueue(name="retry_30s", ttl=30000),
                RetryQueue(name="retry_5m", ttl=300000),
            ],
            dead_letter_queue="main_queue_dead",
        )

        with (
            patch(
                "app.infrastructure.messaging.main.get_connection",
                new_callable=AsyncMock,
            ) as mock_get_conn,
            patch(
                "app.infrastructure.messaging.main.get_queue_configs"
            ) as mock_get_configs,
        ):
            mock_get_conn.return_value = mock_connection
            mock_get_configs.return_value = [queue_config]

            result = await start_consumers(keep_alive=False)

            assert mock_channel.declare_queue.call_count == 4

            call_args_list = mock_channel.declare_queue.call_args_list
            assert call_args_list[0].args[0] == "main_queue"
            assert call_args_list[1].args[0] == "retry_30s"
            assert call_args_list[2].args[0] == "retry_5m"
            assert call_args_list[3].args[0] == "main_queue_dead"

            queue_returns[0].consume.assert_called_once()

            assert result == mock_connection
