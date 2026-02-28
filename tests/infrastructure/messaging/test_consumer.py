"""
Test suite for RabbitMQ message consumer.

Run tests:
    pytest app/tests/infrastructure/messaging/test_consumer.py -v

Run with coverage:
    pytest app/tests/infrastructure/messaging/test_consumer.py --cov=app.infrastructure.messaging.consumer --cov-report=term-missing -v
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
import aio_pika

from app.infrastructure.messaging.consumer import process_message


class TestProcessMessage:

    @pytest.mark.asyncio
    async def test_process_message_success(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"user_id": 123}).encode()
        mock_message.headers = {}

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        handler_called = []

        async def test_handler(event):
            handler_called.append(event)

        mock_channel = AsyncMock(spec=aio_pika.Channel)

        await process_message(mock_message, test_handler, mock_channel)

        assert len(handler_called) == 1
        assert handler_called[0] == {"user_id": 123}

        # Verify message was not rejected (no exception)
        mock_message.reject.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_handler_exception_no_retry(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"data": "test"}).encode()
        mock_message.headers = {}

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise ValueError("Processing failed")

        mock_channel = AsyncMock(spec=aio_pika.Channel)

        await process_message(mock_message, failing_handler, mock_channel)

        mock_message.reject.assert_called_once_with(requeue=False)

    @pytest.mark.asyncio
    async def test_process_message_retry_with_single_retry_queue(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"data": "test"}).encode()
        mock_message.headers = {}

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise Exception("Temporary failure")

        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_exchange = AsyncMock()
        mock_channel.default_exchange = mock_exchange

        await process_message(
            mock_message,
            failing_handler,
            mock_channel,
            retry_queue="test_retry",
            max_retries=3,
        )

        mock_exchange.publish.assert_called_once()
        call_args = mock_exchange.publish.call_args
        assert call_args.kwargs["routing_key"] == "test_retry"

        mock_message.reject.assert_called_once_with(requeue=False)

    @pytest.mark.asyncio
    async def test_process_message_retry_increments_attempt(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"data": "test"}).encode()
        mock_message.headers = {"x-retry-attempt": 2}

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise Exception("Failure")

        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_exchange = AsyncMock()
        mock_channel.default_exchange = mock_exchange

        with patch("aio_pika.Message") as mock_message_class:
            await process_message(
                mock_message,
                failing_handler,
                mock_channel,
                retry_queue="test_retry",
                max_retries=5,
            )

            call_kwargs = mock_message_class.call_args[1]
            assert call_kwargs["headers"]["x-retry-attempt"] == 3

    @pytest.mark.asyncio
    async def test_process_message_max_retries_exceeded(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"data": "test"}).encode()
        mock_message.headers = {"x-retry-attempt": 5}  # Already at max

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise Exception("Failure")

        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_exchange = AsyncMock()
        mock_channel.default_exchange = mock_exchange

        await process_message(
            mock_message,
            failing_handler,
            mock_channel,
            retry_queue="test_retry",
            max_retries=5,
        )

        # Should not publish to retry queue
        mock_exchange.publish.assert_not_called()
        mock_message.reject.assert_called_once_with(requeue=False)

    @pytest.mark.asyncio
    async def test_process_message_dead_letter_queue(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"data": "test"}).encode()
        mock_message.headers = {"x-retry-attempt": 5}

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise Exception("Permanent failure")

        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_exchange = AsyncMock()
        mock_channel.default_exchange = mock_exchange

        await process_message(
            mock_message,
            failing_handler,
            mock_channel,
            retry_queue="test_retry",
            max_retries=5,
            dead_letter_queue="test_dead",
        )

        mock_exchange.publish.assert_called_once()
        call_args = mock_exchange.publish.call_args
        assert call_args.kwargs["routing_key"] == "test_dead"

    @pytest.mark.asyncio
    async def test_process_message_multiple_retry_queues(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"data": "test"}).encode()
        mock_message.headers = {"x-retry-attempt": 1}

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise Exception("Failure")

        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_exchange = AsyncMock()
        mock_channel.default_exchange = mock_exchange

        retry_queues = [
            {"name": "retry_30s", "ttl": 30000},
            {"name": "retry_5m", "ttl": 300000},
            {"name": "retry_1h", "ttl": 3600000},
        ]

        await process_message(
            mock_message, failing_handler, mock_channel, retry_queues=retry_queues
        )

        # Should route to second retry queue (attempt 1)
        call_args = mock_exchange.publish.call_args
        assert call_args.kwargs["routing_key"] == "retry_5m"

    @pytest.mark.asyncio
    async def test_process_message_multiple_retries_exhausted(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"data": "test"}).encode()
        mock_message.headers = {"x-retry-attempt": 3}  # Beyond retry_queues length

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise Exception("Failure")

        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_exchange = AsyncMock()
        mock_channel.default_exchange = mock_exchange

        retry_queues = [
            {"name": "retry_30s", "ttl": 30000},
            {"name": "retry_5m", "ttl": 300000},
        ]

        await process_message(
            mock_message,
            failing_handler,
            mock_channel,
            retry_queues=retry_queues,
            dead_letter_queue="test_dead",
        )

        # Should route to dead letter queue
        call_args = mock_exchange.publish.call_args
        assert call_args.kwargs["routing_key"] == "test_dead"

    @pytest.mark.asyncio
    async def test_process_message_no_retry_attempt_header(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"data": "test"}).encode()
        mock_message.headers = None  # No headers

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise Exception("Failure")

        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_exchange = AsyncMock()
        mock_channel.default_exchange = mock_exchange

        with patch("aio_pika.Message") as mock_message_class:
            await process_message(
                mock_message,
                failing_handler,
                mock_channel,
                retry_queue="test_retry",
                max_retries=3,
            )

            # Should default attempt to 0
            call_kwargs = mock_message_class.call_args[1]
            assert call_kwargs["headers"]["x-retry-attempt"] == 1

    @pytest.mark.asyncio
    async def test_process_message_preserves_body(self):
        original_body = json.dumps({"complex": {"data": [1, 2, 3]}}).encode()
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = original_body
        mock_message.headers = {}

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise Exception("Failure")

        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_exchange = AsyncMock()
        mock_channel.default_exchange = mock_exchange

        with patch("aio_pika.Message") as mock_message_class:
            await process_message(
                mock_message,
                failing_handler,
                mock_channel,
                retry_queue="test_retry",
                max_retries=3,
            )

            call_kwargs = mock_message_class.call_args[1]
            assert call_kwargs["body"] == original_body

    @pytest.mark.asyncio
    async def test_process_message_persistent_delivery_on_retry(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"data": "test"}).encode()
        mock_message.headers = {}

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise Exception("Failure")

        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_exchange = AsyncMock()
        mock_channel.default_exchange = mock_exchange

        with patch("aio_pika.Message") as mock_message_class:
            await process_message(
                mock_message, failing_handler, mock_channel, retry_queue="test_retry"
            )

            call_kwargs = mock_message_class.call_args[1]
            assert call_kwargs["delivery_mode"] == aio_pika.DeliveryMode.PERSISTENT


class TestDeadLetterHeaderEnrichment:
    """Tests for x-error-message and x-original-queue headers added during dead-lettering."""

    @pytest.mark.asyncio
    async def test_dead_letter_includes_error_message_header(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"data": "test"}).encode()
        mock_message.headers = {"x-retry-attempt": 3}

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise ValueError("Connection timed out")

        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_exchange = AsyncMock()
        mock_channel.default_exchange = mock_exchange

        with patch(
            "app.infrastructure.messaging.consumer.EmailManagerService"
        ) as mock_email:
            mock_email.send_dlq_alert = AsyncMock()
            with patch("aio_pika.Message") as mock_msg_cls:
                await process_message(
                    mock_message,
                    failing_handler,
                    mock_channel,
                    max_retries=3,
                    dead_letter_queue="test_dead",
                )

                call_kwargs = mock_msg_cls.call_args[1]
                assert (
                    call_kwargs["headers"]["x-error-message"] == "Connection timed out"
                )

    @pytest.mark.asyncio
    async def test_dead_letter_includes_original_queue_header(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"data": "test"}).encode()
        mock_message.headers = {"x-retry-attempt": 3}

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise Exception("Failure")

        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_exchange = AsyncMock()
        mock_channel.default_exchange = mock_exchange

        with patch(
            "app.infrastructure.messaging.consumer.EmailManagerService"
        ) as mock_email:
            mock_email.send_dlq_alert = AsyncMock()
            with patch("aio_pika.Message") as mock_msg_cls:
                await process_message(
                    mock_message,
                    failing_handler,
                    mock_channel,
                    max_retries=3,
                    dead_letter_queue="otp_emails_dead",
                )

                call_kwargs = mock_msg_cls.call_args[1]
                assert call_kwargs["headers"]["x-original-queue"] == "otp_emails"

    @pytest.mark.asyncio
    async def test_dead_letter_no_original_queue_for_non_dead_suffix(self):
        mock_message = AsyncMock(spec=aio_pika.IncomingMessage)
        mock_message.body = json.dumps({"data": "test"}).encode()
        mock_message.headers = {"x-retry-attempt": 3}

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        mock_message.process.return_value = mock_context

        async def failing_handler(event):
            raise Exception("Failure")

        mock_channel = AsyncMock(spec=aio_pika.Channel)
        mock_exchange = AsyncMock()
        mock_channel.default_exchange = mock_exchange

        with patch(
            "app.infrastructure.messaging.consumer.EmailManagerService"
        ) as mock_email:
            mock_email.send_dlq_alert = AsyncMock()
            with patch("aio_pika.Message") as mock_msg_cls:
                await process_message(
                    mock_message,
                    failing_handler,
                    mock_channel,
                    max_retries=3,
                    dead_letter_queue="custom_dlq",
                )

                call_kwargs = mock_msg_cls.call_args[1]
                assert "x-original-queue" not in call_kwargs["headers"]
