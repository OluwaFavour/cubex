"""
Pytest configuration and shared fixtures.

This module provides shared fixtures and configuration for all tests.
"""

import asyncio
import os
from pathlib import Path

import pytest


# ============================================================================
# Pytest Configuration
# ============================================================================


def pytest_configure(config):
    """Configure pytest with custom settings."""
    # Set test environment variable
    os.environ["ENVIRONMENT"] = "test"

    # Register custom markers
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require real database/services)",
    )


@pytest.fixture(scope="module")
def setup_test_database():
    """Set up test database with migrations before integration tests (synchronous)."""
    from app.shared.config import settings
    import subprocess

    # Only run if TEST_DATABASE_URL is set
    if (
        not settings.TEST_DATABASE_URL
        or settings.TEST_DATABASE_URL == "sqlite+aiosqlite:///:memory:"
    ):
        pytest.skip("TEST_DATABASE_URL not configured for integration tests")

    # Run migrations on test database
    # Set environment variable to use TEST_DATABASE_URL
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = settings.TEST_DATABASE_URL

    try:
        # Run alembic upgrade
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        if result.returncode != 0:
            print(f"Migration stdout: {result.stdout}")
            print(f"Migration stderr: {result.stderr}")
            pytest.fail(f"Migration failed: {result.stderr}")
    except Exception as e:
        pytest.fail(f"Migration error: {e}")
    finally:
        # Restore original DATABASE_URL
        if original_db_url:
            os.environ["DATABASE_URL"] = original_db_url
        else:
            os.environ.pop("DATABASE_URL", None)

    yield settings.TEST_DATABASE_URL

    # Cleanup: downgrade all migrations
    os.environ["DATABASE_URL"] = settings.TEST_DATABASE_URL
    try:
        subprocess.run(
            ["alembic", "downgrade", "base"],
            capture_output=True,
            cwd=Path(__file__).parent.parent.parent,
        )
    finally:
        if original_db_url:
            os.environ["DATABASE_URL"] = original_db_url
        else:
            os.environ.pop("DATABASE_URL", None)


@pytest.fixture
async def test_db_session(setup_test_database):
    """Provide a test database session for integration tests."""
    from sqlalchemy.ext.asyncio import (
        create_async_engine,
        async_sessionmaker,
        AsyncSession,
    )

    # Create engine and session maker for test database
    test_engine = create_async_engine(
        setup_test_database,
        echo=False,
        pool_pre_ping=True,
    )

    TestSessionLocal = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with TestSessionLocal() as session:
        yield session
        await session.rollback()  # Rollback any changes after test

    await test_engine.dispose()


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Path Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="session")
def app_root(project_root) -> Path:
    """Return the app root directory."""
    return project_root / "app"


# ============================================================================
# Mock Settings Fixture
# ============================================================================


@pytest.fixture
def mock_settings():
    """Provide mock settings for testing."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.JWT_SECRET_KEY = "test_secret_key_for_testing_only"
    settings.JWT_ALGORITHM = "HS256"
    settings.ENVIRONMENT = "test"
    settings.DEBUG = True
    settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"

    return settings
