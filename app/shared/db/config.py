from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    async_sessionmaker,
    AsyncAttrs,
)
from sqlalchemy.orm import DeclarativeBase

from app.shared.config import settings

ASYNC_SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

async_engine: AsyncEngine = create_async_engine(
    ASYNC_SQLALCHEMY_DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,  # Increase pool size for concurrent connections
    max_overflow=30,  # Allow overflow connections
    pool_pre_ping=True,  # Validate connections before use
    pool_recycle=3600,  # Recycle connections every hour
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autoflush=False,
    expire_on_commit=False,
    autobegin=True,  # Automatically begin transactions
)


# Base class for declarative_base
class Base(AsyncAttrs, DeclarativeBase):
    pass


async def init_db() -> None:
    """
    Initializes the database by creating all the tables defined in the metadata.

    Returns:
        None
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    """
    Dispose the database connection.
    This function is responsible for disposing the database connection by calling the `dispose()` method of the `async_engine` object.

    Returns:
        None
    """
    await async_engine.dispose()
