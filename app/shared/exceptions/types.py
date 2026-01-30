from fastapi import status


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: dict | None = None,
    ):
        self.message = message
        self.status_code = status_code or status.HTTP_500_INTERNAL_SERVER_ERROR
        self.details = details
        super().__init__(message)


class DatabaseException(AppException):
    """Exception raised for database-related errors."""

    def __init__(self, message: str = "A database error occurred."):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR)


class AuthenticationException(AppException):
    """Exception raised for authentication-related errors."""

    def __init__(self, message: str = "Authentication failed."):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED)


class InvalidCredentialsException(AuthenticationException):
    """Exception raised when provided credentials are invalid."""

    def __init__(self, message: str = "Invalid email or password."):
        super().__init__(message)


class OAuthException(AppException):
    """Exception raised for OAuth-related errors."""

    def __init__(self, message: str = "OAuth authentication failed."):
        super().__init__(message, status.HTTP_400_BAD_REQUEST)


class OTPExpiredException(AppException):
    """Exception raised when OTP has expired."""

    def __init__(self, message: str = "OTP has expired. Please request a new one."):
        super().__init__(message, status.HTTP_400_BAD_REQUEST)


class OTPInvalidException(AppException):
    """Exception raised when OTP is invalid."""

    def __init__(self, message: str = "Invalid OTP code."):
        super().__init__(message, status.HTTP_400_BAD_REQUEST)


class TooManyAttemptsException(AppException):
    """Exception raised when too many OTP verification attempts."""

    def __init__(self, message: str = "Too many attempts. Please request a new OTP."):
        super().__init__(message, status.HTTP_429_TOO_MANY_REQUESTS)


class RateLimitExceededException(AppException):
    """Exception raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please try again later.",
        retry_after: int | None = None,
    ):
        super().__init__(message, status.HTTP_429_TOO_MANY_REQUESTS)
        self.retry_after = retry_after


__all__ = [
    "AppException",
    "DatabaseException",
    "AuthenticationException",
    "InvalidCredentialsException",
    "OAuthException",
    "OTPExpiredException",
    "OTPInvalidException",
    "TooManyAttemptsException",
    "RateLimitExceededException",
]
