from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Asynchronous generator function that returns an async session.
    Create a new async session for each request and close it after the request is finished.

    Yields:
        async_session: An async session object.
    """
    async with AsyncSessionLocal() as async_session:
        yield async_session

