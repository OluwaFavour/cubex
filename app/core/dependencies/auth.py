"""
Authentication dependencies for FastAPI endpoints.

- Extracting and validating JWT access tokens from requests
- Getting the current authenticated user
- Ensuring user is active and verified
- Optional authentication for public endpoints

Example usage:
    from app.core.dependencies.auth import get_current_user, get_current_active_user

    @router.get("/me")
    async def get_profile(user: User = Depends(get_current_active_user)):
        return user

    @router.get("/public")
    async def public_endpoint(user: User | None = Depends(get_optional_user)):
        if user:
            return {"message": f"Hello, {user.full_name}"}
        return {"message": "Hello, guest"}
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.db import get_async_session
from app.core.config import auth_logger
from app.core.db.crud import user_db
from app.core.db.models import User
from app.core.exceptions.types import AuthenticationException, ForbiddenException
from app.core.utils import decode_jwt_token

# Security scheme for Bearer token authentication
# auto_error=True returns 401 if no token, auto_error=False returns None
bearer_scheme = HTTPBearer(auto_error=True)
optional_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """
    Extract and validate the JWT access token from the Authorization header.

    This dependency:
    1. Extracts the Bearer token from the Authorization header
    2. Decodes and validates the JWT token
    3. Fetches the user from the database
    4. Returns the user object

    Args:
        credentials: The HTTP Bearer credentials containing the access token.
        session: The database session.

    Returns:
        User: The authenticated user object.

    Raises:
        HTTPException: 401 if token is missing, invalid, expired, or user not found.

    Example:
        @router.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user_id": str(user.id)}
    """
    token = credentials.credentials

    # Decode and validate the token
    payload = decode_jwt_token(token)

    if payload is None:
        auth_logger.warning("Authentication failed: invalid or expired token")
        raise AuthenticationException("Invalid or expired access token")

    user_id_str = payload.get("sub")
    if not user_id_str:
        auth_logger.warning("Authentication failed: token missing 'sub' claim")
        raise AuthenticationException("Invalid access token")

    token_type = payload.get("type")
    if token_type != "access":
        auth_logger.warning(f"Authentication failed: wrong token type '{token_type}'")
        raise AuthenticationException("Invalid access token")

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        auth_logger.warning(
            f"Authentication failed: invalid user ID format '{user_id_str}'"
        )
        raise AuthenticationException("Invalid access token")

    # Fetch user from database (use transaction to avoid leaving implicit transaction open)
    async with session.begin():
        user = await user_db.get_by_id(session=session, id=user_id)

    if user is None:
        auth_logger.warning(f"Authentication failed: user not found {user_id}")
        raise AuthenticationException("User not found")

    if user.is_deleted:
        auth_logger.warning(f"Authentication failed: user deleted {user_id}")
        raise AuthenticationException("User account has been deleted")

    auth_logger.debug(f"User authenticated: {user.email}")
    return user


async def get_current_active_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Ensure the current user is active.

    This dependency wraps get_current_user and adds an additional
    check to ensure the user's account is active.

    Args:
        user: The authenticated user from get_current_user.

    Returns:
        User: The authenticated and active user object.

    Raises:
        HTTPException: 403 if user account is deactivated.

    Example:
        @router.post("/action")
        async def some_action(user: User = Depends(get_current_active_user)):
            # Only active users can access this
            return {"success": True}
    """
    if not user.is_active:
        auth_logger.warning(f"Access denied: user deactivated {user.email}")
        raise ForbiddenException("User account is deactivated")

    return user


async def get_current_verified_user(
    user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """
    Ensure the current user has verified their email.

    This dependency wraps get_current_active_user and adds an additional
    check to ensure the user's email is verified.

    Args:
        user: The authenticated and active user.

    Returns:
        User: The authenticated, active, and verified user object.

    Raises:
        HTTPException: 403 if email is not verified.

    Example:
        @router.post("/sensitive-action")
        async def sensitive_action(user: User = Depends(get_current_verified_user)):
            # Only verified users can access this
            return {"success": True}
    """
    if not user.email_verified:
        auth_logger.warning(f"Access denied: email not verified {user.email}")
        raise ForbiddenException("Email verification required")

    return user


async def get_optional_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(optional_bearer_scheme),
    ],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> User | None:
    """
    Optionally get the current user if an access token is provided.

    This dependency is useful for endpoints that work for both
    authenticated and unauthenticated users, but may provide
    enhanced functionality for authenticated users.

    Args:
        credentials: Optional HTTP Bearer credentials.
        session: The database session.

    Returns:
        User | None: The authenticated user if token is valid, None otherwise.

    Example:
        @router.get("/content")
        async def get_content(user: User | None = Depends(get_optional_user)):
            if user:
                return {"content": "personalized", "user": user.email}
            return {"content": "generic"}
    """
    if credentials is None:
        return None

    token = credentials.credentials

    # Decode and validate the token
    payload = decode_jwt_token(token)
    if payload is None:
        return None

    user_id_str = payload.get("sub")
    if not user_id_str:
        return None

    token_type = payload.get("type")
    if token_type != "access":
        return None

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        return None

    # Fetch user from database (use transaction to avoid leaving implicit transaction open)
    async with session.begin():
        user = await user_db.get_by_id(session=session, id=user_id)

    if user is None or user.is_deleted or not user.is_active:
        return None

    return user


# Type aliases for cleaner dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
CurrentVerifiedUser = Annotated[User, Depends(get_current_verified_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


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
