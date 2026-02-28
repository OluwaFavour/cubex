"""
Quota service for Career usage tracking and validation.

This module provides business logic for:
- Validating user quota and logging usage
- Committing usage logs (idempotent)
- Per-user rate limiting (per-minute and per-day windows)

Usage flow:
1. AI tool server calls /career/internal/usage/validate with:
   - Bearer token (JWT for user auth)
   - X-Internal-API-Key header (server auth)
2. CareerQuotaService validates user, logs usage, checks quota
3. Returns granted/denied response with usage_id
4. AI tool server calls /career/internal/usage/commit to finalize usage

Key differences from API QuotaService:
- User-scoped (not workspace-scoped)
- No API keys — uses JWT + internal API key
- Rate limit keys: rate_limit:career:{user_id}:{window}
- Both per-minute and per-day rate limits
"""

from dataclasses import dataclass
from decimal import Decimal
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_career.db.crud import (
    career_analysis_result_db,
    career_usage_log_db,
)
from app.core.config import career_logger
from app.core.db.crud import career_subscription_context_db
from app.core.enums import AccessStatus, FeatureKey
from app.core.services.quota_cache import QuotaCacheService
from app.core.services.redis_service import RedisService
from app.core.utils import create_request_fingerprint


@dataclass
class RateLimitInfo:
    """Rate limiting information for Career API responses.

    Fields are ``None`` when the corresponding rate-limit window is
    unlimited (i.e. no cap configured for that window).

    Attributes:
        limit_per_minute: Maximum requests per minute, or ``None`` (unlimited).
        remaining_per_minute: Requests remaining in the minute window.
        reset_per_minute: Unix timestamp when the minute window resets.
        limit_per_day: Maximum requests per day, or ``None`` (unlimited).
        remaining_per_day: Requests remaining in the day window.
        reset_per_day: Unix timestamp when the day window resets.
        is_exceeded: Whether any rate limit has been exceeded.
        exceeded_window: Which window was exceeded ('minute', 'day', or None).
    """

    limit_per_minute: int | None = None
    remaining_per_minute: int | None = None
    reset_per_minute: int | None = None
    limit_per_day: int | None = None
    remaining_per_day: int | None = None
    reset_per_day: int | None = None
    is_exceeded: bool = False
    exceeded_window: str | None = None


