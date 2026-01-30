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

- `test_utils.py` - Tests for utility functions in `app.shared.utils`
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

The project aims for high test coverage (>80%). Check coverage with:

```bash
pytest --cov=app --cov-report=term-missing
```

## Continuous Integration

Tests are automatically run in CI/CD pipelines. Ensure all tests pass before submitting pull requests.
