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


class NotFoundException(AppException):
    """Exception raised when a resource is not found."""

    def __init__(self, message: str = "Resource not found."):
        super().__init__(message, status.HTTP_404_NOT_FOUND)


class UserNotFoundException(NotFoundException):
    """Exception raised when a user is not found."""

    def __init__(self, message: str = "User not found."):
        super().__init__(message)


class ConflictException(AppException):
    """Exception raised when there's a conflict with existing resources."""

    def __init__(self, message: str = "Resource conflict."):
        super().__init__(message, status.HTTP_409_CONFLICT)


class UserAlreadyExistsException(ConflictException):
    """Exception raised when a user already exists."""

    def __init__(self, message: str = "User with this email already exists."):
        super().__init__(message)


class BadRequestException(AppException):
    """Exception raised for bad request errors."""

    def __init__(self, message: str = "Bad request."):
        super().__init__(message, status.HTTP_400_BAD_REQUEST)


class ForbiddenException(AppException):
    """Exception raised when access is forbidden."""

    def __init__(self, message: str = "Access forbidden."):
        super().__init__(message, status.HTTP_403_FORBIDDEN)


class PaymentRequiredException(AppException):
    """Exception raised when payment is required."""

    def __init__(self, message: str = "Payment required."):
        super().__init__(message, status.HTTP_402_PAYMENT_REQUIRED)


class InvalidStateException(BadRequestException):
    """Exception raised when OAuth state parameter is invalid."""

    def __init__(self, message: str = "Invalid state parameter."):
        super().__init__(message)


class StripeAPIException(AppException):
    """Exception raised for Stripe API errors."""

    def __init__(
        self,
        message: str = "A Stripe API error occurred.",
        status_code: int = status.HTTP_502_BAD_GATEWAY,
        stripe_code: str | None = None,
        error_type: str = "api_error",
        param: str | None = None,
        request_id: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, status_code, details)
        self.stripe_code = stripe_code
        self.error_type = error_type
        self.param = param
        self.request_id = request_id


class StripeCardException(AppException):
    """Exception raised for Stripe card errors (declined, invalid, etc.)."""

    def __init__(
        self,
        message: str = "Card was declined.",
        stripe_code: str | None = None,
        decline_code: str | None = None,
        param: str | None = None,
        request_id: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, status.HTTP_402_PAYMENT_REQUIRED, details)
        self.stripe_code = stripe_code
        self.decline_code = decline_code
        self.param = param
        self.request_id = request_id


class IdempotencyException(AppException):
    """Exception raised for Stripe idempotency errors."""

    def __init__(
        self,
        message: str = "Idempotency key was used with different parameters.",
        request_id: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, status.HTTP_409_CONFLICT, details)
        self.request_id = request_id


class RateLimitException(AppException):
    """Exception raised when Stripe rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Stripe rate limit exceeded. Please try again later.",
        details: dict | None = None,
    ):
        super().__init__(message, status.HTTP_429_TOO_MANY_REQUESTS, details)


class NotImplementedException(AppException):
    """Exception raised when a feature is not yet implemented."""

    def __init__(
        self,
        message: str = "This feature is not yet implemented.",
        details: dict | None = None,
    ):
        super().__init__(message, status.HTTP_501_NOT_IMPLEMENTED, details)


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
    "NotFoundException",
    "UserNotFoundException",
    "ConflictException",
    "UserAlreadyExistsException",
    "BadRequestException",
    "ForbiddenException",
    "PaymentRequiredException",
    "InvalidStateException",
    "StripeAPIException",
    "StripeCardException",
    "IdempotencyException",
    "RateLimitException",
    "NotImplementedException",
]

