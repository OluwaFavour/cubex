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

    def test_app_exception_with_message_only(self):
        exc = AppException("Test error")

        assert exc.message == "Test error"
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert str(exc) == "Test error"

    def test_app_exception_with_custom_status_code(self):
        exc = AppException("Test error", status_code=status.HTTP_400_BAD_REQUEST)

        assert exc.message == "Test error"
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert str(exc) == "Test error"

    def test_app_exception_with_none_status_code(self):
        exc = AppException("Test error", status_code=None)

        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_app_exception_inheritance(self):
        exc = AppException("Test error")

        assert isinstance(exc, Exception)
        assert isinstance(exc, AppException)


class TestDatabaseException:

    def test_database_exception_default_message(self):
        exc = DatabaseException()

        assert exc.message == "A database error occurred."
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert str(exc) == "A database error occurred."

    def test_database_exception_custom_message(self):
        exc = DatabaseException("Connection failed")

        assert exc.message == "Connection failed"
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert str(exc) == "Connection failed"

    def test_database_exception_inheritance(self):
        exc = DatabaseException()

        assert isinstance(exc, Exception)
        assert isinstance(exc, AppException)
        assert isinstance(exc, DatabaseException)

    def test_database_exception_always_has_500_status(self):
        exc = DatabaseException("Test database error")

        # DatabaseException always sets status to 500 internally
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
