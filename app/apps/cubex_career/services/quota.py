"""
Quota service for Career usage tracking and validation.

This module provides business logic for:
- Validating user quota and logging usage
- Committing usage logs (idempotent)

Usage flow:
1. External API calls /internal/usage/validate with access_token in header
2. QuotaService validates user, logs usage, checks quota
3. Returns granted/denied response with usage_id
4. External API calls /internal/usage/commit to finalize usage
"""

from dataclasses import dataclass
from decimal import Decimal
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_api.db.crud import api_key_db, usage_log_db, workspace_db
from app.apps.cubex_api.db.models import APIKey
from app.core.services.quota_cache import QuotaCacheService
from app.core.config import settings, workspace_logger
from app.core.services.redis_service import RedisService
from app.core.db.crud import api_subscription_context_db
from app.core.enums import AccessStatus
from app.core.exceptions.types import NotFoundException
from app.core.utils import create_request_fingerprint, hmac_hash_otp


# ============================================================================
# Constants
# ============================================================================

# API key prefixes for identification
API_KEY_PREFIX = "cbx_live_"  # Live keys (consume credits)
TEST_API_KEY_PREFIX = "cbx_test_"  # Test keys (no credits charged)

# Client ID prefix for workspace identification
CLIENT_ID_PREFIX = "ws_"


# ============================================================================
# Exceptions
# ============================================================================


class APIKeyNotFoundException(NotFoundException):
    """Raised when API key is not found."""

    def __init__(self, message: str = "API key not found."):
        super().__init__(message)


class APIKeyInvalidException(NotFoundException):
    """Raised when API key is invalid, expired, or revoked."""

    def __init__(self, message: str = "API key is invalid, expired, or revoked."):
        super().__init__(message)


class UsageLogNotFoundException(NotFoundException):
    """Raised when usage log is not found."""

    def __init__(self, message: str = "Usage log not found."):
        super().__init__(message)


# ============================================================================
# Rate Limiting Data Classes
# ============================================================================


@dataclass
class RateLimitInfo:
    """Rate limiting information for API responses.

    Attributes:
        limit: Maximum requests allowed per minute.
        remaining: Number of requests remaining in the current window.
        reset_timestamp: Unix timestamp when the rate limit window resets.
        is_exceeded: Whether the rate limit has been exceeded.
    """

    limit: int
    remaining: int
    reset_timestamp: int
    is_exceeded: bool = False


@dataclass
class ResolvedAPIKey:
    """Container for resolved API key information.

    Used by _resolve_api_key helper to return all necessary data
    for subsequent processing steps.
    """

    api_key_id: UUID
    workspace_id: UUID
    is_test_key: bool
    plan_id: UUID | None


# ============================================================================
# Service
# ============================================================================


