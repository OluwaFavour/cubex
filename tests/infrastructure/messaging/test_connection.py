"""
Test suite for RabbitMQ connection management.

Run tests:
    pytest app/tests/infrastructure/messaging/test_connection.py -v

Run with coverage:
    pytest app/tests/infrastructure/messaging/test_connection.py --cov=app.infrastructure.messaging.connection --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, patch

import pytest
import aio_pika

from app.infrastructure.messaging.connection import get_connection


class TestGetConnection:

    @pytest.mark.asyncio
    async def test_get_connection_creates_new_connection(self):
        # Import the module to reset _connection
        from app.infrastructure.messaging import connection as conn_module

        conn_module._connection = None

        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_connection.is_closed = False

        with patch("aio_pika.connect_robust", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_connection

            result = await get_connection()

            assert result == mock_connection
            mock_connect.assert_called_once()
            call_args = mock_connect.call_args[0]
            assert len(call_args) > 0  # URL was passed

    @pytest.mark.asyncio
    async def test_get_connection_reuses_existing_connection(self):
        from app.infrastructure.messaging import connection as conn_module

        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_connection.is_closed = False
        conn_module._connection = mock_connection

        with patch("aio_pika.connect_robust", new_callable=AsyncMock) as mock_connect:
            result = await get_connection()

            assert result == mock_connection
            mock_connect.assert_not_called()  # Should not create new connection

    @pytest.mark.asyncio
    async def test_get_connection_recreates_closed_connection(self):
        from app.infrastructure.messaging import connection as conn_module

        old_connection = AsyncMock(spec=aio_pika.RobustConnection)
        old_connection.is_closed = True  # Closed connection
        conn_module._connection = old_connection

        new_connection = AsyncMock(spec=aio_pika.RobustConnection)
        new_connection.is_closed = False

        with patch("aio_pika.connect_robust", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = new_connection

            result = await get_connection()

            assert result == new_connection
            assert result != old_connection
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_connection_uses_settings_url(self):
        from app.infrastructure.messaging import connection as conn_module
        from app.core.config import settings

        conn_module._connection = None

        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_connection.is_closed = False

        with patch("aio_pika.connect_robust", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_connection

            await get_connection()

            mock_connect.assert_called_once_with(settings.RABBITMQ_URL)

    @pytest.mark.asyncio
    async def test_get_connection_returns_robust_connection(self):
        from app.infrastructure.messaging import connection as conn_module

        conn_module._connection = None

        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_connection.is_closed = False

        with patch("aio_pika.connect_robust", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_connection

            result = await get_connection()

            # Check it's a RobustConnection (or mock thereof)
            assert hasattr(result, "is_closed")
