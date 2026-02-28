# Tests

This directory contains all unit tests, integration tests, and test utilities for the application.

## Table of Contents

- [Setup](#setup)
- [Running Tests](#running-tests)
- [Test Structure](#test-structure)
- [Endpoint Testing Guide](#endpoint-testing-guide)
- [Writing Tests](#writing-tests)
- [Coverage](#coverage)

## Setup

### Install Dependencies

```bash
pip install -r requirements-dev.txt
```

### Configure Test Database

Set the `TEST_DATABASE_URL` environment variable to point to your test database:

```bash
# .env or environment
TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/cubex_test
```

The test database should be a separate database from your development database to avoid data conflicts.

## Running Tests

### Run all tests

```bash
pytest
```

### Run specific test file

```bash
pytest tests/core/routers/test_auth.py
```

### Run specific test class

```bash
pytest tests/core/routers/test_auth.py::TestSignupEndpoint
```

### Run specific test function

```bash
pytest tests/core/routers/test_auth.py::TestSignupEndpoint::test_signup_success
```

### Run router tests only

```bash
pytest tests/core/routers/ tests/apps/
```

### Run with coverage report

```bash
pytest --cov=app --cov-report=html
```

Then open `htmlcov/index.html` in your browser to view the coverage report.

### Run only fast tests (skip slow tests)

```bash
pytest -m "not slow"
```

### Run with verbose output

```bash
pytest -v
```

### Run with extra verbosity

```bash
pytest -vv
```

### Run with short traceback (recommended for large test suites)

```bash
pytest --tb=short
```

## Test Structure

### Router Tests (Integration)

- `core/routers/test_auth.py` - Authentication endpoints (46 tests)
- `core/routers/test_webhook.py` - Stripe webhook handling (30 tests)
- `apps/cubex_api/routers/test_workspace.py` - Workspace management endpoints
- `apps/cubex_api/routers/test_subscription.py` - API subscription endpoints
- `apps/cubex_career/routers/test_subscription.py` - Career subscription endpoints
- `apps/cubex_career/routers/test_history.py` - Analysis history endpoints (29 tests)
- `apps/cubex_career/routers/test_internal.py` - Career internal API (50 tests)

### CRUD Tests

- `apps/cubex_career/db/test_analysis_result_crud.py` - Analysis result CRUD operations (34 tests)

### Schema Tests

- `apps/cubex_career/test_schemas.py` - Career schema validation (30 tests)

### Core Tests

- `core/dependencies/test_db.py` - DB dependencies (3 tests)
- `core/dependencies/test_auth.py` - Auth dependencies

### Main Application Tests

- `test_main.py` - FastAPI app initialization and health checks (33 tests)
- `test_utils.py` - Utility functions in `app.core.utils` (76 tests)

### Services Tests

- `services/test_brevo.py` - Brevo email service (41 tests)
- `services/test_cloudinary.py` - Cloudinary file service (23 tests)
- `services/test_template.py` - Jinja2 template rendering (17 tests)

### Infrastructure Tests

- `infrastructure/messaging/test_connection.py` - RabbitMQ connection (5 tests)
- `infrastructure/messaging/test_queues.py` - Queue configuration (17 tests)
- `infrastructure/messaging/test_publisher.py` - Event publishing (7 tests)
- `infrastructure/messaging/test_consumer.py` - Message processing (13 tests)
- `infrastructure/messaging/test_main.py` - Consumer startup (10 tests)
- `infrastructure/scheduler/test_main.py` - Scheduler initialization (4 tests)

### Core Module Tests

- `core/db/test_config.py` - Database configuration (7 tests)
- `core/exceptions/test_types.py` - Exception types (8 tests)
- `core/exceptions/test_handlers.py` - Exception handlers (5 tests)
- `core/test_logger.py` - Logger and Sentry integration (17 tests)

### Configuration

- `conftest.py` - Shared pytest fixtures and configuration

## Endpoint Testing Guide

This section provides a comprehensive guide on how to write integration tests for API endpoints. Our endpoint tests use real database transactions with automatic rollback for complete test isolation.

### Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│                         Test Function                           │
│  1. Create test data using fixtures (users, workspaces, etc.)  │
│  2. Make HTTP request using AsyncClient                        │
│  3. Assert response status code and body                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Test Database Session                       │
│  - Outer transaction wraps entire test                          │
│  - App's begin() calls converted to savepoints                  │
│  - Automatic rollback after each test                           │
└─────────────────────────────────────────────────────────────────┘
```

### Key Concepts

1. **Real Database**: Tests run against a real PostgreSQL test database, not mocks
2. **Automatic Migrations**: Database migrations run automatically at the start of each test session
3. **Transaction Rollback**: Each test runs in a transaction that's rolled back after completion
4. **Shared Session**: Test fixtures and the app use the same database session
5. **Auto-mocked External Services**: Stripe, RabbitMQ, etc. are automatically mocked
6. **Automatic Cleanup**: All tables are truncated at the end of the test session

### Session-Scoped Fixtures

These fixtures run once per test session:

| Fixture | Description |
| ------- | ----------- |
| `setup_test_database` | Runs migrations at session start, truncates tables at session end (autouse) |
| `event_loop_policy` | Provides event loop policy for session-scoped async operations |

### Available Fixtures

The following fixtures are available in `conftest.py`:

| Fixture | Description |
| ------- | ----------- |
| `db_session` | Async database session with transaction rollback |
| `client` | AsyncClient for making HTTP requests |
| `app` | FastAPI application instance |
| `test_user` | Verified user with password "password123" |
| `test_user_unverified` | Unverified user for testing verification flows |
| `auth_headers` | Authorization headers for `test_user` |
| `authenticated_client` | Client with auth headers pre-configured |
| `test_workspace` | Personal workspace for `test_user` |
| `personal_workspace` | Alias for `test_workspace` |
| `_reset_singletons` | Resets all singleton services, event publisher, and lifecycle hooks after each test (autouse) |
| `basic_api_plan` | Basic tier API plan |
| `professional_api_plan` | Professional tier API plan |
| `free_career_plan` | Free tier career plan |
| `plus_career_plan` | Plus tier career plan |
| `pro_career_plan` | Pro tier career plan |
| `career_subscription` | Active career subscription for `test_user` |
| `paid_career_subscription` | Paid Plus tier career subscription |
| `career_feature_cost_config` | FeatureCostConfig for `CAREER_CAREER_PATH` (required by commit/history tests) |

### Writing Your First Endpoint Test

#### 1. Basic Structure

Create a new test file in the appropriate directory:

```python
# tests/core/routers/test_my_router.py

"""
Integration tests for my router endpoints.
"""

import pytest
from httpx import AsyncClient


class TestMyEndpoint:
    """Tests for POST /my-endpoint"""

    @pytest.mark.asyncio
    async def test_endpoint_success(self, client: AsyncClient):
        """Should return 200 on successful request."""
        response = await client.post(
            "/my-endpoint",
            json={"field": "value"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
```

#### 2. Testing with Authentication

Use the `auth_headers` fixture for authenticated requests:

```python
@pytest.mark.asyncio
async def test_protected_endpoint(
    self, client: AsyncClient, auth_headers: dict, test_user
):
    """Should return user data for authenticated request."""
    response = await client.get(
        "/users/me",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
```

Or use the `authenticated_client` fixture:

```python
@pytest.mark.asyncio
async def test_protected_endpoint(self, authenticated_client: AsyncClient, test_user):
    """Should return user data for authenticated request."""
    response = await authenticated_client.get("/users/me")

    assert response.status_code == 200
    assert response.json()["email"] == test_user.email
```

#### 3. Testing with Database Records

Use fixtures to create required database records:

```python
@pytest.mark.asyncio
async def test_get_workspace(
    self,
    client: AsyncClient,
    auth_headers: dict,
    test_workspace,  # Creates workspace in DB
):
    """Should return workspace details."""
    response = await client.get(
        f"/workspaces/{test_workspace.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == test_workspace.name
```

#### 4. Testing Error Cases

Always test error conditions:

```python
class TestMyEndpoint:
    """Tests for POST /my-endpoint"""

    @pytest.mark.asyncio
    async def test_endpoint_unauthorized(self, client: AsyncClient):
        """Should return 401 without authentication."""
        response = await client.post("/my-endpoint", json={})

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_endpoint_validation_error(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return 422 for invalid input."""
        response = await client.post(
            "/my-endpoint",
            json={"invalid_field": "value"},
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return 404 for non-existent resource."""
        from uuid import uuid4

        response = await client.get(
            f"/resources/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404
```

### Creating Custom Fixtures

#### Creating a Custom User

```python
@pytest.fixture
async def admin_user(db_session: AsyncSession):
    """Create an admin user."""
    from uuid import uuid4
    from app.core.db.models import User

    user = User(
        id=uuid4(),
        email="admin@example.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.vwPbgsgNJwKrWe",
        full_name="Admin User",
        email_verified=True,
        is_active=True,
        is_admin=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user
```

#### Creating Auth Headers for Custom User

```python
@pytest.fixture
def admin_auth_headers(admin_user):
    """Create auth headers for admin user."""
    from tests.conftest import create_test_access_token

    token = create_test_access_token(admin_user)
    return {"Authorization": f"Bearer {token}"}
```

#### Creating a Subscription

```python
@pytest.fixture
async def premium_subscription(
    db_session: AsyncSession, test_user, professional_api_plan
):
    """Create a premium subscription."""
    from uuid import uuid4
    from datetime import datetime, timezone
    from app.core.db.models import Subscription
    from app.core.enums import SubscriptionStatus

    subscription = Subscription(
        id=uuid4(),
        user_id=test_user.id,
        plan_id=professional_api_plan.id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
        stripe_subscription_id="sub_premium_123",
    )
    db_session.add(subscription)
    await db_session.flush()
    return subscription
```

### Testing Webhooks

For webhook endpoints, mock signature verification:

```python
from unittest.mock import patch, AsyncMock

class TestStripeWebhook:
    """Tests for POST /webhooks/stripe"""

    @pytest.mark.asyncio
    async def test_webhook_checkout_completed(self, client: AsyncClient):
        """Should process checkout.session.completed event."""
        event_data = {
            "id": "evt_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "subscription": "sub_123",
                    "customer": "cus_123",
                    "metadata": {"user_id": "user_123"},
                }
            },
        }

        with patch(
            "app.core.routers.webhook.Stripe.verify_webhook_signature",
            return_value=event_data,
        ), patch(
            "app.core.routers.webhook.get_publisher",
            return_value=AsyncMock(),
        ) as mock_get_pub:
            response = await client.post(
                "/webhooks/stripe",
                content="{}",
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "valid_signature",
                },
            )

        assert response.status_code == 200
        assert response.json()["status"] == "received"
        mock_get_pub.return_value.assert_called_once()
```

### Testing OAuth Flows

Mock external OAuth providers:

```python
from unittest.mock import patch, AsyncMock

class TestGoogleOAuth:
    """Tests for Google OAuth callback"""

    @pytest.mark.asyncio
    async def test_google_callback_new_user(self, client: AsyncClient):
        """Should create new user from Google OAuth."""
        mock_user_info = {
            "email": "newuser@gmail.com",
            "name": "New User",
            "picture": "https://example.com/photo.jpg",
            "email_verified": True,
        }

        with patch(
            "app.core.services.oauth.google.GoogleOAuth.exchange_code",
            new_callable=AsyncMock,
            return_value={"access_token": "google_token"},
        ), patch(
            "app.core.services.oauth.google.GoogleOAuth.get_user_info",
            new_callable=AsyncMock,
            return_value=mock_user_info,
        ):
            response = await client.get(
                "/auth/google/callback",
                params={"code": "auth_code", "state": "state"},
            )

        assert response.status_code == 200
        assert "access_token" in response.json()
```

### Test Organization Best Practices

#### 1. Group Tests by Endpoint

```python
class TestCreateWorkspace:
    """Tests for POST /workspaces"""
    # All tests for creating workspaces

class TestGetWorkspace:
    """Tests for GET /workspaces/{id}"""
    # All tests for getting a workspace

class TestUpdateWorkspace:
    """Tests for PUT /workspaces/{id}"""
    # All tests for updating a workspace

class TestDeleteWorkspace:
    """Tests for DELETE /workspaces/{id}"""
    # All tests for deleting a workspace
```

#### 2. Use Descriptive Test Names

```python
# Good
def test_create_workspace_returns_201_with_valid_data()
def test_create_workspace_returns_400_when_name_too_long()
def test_create_workspace_returns_401_without_auth()

# Bad
def test_create_workspace()
def test_error()
def test_1()
```

#### 3. Test One Thing Per Test

```python
# Good - separate tests for each assertion
@pytest.mark.asyncio
async def test_signup_creates_user(self, client, db_session):
    """Should create user in database."""
    response = await client.post("/auth/signup", json={...})
    user = await db_session.get(User, response.json()["id"])
    assert user is not None

@pytest.mark.asyncio
async def test_signup_sends_verification_email(self, client):
    """Should queue verification email."""
    with patch("app.core.services.auth.get_publisher", return_value=AsyncMock()) as mock:
        await client.post("/auth/signup", json={...})
    mock.return_value.assert_called_once()

# Bad - multiple unrelated assertions
@pytest.mark.asyncio
async def test_signup(self, client, db_session):
    response = await client.post("/auth/signup", json={...})
    assert response.status_code == 201
    user = await db_session.get(User, ...)
    assert user is not None
    # ... many more assertions
```

#### 4. Add Module-Level Tests

Include tests for router configuration and exports:

```python
class TestRouterConfiguration:
    """Tests for router setup."""

    def test_router_is_api_router(self):
        from fastapi import APIRouter
        from app.core.routers.auth import router

        assert isinstance(router, APIRouter)

    def test_router_has_correct_prefix(self):
        from app.core.routers.auth import router

        assert router.prefix == "/auth"

    def test_router_has_correct_tags(self):
        from app.core.routers.auth import router

        assert "Authentication" in router.tags
```

### Troubleshooting

#### "Event loop is closed" Error

This usually means an async resource (like Stripe's HTTP client) is trying to clean up after the test. The `mock_stripe` fixture automatically handles this by mocking Stripe API calls.

#### Test Data Not Visible to App

Ensure you're using fixtures that depend on `db_session`. The session override makes test data visible to the app within the same transaction.

#### Flaky Tests

If tests pass individually but fail when run together:

1. Check for shared state between tests
2. Ensure all fixtures are function-scoped
3. Verify database records are created within the test transaction

#### Slow Tests

- Use `pytest -x` to stop on first failure
- Run specific test files during development
- Use `--tb=short` for shorter tracebacks

## Writing Tests

### Test Organization

Tests are organized by the module they test:

- `test_<module_name>.py` for each module
- Use classes to group related tests: `TestFunctionName` or `TestEndpointName`
- Use descriptive test names: `test_<what>_<condition>_<expected>`

### Example Unit Test

```python
class TestMyFunction:
    """Test suite for my_function."""

    def test_my_function_success(self):
        """Test successful execution."""
        result = my_function("input")
        assert result == "expected_output"

    def test_my_function_with_none(self):
        """Test handling of None input."""
        result = my_function(None)
        assert result is None
```

### Example Integration Test

```python
class TestCreateUser:
    """Tests for POST /users endpoint."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, client: AsyncClient):
        """Should create user and return 201."""
        response = await client.post(
            "/users",
            json={"email": "new@example.com", "password": "secure123"},
        )

        assert response.status_code == 201
        assert response.json()["email"] == "new@example.com"

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(
        self, client: AsyncClient, test_user
    ):
        """Should return 400 for duplicate email."""
        response = await client.post(
            "/users",
            json={"email": test_user.email, "password": "secure123"},
        )

        assert response.status_code == 400
```

### Async Tests

For async functions, use the `@pytest.mark.asyncio` decorator:

```python
@pytest.mark.asyncio
async def test_async_function():
    """Test async function."""
    result = await my_async_function()
    assert result is not None
```

### Using Fixtures

Fixtures provide reusable test data and setup:

```python
@pytest.fixture
def sample_user():
    """Create a sample user for testing."""
    return {"id": 1, "email": "test@example.com"}


def test_with_fixture(sample_user):
    """Test using a fixture."""
    assert sample_user["id"] == 1
```

### Using Mocks

Mock external dependencies to isolate tests:

```python
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_with_mock(client: AsyncClient):
    """Test with mocked external service."""
    with patch(
        "app.services.external.call_api",
        new_callable=AsyncMock,
        return_value={"data": "mocked"},
    ):
        response = await client.get("/endpoint")

    assert response.status_code == 200
```

## Coverage

### Current Test Count: 1700+ tests

Check coverage with:

```bash
pytest --cov=app --cov-report=term-missing
```

Or generate an HTML report:

```bash
pytest --cov=app --cov-report=html
```

Then open `htmlcov/index.html` in your browser.

## Continuous Integration

Tests are automatically run in CI/CD pipelines. Ensure all tests pass before submitting pull requests:

```bash
# Run full test suite before pushing
pytest --tb=short

# Run with coverage to ensure adequate coverage
pytest --cov=app --cov-fail-under=70
```
