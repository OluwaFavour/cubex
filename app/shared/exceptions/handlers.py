from typing import Any, cast

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.shared.config import request_logger
from app.shared.exceptions.types import (
    AppException,
    AuthenticationException,
    BadRequestException,
    ConflictException,
    DatabaseException,
    ForbiddenException,
    IdempotencyException,
    NotFoundException,
    OAuthException,
    OTPExpiredException,
    OTPInvalidException,
    RateLimitException,
    RateLimitExceededException,
    StripeAPIException,
    StripeCardException,
    TooManyAttemptsException,
)


async def general_exception_handler(request: Request, exc: Exception):
    """
    Handles general exceptions by returning a JSON response with the error message.

    Args:
        request: The request object.
        exc (AppException): The exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 500.
    """
    app_exc = cast(AppException, exc)
    request_logger.error(f"GeneralException: {exc}")
    return JSONResponse(
        status_code=app_exc.status_code,
        content={"detail": f"An unexpected error occurred.\n{str(exc)}"},
    )


async def database_exception_handler(request: Request, exc: Exception):
    """
    Handles database exceptions by returning a JSON response with the error message.

    Args:
        request: The request object.
        exc (DatabaseException): The database exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 500.
    """
    db_exc = cast(DatabaseException, exc)
    request_logger.error(f"DatabaseException: {exc}")
    return JSONResponse(
        status_code=db_exc.status_code,
        content={"detail": f"A database error occurred.\n{str(exc)}"},
    )


