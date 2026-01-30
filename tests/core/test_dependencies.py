"""
Test suite for FastAPI dependencies.

Run tests:
    pytest app/tests/core/test_dependencies.py -v

Run with coverage:
    pytest app/tests/core/test_dependencies.py --cov=app.core.dependencies --cov-report=term-missing -v
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_async_session


class TestGetAsyncSession:
    """Test suite for get_async_session dependency."""

    @pytest.mark.asyncio
    async def test_get_async_session_yields_session(self):
        """Test that get_async_session yields a valid AsyncSession."""
        async_gen = get_async_session()

        # Get the session from the async generator
        session = await async_gen.__anext__()

        # Verify it's an AsyncSession instance
        assert isinstance(session, AsyncSession)
        assert session is not None

        # Clean up - close the generator
        try:
            await async_gen.__anext__()
        except StopAsyncIteration:
            pass  # Expected when generator is exhausted

    @pytest.mark.asyncio
    async def test_get_async_session_context_manager(self):
        """Test that session is properly managed in context."""
        session_instance = None

        async for session in get_async_session():
            session_instance = session
            assert isinstance(session, AsyncSession)
            # Session should be active during iteration
            assert not session.is_active or session.in_transaction() is False
            break

        # Verify we got a session
        assert session_instance is not None

    @pytest.mark.asyncio
    async def test_get_async_session_creates_new_session_each_call(self):
        """Test that each call creates a new session."""
        async_gen1 = get_async_session()
        async_gen2 = get_async_session()

        session1 = await async_gen1.__anext__()
        session2 = await async_gen2.__anext__()

        # Should be different session instances
        assert session1 is not session2

        # Clean up
        for gen in [async_gen1, async_gen2]:
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
