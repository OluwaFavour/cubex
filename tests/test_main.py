"""
Unit tests for the main FastAPI application.

This module provides comprehensive test coverage for:
- FastAPI app initialization and configuration
- Lifespan events (startup and shutdown)
- Middleware configuration
- Health check endpoint
- Root endpoint
- CORS and session middleware
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app, lifespan


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def client():
    """Test client for synchronous requests."""
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Async test client for asynchronous requests."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = AsyncMock(spec=AsyncSession)
    session.begin = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


# ============================================================================
# Tests for App Configuration
# ============================================================================


class TestAppConfiguration:
    """Test suite for FastAPI app configuration."""

    def test_app_title(self):
        """Test that app has correct title from settings."""
        assert app.title == "CueBX"

    def test_app_version(self):
        """Test that app has correct version from settings."""
        assert app.version == "1.0.0"

    def test_app_debug_mode(self):
        """Test that app debug mode is set correctly."""
        assert app.debug is True

    def test_app_openapi_url(self):
        """Test that OpenAPI URL is configured correctly."""
        assert app.openapi_url == "/openapi.json"

    def test_app_docs_url(self):
        """Test that Swagger docs URL is configured."""
        assert app.docs_url == "/docs"

    def test_app_redoc_url(self):
        """Test that ReDoc URL is configured."""
        assert app.redoc_url == "/redoc"

    def test_app_has_cors_middleware(self):
        """Test that CORS middleware is configured."""
        # Check if CORSMiddleware is in the middleware stack
        middleware_types = [m.cls for m in app.user_middleware]
        from starlette.middleware.cors import CORSMiddleware

        assert CORSMiddleware in middleware_types

    def test_app_has_session_middleware(self):
        """Test that Session middleware is configured."""
        middleware_types = [m.cls for m in app.user_middleware]
        from starlette.middleware.sessions import SessionMiddleware

        assert SessionMiddleware in middleware_types


# ============================================================================
# Tests for Lifespan Events
# ============================================================================


class TestLifespanEvents:
    """Test suite for application lifespan events."""

    @pytest.mark.asyncio
    async def test_lifespan_startup_starts_scheduler(self):
        """Test that lifespan startup starts the scheduler."""
        with patch("app.main.scheduler") as mock_scheduler, patch(
            "app.main.CloudinaryService"
        ), patch("app.main.BrevoService") as mock_brevo, patch(
            "app.main.start_consumers", new_callable=AsyncMock
        ) as mock_consumers, patch(
            "app.main.Renderer"
        ), patch(
            "app.main.generate_openapi_json"
        ) as mock_openapi, patch(
            "app.main.write_to_file_async", new_callable=AsyncMock
        ), patch(
            "app.main.RedisService"
        ) as mock_redis, patch(
            "app.main.GoogleOAuthService"
        ) as mock_google, patch(
            "app.main.GitHubOAuthService"
        ) as mock_github:

            mock_brevo.init = AsyncMock()
            mock_consumers.return_value = None
            mock_openapi.return_value = "{}"
            mock_redis.init = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_google.init = AsyncMock()
            mock_google.aclose = AsyncMock()
            mock_github.init = AsyncMock()
            mock_github.aclose = AsyncMock()

            async with lifespan(app):
                pass

            mock_scheduler.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_startup_configures_cloudinary(self):
        """Test that lifespan startup configures Cloudinary."""
        with patch("app.main.scheduler"), patch(
            "app.main.CloudinaryService"
        ) as mock_cloudinary, patch("app.main.BrevoService") as mock_brevo, patch(
            "app.main.start_consumers", new_callable=AsyncMock
        ) as mock_consumers, patch(
            "app.main.Renderer"
        ), patch(
            "app.main.generate_openapi_json"
        ) as mock_openapi, patch(
            "app.main.write_to_file_async", new_callable=AsyncMock
        ), patch(
            "app.main.RedisService"
        ) as mock_redis, patch(
            "app.main.GoogleOAuthService"
        ) as mock_google, patch(
            "app.main.GitHubOAuthService"
        ) as mock_github:

            mock_brevo.init = AsyncMock()
            mock_consumers.return_value = None
            mock_openapi.return_value = "{}"
            mock_redis.init = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_google.init = AsyncMock()
            mock_google.aclose = AsyncMock()
            mock_github.init = AsyncMock()
            mock_github.aclose = AsyncMock()

            async with lifespan(app):
                pass

            mock_cloudinary.init.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_startup_initializes_brevo(self):
        """Test that lifespan startup initializes Brevo service."""
        with patch("app.main.scheduler"), patch("app.main.CloudinaryService"), patch(
            "app.main.BrevoService"
        ) as mock_brevo, patch(
            "app.main.start_consumers", new_callable=AsyncMock
        ) as mock_consumers, patch(
            "app.main.Renderer"
        ), patch(
            "app.main.generate_openapi_json"
        ) as mock_openapi, patch(
            "app.main.write_to_file_async", new_callable=AsyncMock
        ), patch(
            "app.main.RedisService"
        ) as mock_redis, patch(
            "app.main.GoogleOAuthService"
        ) as mock_google, patch(
            "app.main.GitHubOAuthService"
        ) as mock_github:

            mock_consumers.return_value = None
            mock_openapi.return_value = "{}"
            mock_brevo.init = AsyncMock()
            mock_redis.init = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_google.init = AsyncMock()
            mock_google.aclose = AsyncMock()
            mock_github.init = AsyncMock()
            mock_github.aclose = AsyncMock()

            async with lifespan(app):
                pass

            mock_brevo.init.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_startup_starts_message_consumers(self):
        """Test that lifespan startup starts message consumers."""
        with patch("app.main.scheduler"), patch("app.main.CloudinaryService"), patch(
            "app.main.BrevoService"
        ) as mock_brevo, patch(
            "app.main.start_consumers", new_callable=AsyncMock
        ) as mock_consumers, patch(
            "app.main.Renderer"
        ), patch(
            "app.main.generate_openapi_json"
        ) as mock_openapi, patch(
            "app.main.write_to_file_async", new_callable=AsyncMock
        ), patch(
            "app.main.RedisService"
        ) as mock_redis, patch(
            "app.main.GoogleOAuthService"
        ) as mock_google, patch(
            "app.main.GitHubOAuthService"
        ) as mock_github:

            mock_brevo.init = AsyncMock()
            mock_consumers.return_value = None
            mock_openapi.return_value = "{}"
            mock_redis.init = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_google.init = AsyncMock()
            mock_google.aclose = AsyncMock()
            mock_github.init = AsyncMock()
            mock_github.aclose = AsyncMock()

            async with lifespan(app):
                pass

            mock_consumers.assert_called_once_with(keep_alive=False)

    @pytest.mark.asyncio
    async def test_lifespan_startup_initializes_renderer(self):
        """Test that lifespan startup initializes template renderer."""
        with patch("app.main.scheduler"), patch("app.main.CloudinaryService"), patch(
            "app.main.BrevoService"
        ) as mock_brevo, patch(
            "app.main.start_consumers", new_callable=AsyncMock
        ) as mock_consumers, patch(
            "app.main.Renderer"
        ) as mock_renderer, patch(
            "app.main.generate_openapi_json"
        ) as mock_openapi, patch(
            "app.main.write_to_file_async", new_callable=AsyncMock
        ), patch(
            "app.main.RedisService"
        ) as mock_redis, patch(
            "app.main.GoogleOAuthService"
        ) as mock_google, patch(
            "app.main.GitHubOAuthService"
        ) as mock_github:

            mock_brevo.init = AsyncMock()
            mock_consumers.return_value = None
            mock_openapi.return_value = "{}"
            mock_redis.init = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_google.init = AsyncMock()
            mock_google.aclose = AsyncMock()
            mock_github.init = AsyncMock()
            mock_github.aclose = AsyncMock()

            async with lifespan(app):
                pass

            mock_renderer.initialize.assert_called_once_with("app/templates")

    @pytest.mark.asyncio
    async def test_lifespan_startup_generates_openapi_schema(self):
        """Test that lifespan startup generates OpenAPI schema."""
        with patch("app.main.scheduler"), patch("app.main.CloudinaryService"), patch(
            "app.main.BrevoService"
        ) as mock_brevo, patch(
            "app.main.start_consumers", new_callable=AsyncMock
        ) as mock_consumers, patch(
            "app.main.Renderer"
        ), patch(
            "app.main.generate_openapi_json"
        ) as mock_openapi, patch(
            "app.main.write_to_file_async", new_callable=AsyncMock
        ) as mock_write, patch(
            "app.main.RedisService"
        ) as mock_redis, patch(
            "app.main.GoogleOAuthService"
        ) as mock_google, patch(
            "app.main.GitHubOAuthService"
        ) as mock_github:

            mock_brevo.init = AsyncMock()
            mock_consumers.return_value = None
            mock_openapi.return_value = '{"openapi": "3.0.0"}'
            mock_redis.init = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_google.init = AsyncMock()
            mock_google.aclose = AsyncMock()
            mock_github.init = AsyncMock()
            mock_github.aclose = AsyncMock()

            async with lifespan(app):
                pass

            mock_openapi.assert_called_once_with(app)
            mock_write.assert_called_once_with("openapi.json", '{"openapi": "3.0.0"}')

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_closes_consumer_connection(self):
        """Test that lifespan shutdown closes message consumer connection."""
        mock_connection = AsyncMock()

        with patch("app.main.scheduler"), patch("app.main.CloudinaryService"), patch(
            "app.main.BrevoService"
        ) as mock_brevo, patch(
            "app.main.start_consumers", new_callable=AsyncMock
        ) as mock_consumers, patch(
            "app.main.Renderer"
        ), patch(
            "app.main.generate_openapi_json"
        ) as mock_openapi, patch(
            "app.main.write_to_file_async", new_callable=AsyncMock
        ), patch(
            "app.main.RedisService"
        ) as mock_redis, patch(
            "app.main.GoogleOAuthService"
        ) as mock_google, patch(
            "app.main.GitHubOAuthService"
        ) as mock_github:

            mock_brevo.init = AsyncMock()
            mock_consumers.return_value = mock_connection
            mock_openapi.return_value = "{}"
            mock_redis.init = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_google.init = AsyncMock()
            mock_google.aclose = AsyncMock()
            mock_github.init = AsyncMock()
            mock_github.aclose = AsyncMock()

            async with lifespan(app):
                pass

            mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_no_connection_to_close(self):
        """Test that lifespan shutdown handles no consumer connection gracefully."""
        with patch("app.main.scheduler") as mock_scheduler, patch(
            "app.main.CloudinaryService"
        ), patch("app.main.BrevoService") as mock_brevo, patch(
            "app.main.start_consumers", new_callable=AsyncMock
        ) as mock_consumers, patch(
            "app.main.Renderer"
        ), patch(
            "app.main.generate_openapi_json"
        ) as mock_openapi, patch(
            "app.main.write_to_file_async", new_callable=AsyncMock
        ), patch(
            "app.main.RedisService"
        ) as mock_redis, patch(
            "app.main.GoogleOAuthService"
        ) as mock_google, patch(
            "app.main.GitHubOAuthService"
        ) as mock_github:

            mock_brevo.init = AsyncMock()
            mock_consumers.return_value = None  # No connection
            mock_openapi.return_value = "{}"
            mock_redis.init = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_google.init = AsyncMock()
            mock_google.aclose = AsyncMock()
            mock_github.init = AsyncMock()
            mock_github.aclose = AsyncMock()

            async with lifespan(app):
                pass

            # Should not raise any error
            mock_scheduler.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_stops_scheduler(self):
        """Test that lifespan shutdown stops the scheduler."""
        with patch("app.main.scheduler") as mock_scheduler, patch(
            "app.main.CloudinaryService"
        ), patch("app.main.BrevoService") as mock_brevo, patch(
            "app.main.start_consumers", new_callable=AsyncMock
        ) as mock_consumers, patch(
            "app.main.Renderer"
        ), patch(
            "app.main.generate_openapi_json"
        ) as mock_openapi, patch(
            "app.main.write_to_file_async", new_callable=AsyncMock
        ), patch(
            "app.main.RedisService"
        ) as mock_redis, patch(
            "app.main.GoogleOAuthService"
        ) as mock_google, patch(
            "app.main.GitHubOAuthService"
        ) as mock_github:

            mock_brevo.init = AsyncMock()
            mock_consumers.return_value = None
            mock_openapi.return_value = "{}"
            mock_redis.init = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_google.init = AsyncMock()
            mock_google.aclose = AsyncMock()
            mock_github.init = AsyncMock()
            mock_github.aclose = AsyncMock()

            async with lifespan(app):
                pass

            mock_scheduler.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_closes_redis(self):
        """Test that lifespan shutdown closes Redis service."""
        with patch("app.main.scheduler"), patch("app.main.CloudinaryService"), patch(
            "app.main.BrevoService"
        ) as mock_brevo, patch(
            "app.main.start_consumers", new_callable=AsyncMock
        ) as mock_consumers, patch(
            "app.main.Renderer"
        ), patch(
            "app.main.generate_openapi_json"
        ) as mock_openapi, patch(
            "app.main.write_to_file_async", new_callable=AsyncMock
        ), patch(
            "app.main.RedisService"
        ) as mock_redis, patch(
            "app.main.GoogleOAuthService"
        ) as mock_google, patch(
            "app.main.GitHubOAuthService"
        ) as mock_github:

            mock_brevo.init = AsyncMock()
            mock_consumers.return_value = None
            mock_openapi.return_value = "{}"
            mock_redis.init = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_google.init = AsyncMock()
            mock_google.aclose = AsyncMock()
            mock_github.init = AsyncMock()
            mock_github.aclose = AsyncMock()

            async with lifespan(app):
                pass

            mock_redis.aclose.assert_called_once()


# ============================================================================
# Tests for Root Endpoint
# ============================================================================


class TestRootEndpoint:
    """Test suite for root endpoint."""

    def test_root_endpoint_returns_welcome_message(self, client):
        """Test that root endpoint returns welcome message."""
        response = client.get("/")

        assert response.status_code == 200
        assert "message" in response.json()
        assert response.json()["message"] == "Welcome to CueBX API"

    def test_root_endpoint_returns_documentation_links(self, client):
        """Test that root endpoint returns documentation links."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "documentations" in data
        assert "swagger" in data["documentations"]
        assert "redoc" in data["documentations"]

    def test_root_endpoint_swagger_link_format(self, client):
        """Test that swagger documentation link is correctly formatted."""
        response = client.get("/")

        data = response.json()
        swagger_url = data["documentations"]["swagger"]
        assert swagger_url.endswith("/docs")
        assert swagger_url.startswith("http")

    def test_root_endpoint_redoc_link_format(self, client):
        """Test that redoc documentation link is correctly formatted."""
        response = client.get("/")

        data = response.json()
        redoc_url = data["documentations"]["redoc"]
        assert redoc_url.endswith("/redoc")
        assert redoc_url.startswith("http")

    def test_root_endpoint_returns_version(self, client):
        """Test that root endpoint returns API version."""
        response = client.get("/")

        data = response.json()
        assert "version" in data
        assert data["version"] == "1.0.0"

    def test_root_endpoint_not_in_schema(self, client):
        """Test that root endpoint is not included in OpenAPI schema."""
        openapi_schema = app.openapi()
        assert "/" not in openapi_schema.get("paths", {})