async def authentication_exception_handler(request: Request, exc: Exception):
    """
    Handles authentication exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (AuthenticationException): The authentication exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 401.
    """
    auth_exc = cast(AuthenticationException, exc)
    request_logger.warning(f"AuthenticationException: {exc}")
    return JSONResponse(
        status_code=auth_exc.status_code,
        content={"detail": str(exc)},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def oauth_exception_handler(request: Request, exc: Exception):
    """
    Handles OAuth exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (OAuthException): The OAuth exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 400.
    """
    oauth_exc = cast(OAuthException, exc)
    request_logger.warning(f"OAuthException: {exc}")
    return JSONResponse(
        status_code=oauth_exc.status_code,
        content={"detail": str(exc)},
    )


async def otp_expired_exception_handler(request: Request, exc: Exception):
    """
    Handles OTP expired exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (OTPExpiredException): The OTP expired exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 400.
    """
    otp_exc = cast(OTPExpiredException, exc)
    request_logger.warning(f"OTPExpiredException: {exc}")
    return JSONResponse(
        status_code=otp_exc.status_code,
        content={"detail": str(exc)},
    )


async def otp_invalid_exception_handler(request: Request, exc: Exception):
    """
    Handles OTP invalid exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (OTPInvalidException): The OTP invalid exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 400.
    """
    otp_exc = cast(OTPInvalidException, exc)
    request_logger.warning(f"OTPInvalidException: {exc}")
    return JSONResponse(
        status_code=otp_exc.status_code,
        content={"detail": str(exc)},
    )


async def too_many_attempts_exception_handler(request: Request, exc: Exception):
    """
    Handles too many attempts exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (TooManyAttemptsException): The too many attempts exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 429.
    """
    tma_exc = cast(TooManyAttemptsException, exc)
    request_logger.warning(f"TooManyAttemptsException: {exc}")
    return JSONResponse(
        status_code=tma_exc.status_code,
        content={"detail": str(exc)},
    )


async def rate_limit_exception_handler(request: Request, exc: Exception):
    """
    Handles rate limit exceeded exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (RateLimitExceededException): The rate limit exception instance.

    Returns:
        JSONResponse: A response with status code 429 and optional Retry-After header.
    """
    rate_exc = cast(RateLimitExceededException, exc)
    request_logger.warning(f"RateLimitExceededException: {exc}")
    headers = {}
    if rate_exc.retry_after:
        headers["Retry-After"] = str(rate_exc.retry_after)
    return JSONResponse(
        status_code=rate_exc.status_code,
        content={"detail": str(exc)},
        headers=headers,
    )


async def not_found_exception_handler(request: Request, exc: Exception):
    """
    Handles not found exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (NotFoundException): The not found exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 404.
    """
    nf_exc = cast(NotFoundException, exc)
    request_logger.warning(f"NotFoundException: {exc}")
    return JSONResponse(
        status_code=nf_exc.status_code,
        content={"detail": str(exc)},
    )


async def conflict_exception_handler(request: Request, exc: Exception):
    """
    Handles conflict exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (ConflictException): The conflict exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 409.
    """
    conf_exc = cast(ConflictException, exc)
    request_logger.warning(f"ConflictException: {exc}")
    return JSONResponse(
        status_code=conf_exc.status_code,
        content={"detail": str(exc)},
    )


async def bad_request_exception_handler(request: Request, exc: Exception):
    """
    Handles bad request exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (BadRequestException): The bad request exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 400.
    """
    br_exc = cast(BadRequestException, exc)
    request_logger.warning(f"BadRequestException: {exc}")
    return JSONResponse(
        status_code=br_exc.status_code,
        content={"detail": str(exc)},
    )


async def forbidden_exception_handler(request: Request, exc: Exception):
    """
    Handles forbidden exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (ForbiddenException): The forbidden exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 403.
    """
    forb_exc = cast(ForbiddenException, exc)
    request_logger.warning(f"ForbiddenException: {exc}")
    return JSONResponse(
        status_code=forb_exc.status_code,
        content={"detail": str(exc)},
    )


async def stripe_api_exception_handler(request: Request, exc: Exception):
    """
    Handles Stripe API exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (StripeAPIException): The Stripe API exception instance.

    Returns:
        JSONResponse: A response containing the error details and appropriate status code.
    """
    stripe_exc = cast(StripeAPIException, exc)
    request_logger.error(
        f"StripeAPIException: {exc} | Request-Id: {stripe_exc.request_id}"
    )
    return JSONResponse(
        status_code=stripe_exc.status_code,
        content={
            "detail": str(exc),
            "error_type": stripe_exc.error_type,
            "stripe_code": stripe_exc.stripe_code,
            "request_id": stripe_exc.request_id,
        },
    )


async def stripe_card_exception_handler(request: Request, exc: Exception):
    """
    Handles Stripe card exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (StripeCardException): The Stripe card exception instance.

    Returns:
        JSONResponse: A response containing the card error details and status code 402.
    """
    card_exc = cast(StripeCardException, exc)
    request_logger.warning(
        f"StripeCardException: {exc} | Decline code: {card_exc.decline_code}"
    )
    return JSONResponse(
        status_code=card_exc.status_code,
        content={
            "detail": str(exc),
            "stripe_code": card_exc.stripe_code,
            "decline_code": card_exc.decline_code,
            "param": card_exc.param,
        },
    )


async def idempotency_exception_handler(request: Request, exc: Exception):
    """
    Handles idempotency exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (IdempotencyException): The idempotency exception instance.

    Returns:
        JSONResponse: A response containing the error details and status code 409.
    """
    idemp_exc = cast(IdempotencyException, exc)
    request_logger.warning(
        f"IdempotencyException: {exc} | Request-Id: {idemp_exc.request_id}"
    )
    return JSONResponse(
        status_code=idemp_exc.status_code,
        content={
            "detail": str(exc),
            "request_id": idemp_exc.request_id,
        },
    )


async def stripe_rate_limit_exception_handler(request: Request, exc: Exception):
    """
    Handles Stripe rate limit exceptions by returning a JSON response.

    Args:
        request: The request object.
        exc (RateLimitException): The Stripe rate limit exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 429.
    """
    rate_exc = cast(RateLimitException, exc)
    request_logger.warning(f"RateLimitException (Stripe): {exc}")
    return JSONResponse(
        status_code=rate_exc.status_code,
        content={"detail": str(exc)},
    )


exception_schema: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        "description": "Bad Request",
        "content": {
            "application/json": {
                "example": {"detail": "Bad request error message"},
            }
        },
    },
    status.HTTP_404_NOT_FOUND: {
        "description": "Not Found",
        "content": {
            "application/json": {
                "example": {"detail": "Resource not found."},
            }
        },
    },
    status.HTTP_409_CONFLICT: {
        "description": "Conflict",
        "content": {
            "application/json": {
                "example": {"detail": "Resource conflict."},
            }
        },
    },
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
    "not_found_exception_handler",
    "conflict_exception_handler",
    "bad_request_exception_handler",
    "forbidden_exception_handler",
    "stripe_api_exception_handler",
    "stripe_card_exception_handler",
    "idempotency_exception_handler",
    "stripe_rate_limit_exception_handler",
    "exception_schema",
]
