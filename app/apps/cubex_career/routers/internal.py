"""
Internal API router for Career product.

This module provides endpoints for:
- Usage validation and logging (creates PENDING usage logs)
- Usage committing (marks usage as SUCCESS or FAILED)

These endpoints are called by the AI tool server with:
1. Bearer token (JWT) in Authorization header — authenticates the user
2. X-Internal-API-Key header — authenticates the AI tool server

Flow: frontend → AI tool server → this internal endpoint → AI tool server → frontend

Security layers:
1. Bearer JWT token validation (user authentication)
2. X-Internal-API-Key header validation (server authentication)
3. CORS configuration (separate from public API)
4. IP-level restrictions (configured at infrastructure level)
"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_career.schemas.internal import (
    UsageCommitRequest,
    UsageCommitResponse,
    UsageValidateRequest,
    UsageValidateResponse,
)
from app.apps.cubex_career.services.quota import career_quota_service
from app.core.db.crud import career_subscription_context_db
from app.core.enums import AccessStatus
from app.core.dependencies import (
    CurrentActiveUser,
    get_async_session,
    InternalAPIKeyDep,
)


router = APIRouter(prefix="/internal", tags=["Career - Internal API"])


@router.post(
    "/usage/validate",
    response_model=UsageValidateResponse,
    summary="Validate user and log usage",
    description="""
    Validate user quota and log usage for the career product.

    This endpoint is called by the AI tool server to:
    1. Authenticate the user via JWT (Bearer token)
    2. Check user-level rate limits (per-minute and per-day)
    3. Check user quota (credits used vs credits_allocation)
    4. Create a PENDING usage log for quota tracking
    5. Calculate and reserve credits for billing
    6. Return access granted/denied with a usage_id and credits_reserved

    **Rate Limiting**: User-level rate limiting is enforced using sliding
    windows for both per-minute and per-day limits. Limits are configurable
    per plan via PlanPricingRule.

    **Rate Limit Response Headers** (AI tool server should forward these):
    | Header | Type | Description |
    |--------|------|-------------|
    | `X-RateLimit-Limit-Minute` | int | Max requests per minute |
    | `X-RateLimit-Remaining-Minute` | int | Remaining in current minute window |
    | `X-RateLimit-Reset-Minute` | int | Unix timestamp when minute window resets |
    | `X-RateLimit-Limit-Day` | int | Max requests per day |
    | `X-RateLimit-Remaining-Day` | int | Remaining in current day window |
    | `X-RateLimit-Reset-Day` | int | Unix timestamp when day window resets |
    | `Retry-After` | int | Seconds until rate limit resets (only on 429) |

    **Idempotency**: Uses request_id + fingerprint (computed from endpoint,
    method, payload_hash, usage_estimate) for true idempotency.

    The caller must then call /usage/commit to mark the usage as SUCCESS
    or FAILED after the request completes. PENDING logs that are not
    committed will be expired by a scheduled job.

    **Security**: Requires Bearer JWT token AND X-Internal-API-Key header.
    """,
    responses={
        200: {
            "description": "Access granted or idempotent request",
            "content": {
                "application/json": {
                    "examples": {
                        "granted": {
                            "summary": "Access Granted",
                            "value": {
                                "access": "granted",
                                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                                "usage_id": "550e8400-e29b-41d4-a716-446655440000",
                                "message": "Access granted. 98.50 credits remaining after this request.",
                                "credits_reserved": "1.50",
                            },
                        },
                        "granted_idempotent": {
                            "summary": "Granted - Idempotent Request",
                            "value": {
                                "access": "granted",
                                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                                "usage_id": "550e8400-e29b-41d4-a716-446655440000",
                                "message": "Request already processed (idempotent). Access: granted",
                                "credits_reserved": "1.50",
                            },
                        },
                    }
                }
            },
        },
        429: {
            "description": "Rate limit or quota exceeded",
            "content": {
                "application/json": {
                    "examples": {
                        "rate_limit_exceeded_minute": {
                            "summary": "Rate Limit Exceeded (per-minute)",
                            "value": {
                                "access": "denied",
                                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                                "usage_id": None,
                                "message": "Rate limit exceeded. Limit: 20 requests/minute. Try again in 45 seconds.",
                                "credits_reserved": None,
                            },
                        },
                        "rate_limit_exceeded_day": {
                            "summary": "Rate Limit Exceeded (per-day)",
                            "value": {
                                "access": "denied",
                                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                                "usage_id": None,
                                "message": "Rate limit exceeded. Limit: 200 requests/day. Try again in 3600 seconds.",
                                "credits_reserved": None,
                            },
                        },
                        "quota_exceeded": {
                            "summary": "Quota Exceeded",
                            "value": {
                                "access": "denied",
                                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                                "usage_id": "550e8400-e29b-41d4-a716-446655440000",
                                "message": "Quota exceeded. Used 100.00/100.00 credits. This request requires 1.50 credits.",
                                "credits_reserved": "1.50",
                            },
                        },
                    }
                }
            },
        },
    },
)
async def validate_usage(
    request: UsageValidateRequest,
    current_user: CurrentActiveUser,
    _: InternalAPIKeyDep,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> JSONResponse:
    """
    Validate user and log usage.

    Returns access status, usage_id (if logged), credits_reserved, and a message.
    """
    client_ip = request.client.ip if request.client else None
    client_user_agent = request.client.user_agent if request.client else None

    usage_estimate = None
    if request.usage_estimate:
        usage_estimate = {
            "input_chars": request.usage_estimate.input_chars,
            "max_output_tokens": request.usage_estimate.max_output_tokens,
            "model": request.usage_estimate.model,
        }

    context = await career_subscription_context_db.get_by_user(session, current_user.id)

    plan_id = None
    subscription_id = None
    if context and context.subscription:
        plan_id = context.subscription.plan_id
        subscription_id = context.subscription_id

    if subscription_id is None:
        # User has no career subscription
        response_data = UsageValidateResponse(
            access=AccessStatus.DENIED,
            user_id=current_user.id,
            usage_id=None,
            message="No active career subscription found.",
            credits_reserved=None,
        )
        return JSONResponse(
            content=response_data.model_dump(mode="json"),
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
        )

    async with session.begin():
        (
            access,
            usage_id,
            message,
            credits_reserved,
            status_code,
            rate_limit_info,
        ) = await career_quota_service.validate_and_log_usage(
            session=session,
            user_id=current_user.id,
            plan_id=plan_id,
            subscription_id=subscription_id,
            request_id=request.request_id,
            feature_key=request.feature_key,
            endpoint=request.endpoint,
            method=request.method,
            payload_hash=request.payload_hash,
            client_ip=client_ip,
            client_user_agent=client_user_agent,
            usage_estimate=usage_estimate,
            commit_self=False,
        )

    response_data = UsageValidateResponse(
        access=access,
        user_id=current_user.id,
        usage_id=usage_id,
        message=message,
        credits_reserved=credits_reserved,
    )

    headers: dict[str, str] = {}
    if rate_limit_info is not None:
        headers["X-RateLimit-Limit-Minute"] = str(rate_limit_info.limit_per_minute)
        headers["X-RateLimit-Remaining-Minute"] = str(
            rate_limit_info.remaining_per_minute
        )
        headers["X-RateLimit-Reset-Minute"] = str(rate_limit_info.reset_per_minute)
        headers["X-RateLimit-Limit-Day"] = str(rate_limit_info.limit_per_day)
        headers["X-RateLimit-Remaining-Day"] = str(rate_limit_info.remaining_per_day)
        headers["X-RateLimit-Reset-Day"] = str(rate_limit_info.reset_per_day)

        # Add Retry-After header for rate limit exceeded responses
        if rate_limit_info.is_exceeded:
            if rate_limit_info.exceeded_window == "minute":
                retry_after = max(
                    0, rate_limit_info.reset_per_minute - int(time.time())
                )
            else:
                retry_after = max(0, rate_limit_info.reset_per_day - int(time.time()))
            headers["Retry-After"] = str(retry_after)

    return JSONResponse(
        content=response_data.model_dump(mode="json"),
        status_code=status_code,
        headers=headers if headers else None,
    )


@router.post(
    "/usage/commit",
    response_model=UsageCommitResponse,
    status_code=status.HTTP_200_OK,
    summary="Commit a usage log",
    description="""
    Commit a pending usage log entry (idempotent).

    This endpoint is called by the AI tool server after a request
    completes to mark the usage as SUCCESS (counts toward quota) or FAILED
    (does not count toward quota).

    **Metrics (optional)**: When `success=True`, you can optionally provide
    metrics about the request:
    - `model_used`: Model identifier (e.g., "gpt-4o")
    - `input_tokens`: Actual input tokens used (0-2,000,000)
    - `output_tokens`: Actual output tokens generated (0-2,000,000)
    - `latency_ms`: Request latency in milliseconds (0-3,600,000)

    **Failure Details (required when success=False)**: When `success=False`,
    you MUST provide failure details:
    - `failure_type`: Category of failure
    - `reason`: Human-readable description (max 1000 chars)

    **Idempotent**: Safe to retry. If the usage log is already committed
    or doesn't exist, success is still returned.

    **Security**: Requires X-Internal-API-Key header.
    """,
    responses={
        200: {
            "description": "Commit result",
            "content": {
                "application/json": {
                    "examples": {
                        "success_with_metrics": {
                            "summary": "Success with Metrics",
                            "value": {
                                "success": True,
                                "message": "Usage committed as SUCCESS.",
                            },
                        },
                        "failed_with_details": {
                            "summary": "Failed with Details",
                            "value": {
                                "success": True,
                                "message": "Usage committed as FAILED.",
                            },
                        },
                        "already_committed": {
                            "summary": "Already Committed (Idempotent)",
                            "value": {
                                "success": True,
                                "message": "Usage log not found, but operation is idempotent.",
                            },
                        },
                        "ownership_mismatch": {
                            "summary": "Ownership Mismatch",
                            "value": {
                                "success": False,
                                "message": "User does not own this usage log.",
                            },
                        },
                    }
                }
            },
        },
        401: {"description": "Invalid or missing internal API key or JWT"},
        422: {
            "description": "Validation error (e.g., missing failure details when success=False)",
        },
    },
)
async def commit_usage(
    request: UsageCommitRequest,
    _: InternalAPIKeyDep,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> UsageCommitResponse:
    """
    Commit a pending usage log entry.

    This is idempotent - if the log is already committed or doesn't exist,
    success is still returned.
    """
    metrics = None
    if request.metrics:
        metrics = {
            "model_used": request.metrics.model_used,
            "input_tokens": request.metrics.input_tokens,
            "output_tokens": request.metrics.output_tokens,
            "latency_ms": request.metrics.latency_ms,
        }

    failure = None
    if request.failure:
        failure = {
            "failure_type": request.failure.failure_type,
            "reason": request.failure.reason,
        }

    async with session.begin():
        success, message = await career_quota_service.commit_usage(
            session=session,
            user_id=request.user_id,
            usage_id=request.usage_id,
            success=request.success,
            metrics=metrics,
            failure=failure,
            commit_self=False,
        )

    return UsageCommitResponse(
        success=success,
        message=message,
    )


__all__ = ["router"]

