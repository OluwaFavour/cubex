"""
Shared dependencies for FastAPI endpoints.

This module exports all shared FastAPI dependency functions
used across multiple application modules.
"""

from app.shared.dependencies.auth import (
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
]
