"""
Test suite for FastAPI dependencies.

Run tests:
    pytest app/tests/core/test_db.py -v

Run with coverage:
    pytest app/tests/core/test_db.py --cov=app.core.dependencies --cov-report=term-missing -v
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_async_session


class TestGetAsyncSession:

    @pytest.mark.asyncio
    async def test_get_async_session_yields_session(self):
        async_gen = get_async_session()

        session = await async_gen.__anext__()

        assert isinstance(session, AsyncSession)
        assert session is not None

        try:
            await async_gen.__anext__()
        except StopAsyncIteration:
            pass  # Expected when generator is exhausted

    @pytest.mark.asyncio
    async def test_get_async_session_context_manager(self):
        session_instance = None

        async for session in get_async_session():
            session_instance = session
            assert isinstance(session, AsyncSession)
            # Session should be active during iteration
            assert not session.is_active or session.in_transaction() is False
            break

        assert session_instance is not None

    @pytest.mark.asyncio
    async def test_get_async_session_creates_new_session_each_call(self):
        async_gen1 = get_async_session()
        async_gen2 = get_async_session()

        session1 = await async_gen1.__anext__()
        session2 = await async_gen2.__anext__()

        assert session1 is not session2

        for gen in [async_gen1, async_gen2]:
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass

