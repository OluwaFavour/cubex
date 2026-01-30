# Tests

This directory contains all unit tests, integration tests, and test utilities for the application.

## Setup

Install test dependencies:

```bash
pip install -r requirements-dev.txt
```

## Running Tests

### Run all tests

```bash
pytest
```

### Run specific test file

```bash
pytest app/tests/test_utils.py
```

### Run specific test class

```bash
pytest app/tests/test_utils.py::TestHashPassword
```

### Run specific test function

```bash
pytest app/tests/test_utils.py::TestHashPassword::test_hash_password_success
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

## Test Structure

### Core Tests

- `core/test_dependencies.py` - Tests for FastAPI dependencies (3 tests)

### Main Application Tests

- `test_main.py` - Tests for FastAPI app initialization and endpoints (33 tests)
- `test_utils.py` - Tests for utility functions in `app.shared.utils` (76 tests)

### Services Tests

- `services/test_brevo.py` - Tests for Brevo email service (41 tests)
- `services/test_cloudinary.py` - Tests for Cloudinary file service (23 tests)
- `services/test_template.py` - Tests for Jinja2 template rendering (17 tests)

### Infrastructure Tests

- `infrastructure/messaging/test_connection.py` - RabbitMQ connection (5 tests)
- `infrastructure/messaging/test_queues.py` - Queue configuration (17 tests)
- `infrastructure/messaging/test_publisher.py` - Event publishing (7 tests)
- `infrastructure/messaging/test_consumer.py` - Message processing (13 tests)
- `infrastructure/messaging/test_main.py` - Consumer startup (10 tests)
- `infrastructure/scheduler/test_main.py` - Scheduler initialization (4 tests)

### Shared Module Tests

- `shared/db/test_config.py` - Database configuration (7 tests)
- `shared/exceptions/test_types.py` - Exception types (8 tests)
- `shared/exceptions/test_handlers.py` - Exception handlers (5 tests)
- `shared/test_logger.py` - Logger and Sentry integration (17 tests)

### Configuration

- `conftest.py` - Shared pytest fixtures and configuration

## Writing Tests

### Test Organization

Tests are organized by the module they test:

- `test_<module_name>.py` for each module
- Use classes to group related tests: `TestFunctionName`
- Use descriptive test names: `test_<what>_<condition>_<expected>`

### Example Test

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

## Coverage

**Current Coverage: 100%** (676/676 statements)

The project maintains 100% test coverage across all modules. Check coverage with:

```bash
pytest --cov=app --cov-report=term-missing
```

### Coverage by Module

- Core: 100% (6 statements)
- Main: 100% (78 statements)
- Utils: 100% (132 statements)
- Services: 100% (207 statements)
- Infrastructure: 100% (110 statements)
- Shared: 100% (143 statements)

## Continuous Integration

Tests are automatically run in CI/CD pipelines. Ensure all tests pass before submitting pull requests.
