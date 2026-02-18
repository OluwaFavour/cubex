"""
Rate limiting service with configurable backends.

This module provides rate limiting functionality with support for both
in-memory and Redis backends. It includes stackable FastAPI dependencies
for per-IP, per-user, and per-endpoint rate limiting.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal

from fastapi import Request

from app.core.config import rate_limit_logger, settings
from app.core.exceptions.types import (
    AuthenticationException,
    RateLimitExceededException,
)
from app.core.services.redis_service import RedisService


@dataclass
class RateLimitResult:
    """
    Result of a rate limit check.

    Attributes:
        allowed: Whether the request is allowed.
        remaining: Number of remaining requests in the current window.
        limit: The maximum number of requests allowed.
        reset_at: When the rate limit window resets.
        retry_after: Seconds until the client can retry (only if not allowed).
    """

    allowed: bool
    remaining: int
    limit: int
    reset_at: datetime
    retry_after: int | None = None


class RateLimitBackend(ABC):
    """
    Abstract base class for rate limit backends.

    Implementations must provide methods for checking rate limits,
    resetting keys, and getting remaining request counts.
    """

    @abstractmethod
    async def check(self, key: str, limit: int, window: int) -> RateLimitResult:
        """
        Check if a request is allowed under the rate limit.

        Args:
            key: The rate limit key (e.g., "ip:192.168.1.1:/api/test").
            limit: Maximum number of requests allowed in the window.
            window: Time window in seconds.

        Returns:
            RateLimitResult with the check outcome.
        """
        pass

    @abstractmethod
    async def reset(self, key: str) -> None:
        """
        Reset the rate limit for a key.

        Args:
            key: The rate limit key to reset.
        """
        pass

    @abstractmethod
    async def get_remaining(self, key: str, limit: int, window: int) -> int:
        """
        Get the remaining number of requests for a key.

        Args:
            key: The rate limit key.
            limit: The configured limit (used if key doesn't exist).
            window: Time window in seconds.

        Returns:
            Number of remaining requests.
        """
        pass


class MemoryBackend(RateLimitBackend):
    """
    In-memory rate limit backend using a dictionary.

    This backend is suitable for single-instance deployments or development.
    For distributed systems, use RedisBackend instead.

    Note:
        Data is lost on application restart.
        Not suitable for multi-process or multi-instance deployments.
    """

    def __init__(self):
        """Initialize the memory backend with an empty store."""
        self._store: dict[str, tuple[int, datetime]] = {}

    async def check(self, key: str, limit: int, window: int) -> RateLimitResult:
        """
        Check if a request is allowed under the rate limit.

        Args:
            key: The rate limit key.
            limit: Maximum requests allowed.
            window: Time window in seconds.

        Returns:
            RateLimitResult with the check outcome.
        """
        now = datetime.now(timezone.utc)

        if key in self._store:
            count, reset_at = self._store[key]

            # Check if window has expired
            if now >= reset_at:
                # Window expired, start fresh
                reset_at = datetime.fromtimestamp(
                    now.timestamp() + window, tz=timezone.utc
                )
                self._store[key] = (1, reset_at)
                rate_limit_logger.debug(f"Rate limit window reset for key: {key}")
                return RateLimitResult(
                    allowed=True,
                    remaining=limit - 1,
                    limit=limit,
                    reset_at=reset_at,
                )

            # Check if limit exceeded
            if count >= limit:
                retry_after = int((reset_at - now).total_seconds())
                rate_limit_logger.warning(
                    f"Rate limit exceeded for key: {key}, retry after: {retry_after}s"
                )
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    limit=limit,
                    reset_at=reset_at,
                    retry_after=max(1, retry_after),
                )

            # Increment count
            self._store[key] = (count + 1, reset_at)
            remaining = limit - count - 1
            rate_limit_logger.debug(
                f"Rate limit check passed for key: {key}, remaining: {remaining}"
            )
            return RateLimitResult(
                allowed=True,
                remaining=remaining,
                limit=limit,
                reset_at=reset_at,
            )

        # New key, create entry
        reset_at = datetime.fromtimestamp(now.timestamp() + window, tz=timezone.utc)
        self._store[key] = (1, reset_at)
        rate_limit_logger.debug(f"New rate limit entry created for key: {key}")
        return RateLimitResult(
            allowed=True,
            remaining=limit - 1,
            limit=limit,
            reset_at=reset_at,
        )

    async def reset(self, key: str) -> None:
        """
        Reset the rate limit for a key.

        Args:
            key: The rate limit key to reset.
        """
        if key in self._store:
            del self._store[key]
            rate_limit_logger.debug(f"Rate limit reset for key: {key}")

    async def get_remaining(self, key: str, limit: int, window: int) -> int:
        """
        Get the remaining number of requests for a key.

        Args:
            key: The rate limit key.
            limit: The configured limit.
            window: Time window in seconds.

        Returns:
            Number of remaining requests.
        """
        if key not in self._store:
            return limit

        count, reset_at = self._store[key]
        now = datetime.now(timezone.utc)

        # If window expired, full limit available
        if now >= reset_at:
            return limit

        return max(0, limit - count)


class RedisBackend(RateLimitBackend):
    """
    Redis-based rate limit backend.

    This backend is suitable for distributed systems where multiple
    instances need to share rate limit state. Uses Redis INCR with
    expiration for atomic counter operations.
    """

    async def check(self, key: str, limit: int, window: int) -> RateLimitResult:
        """
        Check if a request is allowed under the rate limit.

        Uses Redis INCR for atomic increment and sets expiration on first request.

        Args:
            key: The rate limit key.
            limit: Maximum requests allowed.
            window: Time window in seconds.

        Returns:
            RateLimitResult with the check outcome.
        """
        now = datetime.now(timezone.utc)

        # Increment counter
        count = await RedisService.incr(key)

        if count is None:
            # Redis error, allow request but log warning
            rate_limit_logger.warning(
                f"Redis error during rate limit check for key: {key}, allowing request"
            )
            return RateLimitResult(
                allowed=True,
                remaining=limit - 1,
                limit=limit,
                reset_at=datetime.fromtimestamp(
                    now.timestamp() + window, tz=timezone.utc
                ),
            )

        # Set expiration on first request
        if count == 1:
            await RedisService.expire(key, window)

        # Get TTL for reset time
        ttl = await RedisService.ttl(key)
        if ttl is None or ttl < 0:
            ttl = window

        reset_at = datetime.fromtimestamp(now.timestamp() + ttl, tz=timezone.utc)

        # Check if limit exceeded
        if count > limit:
            rate_limit_logger.warning(
                f"Rate limit exceeded for key: {key}, count: {count}, retry after: {ttl}s"
            )
            return RateLimitResult(
                allowed=False,
                remaining=0,
                limit=limit,
                reset_at=reset_at,
                retry_after=max(1, ttl),
            )

        remaining = limit - count
        rate_limit_logger.debug(
            f"Rate limit check passed for key: {key}, remaining: {remaining}"
        )
        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            limit=limit,
            reset_at=reset_at,
        )

    async def reset(self, key: str) -> None:
        """
        Reset the rate limit for a key.

        Args:
            key: The rate limit key to reset.
        """
        await RedisService.delete(key)
        rate_limit_logger.debug(f"Rate limit reset for key: {key}")

    async def get_remaining(self, key: str, limit: int, window: int) -> int:
        """
        Get the remaining number of requests for a key.

        Args:
            key: The rate limit key.
            limit: The configured limit.
            window: Time window in seconds.

        Returns:
            Number of remaining requests.
        """
        value = await RedisService.get(key)
        if value is None:
            return limit

        try:
            count = int(value)
            return max(0, limit - count)
        except ValueError:
            return limit


class RateLimiter:
    """
    Rate limiter with configurable backend.

    This class provides a simple interface for rate limiting with
    automatic backend selection based on configuration.

    Args:
        backend: The backend to use ("memory" or "redis").
                 If None, uses settings.RATE_LIMIT_BACKEND.

    Example:
        >>> limiter = RateLimiter(backend="memory")
        >>> result = await limiter.check("my_key", limit=10, window=60)
        >>> if not result.allowed:
        ...     raise RateLimitExceededException(retry_after=result.retry_after)
    """

    def __init__(self, backend: Literal["memory", "redis"] | None = None):
        """
        Initialize the rate limiter.

        Args:
            backend: The backend type. Defaults to settings.RATE_LIMIT_BACKEND.
        """
        if backend is None:
            backend = settings.RATE_LIMIT_BACKEND

        if backend == "redis":
            self._backend: RateLimitBackend = RedisBackend()
        else:
            self._backend = MemoryBackend()

        rate_limit_logger.debug(f"RateLimiter initialized with {backend} backend")

    async def check(self, key: str, limit: int, window: int) -> RateLimitResult:
        """
        Check if a request is allowed under the rate limit.

        Args:
            key: The rate limit key.
            limit: Maximum requests allowed.
            window: Time window in seconds.

        Returns:
            RateLimitResult with the check outcome.
        """
        return await self._backend.check(key, limit, window)

    async def reset(self, key: str) -> None:
        """
        Reset the rate limit for a key.

        Args:
            key: The rate limit key to reset.
        """
        await self._backend.reset(key)

    async def get_remaining(self, key: str, limit: int, window: int) -> int:
        """
        Get the remaining number of requests for a key.

        Args:
            key: The rate limit key.
            limit: The configured limit.
            window: Time window in seconds.

        Returns:
            Number of remaining requests.
        """
        return await self._backend.get_remaining(key, limit, window)


def format_rate_limit_key(
    key_type: Literal["ip", "user", "endpoint", "email"],
    identifier: str,
    endpoint: str,
) -> str:
    """
    Format a rate limit key with consistent structure.

    Args:
        key_type: The type of rate limit ("ip", "user", "endpoint", or "email").
        identifier: The identifier (IP address, user ID, email, or endpoint path).
        endpoint: The endpoint path.

    Returns:
        Formatted rate limit key string.

    Example:
        >>> format_rate_limit_key("ip", "192.168.1.1", "/api/test")
        'rate_limit:ip:192.168.1.1:/api/test'
    """
    return f"rate_limit:{key_type}:{identifier}:{endpoint}"


def rate_limit_by_ip(
    limit: int | None = None,
    window: int | None = None,
    backend: Literal["memory", "redis"] | None = None,
) -> Callable:
    """
    Create a FastAPI dependency for IP-based rate limiting.

    This dependency extracts the client IP from the request and
    applies rate limiting based on that IP address.

    Args:
        limit: Maximum requests allowed. Defaults to settings.RATE_LIMIT_DEFAULT_REQUESTS.
        window: Time window in seconds. Defaults to settings.RATE_LIMIT_DEFAULT_WINDOW.
        backend: Backend type. Defaults to settings.RATE_LIMIT_BACKEND.

    Returns:
        A FastAPI dependency function.

    Example:
        >>> @app.get("/api/resource")
        >>> async def get_resource(
        ...     rate_limit: RateLimitResult = Depends(rate_limit_by_ip(limit=10, window=60))
        ... ):
        ...     return {"remaining": rate_limit.remaining}
    """
    _limit = limit if limit is not None else settings.RATE_LIMIT_DEFAULT_REQUESTS
    _window = window if window is not None else settings.RATE_LIMIT_DEFAULT_WINDOW

    async def dependency(request: Request) -> RateLimitResult:
        limiter = RateLimiter(backend=backend)
        client_ip = request.client.host if request.client else "unknown"
        endpoint = request.url.path
        key = format_rate_limit_key("ip", client_ip, endpoint)

        result = await limiter.check(key, _limit, _window)

        if not result.allowed:
            raise RateLimitExceededException(
                message=f"Rate limit exceeded. Try again in {result.retry_after} seconds.",
                retry_after=result.retry_after,
            )

        return result

    return dependency


def rate_limit_by_user(
    limit: int | None = None,
    window: int | None = None,
    backend: Literal["memory", "redis"] | None = None,
) -> Callable:
    """
    Create a FastAPI dependency for user-based rate limiting.

    This dependency requires a user_id parameter and applies rate
    limiting based on the authenticated user.

    Args:
        limit: Maximum requests allowed. Defaults to settings.RATE_LIMIT_DEFAULT_REQUESTS.
        window: Time window in seconds. Defaults to settings.RATE_LIMIT_DEFAULT_WINDOW.
        backend: Backend type. Defaults to settings.RATE_LIMIT_BACKEND.

    Returns:
        A FastAPI dependency function.

    Example:
        >>> @app.get("/api/resource")
        >>> async def get_resource(
        ...     current_user: User = Depends(get_current_user),
        ...     rate_limit: RateLimitResult = Depends(
        ...         rate_limit_by_user(limit=100, window=3600)
        ...     )
        ... ):
        ...     return {"remaining": rate_limit.remaining}
    """
    _limit = limit if limit is not None else settings.RATE_LIMIT_DEFAULT_REQUESTS
    _window = window if window is not None else settings.RATE_LIMIT_DEFAULT_WINDOW

    async def dependency(
        request: Request,
        user_id: str | None = None,
    ) -> RateLimitResult:
        if user_id is None:
            raise AuthenticationException(
                "User authentication required for rate limiting"
            )

        limiter = RateLimiter(backend=backend)
        endpoint = request.url.path
        key = format_rate_limit_key("user", user_id, endpoint)

        result = await limiter.check(key, _limit, _window)

        if not result.allowed:
            raise RateLimitExceededException(
                message=f"Rate limit exceeded. Try again in {result.retry_after} seconds.",
                retry_after=result.retry_after,
            )

        return result

    return dependency


def rate_limit_by_endpoint(
    limit: int | None = None,
    window: int | None = None,
    backend: Literal["memory", "redis"] | None = None,
) -> Callable:
    """
    Create a FastAPI dependency for endpoint-based rate limiting.

    This dependency applies a global rate limit to an endpoint,
    regardless of the client or user making the request.

    Args:
        limit: Maximum requests allowed. Defaults to settings.RATE_LIMIT_DEFAULT_REQUESTS.
        window: Time window in seconds. Defaults to settings.RATE_LIMIT_DEFAULT_WINDOW.
        backend: Backend type. Defaults to settings.RATE_LIMIT_BACKEND.

    Returns:
        A FastAPI dependency function.

    Example:
        >>> @app.get("/api/expensive-operation")
        >>> async def expensive_operation(
        ...     rate_limit: RateLimitResult = Depends(
        ...         rate_limit_by_endpoint(limit=5, window=60)
        ...     )
        ... ):
        ...     return {"result": "expensive computation"}
    """
    _limit = limit if limit is not None else settings.RATE_LIMIT_DEFAULT_REQUESTS
    _window = window if window is not None else settings.RATE_LIMIT_DEFAULT_WINDOW

    async def dependency(request: Request) -> RateLimitResult:
        limiter = RateLimiter(backend=backend)
        endpoint = request.url.path
        key = format_rate_limit_key("endpoint", endpoint, endpoint)

        result = await limiter.check(key, _limit, _window)

        if not result.allowed:
            raise RateLimitExceededException(
                message=f"Rate limit exceeded. Try again in {result.retry_after} seconds.",
                retry_after=result.retry_after,
            )

        return result

    return dependency


def rate_limit_by_email(
    limit: int | None = None,
    window: int | None = None,
    backend: Literal["memory", "redis"] | None = None,
) -> Callable:
    """
    Create a rate limiter for email-based rate limiting.

    This function returns a dependency factory that creates a rate limit
    check based on the email address. Unlike other rate limiters, this
    returns a callable that must be invoked with the email address.

    Args:
        limit: Maximum requests allowed. Defaults to settings.RATE_LIMIT_DEFAULT_REQUESTS.
        window: Time window in seconds. Defaults to settings.RATE_LIMIT_DEFAULT_WINDOW.
        backend: Backend type. Defaults to settings.RATE_LIMIT_BACKEND.

    Returns:
        An async function that takes an email and endpoint, and checks rate limit.

    Example:
        >>> check_rate_limit = rate_limit_by_email(limit=3, window=3600)
        >>> @app.post("/contact-sales")
        >>> async def contact_sales(
        ...     request: Request,
        ...     data: ContactSalesRequest,
        ... ):
        ...     await check_rate_limit(data.email, request.url.path)
        ...     # Process request...
    """
    _limit = limit if limit is not None else settings.RATE_LIMIT_DEFAULT_REQUESTS
    _window = window if window is not None else settings.RATE_LIMIT_DEFAULT_WINDOW

    async def check(email: str, endpoint: str) -> RateLimitResult:
        limiter = RateLimiter(backend=backend)
        key = format_rate_limit_key("email", email.lower(), endpoint)

        result = await limiter.check(key, _limit, _window)

        if not result.allowed:
            raise RateLimitExceededException(
                message=f"Rate limit exceeded. Try again in {result.retry_after} seconds.",
                retry_after=result.retry_after,
            )

        return result

    return check


__all__ = [
    "RateLimitResult",
    "RateLimitBackend",
    "MemoryBackend",
    "RedisBackend",
    "RateLimiter",
    "format_rate_limit_key",
    "rate_limit_by_email",
    "rate_limit_by_ip",
    "rate_limit_by_user",
    "rate_limit_by_endpoint",
]
