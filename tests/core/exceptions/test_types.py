"""
Test suite for custom exception types.

Run tests:
    pytest app/tests/core/exceptions/test_types.py -v

Run with coverage:
    pytest app/tests/core/exceptions/test_types.py --cov=app.core.exceptions.types --cov-report=term-missing -v
"""

from fastapi import status

from app.core.exceptions.types import AppException, DatabaseException


class TestAppException:
    """Test suite for AppException."""

    def test_app_exception_with_message_only(self):
        """Test AppException with message only."""
        exc = AppException("Test error")

        assert exc.message == "Test error"
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert str(exc) == "Test error"

    def test_app_exception_with_custom_status_code(self):
        """Test AppException with custom status code."""
        exc = AppException("Test error", status_code=status.HTTP_400_BAD_REQUEST)

        assert exc.message == "Test error"
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert str(exc) == "Test error"

    def test_app_exception_with_none_status_code(self):
        """Test AppException with None status code defaults to 500."""
        exc = AppException("Test error", status_code=None)

        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_app_exception_inheritance(self):
        """Test that AppException inherits from Exception."""
        exc = AppException("Test error")

        assert isinstance(exc, Exception)
        assert isinstance(exc, AppException)


class TestDatabaseException:
    """Test suite for DatabaseException."""

    def test_database_exception_default_message(self):
        """Test DatabaseException with default message."""
        exc = DatabaseException()

        assert exc.message == "A database error occurred."
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert str(exc) == "A database error occurred."

    def test_database_exception_custom_message(self):
        """Test DatabaseException with custom message."""
        exc = DatabaseException("Connection failed")

        assert exc.message == "Connection failed"
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert str(exc) == "Connection failed"

    def test_database_exception_inheritance(self):
        """Test that DatabaseException inherits from AppException."""
        exc = DatabaseException()

        assert isinstance(exc, Exception)
        assert isinstance(exc, AppException)
        assert isinstance(exc, DatabaseException)

    def test_database_exception_always_has_500_status(self):
        """Test that DatabaseException always has 500 status code."""
        exc = DatabaseException("Test database error")

        # DatabaseException always sets status to 500 internally
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
