"""
Quota service for API usage tracking and validation.

This module provides business logic for:
- Validating API keys and logging usage
- Committing usage logs (idempotent)
- Future: Quota checking and enforcement

Usage flow:
1. External API calls /internal/usage/validate with API key and client_id
2. QuotaService validates key, logs usage, checks quota
3. Returns granted/denied response with usage_id
4. External API calls /internal/usage/commit to finalize usage
"""

from decimal import Decimal
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_api.db.crud import api_key_db, usage_log_db, workspace_db
from app.apps.cubex_api.db.models import APIKey
from app.apps.cubex_api.services.quota_cache import QuotaCacheService
from app.shared.config import settings, workspace_logger
from app.shared.enums import AccessStatus
from app.shared.exceptions.types import NotFoundException
from app.shared.utils import create_request_fingerprint, hmac_hash_otp


# ============================================================================
# Constants
# ============================================================================

# API key prefix for identification
API_KEY_PREFIX = "cbx_live_"

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
# Service
# ============================================================================


class QuotaService:
    """Service for API usage validation and quota management."""

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _generate_api_key(self) -> tuple[str, str, str]:
        """
        Generate a new API key with its hash and prefix.

        Returns:
            Tuple of (raw_key, key_hash, key_prefix).
            - raw_key: Full API key to give to user (cbx_live_xxx...)
            - key_hash: HMAC-SHA256 hash for storage and lookup
            - key_prefix: Display prefix (cbx_live_ + first 5 chars of token)
        """
        # Generate random token
        token = secrets.token_urlsafe(32)

        # Construct full API key
        raw_key = f"{API_KEY_PREFIX}{token}"

        # Hash the full key for storage
        key_hash = hmac_hash_otp(raw_key, settings.OTP_HMAC_SECRET)

        # Create display prefix (cbx_live_ + first 5 chars of token)
        key_prefix = f"{API_KEY_PREFIX}{token[:5]}"

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
        return api_key.startswith(API_KEY_PREFIX) and len(api_key) > len(API_KEY_PREFIX)

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

    # ========================================================================
    # API Key Management
    # ========================================================================

    async def create_api_key(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        name: str,
        expires_in_days: int | None = 90,
        commit_self: bool = True,
    ) -> tuple[APIKey, str]:
        """
        Create a new API key for a workspace.

        Args:
            session: Database session.
            workspace_id: Workspace to create key for.
            name: User-defined label for the key.
            expires_in_days: Days until expiry (None = never).
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

        # Generate key
        raw_key, key_hash, key_prefix = self._generate_api_key()

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
            },
            commit_self=commit_self,
        )

        workspace_logger.info(
            f"Created API key '{name}' for workspace {workspace_id} "
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
    ) -> tuple[AccessStatus, UUID | None, str, Decimal | None, int]:
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
            Tuple of (access_status, usage_id, message, credits_reserved, status_code).
            - access_status: GRANTED or DENIED
            - usage_id: UUID of usage log (None if denied before logging)
            - message: Human-readable status message
            - credits_reserved: The billable cost in credits (None if denied)
            - status_code: HTTP status code for the response
        """
        # Parse client_id first (needed for idempotency check with workspace isolation)
        workspace_id = self._parse_client_id(client_id)
        if workspace_id is None:
            workspace_logger.warning(f"Invalid client_id format: {client_id}")
            return (
                AccessStatus.DENIED,
                None,
                "Invalid client_id format. Expected: ws_<uuid_hex>",
                None,
                status.HTTP_400_BAD_REQUEST,
            )

        # Compute fingerprint for idempotency
        fingerprint_hash = create_request_fingerprint(
            endpoint=endpoint,
            method=method,
            payload_hash=payload_hash,
            usage_estimate=usage_estimate,
        )

        # Check for existing request with same workspace + request_id + fingerprint (true idempotency)
        existing_log = await usage_log_db.get_by_request_id_and_fingerprint(
            session, workspace_id, request_id, fingerprint_hash
        )
        if existing_log:
            # True duplicate - return the stored access_status
            access = AccessStatus(existing_log.access_status)
            workspace_logger.info(
                f"Idempotent request: workspace={workspace_id}, request_id={request_id}, "
                f"fingerprint={fingerprint_hash[:16]}..., "
                f"returning existing access_status={access.value}, "
                f"usage_id={existing_log.id}"
            )
            return (
                access,
                existing_log.id,
                f"Request already processed (idempotent). Access: {access.value}",
                existing_log.credits_reserved,
                status.HTTP_200_OK,
            )

        # Validate API key format
        if not self._validate_api_key_format(api_key):
            workspace_logger.warning(f"Invalid API key format: {api_key[:20]}...")
            return (
                AccessStatus.DENIED,
                None,
                "Invalid API key format.",
                None,
                status.HTTP_400_BAD_REQUEST,
            )

        # Hash and lookup API key
        key_hash = self._hash_api_key(api_key)
        api_key_record = await api_key_db.get_active_by_hash(session, key_hash)

        if not api_key_record:
            workspace_logger.warning(
                f"API key not found or invalid for client_id: {client_id}"
            )
            return (
                AccessStatus.DENIED,
                None,
                "API key not found, expired, or revoked.",
                None,
                status.HTTP_401_UNAUTHORIZED,
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
            )

        # Update last_used_at
        await api_key_db.update_last_used(session, api_key_record.id, commit_self=False)

        # Calculate billable cost using QuotaCacheService
        # Get the workspace's subscription plan_id for pricing multiplier
        workspace = await workspace_db.get_by_id(session, workspace_id)
        plan_id = None
        subscription = None
        if workspace and workspace.subscription:
            subscription = workspace.subscription
            plan_id = subscription.plan_id

        credits_reserved = await QuotaCacheService.calculate_billable_cost(
            endpoint, plan_id
        )

        # ====================================================================
        # Quota Checking
        # ====================================================================

        # Get credits limit for the plan (with DB fallback if cache unavailable)
        credits_limit = (
            await QuotaCacheService.get_plan_credits_allocation_with_fallback(
                session, plan_id
            )
        )

        # Calculate billing period
        subscription_period_start = None
        subscription_period_end = None
        if subscription is not None:
            subscription_period_start = subscription.current_period_start
            subscription_period_end = subscription.current_period_end

        # Use workspace.created_at for fallback period calculation
        workspace_created_at = (
            workspace.created_at if workspace else datetime.now(timezone.utc)
        )
        period_start, period_end = self._calculate_billing_period(
            subscription_period_start,
            subscription_period_end,
            workspace_created_at,
        )

        # Sum current usage for the period (only SUCCESS logs count)
        current_usage = await usage_log_db.sum_credits_for_period(
            session, workspace_id, period_start, period_end
        )

        # Check quota: current_usage + credits_reserved <= credits_limit
        remaining_credits = credits_limit - current_usage
        if current_usage + credits_reserved <= credits_limit:
            access_status = AccessStatus.GRANTED
            message = (
                f"Access granted. {remaining_credits - credits_reserved:.2f} credits "
                f"remaining after this request."
            )
            response_status_code = status.HTTP_200_OK
        else:
            access_status = AccessStatus.DENIED
            message = (
                f"Quota exceeded. Used {current_usage:.2f}/{credits_limit:.2f} credits. "
                f"This request requires {credits_reserved:.2f} credits."
            )
            response_status_code = status.HTTP_429_TOO_MANY_REQUESTS

        # Create usage log with PENDING status and store access decision
        usage_log = await usage_log_db.create(
            session,
            {
                "api_key_id": api_key_record.id,
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

        workspace_logger.info(
            f"Usage logged (PENDING): workspace={workspace_id}, "
            f"api_key={api_key_record.key_prefix}***, "
            f"usage_id={usage_log.id}, request_id={request_id}, "
            f"fingerprint={fingerprint_hash[:16]}..., "
            f"access_status={access_status.value}, "
            f"endpoint={endpoint}, method={method}, "
            f"credits_reserved={credits_reserved}, "
            f"current_usage={current_usage:.2f}/{credits_limit:.2f}"
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
            commit_self=commit_self,
        )

        if committed_log:
            status_str = "SUCCESS" if success else "FAILED"
            workspace_logger.info(
                f"Usage committed as {status_str}: usage_id={usage_id}, "
                f"api_key={api_key_record.key_prefix}***"
            )
            return (True, f"Usage committed as {status_str}.")

        # Shouldn't happen, but handle gracefully
        return (True, "Usage log not found, but operation is idempotent.")


# Global service instance
quota_service = QuotaService()


__all__ = [
    "QuotaService",
    "quota_service",
    "APIKeyNotFoundException",
    "APIKeyInvalidException",
    "UsageLogNotFoundException",
    "API_KEY_PREFIX",
    "CLIENT_ID_PREFIX",
]
