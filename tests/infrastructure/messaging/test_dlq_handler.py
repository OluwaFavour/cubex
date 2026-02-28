"""
Test suite for the dead-letter queue message handler.

Run tests:
    pytest tests/infrastructure/messaging/test_dlq_handler.py -v

Run with coverage:
    pytest tests/infrastructure/messaging/test_dlq_handler.py --cov=app.infrastructure.messaging.handlers.dlq_handler --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aio_pika

from app.infrastructure.messaging.handlers.dlq_handler import (
    _sanitise_headers,
    handle_dlq_message,
)
from app.core.enums import DLQMessageStatus

# ---------------------------------------------------------------------------
# _sanitise_headers
# ---------------------------------------------------------------------------


class TestSanitiseHeaders:

    def test_bytes_values_decoded(self):
        headers = {"x-error-message": b"connection reset"}
        result = _sanitise_headers(headers)
        assert result == {"x-error-message": "connection reset"}

    def test_string_values_preserved(self):
        headers = {"x-original-queue": "otp_emails"}
        result = _sanitise_headers(headers)
        assert result == {"x-original-queue": "otp_emails"}

    def test_int_values_preserved(self):
        headers = {"x-retry-attempt": 3}
        result = _sanitise_headers(headers)
        assert result == {"x-retry-attempt": 3}

    def test_float_values_preserved(self):
        headers = {"x-delay": 30.5}
        result = _sanitise_headers(headers)
        assert result == {"x-delay": 30.5}

    def test_bool_values_preserved(self):
        headers = {"x-redelivered": True}
        result = _sanitise_headers(headers)
        assert result == {"x-redelivered": True}

    def test_none_values_preserved(self):
        headers = {"x-optional": None}
        result = _sanitise_headers(headers)
        assert result == {"x-optional": None}

    def test_other_types_stringified(self):
        headers = {"x-custom": ["a", "b"]}
        result = _sanitise_headers(headers)
        assert result == {"x-custom": "['a', 'b']"}

    def test_empty_headers(self):
        assert _sanitise_headers({}) == {}

    def test_mixed_types(self):
        headers = {
            "x-retry-attempt": 2,
            "x-error-message": b"timeout",
            "x-original-queue": "emails",
            "x-flag": True,
            "x-nothing": None,
        }
        result = _sanitise_headers(headers)
        assert result == {
            "x-retry-attempt": 2,
            "x-error-message": "timeout",
            "x-original-queue": "emails",
            "x-flag": True,
            "x-nothing": None,
        }

    def test_non_utf8_bytes_use_replace(self):
        headers = {"x-bad": b"\xff\xfe"}
        result = _sanitise_headers(headers)
        # Should not raise — `errors="replace"` is used
        assert isinstance(result["x-bad"], str)


# ---------------------------------------------------------------------------
# handle_dlq_message
# ---------------------------------------------------------------------------


class TestHandleDLQMessage:

    def _make_message(
        self,
        body: str = '{"user_id": 1}',
        headers: dict | None = None,
    ) -> AsyncMock:
        """Create a mock aio_pika.IncomingMessage."""
        msg = AsyncMock(spec=aio_pika.IncomingMessage)
        msg.body = body.encode("utf-8")
        msg.headers = headers or {}

        # Set up async context manager for message.process()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        msg.process.return_value = ctx

        return msg

    @staticmethod
    def _patch_session():
        """Create a mock AsyncSessionLocal that works as `async with AsyncSessionLocal() as session:`."""
        mock_session = MagicMock()

        # session.begin() is a sync call returning an async context manager
        begin_ctx = MagicMock()
        begin_ctx.__aenter__ = AsyncMock()
        begin_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.begin.return_value = begin_ctx

        # AsyncSessionLocal() → async context manager yielding mock_session
        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        patcher = patch(
            "app.infrastructure.messaging.handlers.dlq_handler.AsyncSessionLocal",
            return_value=session_ctx,
        )
        return patcher, mock_session

    @pytest.mark.asyncio
    async def test_persists_basic_message(self):
        """Handler should persist a DLQ message row and ACK."""
        patcher, mock_session = self._patch_session()
        with patcher:
            msg = self._make_message()
            await handle_dlq_message(msg, queue_name="otp_emails_dead")

        # session.add was called with a DLQMessage
        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.queue_name == "otp_emails_dead"
        assert added_obj.message_body == '{"user_id": 1}'
        assert added_obj.status == DLQMessageStatus.PENDING

        # The message should NOT be rejected (ACK via process context)
        msg.reject.assert_not_called()

    @pytest.mark.asyncio
    async def test_extracts_retry_attempt(self):
        patcher, mock_session = self._patch_session()
        with patcher:
            msg = self._make_message(headers={"x-retry-attempt": 5})
            await handle_dlq_message(msg, queue_name="stripe_checkout_completed_dead")

        added = mock_session.add.call_args[0][0]
        assert added.attempt_count == 5

    @pytest.mark.asyncio
    async def test_extracts_error_message_string(self):
        patcher, mock_session = self._patch_session()
        with patcher:
            msg = self._make_message(
                headers={"x-error-message": "Connection reset by peer"}
            )
            await handle_dlq_message(msg, queue_name="otp_emails_dead")

        added = mock_session.add.call_args[0][0]
        assert added.error_message == "Connection reset by peer"

    @pytest.mark.asyncio
    async def test_extracts_error_message_bytes(self):
        patcher, mock_session = self._patch_session()
        with patcher:
            msg = self._make_message(headers={"x-error-message": b"timeout exceeded"})
            await handle_dlq_message(msg, queue_name="otp_emails_dead")

        added = mock_session.add.call_args[0][0]
        assert added.error_message == "timeout exceeded"

    @pytest.mark.asyncio
    async def test_extracts_error_message_other_type(self):
        """Non-bytes, non-str error_message should be cast to str."""
        patcher, mock_session = self._patch_session()
        with patcher:
            msg = self._make_message(headers={"x-error-message": 42})
            await handle_dlq_message(msg, queue_name="otp_emails_dead")

        added = mock_session.add.call_args[0][0]
        assert added.error_message == "42"

    @pytest.mark.asyncio
    async def test_missing_retry_attempt_defaults_to_zero(self):
        patcher, mock_session = self._patch_session()
        with patcher:
            msg = self._make_message(headers={})
            await handle_dlq_message(msg, queue_name="otp_emails_dead")

        added = mock_session.add.call_args[0][0]
        assert added.attempt_count == 0

    @pytest.mark.asyncio
    async def test_headers_are_sanitised(self):
        patcher, mock_session = self._patch_session()
        with patcher:
            msg = self._make_message(
                headers={
                    "x-retry-attempt": 3,
                    "x-error-message": b"fail",
                    "x-original-queue": "otp_emails",
                }
            )
            await handle_dlq_message(msg, queue_name="otp_emails_dead")

        added = mock_session.add.call_args[0][0]
        # All header values should be JSON-safe (no bytes)
        for val in added.headers.values():
            assert not isinstance(val, bytes)

    @pytest.mark.asyncio
    async def test_none_headers_handled(self):
        patcher, mock_session = self._patch_session()
        with patcher:
            msg = self._make_message()
            msg.headers = None
            await handle_dlq_message(msg, queue_name="otp_emails_dead")

        added = mock_session.add.call_args[0][0]
        assert added.headers == {}
        assert added.attempt_count == 0

    @pytest.mark.asyncio
    async def test_db_error_rejects_message(self):
        """If persisting fails, the message should be rejected (no requeue)."""
        # Make the session context manager raise on __aenter__
        session_ctx = AsyncMock()
        session_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.infrastructure.messaging.handlers.dlq_handler.AsyncSessionLocal",
            return_value=session_ctx,
        ):
            msg = self._make_message()
            await handle_dlq_message(msg, queue_name="otp_emails_dead")

        msg.reject.assert_called_once_with(requeue=False)

    @pytest.mark.asyncio
    async def test_non_utf8_body_decoded_with_replace(self):
        patcher, mock_session = self._patch_session()
        with patcher:
            msg = self._make_message()
            msg.body = b"\xff\xfe invalid utf-8"
            await handle_dlq_message(msg, queue_name="otp_emails_dead")

        added = mock_session.add.call_args[0][0]
        # Should not raise — `errors="replace"` is used in handler
        assert isinstance(added.message_body, str)
