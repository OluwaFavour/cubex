

from typing import Annotated

from fastapi import Depends, Header

from app.core.config import request_logger, settings
from app.core.exceptions.types import AuthenticationException


class InvalidInternalAPIKeyException(AuthenticationException):
    """Raised when internal API key is invalid or missing."""

    def __init__(self, message: str = "Invalid or missing internal API key.") -> None:
        super().__init__(message)


async def verify_internal_api_key(
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> str:
    """
    Verify the internal API key for internal endpoints.

    This dependency validates the X-Internal-API-Key header against
    the configured INTERNAL_API_SECRET. Used for internal communication
    between this app and external developer APIs.

    Args:
        x_internal_api_key: The API key from X-Internal-API-Key header.

    Returns:
        The validated API key.

    Raises:
        InvalidInternalAPIKeyException: If the key is missing or invalid.
    """
    if not x_internal_api_key:
        request_logger.warning("Internal API request missing X-Internal-API-Key header")
        raise InvalidInternalAPIKeyException("Missing X-Internal-API-Key header.")

    if x_internal_api_key != settings.INTERNAL_API_SECRET:
        request_logger.warning("Internal API request with invalid API key")
        raise InvalidInternalAPIKeyException("Invalid internal API key.")

    return x_internal_api_key


# Type alias for internal API authentication
InternalAPIKeyDep = Annotated[str, Depends(verify_internal_api_key)]

__all__ = [
    # Dependency functions
    "verify_internal_api_key",
    # Type aliases
    "InternalAPIKeyDep",
    # Exceptions
    "InvalidInternalAPIKeyException",
]

