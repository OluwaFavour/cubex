from fastapi import status


class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code or status.HTTP_500_INTERNAL_SERVER_ERROR
        super().__init__(message)


class DatabaseException(AppException):
    """Exception raised for database-related errors."""

    def __init__(self, message: str = "A database error occurred."):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR)