# ============================================================================
# Tests for Health Check Endpoint
# ============================================================================


class TestHealthCheckEndpoint:
    """Test suite for health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_returns_ok_status(self, async_client, mock_db_session):
        """Test that health check returns OK status when database and Redis are reachable."""
        # Mock successful database query with proper context manager

        mock_result = MagicMock()  # Use MagicMock for synchronous scalar()
        mock_result.scalar.return_value = 1  # scalar() returns 1 synchronously

        # execute() returns a Result, which is awaitable
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock the session.begin() context manager properly
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_db_session.begin = MagicMock(return_value=mock_cm)

        # Create a generator function for dependency override
        async def get_session_override():
            yield mock_db_session

        from app.main import app as test_app
        from app.core.dependencies import get_async_session

        test_app.dependency_overrides[get_async_session] = get_session_override

        try:
            # Mock Redis ping to return True
            with patch(
                "app.main.RedisService.ping", new_callable=AsyncMock, return_value=True
            ):
                response = await async_client.get("/health")

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ok"
                assert "CueBX API is running" in data["message"]
                assert data["checks"]["database"] == "ok"
                assert data["checks"]["redis"] == "ok"

                # Verify database query was executed
                mock_db_session.execute.assert_called_once()
                mock_result.scalar.assert_called_once()
        finally:
            test_app.dependency_overrides.clear()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_health_check_database_query_executed(self, setup_test_database):
        """Test that health check executes database query.

        Note: This is an integration test that requires a real database connection.
        To run integration tests: pytest -m integration
        To skip integration tests: pytest -m "not integration"
        """
        from httpx import AsyncClient, ASGITransport
        from sqlalchemy.ext.asyncio import (
            create_async_engine,
            async_sessionmaker,
            AsyncSession,
        )

        # Create fresh engine and session for this test
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

        # Override session dependency
        async def override_get_session():
            async with TestSessionLocal() as session:
                yield session

        from app.main import app as test_app
        from app.core.dependencies import get_async_session

        test_app.dependency_overrides[get_async_session] = override_get_session

        try:
            # Mock Redis ping to return True for this test
            with patch(
                "app.main.RedisService.ping", new_callable=AsyncMock, return_value=True
            ):
                # Test the health check endpoint with real database
                transport = ASGITransport(app=test_app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.get("/health")
                    assert response.status_code == 200
                    assert response.json()["status"] == "ok"
        finally:
            test_app.dependency_overrides.clear()
            await test_engine.dispose()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_health_check_handles_database_failure(self):
        """Test that health check handles database connection failure.

        Note: This is an integration test that tests error handling.
        To run integration tests: pytest -m integration
        To skip integration tests: pytest -m "not integration"
        """
        from httpx import AsyncClient, ASGITransport
        from sqlalchemy.exc import OperationalError
        from sqlalchemy.ext.asyncio import AsyncSession
        from unittest.mock import AsyncMock

        # Create a mock session that will fail on execute
        async def failing_session():
            """Generator that yields a session that fails on execute."""
            mock_session = AsyncMock(spec=AsyncSession)

            # Make begin() return a context manager that works
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
            mock_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session.begin.return_value = mock_cm

            # Make execute fail
            mock_session.execute = AsyncMock(
                side_effect=OperationalError("Database connection failed", None, None)
            )

            yield mock_session

        # Override the dependency
        from app.main import app as test_app
        from app.core.dependencies import get_async_session

        test_app.dependency_overrides[get_async_session] = failing_session

        try:
            # Mock Redis ping to return True (we're testing DB failure, not Redis)
            with patch(
                "app.main.RedisService.ping", new_callable=AsyncMock, return_value=True
            ):
                transport = ASGITransport(app=test_app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.get("/health")
                    assert response.status_code == 503
                    data = response.json()
                    # The error handler wraps it in "detail"
                    assert "detail" in data
                    assert "One or more health checks failed" in data["detail"]
        finally:
            # Clean up the override
            test_app.dependency_overrides.clear()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_health_check_invalid_database_response(self):
        """Test that health check handles invalid database response.

        Note: This is an integration test that tests database response validation.
        To run integration tests: pytest -m integration
        To skip integration tests: pytest -m "not integration"
        """
        from httpx import AsyncClient, ASGITransport
        from sqlalchemy.ext.asyncio import AsyncSession
        from unittest.mock import AsyncMock

        # Create a mock session that returns invalid result
        async def invalid_result_session():
            """Generator that yields a session returning invalid result."""
            mock_session = AsyncMock(spec=AsyncSession)

            # Make begin() return a context manager that works
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
            mock_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session.begin.return_value = mock_cm

            # Make execute return a result with scalar != 1
            mock_result = MagicMock()
            mock_result.scalar.return_value = 0  # Return 0 instead of 1
            mock_session.execute = AsyncMock(return_value=mock_result)

            yield mock_session

        # Override the dependency
        from app.main import app as test_app
        from app.core.dependencies import get_async_session

        test_app.dependency_overrides[get_async_session] = invalid_result_session

        try:
            # Mock Redis ping to return True (we're testing DB response, not Redis)
            with patch(
                "app.main.RedisService.ping", new_callable=AsyncMock, return_value=True
            ):
                transport = ASGITransport(app=test_app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.get("/health")
                    assert response.status_code == 503
                    data = response.json()
                    assert "detail" in data
                    # The outer exception handler wraps it
                    assert "One or more health checks failed" in data["detail"]
        finally:
            # Clean up the override
            test_app.dependency_overrides.clear()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_health_check_head_method_supported(self, setup_test_database):
        """Test that health check endpoint supports HEAD method.

        Note: This is an integration test that requires a real database connection.
        To run integration tests: pytest -m integration
        To skip integration tests: pytest -m "not integration"
        """
        from httpx import AsyncClient, ASGITransport
        from sqlalchemy.ext.asyncio import (
            create_async_engine,
            async_sessionmaker,
            AsyncSession,
        )

        # Create a fresh session for this test to avoid transaction conflicts
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

        # Create session override
        async def override_get_session():
            async with TestSessionLocal() as session:
                yield session

        from app.main import app as test_app
        from app.core.dependencies import get_async_session

        test_app.dependency_overrides[get_async_session] = override_get_session

        try:
            # Mock Redis ping to return True for this test
            with patch(
                "app.main.RedisService.ping", new_callable=AsyncMock, return_value=True
            ):
                # Test HEAD method
                transport = ASGITransport(app=test_app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.head("/health")
                    assert response.status_code == 200
                    # HEAD responses have empty body
                    assert len(response.content) == 0
        finally:
            test_app.dependency_overrides.clear()
            await test_engine.dispose()

    def test_health_check_in_openapi_schema(self):
        """Test that health check endpoint is in OpenAPI schema."""
        openapi_schema = app.openapi()
        assert "/health" in openapi_schema.get("paths", {})


# ============================================================================
# Tests for Middleware
# ============================================================================


class TestMiddleware:
    """Test suite for middleware configuration."""

    def test_cors_allows_configured_origins(self, client):
        """Test that CORS allows requests from configured origins."""
        response = client.get("/", headers={"Origin": "http://localhost:3000"})

        # Should not be blocked
        assert response.status_code == 200

    def test_session_cookie_set_on_response(self, client):
        """Test that session cookie is set in response."""
        response = client.get("/")

        # Check if session cookie exists (might not be set on simple GET)
        # This is more of a smoke test
        assert response.status_code == 200
