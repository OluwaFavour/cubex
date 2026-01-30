from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.shared.config import request_logger
from app.shared.exceptions.types import (
    AppException,
    AuthenticationException,
    DatabaseException,
    OAuthException,
    OTPExpiredException,
    OTPInvalidException,
    RateLimitExceededException,
    TooManyAttemptsException,
)


async def general_exception_handler(request: Request, exc: AppException):
    """
    Handles general exceptions by returning a JSON response with the error message.

    Args:
        request: The request object.
        exc (AppException): The exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 500.
    """
    request_logger.error(f"GeneralException: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": f"An unexpected error occurred.\n{str(exc)}"},
    )


async def database_exception_handler(request: Request, exc: DatabaseException):
    """
    Handles database exceptions by returning a JSON response with the error message.

    Args:
        request: The request object.
        exc (DatabaseException): The database exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 500.
    """
    request_logger.error(f"DatabaseException: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": f"A database error occurred.\n{str(exc)}"},
    )


async def authentication_exception_handler(
    request: Request, exc: AuthenticationException
):
    """
    Handles authentication exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (AuthenticationException): The authentication exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 401.
    """
    request_logger.warning(f"AuthenticationException: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def oauth_exception_handler(request: Request, exc: OAuthException):
    """
    Handles OAuth exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (OAuthException): The OAuth exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 400.
    """
    request_logger.warning(f"OAuthException: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
    )


async def otp_expired_exception_handler(request: Request, exc: OTPExpiredException):
    """
    Handles OTP expired exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (OTPExpiredException): The OTP expired exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 400.
    """
    request_logger.warning(f"OTPExpiredException: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
    )


async def otp_invalid_exception_handler(request: Request, exc: OTPInvalidException):
    """
    Handles OTP invalid exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (OTPInvalidException): The OTP invalid exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 400.
    """
    request_logger.warning(f"OTPInvalidException: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
    )


async def too_many_attempts_exception_handler(
    request: Request, exc: TooManyAttemptsException
):
    """
    Handles too many attempts exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (TooManyAttemptsException): The too many attempts exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 429.
    """
    request_logger.warning(f"TooManyAttemptsException: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
    )


async def rate_limit_exception_handler(
    request: Request, exc: RateLimitExceededException
):
    """
    Handles rate limit exceeded exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (RateLimitExceededException): The rate limit exception instance.

    Returns:
        JSONResponse: A response with status code 429 and optional Retry-After header.
    """
    request_logger.warning(f"RateLimitExceededException: {exc}")
    headers = {}
    if exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
        headers=headers,
    )


exception_schema = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "description": "Internal Server Error",
        "content": {
            "application/json": {
                "example": {"detail": "Some internal server error message"},
            }
        },
    },
    status.HTTP_401_UNAUTHORIZED: {
        "description": "Authentication Error",
        "content": {
            "application/json": {
                "example": {"detail": "Authentication failed."},
            }
        },
    },
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "description": "Rate Limit Exceeded",
        "content": {
            "application/json": {
                "example": {"detail": "Rate limit exceeded. Please try again later."},
            }
        },
    },
}


__all__ = [
    "general_exception_handler",
    "database_exception_handler",
    "authentication_exception_handler",
    "oauth_exception_handler",
    "otp_expired_exception_handler",
    "otp_invalid_exception_handler",
    "too_many_attempts_exception_handler",
    "rate_limit_exception_handler",
    "exception_schema",
]
