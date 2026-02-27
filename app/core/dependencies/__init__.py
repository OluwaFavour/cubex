"""
Shared dependencies for FastAPI endpoints.

"""

from app.core.dependencies.auth import (
    get_current_user,
    get_current_active_user,
    get_current_verified_user,
    get_optional_user,
    CurrentUser,
    CurrentActiveUser,
    CurrentVerifiedUser,
    OptionalUser,
    bearer_scheme,
    optional_bearer_scheme,
)
from app.core.dependencies.db import get_async_session
from app.core.dependencies.internal import (
    verify_internal_api_key,
    InternalAPIKeyDep,
    InvalidInternalAPIKeyException,
)

__all__ = [
    "get_current_user",
    "get_current_active_user",
    "get_current_verified_user",
    "get_optional_user",
    "CurrentUser",
    "CurrentActiveUser",
    "CurrentVerifiedUser",
    "OptionalUser",
    "bearer_scheme",
    "optional_bearer_scheme",
    # Dependency functions
    "verify_internal_api_key",
    # Type aliases
    "InternalAPIKeyDep",
    # Exceptions
    "InvalidInternalAPIKeyException",
    "get_async_session",
]

