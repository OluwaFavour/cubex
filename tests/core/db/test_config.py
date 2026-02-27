"""
Test suite for database configuration and utilities.

Run tests:
    pytest app/tests/core/db/test_config.py -v

Run with coverage:
    pytest app/tests/core/db/test_config.py --cov=app.core.db.config --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncConnection

from app.core.db.config import (
    async_engine,
    AsyncSessionLocal,
    Base,
    init_db,
    dispose_db,
)


class TestDatabaseConfiguration:

    def test_async_engine_is_async_engine(self):
        assert isinstance(async_engine, AsyncEngine)

    def test_async_session_local_is_sessionmaker(self):
        # AsyncSessionLocal is an async_sessionmaker instance
        assert AsyncSessionLocal is not None
        assert hasattr(AsyncSessionLocal, "__call__")

    def test_base_is_declarative_base(self):
        assert hasattr(Base, "metadata")
        assert hasattr(Base, "registry")


class TestInitDb:

    @pytest.mark.asyncio
    async def test_init_db_creates_tables(self):
        mock_conn = AsyncMock(spec=AsyncConnection)
        mock_begin = AsyncMock()
        mock_begin.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_begin.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.db.config.async_engine") as mock_engine:
            mock_engine.begin.return_value = mock_begin

            await init_db()

            mock_engine.begin.assert_called_once()

            mock_conn.run_sync.assert_called_once()
            create_all_func = mock_conn.run_sync.call_args[0][0]

            assert callable(create_all_func)

    @pytest.mark.asyncio
    async def test_init_db_handles_connection_context(self):
        call_count = 0

        async def mock_begin(self):
            nonlocal call_count
            call_count += 1
            mock_conn = AsyncMock(spec=AsyncConnection)
            return mock_conn

        mock_context = AsyncMock()
        mock_context.__aenter__ = mock_begin
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.db.config.async_engine") as mock_engine:
            mock_engine.begin.return_value = mock_context

            await init_db()

            assert call_count == 1
            mock_context.__aexit__.assert_called_once()


class TestDisposeDb:

    @pytest.mark.asyncio
    async def test_dispose_db_calls_engine_dispose(self):
        with patch("app.core.db.config.async_engine") as mock_engine:
            mock_engine.dispose = AsyncMock()

            await dispose_db()

            mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispose_db_is_awaitable(self):
        with patch("app.core.db.config.async_engine") as mock_engine:
            mock_engine.dispose = AsyncMock()

            result = await dispose_db()

            # dispose_db returns None
            assert result is None
            mock_engine.dispose.assert_called_once()

