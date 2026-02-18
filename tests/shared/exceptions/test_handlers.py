"""
Test suite for exception handlers.

Run tests:
    pytest app/tests/shared/exceptions/test_handlers.py -v

Run with coverage:
    pytest app/tests/shared/exceptions/test_handlers.py --cov=app.core.exceptions.handlers --cov-report=term-missing -v
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import status

from app.core.exceptions.handlers import (
    general_exception_handler,
    database_exception_handler,
    exception_schema,
)
from app.core.exceptions.types import AppException, DatabaseException


class TestGeneralExceptionHandler:
    """Test suite for general_exception_handler."""

    @pytest.mark.asyncio
    async def test_general_exception_handler_returns_json_response(self):
        """Test that general exception handler returns proper JSON response."""
        mock_request = MagicMock()
        exc = AppException("Test error", status_code=status.HTTP_400_BAD_REQUEST)

        with patch("app.core.exceptions.handlers.request_logger") as mock_logger:
            response = await general_exception_handler(mock_request, exc)

            # Verify logger was called
            mock_logger.error.assert_called_once()
            assert "GeneralException" in str(mock_logger.error.call_args[0][0])

            # Verify response
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert b"An unexpected error occurred" in response.body
            assert b"Test error" in response.body

    @pytest.mark.asyncio
    async def test_general_exception_handler_with_default_500_status(self):
        """Test general exception handler with default 500 status."""
        mock_request = MagicMock()
        exc = AppException("Internal error")

        with patch("app.core.exceptions.handlers.request_logger"):
            response = await general_exception_handler(mock_request, exc)

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert b"An unexpected error occurred" in response.body


class TestDatabaseExceptionHandler:
    """Test suite for database_exception_handler."""

    @pytest.mark.asyncio
    async def test_database_exception_handler_returns_json_response(self):
        """Test that database exception handler returns proper JSON response."""
        mock_request = MagicMock()
        exc = DatabaseException("Connection lost")

        with patch("app.core.exceptions.handlers.request_logger") as mock_logger:
            response = await database_exception_handler(mock_request, exc)

            # Verify logger was called
            mock_logger.error.assert_called_once()
            assert "DatabaseException" in str(mock_logger.error.call_args[0][0])

            # Verify response
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert b"A database error occurred" in response.body
            assert b"Connection lost" in response.body

    @pytest.mark.asyncio
    async def test_database_exception_handler_with_default_message(self):
        """Test database exception handler with default message."""
        mock_request = MagicMock()
        exc = DatabaseException()

        with patch("app.core.exceptions.handlers.request_logger"):
            response = await database_exception_handler(mock_request, exc)

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert b"A database error occurred" in response.body


class TestExceptionSchema:
    """Test suite for exception_schema."""

    def test_exception_schema_structure(self):
        """Test that exception_schema has proper structure."""
        assert isinstance(exception_schema, dict)
        assert status.HTTP_500_INTERNAL_SERVER_ERROR in exception_schema

        # Check schema content
        schema_entry = exception_schema[status.HTTP_500_INTERNAL_SERVER_ERROR]
        assert "description" in schema_entry
        assert "content" in schema_entry
        assert "application/json" in schema_entry["content"]
        assert "example" in schema_entry["content"]["application/json"]
