"""
Test suite for RabbitMQ message publisher.

Run tests:
    pytest app/tests/infrastructure/messaging/test_publisher.py -v

Run with coverage:
    pytest app/tests/infrastructure/messaging/test_publisher.py --cov=app.infrastructure.messaging.publisher --cov-report=term-missing -v
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aio_pika

from app.infrastructure.messaging.publisher import publish_event


class TestPublishEvent:

    @pytest.mark.asyncio
    async def test_publish_event_basic(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_queue = AsyncMock()
        mock_exchange = AsyncMock()

        # Make channel() awaitable
        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.declare_queue.return_value = mock_queue
        mock_channel.default_exchange = mock_exchange

        event_data = {"user_id": 123, "action": "login"}
        queue_name = "test_queue"

        with patch(
            "app.infrastructure.messaging.publisher.get_connection",
            new_callable=AsyncMock,
        ) as mock_get_conn:
            mock_get_conn.return_value = mock_connection

            await publish_event(queue_name, event_data)

            mock_get_conn.assert_called_once()
            mock_connection.channel.assert_called_once()

            mock_channel.declare_queue.assert_called_once_with(queue_name, durable=True)

            mock_exchange.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_event_with_headers(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_queue = AsyncMock()
        mock_exchange = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.declare_queue.return_value = mock_queue
        mock_channel.default_exchange = mock_exchange

        event_data = {"data": "test"}
        headers = {"x-custom-header": "value", "x-priority": "high"}

        with patch(
            "app.infrastructure.messaging.publisher.get_connection",
            new_callable=AsyncMock,
        ) as mock_get_conn:
            mock_get_conn.return_value = mock_connection

            await publish_event("test_queue", event_data, headers)

            mock_exchange.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_event_message_format(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_queue = AsyncMock()
        mock_exchange = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.declare_queue.return_value = mock_queue
        mock_channel.default_exchange = mock_exchange

        event_data = {"key": "value"}

        with patch(
            "app.infrastructure.messaging.publisher.get_connection",
            new_callable=AsyncMock,
        ) as mock_get_conn, patch("aio_pika.Message") as mock_message_class:
            mock_get_conn.return_value = mock_connection
            mock_message_instance = MagicMock()
            mock_message_class.return_value = mock_message_instance

            await publish_event("test_queue", event_data)

            mock_message_class.assert_called_once()
            call_kwargs = mock_message_class.call_args[1]

            assert call_kwargs["body"] == json.dumps(event_data).encode()
            assert call_kwargs["content_type"] == "application/json"
            assert call_kwargs["delivery_mode"] == aio_pika.DeliveryMode.PERSISTENT
            assert call_kwargs["headers"] == {}

    @pytest.mark.asyncio
    async def test_publish_event_persistent_delivery(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_queue = AsyncMock()
        mock_exchange = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.declare_queue.return_value = mock_queue
        mock_channel.default_exchange = mock_exchange

        with patch(
            "app.infrastructure.messaging.publisher.get_connection",
            new_callable=AsyncMock,
        ) as mock_get_conn, patch("aio_pika.Message") as mock_message_class:
            mock_get_conn.return_value = mock_connection
            mock_message_instance = MagicMock()
            mock_message_class.return_value = mock_message_instance

            await publish_event("test_queue", {"data": "test"})

            call_kwargs = mock_message_class.call_args[1]
            assert call_kwargs["delivery_mode"] == aio_pika.DeliveryMode.PERSISTENT

    @pytest.mark.asyncio
    async def test_publish_event_routing_key(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_queue = AsyncMock()
        mock_exchange = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.declare_queue.return_value = mock_queue
        mock_channel.default_exchange = mock_exchange

        queue_name = "my_custom_queue"

        with patch(
            "app.infrastructure.messaging.publisher.get_connection",
            new_callable=AsyncMock,
        ) as mock_get_conn:
            mock_get_conn.return_value = mock_connection

            await publish_event(queue_name, {"data": "test"})

            call_args = mock_exchange.publish.call_args
            assert call_args.kwargs["routing_key"] == queue_name

    @pytest.mark.asyncio
    async def test_publish_event_complex_data(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_queue = AsyncMock()
        mock_exchange = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.declare_queue.return_value = mock_queue
        mock_channel.default_exchange = mock_exchange

        complex_event = {
            "user": {
                "id": 123,
                "email": "test@example.com",
                "metadata": {"role": "admin"},
            },
            "items": [1, 2, 3],
            "timestamp": "2024-01-01T00:00:00Z",
        }

        with patch(
            "app.infrastructure.messaging.publisher.get_connection",
            new_callable=AsyncMock,
        ) as mock_get_conn, patch("aio_pika.Message") as mock_message_class:
            mock_get_conn.return_value = mock_connection

            await publish_event("test_queue", complex_event)

            call_kwargs = mock_message_class.call_args[1]
            decoded = json.loads(call_kwargs["body"].decode())
            assert decoded == complex_event

    @pytest.mark.asyncio
    async def test_publish_event_default_headers(self):
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_queue = AsyncMock()
        mock_exchange = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.declare_queue.return_value = mock_queue
        mock_channel.default_exchange = mock_exchange

        with patch(
            "app.infrastructure.messaging.publisher.get_connection",
            new_callable=AsyncMock,
        ) as mock_get_conn, patch("aio_pika.Message") as mock_message_class:
            mock_get_conn.return_value = mock_connection

            # Call without headers parameter
            await publish_event("test_queue", {"data": "test"})

            call_kwargs = mock_message_class.call_args[1]
            assert call_kwargs["headers"] == {}