class QuotaService:
    """Service for API usage validation and quota management."""

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _generate_api_key(self, is_test_key: bool = False) -> tuple[str, str, str]:
        """
        Generate a new API key with its hash and prefix.

        Args:
            is_test_key: Whether to generate a test key (cbx_test_) or live key (cbx_live_).

        Returns:
            Tuple of (raw_key, key_hash, key_prefix).
            - raw_key: Full API key to give to user (cbx_live_xxx... or cbx_test_xxx...)
            - key_hash: HMAC-SHA256 hash for storage and lookup
            - key_prefix: Display prefix (prefix + first 5 chars of token)
        """
        # Generate random token
        token = secrets.token_urlsafe(32)

        # Choose prefix based on key type
        prefix = TEST_API_KEY_PREFIX if is_test_key else API_KEY_PREFIX

        # Construct full API key
        raw_key = f"{prefix}{token}"

        # Hash the full key for storage
        key_hash = hmac_hash_otp(raw_key, settings.OTP_HMAC_SECRET)

        # Create display prefix (prefix + first 5 chars of token)
        key_prefix = f"{prefix}{token[:5]}"

        return raw_key, key_hash, key_prefix

    def _hash_api_key(self, raw_key: str) -> str:
        """
        Hash an API key for lookup.

        Args:
            raw_key: The full API key.

        Returns:
            HMAC-SHA256 hash of the key.
        """
        return hmac_hash_otp(raw_key, settings.OTP_HMAC_SECRET)

    def _parse_client_id(self, client_id: str) -> UUID | None:
        """
        Parse a client_id to extract the workspace UUID.

        Client ID format: ws_<workspace_uuid_hex> (32 hex chars, no hyphens)

        Args:
            client_id: The client ID string.

        Returns:
            UUID of the workspace, or None if invalid format.
        """
        if not client_id.startswith(CLIENT_ID_PREFIX):
            return None

        hex_part = client_id.removeprefix(CLIENT_ID_PREFIX)

        try:
            return UUID(hex_part)
        except ValueError:
            return None

    def _validate_api_key_format(self, api_key: str) -> bool:
        """
        Validate API key format.

        Args:
            api_key: The API key to validate.

        Returns:
            True if format is valid, False otherwise.
        """
        is_live = api_key.startswith(API_KEY_PREFIX) and len(api_key) > len(
            API_KEY_PREFIX
        )
        is_test = api_key.startswith(TEST_API_KEY_PREFIX) and len(api_key) > len(
            TEST_API_KEY_PREFIX
        )
        return is_live or is_test

    def _calculate_billing_period(
        self,
        subscription_period_start: datetime | None,
        subscription_period_end: datetime | None,
        workspace_created_at: datetime,
        now: datetime | None = None,
    ) -> tuple[datetime, datetime]:
        """
        Calculate the billing period for quota checking.

        If subscription has current_period_start/end, use those.
        Otherwise, use 30-day rolling periods from workspace creation date.

        Args:
            subscription_period_start: Subscription's current_period_start (if any).
            subscription_period_end: Subscription's current_period_end (if any).
            workspace_created_at: When the workspace was created.
            now: Current time (for testing). Defaults to UTC now.

        Returns:
            Tuple of (period_start, period_end) datetimes.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # Use subscription billing period if available
        if (
            subscription_period_start is not None
            and subscription_period_end is not None
        ):
            return (subscription_period_start, subscription_period_end)

        # Fall back to 30-day rolling periods from workspace creation
        # Ensure workspace_created_at is timezone-aware
        if workspace_created_at.tzinfo is None:
            workspace_created_at = workspace_created_at.replace(tzinfo=timezone.utc)

        period_length = timedelta(days=30)

        # Calculate which period we're in
        # Period 0: created_at to created_at + 30 days
        # Period 1: created_at + 30 days to created_at + 60 days
        # etc.
        time_since_creation = now - workspace_created_at
        if time_since_creation < timedelta(0):
            # Edge case: now is before workspace creation (shouldn't happen)
            time_since_creation = timedelta(0)

        periods_elapsed = int(
            time_since_creation.total_seconds() // period_length.total_seconds()
        )
        period_start = workspace_created_at + (periods_elapsed * period_length)
        period_end = period_start + period_length

        return (period_start, period_end)

    async def _check_rate_limit(
        self, workspace_id: UUID, plan_id: UUID | None
    ) -> RateLimitInfo:
        """
        Check and update rate limit counter for a workspace.

        Uses a sliding window approach with 60-second windows.
        The counter is stored in Redis with key: rate_limit:{workspace_id}

        Optimized to use a Lua script for atomic INCR + EXPIRE + TTL
        in a single Redis round trip.

        Args:
            workspace_id: The workspace UUID to check rate limit for.
            plan_id: The plan UUID for rate limit configuration.

        Returns:
            RateLimitInfo with current rate limit status.
        """
        # Get rate limit for the plan
        rate_limit = await QuotaCacheService.get_plan_rate_limit(plan_id)

        # Redis key for workspace rate limit
        rate_limit_key = f"rate_limit:{workspace_id}"

        # Atomic rate limit operation: INCR + conditional EXPIRE + TTL
        result = await RedisService.rate_limit_incr(rate_limit_key, 60)

        if result is None:
            # Redis unavailable - allow request but log warning
            workspace_logger.warning(
                f"Rate limit check failed (Redis unavailable) for workspace {workspace_id}"
            )
            return RateLimitInfo(
                limit=rate_limit,
                remaining=rate_limit - 1,
                reset_timestamp=int(time.time()) + 60,
                is_exceeded=False,
            )

        current_count, ttl = result
        if ttl < 0:
            ttl = 60  # Default to 60 seconds if TTL lookup fails

        reset_timestamp = int(time.time()) + ttl
        remaining = max(0, rate_limit - current_count)
        is_exceeded = current_count > rate_limit

        workspace_logger.debug(
            f"Rate limit check: workspace={workspace_id}, "
            f"count={current_count}/{rate_limit}, remaining={remaining}, "
            f"reset_in={ttl}s, exceeded={is_exceeded}"
        )

        return RateLimitInfo(
            limit=rate_limit,
            remaining=remaining,
            reset_timestamp=reset_timestamp,
            is_exceeded=is_exceeded,
        )

    async def _check_idempotency(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        request_id: str,
        fingerprint_hash: str,
    ) -> (
        tuple[
            AccessStatus,
            UUID | None,
            str,
            Decimal | None,
            int,
            bool,
            RateLimitInfo | None,
        ]
        | None
    ):
        """
        Check if this is an idempotent (duplicate) request.

        Args:
            session: Database session.
            workspace_id: The workspace UUID.
            request_id: The request ID from client.
            fingerprint_hash: Hash of request parameters.

        Returns:
            Full response tuple if duplicate found, None otherwise.
        """
        existing_log = await usage_log_db.get_by_request_id_and_fingerprint(
            session, workspace_id, request_id, fingerprint_hash
        )
        if not existing_log:
            return None

        # True duplicate - return the stored access_status
        access = AccessStatus(existing_log.access_status)
        existing_api_key = await api_key_db.get_by_id(session, existing_log.api_key_id)
        is_test = existing_api_key.is_test_key if existing_api_key else False

        workspace_logger.info(
            f"Idempotent request: workspace={workspace_id}, request_id={request_id}, "
            f"fingerprint={fingerprint_hash[:16]}..., "
            f"returning existing access_status={access.value}, "
            f"usage_id={existing_log.id}, is_test={is_test}"
        )
        return (
            access,
            existing_log.id,
            f"Request already processed (idempotent). Access: {access.value}",
            existing_log.credits_reserved,
            status.HTTP_200_OK,
            is_test,
            None,  # rate_limit_info - not tracked for idempotent requests
        )

    async def _resolve_api_key(
        self,
        session: AsyncSession,
        api_key: str,
        workspace_id: UUID,
    ) -> (
        ResolvedAPIKey
        | tuple[
            AccessStatus,
            UUID | None,
            str,
            Decimal | None,
            int,
            bool,
            RateLimitInfo | None,
        ]
    ):
        """
        Resolve and validate an API key, returning key info or error response.

        Uses cache for hot path optimization, falls back to DB on cache miss.

        Args:
            session: Database session.
            api_key: The raw API key string.
            workspace_id: Expected workspace UUID from client_id.

        Returns:
            ResolvedAPIKey on success, or error response tuple on failure.
        """
        key_hash = self._hash_api_key(api_key)

        # Try cache first for hot path optimization
        cached_info = await QuotaCacheService.get_cached_api_key_info(key_hash)

        if cached_info:
            # Cache hit - validate workspace matches
            cached_workspace_id = UUID(cached_info["workspace_id"])
            if cached_workspace_id != workspace_id:
                workspace_logger.warning(
                    f"API key workspace mismatch (cached): key={cached_workspace_id}, "
                    f"client_id={workspace_id}"
                )
                return (
                    AccessStatus.DENIED,
                    None,
                    "API key does not belong to the specified workspace.",
                    None,
                    status.HTTP_403_FORBIDDEN,
                    False,
                    None,
                )

            api_key_id = UUID(cached_info["id"])
            is_test_key = cached_info["is_test_key"] == "1"
            plan_id = (
                UUID(cached_info["plan_id"]) if cached_info.get("plan_id") else None
            )

            # Update last_used_at timestamp
            await api_key_db.update_last_used(session, api_key_id, commit_self=False)

            workspace_logger.debug(
                f"API key cache hit: key_hash={key_hash[:16]}..., "
                f"workspace={workspace_id}, is_test={is_test_key}"
            )

            return ResolvedAPIKey(
                api_key_id=api_key_id,
                workspace_id=workspace_id,
                is_test_key=is_test_key,
                plan_id=plan_id,
            )

        # Cache miss - query database
        api_key_record = await api_key_db.get_active_by_hash(session, key_hash)

        if not api_key_record:
            workspace_logger.warning(
                f"API key not found or invalid for workspace: {workspace_id}"
            )
            return (
                AccessStatus.DENIED,
                None,
                "API key not found, expired, or revoked.",
                None,
                status.HTTP_401_UNAUTHORIZED,
                False,
                None,
            )

        # Verify workspace matches
        if api_key_record.workspace_id != workspace_id:
            workspace_logger.warning(
                f"API key workspace mismatch: key={api_key_record.workspace_id}, "
                f"client_id={workspace_id}"
            )
            return (
                AccessStatus.DENIED,
                None,
                "API key does not belong to the specified workspace.",
                None,
                status.HTTP_403_FORBIDDEN,
                False,
                None,
            )

        # Extract key info
        api_key_id = api_key_record.id
        is_test_key = api_key_record.is_test_key

        # Get plan_id from workspace's subscription (eager-loaded)
        workspace = api_key_record.workspace
        plan_id = None
        if workspace and workspace.subscription:
            plan_id = workspace.subscription.plan_id

        # Cache API key info for subsequent requests (15s TTL)
        await QuotaCacheService.cache_api_key_info(
            key_hash=key_hash,
            api_key_id=str(api_key_id),
            workspace_id=str(workspace_id),
            is_test_key=is_test_key,
            plan_id=str(plan_id) if plan_id else None,
        )

        # Update last_used_at timestamp
        await api_key_db.update_last_used(session, api_key_id, commit_self=False)

        return ResolvedAPIKey(
            api_key_id=api_key_id,
            workspace_id=workspace_id,
            is_test_key=is_test_key,
            plan_id=plan_id,
        )

    async def _check_quota_for_live_key(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        plan_id: UUID | None,
        credits_reserved: Decimal,
    ) -> tuple[AccessStatus, str, int]:
        """
        Check quota for a live API key.

        Args:
            session: Database session.
            workspace_id: The workspace UUID.
            plan_id: The plan UUID (or None for default).
            credits_reserved: Credits required for this request.

        Returns:
            Tuple of (access_status, message, http_status_code).
        """
        # Get credits limit for the plan (with DB fallback if cache unavailable)
        credits_limit = (
            await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session, plan_id
            )
        )

        # Get current usage from subscription context (O(1) lookup)
        context = await api_subscription_context_db.get_by_workspace(
            session, workspace_id
        )

        current_usage = context.credits_used if context else Decimal("0.0000")

        # Check quota: current_usage + credits_reserved <= credits_limit
        remaining_credits = credits_limit - current_usage
        if current_usage + credits_reserved <= credits_limit:
            return (
                AccessStatus.GRANTED,
                f"Access granted. {remaining_credits - credits_reserved:.2f} credits "
                f"remaining after this request.",
                status.HTTP_200_OK,
            )
        else:
            return (
                AccessStatus.DENIED,
                f"Quota exceeded. Used {current_usage:.2f}/{credits_limit:.2f} credits. "
                f"This request requires {credits_reserved:.2f} credits.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )

    # ========================================================================
    # API Key Management
    # ========================================================================

    async def create_api_key(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        name: str,
        expires_in_days: int | None = 90,
        is_test_key: bool = False,
        commit_self: bool = True,
    ) -> tuple[APIKey, str]:
        """
        Create a new API key for a workspace.

        Args:
            session: Database session.
            workspace_id: Workspace to create key for.
            name: User-defined label for the key.
            expires_in_days: Days until expiry (None = never).
            is_test_key: Whether this is a test key (no credits charged).
            commit_self: Whether to commit the transaction.
             If False, caller must commit. Useful for batch operations.

        Returns:
            Tuple of (APIKey model, raw_key).
            The raw_key is shown only once and cannot be retrieved later.
        """
        # Verify workspace exists
        workspace = await workspace_db.get_by_id(session, workspace_id)
        if not workspace or workspace.is_deleted:
            raise NotFoundException(f"Workspace {workspace_id} not found.")

        # Generate key with appropriate prefix
        raw_key, key_hash, key_prefix = self._generate_api_key(is_test_key=is_test_key)

        # Calculate expiry
        expires_at = None
        if expires_in_days is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        # Create API key record
        api_key = await api_key_db.create(
            session,
            {
                "workspace_id": workspace_id,
                "name": name,
                "key_hash": key_hash,
                "key_prefix": key_prefix,
                "expires_at": expires_at,
                "is_active": True,
                "is_test_key": is_test_key,
            },
            commit_self=commit_self,
        )

        key_type = "test" if is_test_key else "live"
        workspace_logger.info(
            f"Created {key_type} API key '{name}' for workspace {workspace_id} "
            f"(prefix: {key_prefix}, expires: {expires_at})"
        )

        return api_key, raw_key

    async def list_api_keys(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        include_inactive: bool = False,
    ) -> list[APIKey]:
        """
        List all API keys for a workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            include_inactive: Include revoked/inactive keys.

        Returns:
            List of API keys.
        """
        keys = await api_key_db.get_by_workspace(
            session, workspace_id, include_inactive=include_inactive
        )
        return list(keys)

    async def revoke_api_key(
        self,
        session: AsyncSession,
        api_key_id: UUID,
        workspace_id: UUID,
        commit_self: bool = True,
    ) -> APIKey:
        """
        Revoke an API key.

        Args:
            session: Database session.
            api_key_id: API key ID to revoke.
            workspace_id: Workspace ID (for authorization check).
            commit_self: Whether to commit the transaction.
             If False, caller must commit. Useful for batch operations.

        Returns:
            The revoked API key.

        Raises:
            APIKeyNotFoundException: If key not found or not owned by workspace.
        """
        api_key = await api_key_db.get_by_id(session, api_key_id)

        if not api_key or api_key.is_deleted:
            raise APIKeyNotFoundException()

        if api_key.workspace_id != workspace_id:
            raise APIKeyNotFoundException()

        if api_key.revoked_at is not None:
            # Already revoked, return as-is
            return api_key

        revoked_key = await api_key_db.revoke(
            session, api_key_id, commit_self=commit_self
        )
        if not revoked_key:
            raise APIKeyNotFoundException()

        workspace_logger.info(
            f"Revoked API key '{api_key.name}' (id: {api_key_id}) "
            f"for workspace {workspace_id}"
        )

        return revoked_key

    # ========================================================================
    # Usage Validation (Internal API)
    # ========================================================================

    async def validate_and_log_usage(
        self,
        session: AsyncSession,
        api_key: str,
        client_id: str,
        request_id: str,
        endpoint: str,
        method: str,
        payload_hash: str,
        client_ip: str | None = None,
        client_user_agent: str | None = None,
        usage_estimate: dict[str, Any] | None = None,
        commit_self: bool = True,
    ) -> tuple[
        AccessStatus, UUID | None, str, Decimal | None, int, bool, RateLimitInfo | None
    ]:
        """
        Validate API key and log usage.

        This is called by the external developer API to validate
        requests and track usage for quota management.

        Idempotency:
            Uses workspace_id + request_id + fingerprint_hash for true idempotency.
            - Same workspace + request_id + fingerprint_hash = return existing record's access_status
            - Same request_id + different fingerprint = create new record (different payload)
            - Different workspace = always independent (workspace isolation)

        The fingerprint is computed from: endpoint + method + payload_hash + usage_estimate

        Args:
            session: Database session.
            api_key: The full API key from the request.
            client_id: Workspace client ID (ws_<uuid_hex>).
            request_id: Globally unique request ID for idempotency.
            endpoint: The API endpoint path being called.
            method: HTTP method (GET, POST, etc.).
            payload_hash: SHA-256 hash of the request payload.
            client_ip: Optional client IP address.
            client_user_agent: Optional client user agent string.
            usage_estimate: Optional usage estimation data.
            commit_self: Whether to commit the transaction.

        Returns:
            Tuple of (access_status, usage_id, message, credits_reserved, status_code, is_test_key, rate_limit_info).
            - access_status: GRANTED or DENIED
            - usage_id: UUID of usage log (None if denied before logging)
            - message: Human-readable status message
            - credits_reserved: The billable cost in credits (None if denied, 0 for test keys)
            - status_code: HTTP status code for the response
            - is_test_key: Whether a test key was used (for mocked responses)
            - rate_limit_info: Rate limiting information (None if rate limit check was skipped)
        """
        # ================================================================
        # Step 1: Parse and validate client_id
        # ================================================================
        workspace_id = self._parse_client_id(client_id)
        if workspace_id is None:
            workspace_logger.warning(f"Invalid client_id format: {client_id}")
            return (
                AccessStatus.DENIED,
                None,
                "Invalid client_id format. Expected: ws_<uuid_hex>",
                None,
                status.HTTP_400_BAD_REQUEST,
                False,
                None,
            )

        # ================================================================
        # Step 2: Check idempotency (duplicate request detection)
        # ================================================================
        fingerprint_hash = create_request_fingerprint(
            endpoint=endpoint,
            method=method,
            payload_hash=payload_hash,
            usage_estimate=usage_estimate,
        )
        idempotent_result = await self._check_idempotency(
            session, workspace_id, request_id, fingerprint_hash
        )
        if idempotent_result is not None:
            return idempotent_result

        # ================================================================
        # Step 3: Validate API key format
        # ================================================================
        if not self._validate_api_key_format(api_key):
            workspace_logger.warning(f"Invalid API key format: {api_key[:20]}...")
            return (
                AccessStatus.DENIED,
                None,
                "Invalid API key format.",
                None,
                status.HTTP_400_BAD_REQUEST,
                False,
                None,
            )

        # ================================================================
        # Step 4: Resolve API key (cache or DB lookup)
        # ================================================================
        key_result = await self._resolve_api_key(session, api_key, workspace_id)
        if isinstance(key_result, tuple):
            return key_result  # Error response

        # Extract resolved key info
        api_key_id = key_result.api_key_id
        is_test_key = key_result.is_test_key
        plan_id = key_result.plan_id

        # ================================================================
        # Step 5: Rate limiting (workspace-level)
        # ================================================================
        rate_limit_info = await self._check_rate_limit(workspace_id, plan_id)
        if rate_limit_info.is_exceeded:
            workspace_logger.warning(
                f"Rate limit exceeded: workspace={workspace_id}, "
                f"limit={rate_limit_info.limit}/min"
            )
            return (
                AccessStatus.DENIED,
                None,
                f"Rate limit exceeded. Limit: {rate_limit_info.limit} requests/minute. "
                f"Try again in {rate_limit_info.reset_timestamp - int(time.time())} seconds.",
                None,
                status.HTTP_429_TOO_MANY_REQUESTS,
                is_test_key,
                rate_limit_info,
            )

        # ================================================================
        # Step 6: Calculate credits and check quota
        # ================================================================
        if is_test_key:
            credits_reserved = Decimal("0.00")
            access_status = AccessStatus.GRANTED
            message = "Access granted (test key - no credits charged)."
            response_status_code = status.HTTP_200_OK
        else:
            credits_reserved = await QuotaCacheService.calculate_billable_cost(
                endpoint, plan_id
            )
            access_status, message, response_status_code = (
                await self._check_quota_for_live_key(
                    session, workspace_id, plan_id, credits_reserved
                )
            )

        # ================================================================
        # Step 7: Create usage log
        # ================================================================
        usage_log = await usage_log_db.create(
            session,
            {
                "api_key_id": api_key_id,
                "workspace_id": workspace_id,
                "request_id": request_id,
                "fingerprint_hash": fingerprint_hash,
                "access_status": access_status.value,
                "endpoint": endpoint,
                "method": method,
                "client_ip": client_ip,
                "client_user_agent": client_user_agent,
                "usage_estimate": usage_estimate,
                "credits_reserved": credits_reserved,
            },
            commit_self=False,
        )

        key_type = "test" if is_test_key else "live"
        workspace_logger.info(
            f"Usage logged (PENDING): workspace={workspace_id}, "
            f"api_key_id={api_key_id} ({key_type}), "
            f"usage_id={usage_log.id}, request_id={request_id}, "
            f"fingerprint={fingerprint_hash[:16]}..., "
            f"access_status={access_status.value}, "
            f"endpoint={endpoint}, method={method}, "
            f"credits_reserved={credits_reserved}, is_test={is_test_key}"
        )

        if commit_self:
            await session.commit()
        else:
            await session.flush()

        return (
            access_status,
            usage_log.id,
            message,
            credits_reserved,
            response_status_code,
            is_test_key,
            rate_limit_info,
        )

    async def commit_usage(
        self,
        session: AsyncSession,
        api_key: str,
        usage_id: UUID,
        success: bool,
        metrics: dict | None = None,
        failure: dict | None = None,
        commit_self: bool = True,
    ) -> tuple[bool, str]:
        """
        Commit a pending usage log (idempotent).

        Called by the external developer API after a request completes
        to mark the usage as SUCCESS (counts toward quota) or FAILED
        (does not count toward quota).

        Args:
            session: Database session.
            api_key: The API key that made the original request.
            usage_id: The usage log ID to commit.
            success: True if request succeeded, False if failed.
            metrics: Optional dict with keys: model_used, input_tokens,
                     output_tokens, latency_ms.
            failure: Optional dict with keys: failure_type, reason.
            commit_self: Whether to commit the transaction.

        Returns:
            Tuple of (success, message).
        """
        # Validate API key format
        if not self._validate_api_key_format(api_key):
            return (True, "Invalid API key format, but operation is idempotent.")

        # Hash and lookup API key
        key_hash = self._hash_api_key(api_key)
        api_key_record = await api_key_db.get_by_key_hash(session, key_hash)

        if not api_key_record:
            # Key doesn't exist - could be deleted, still idempotent
            return (True, "API key not found, but operation is idempotent.")

        # Get usage log
        usage_log = await usage_log_db.get_by_id(session, usage_id)

        if not usage_log or usage_log.is_deleted:
            # Log doesn't exist - already deleted or never existed, idempotent
            return (True, "Usage log not found, but operation is idempotent.")

        # Verify ownership
        if usage_log.api_key_id != api_key_record.id:
            workspace_logger.warning(
                f"Usage commit ownership mismatch: "
                f"usage_log.api_key_id={usage_log.api_key_id}, "
                f"api_key.id={api_key_record.id}"
            )
            return (
                False,
                "API key does not own this usage log.",
            )

        # Commit the usage log (idempotent - commit handles already-committed case)
        committed_log = await usage_log_db.commit(
            session,
            usage_id,
            success=success,
            metrics=metrics,
            failure=failure,
            commit_self=False,  # We'll commit after updating credits counter
        )

        if committed_log:
            # Check if this is a test key - test keys don't increment credits_used
            is_test_key = api_key_record.is_test_key

            # If successfully committed as SUCCESS, increment credits_used counter
            # (but not for test keys - they don't consume credits)
            if (
                success
                and committed_log.credits_charged is not None
                and not is_test_key
            ):
                context = await api_subscription_context_db.get_by_workspace(
                    session, committed_log.workspace_id
                )
                if context:
                    await api_subscription_context_db.increment_credits_used(
                        session, context.id, committed_log.credits_charged
                    )

            if commit_self:
                await session.commit()

            status_str = "SUCCESS" if success else "FAILED"
            key_type = "test" if is_test_key else "live"
            workspace_logger.info(
                f"Usage committed as {status_str}: usage_id={usage_id}, "
                f"api_key={api_key_record.key_prefix}*** ({key_type}), "
                f"credits_charged={'0 (test key)' if is_test_key else committed_log.credits_charged}"
            )
            return (True, f"Usage committed as {status_str}.")

        # Shouldn't happen, but handle gracefully
        return (True, "Usage log not found, but operation is idempotent.")


# Global service instance
quota_service = QuotaService()


__all__ = [
    "QuotaService",
    "quota_service",
    "RateLimitInfo",
    "UsageLogNotFoundException",
]