class CareerQuotaService:
    """Service for Career usage validation and quota management.

    Handles user-scoped quota checking, rate limiting, and usage logging
    for the career product. Users are authenticated via JWT (Bearer token)
    and the calling server is authenticated via X-Internal-API-Key.
    """

    def _calculate_billing_period(
        self,
        subscription_period_start: datetime | None,
        subscription_period_end: datetime | None,
        user_created_at: datetime,
        now: datetime | None = None,
    ) -> tuple[datetime, datetime]:
        """
        Calculate the billing period for quota checking.

        If subscription has current_period_start/end, use those.
        Otherwise, use 30-day rolling periods from user creation date.

        Args:
            subscription_period_start: Subscription's current_period_start (if any).
            subscription_period_end: Subscription's current_period_end (if any).
            user_created_at: When the user was created.
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

        # Fall back to 30-day rolling periods from user creation
        if user_created_at.tzinfo is None:
            user_created_at = user_created_at.replace(tzinfo=timezone.utc)

        period_length = timedelta(days=30)

        time_since_creation = now - user_created_at
        if time_since_creation < timedelta(0):
            time_since_creation = timedelta(0)

        periods_elapsed = int(
            time_since_creation.total_seconds() // period_length.total_seconds()
        )
        period_start = user_created_at + (periods_elapsed * period_length)
        period_end = period_start + period_length

        return (period_start, period_end)

    async def _check_rate_limit(
        self,
        user_id: UUID,
        rate_limit_per_minute: int | None,
        rate_limit_per_day: int | None,
    ) -> RateLimitInfo | None:
        """
        Check and update rate limit counters for a user.

        Checks per-minute and/or per-day rate limits depending on which
        are configured (non-None).  Returns ``None`` when both windows
        are unlimited.

        Args:
            user_id: The user UUID to check rate limit for.
            rate_limit_per_minute: Max requests/minute, or ``None`` (unlimited).
            rate_limit_per_day: Max requests/day, or ``None`` (unlimited).

        Returns:
            RateLimitInfo with current rate limit status, or ``None``
            if both windows are unlimited.
        """
        if rate_limit_per_minute is None and rate_limit_per_day is None:
            return None

        now_ts = int(time.time())

        # -- Per-minute window -----------------------------------------------
        minute_exceeded = False
        minute_remaining: int | None = None
        minute_reset: int | None = None

        if rate_limit_per_minute is not None:
            minute_key = f"rate_limit:career:{user_id}:min"
            minute_result = await RedisService.rate_limit_incr(minute_key, 60)

            if minute_result is None:
                career_logger.warning(
                    f"Rate limit check failed (Redis unavailable) for user {user_id}"
                )
                minute_remaining = rate_limit_per_minute - 1
                minute_reset = now_ts + 60
            else:
                minute_count, minute_ttl = minute_result
                if minute_ttl < 0:
                    minute_ttl = 60
                minute_reset = now_ts + minute_ttl
                minute_remaining = max(0, rate_limit_per_minute - minute_count)
                minute_exceeded = minute_count > rate_limit_per_minute

        # -- Per-day window --------------------------------------------------
        day_exceeded = False
        day_remaining: int | None = None
        day_reset: int | None = None

        if rate_limit_per_day is not None:
            day_key = f"rate_limit:career:{user_id}:day"
            day_result = await RedisService.rate_limit_incr(day_key, 86400)

            if day_result is None:
                career_logger.warning(
                    f"Day rate limit check failed (Redis unavailable) for user {user_id}"
                )
                day_remaining = rate_limit_per_day - 1
                day_reset = now_ts + 86400
            else:
                day_count, day_ttl = day_result
                if day_ttl < 0:
                    day_ttl = 86400
                day_reset = now_ts + day_ttl
                day_remaining = max(0, rate_limit_per_day - day_count)
                day_exceeded = day_count > rate_limit_per_day

        is_exceeded = minute_exceeded or day_exceeded
        exceeded_window = None
        if minute_exceeded:
            exceeded_window = "minute"
        elif day_exceeded:
            exceeded_window = "day"

        career_logger.debug(
            f"Rate limit check: user={user_id}, "
            f"minute={'unlimited' if rate_limit_per_minute is None else f'{minute_remaining}/{rate_limit_per_minute}'}, "
            f"day={'unlimited' if rate_limit_per_day is None else f'{day_remaining}/{rate_limit_per_day}'}, "
            f"exceeded={is_exceeded}"
        )

        return RateLimitInfo(
            limit_per_minute=rate_limit_per_minute,
            remaining_per_minute=minute_remaining,
            reset_per_minute=minute_reset,
            limit_per_day=rate_limit_per_day,
            remaining_per_day=day_remaining,
            reset_per_day=day_reset,
            is_exceeded=is_exceeded,
            exceeded_window=exceeded_window,
        )

    async def _check_idempotency(
        self,
        session: AsyncSession,
        user_id: UUID,
        request_id: str,
        fingerprint_hash: str,
    ) -> (
        tuple[AccessStatus, UUID | None, str, Decimal | None, int, RateLimitInfo | None]
        | None
    ):
        """
        Check if this is an idempotent (duplicate) request.

        Args:
            session: Database session.
            user_id: The user UUID.
            request_id: The request ID from client.
            fingerprint_hash: Hash of request parameters.

        Returns:
            Full response tuple if duplicate found, None otherwise.
        """
        existing_log = await career_usage_log_db.get_by_request_id_and_fingerprint(
            session, user_id, request_id, fingerprint_hash
        )
        if not existing_log:
            return None

        access = AccessStatus(existing_log.access_status)

        career_logger.info(
            f"Idempotent request: user={user_id}, request_id={request_id}, "
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
            None,  # rate_limit_info - not tracked for idempotent requests
        )

    async def _check_quota(
        self,
        session: AsyncSession,
        user_id: UUID,
        credits_limit: Decimal,
        credits_reserved: Decimal,
    ) -> tuple[AccessStatus, str, int]:
        """
        Check quota for a user.

        Args:
            session: Database session.
            user_id: The user UUID.
            credits_limit: The credits allocation for the plan.
            credits_reserved: Credits required for this request.

        Returns:
            Tuple of (access_status, message, http_status_code).
        """
        # Get current usage from subscription context (O(1) lookup)
        context = await career_subscription_context_db.get_by_user(session, user_id)
        current_usage = context.credits_used if context else Decimal("0.00")

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

    async def validate_and_log_usage(
        self,
        session: AsyncSession,
        user_id: UUID,
        plan_id: UUID | None,
        subscription_id: UUID,
        request_id: str,
        feature_key: FeatureKey,
        endpoint: str,
        method: str,
        payload_hash: str,
        client_ip: str | None = None,
        client_user_agent: str | None = None,
        usage_estimate: dict[str, Any] | None = None,
        commit_self: bool = True,
    ) -> tuple[
        AccessStatus, UUID | None, str, Decimal | None, int, RateLimitInfo | None
    ]:
        """
        Validate user and log usage.

        This is called by the AI tool server to validate requests
        and track usage for quota management.

        Idempotency:
            Uses user_id + request_id + fingerprint_hash for true idempotency.

        Args:
            session: Database session.
            user_id: The authenticated user's UUID.
            plan_id: The user's plan UUID (from subscription context).
            subscription_id: The user's subscription ID.
            request_id: Globally unique request ID for idempotency.
            feature_key: The key of feature being used.
            endpoint: The API endpoint path being called.
            method: HTTP method (GET, POST, etc.).
            payload_hash: SHA-256 hash of the request payload.
            client_ip: Optional client IP address.
            client_user_agent: Optional client user agent string.
            usage_estimate: Optional usage estimation data.
            commit_self: Whether to commit the transaction.

        Returns:
            Tuple of (access_status, usage_id, message, credits_reserved,
                       status_code, rate_limit_info).
        """
        fingerprint_hash = create_request_fingerprint(
            endpoint=endpoint,
            method=method,
            payload_hash=payload_hash,
            usage_estimate=usage_estimate,
            feature_key=feature_key.value if feature_key else None,
        )
        idempotent_result = await self._check_idempotency(
            session, user_id, request_id, fingerprint_hash
        )
        if idempotent_result is not None:
            return idempotent_result

        # Get plan config (fail-fast if missing)
        plan_config = await QuotaCacheService.get_plan_config(session, plan_id)
        if plan_config is None:
            career_logger.error(
                f"Plan pricing not configured: plan_id={plan_id}, " f"user={user_id}"
            )
            return (
                AccessStatus.DENIED,
                None,
                "Service configuration error. Please contact support.",
                None,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                None,
            )

        # Rate limit (returns None when both windows are unlimited)
        rate_limit_info = await self._check_rate_limit(
            user_id,
            plan_config.rate_limit_per_minute,
            plan_config.rate_limit_per_day,
        )
        if rate_limit_info is not None and rate_limit_info.is_exceeded:
            window = rate_limit_info.exceeded_window or "minute"
            if window == "minute":
                retry_after = (rate_limit_info.reset_per_minute or 0) - int(time.time())
                limit_str = f"{rate_limit_info.limit_per_minute} requests/minute"
            else:
                retry_after = (rate_limit_info.reset_per_day or 0) - int(time.time())
                limit_str = f"{rate_limit_info.limit_per_day} requests/day"

            career_logger.warning(
                f"Rate limit exceeded: user={user_id}, "
                f"window={window}, limit={limit_str}"
            )
            return (
                AccessStatus.DENIED,
                None,
                f"Rate limit exceeded. Limit: {limit_str}. "
                f"Try again in {max(0, retry_after)} seconds.",
                None,
                status.HTTP_429_TOO_MANY_REQUESTS,
                rate_limit_info,
            )

        credits_reserved = await QuotaCacheService.calculate_billable_cost(
            session, feature_key, plan_id
        )
        if credits_reserved is None:
            career_logger.error(
                f"Feature pricing not configured: feature_key={feature_key}"
            )
            return (
                AccessStatus.DENIED,
                None,
                "Service configuration error. Please contact support.",
                None,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                rate_limit_info,
            )
        access_status, message, response_status_code = await self._check_quota(
            session, user_id, plan_config.credits_allocation, credits_reserved
        )

        usage_log = await career_usage_log_db.create(
            session,
            {
                "user_id": user_id,
                "subscription_id": subscription_id,
                "request_id": request_id,
                "feature_key": feature_key,
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

        career_logger.info(
            f"Usage logged (PENDING): user={user_id}, "
            f"usage_id={usage_log.id}, request_id={request_id}, "
            f"fingerprint={fingerprint_hash[:16]}..., "
            f"access_status={access_status.value}, "
            f"endpoint={endpoint}, method={method}, "
            f"credits_reserved={credits_reserved}"
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
            rate_limit_info,
        )

    async def commit_usage(
        self,
        session: AsyncSession,
        user_id: UUID,
        usage_id: UUID,
        success: bool,
        metrics: dict | None = None,
        failure: dict | None = None,
        result_data: dict | None = None,
        commit_self: bool = True,
    ) -> tuple[bool, str]:
        """
        Commit a pending usage log (idempotent).

        Called by the AI tool server after a request completes
        to mark the usage as SUCCESS (counts toward quota) or FAILED
        (does not count toward quota).

        Args:
            session: Database session.
            user_id: The user UUID who made the request.
            usage_id: The usage log ID to commit.
            success: True if request succeeded, False if failed.
            metrics: Optional dict with keys: model_used, input_tokens,
                     output_tokens, latency_ms.
            failure: Optional dict with keys: failure_type, reason.
            result_data: Optional structured JSON analysis output to save
                         as analysis history (only stored on success).
            commit_self: Whether to commit the transaction.

        Returns:
            Tuple of (success, message).
        """
        usage_log = await career_usage_log_db.get_by_id(session, usage_id)

        if not usage_log or usage_log.is_deleted:
            return (True, "Usage log not found, but operation is idempotent.")

        if usage_log.user_id != user_id:
            career_logger.warning(
                f"Usage commit ownership mismatch: "
                f"usage_log.user_id={usage_log.user_id}, "
                f"request.user_id={user_id}"
            )
            return (
                False,
                "User does not own this usage log.",
            )

        # Commit the usage log (idempotent)
        committed_log = await career_usage_log_db.commit(
            session,
            usage_id,
            success=success,
            metrics=metrics,
            failure=failure,
            commit_self=False,
        )

        if committed_log:
            # If successfully committed as SUCCESS, increment credits_used counter
            if success and committed_log.credits_charged is not None:
                context = await career_subscription_context_db.get_by_user(
                    session, committed_log.user_id
                )
                if context:
                    await career_subscription_context_db.increment_credits_used(
                        session, context.id, committed_log.credits_charged
                    )

            # Store analysis result if provided and successful
            if success and result_data and committed_log.feature_key:
                await career_analysis_result_db.create_from_commit(
                    session,
                    usage_log_id=usage_id,
                    user_id=user_id,
                    feature_key=committed_log.feature_key,
                    result_data=result_data,
                    commit_self=False,
                )

            if commit_self:
                await session.commit()

            status_str = "SUCCESS" if success else "FAILED"
            career_logger.info(
                f"Usage committed as {status_str}: usage_id={usage_id}, "
                f"user={user_id}, "
                f"credits_charged={committed_log.credits_charged}"
            )
            return (True, f"Usage committed as {status_str}.")

        return (True, "Usage log not found, but operation is idempotent.")


# Global service instance
career_quota_service = CareerQuotaService()


__all__ = [
    "CareerQuotaService",
    "career_quota_service",
    "RateLimitInfo",
]
