"""
Internal API router for external developer API communication.

- Usage validation and logging (creates PENDING usage logs)
- Usage committing (marks usage as SUCCESS or FAILED)

These endpoints are protected by internal API key authentication
(X-Internal-API-Key header) and are not meant for public consumption.

Security layers:
1. X-Internal-API-Key header validation
2. CORS configuration (separate from public API)
3. IP-level restrictions (configured at infrastructure level)
"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_api.schemas.workspace import (
    UsageCommitRequest,
    UsageCommitResponse,
    UsageValidateRequest,
    UsageValidateResponse,
)
from app.apps.cubex_api.services.quota import quota_service
from app.core.dependencies import get_async_session, InternalAPIKeyDep


router = APIRouter(prefix="/internal", tags=["Internal API"])


@router.post(
    "/usage/validate",
    response_model=UsageValidateResponse,
    summary="Validate API key and log usage",
    description="""
    Validate an API key and log usage for quota tracking.
    
    This endpoint is called by the external developer API to:
    1. Validate the API key is valid, active, and not expired
    2. Verify the API key belongs to the specified workspace (client_id)
    3. Check workspace-level rate limits
    4. Check workspace quota (credits used vs credits_allocation)
    5. Create a PENDING usage log for quota tracking
    6. Calculate and reserve credits for billing
    7. Return access granted/denied with a usage_id, credits_reserved, and is_test_key
    
    **Key Types**:
    | Type | Prefix | Behavior |
    |------|--------|----------|
    | Live | `cbx_live_` | Full quota enforcement, credits charged |
    | Test | `cbx_test_` | Rate limits apply, zero credits, `is_test_key=true` |
    
    **Test Keys**: Test API keys (`cbx_test_` prefix) are designed for development
    and testing. They bypass quota checks, always return `access: "granted"`, and
    reserve zero credits. The response includes `is_test_key: true` to indicate
    that the caller should return mocked/sample responses instead of real data.
    Note: Rate limits still apply to test keys.
    
    **Rate Limiting**: Workspace-level rate limiting is enforced using sliding
    windows for both per-minute and per-day limits. Limits are configurable
    per plan via PlanPricingRule.
    
    **Rate Limit Response Headers** (Server B should forward these to developers):
    | Header | Type | Description |
    |--------|------|-------------|
    | `X-RateLimit-Limit-Minute` | int | Max requests per minute for this workspace |
    | `X-RateLimit-Remaining-Minute` | int | Remaining in current minute window |
    | `X-RateLimit-Reset-Minute` | int | Unix timestamp when minute window resets |
    | `X-RateLimit-Limit-Day` | int | Max requests per day for this workspace |
    | `X-RateLimit-Remaining-Day` | int | Remaining in current day window |
    | `X-RateLimit-Reset-Day` | int | Unix timestamp when day window resets |
    | `Retry-After` | int | Seconds until rate limit resets (only included on 429 responses) |
    
    **Important**: Server B should copy these headers from this response to the response
    it sends to developers. This allows developers to implement proper rate limit handling
    (e.g., exponential backoff, request throttling) in their applications.
    
    **Note**: These headers are **not always present** (e.g., for idempotent requests or
    early validation failures). Use `.get()` to safely access them and avoid KeyError:
    ```python
    limit_min = response.headers.get("X-RateLimit-Limit-Minute")
    remaining_min = response.headers.get("X-RateLimit-Remaining-Minute")
    reset_min = response.headers.get("X-RateLimit-Reset-Minute")
    limit_day = response.headers.get("X-RateLimit-Limit-Day")
    remaining_day = response.headers.get("X-RateLimit-Remaining-Day")
    reset_day = response.headers.get("X-RateLimit-Reset-Day")
    retry_after = response.headers.get("Retry-After")  # Only on 429
    ```
    
    **Idempotency**: Uses request_id + fingerprint (computed from endpoint,
    method, payload_hash, usage_estimate, and feature_key) for true idempotency.
    - Same request_id + same fingerprint = return existing access_status
    - Same request_id + different fingerprint = create new record (different payload)
    
    The caller must then call /usage/commit to mark the usage as SUCCESS
    or FAILED after the request completes. PENDING logs that are not
    committed will be expired by a scheduled job.
    
    **Quota Enforcement**: The system checks if the workspace has sufficient
    credits remaining in the current billing period. If quota is exceeded,
    access is denied with HTTP 429. Test keys bypass quota checks entirely.
    
    **Usage Estimate Validation**: If `usage_estimate` is provided, at least
    one field must be set (input_chars, max_output_tokens, or model). Fields
    are validated with bounds: input_chars (0-10M), max_output_tokens (0-2M),
    model (max 100 chars).
    
    **Security**: Requires X-Internal-API-Key header.
    
    **Status Codes**:
    - 200: Access granted (quota available, test key, or idempotent request)
    - 400: Invalid request format (bad client_id or API key format)
    - 401: API key not found, expired, or revoked
    - 403: API key does not belong to the specified workspace
    - 429: Rate limit exceeded (per-minute or per-day) OR quota exceeded
    """,
    responses={
        200: {
            "description": "Access granted or idempotent request",
            "content": {
                "application/json": {
                    "examples": {
                        "granted": {
                            "summary": "Access Granted (Live Key)",
                            "value": {
                                "access": "granted",
                                "usage_id": "550e8400-e29b-41d4-a716-446655440000",
                                "message": "Quota available. Remaining: 4500.0000 credits.",
                                "credits_reserved": "1.0000",
                                "is_test_key": False,
                            },
                        },
                        "granted_test_key": {
                            "summary": "Access Granted (Test Key)",
                            "value": {
                                "access": "granted",
                                "usage_id": "550e8400-e29b-41d4-a716-446655440000",
                                "message": "Test key - access granted (no credits charged).",
                                "credits_reserved": "0.0000",
                                "is_test_key": True,
                            },
                        },
                        "granted_idempotent": {
                            "summary": "Granted - Idempotent Request",
                            "value": {
                                "access": "granted",
                                "usage_id": "550e8400-e29b-41d4-a716-446655440000",
                                "message": "Request already processed (idempotent). Access: granted",
                                "credits_reserved": "1.0000",
                                "is_test_key": False,
                            },
                        },
                    }
                }
            },
        },
        400: {
            "description": "Invalid request format",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_client_id": {
                            "summary": "Invalid Client ID",
                            "value": {
                                "access": "denied",
                                "usage_id": None,
                                "message": "Invalid client_id format. Expected: ws_<uuid_hex>",
                                "credits_reserved": None,
                                "is_test_key": False,
                            },
                        },
                        "invalid_api_key_format": {
                            "summary": "Invalid API Key Format",
                            "value": {
                                "access": "denied",
                                "usage_id": None,
                                "message": "Invalid API key format.",
                                "credits_reserved": None,
                                "is_test_key": False,
                            },
                        },
                    }
                }
            },
        },
        401: {
            "description": "API key authentication failed",
            "content": {
                "application/json": {
                    "examples": {
                        "api_key_not_found": {
                            "summary": "API Key Not Found",
                            "value": {
                                "access": "denied",
                                "usage_id": None,
                                "message": "API key not found, expired, or revoked.",
                                "credits_reserved": None,
                                "is_test_key": False,
                            },
                        },
                    }
                }
            },
        },
        403: {
            "description": "API key does not belong to workspace",
            "content": {
                "application/json": {
                    "examples": {
                        "workspace_mismatch": {
                            "summary": "Workspace Mismatch",
                            "value": {
                                "access": "denied",
                                "usage_id": None,
                                "message": "API key does not belong to the specified workspace.",
                                "credits_reserved": None,
                                "is_test_key": False,
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
                            "summary": "Rate Limit Exceeded (Per-Minute)",
                            "description": "Response includes X-RateLimit-*-Minute, X-RateLimit-*-Day, and Retry-After headers",
                            "value": {
                                "access": "denied",
                                "usage_id": None,
                                "message": "Rate limit exceeded. Limit: 20 requests/minute. Try again in 45 seconds.",
                                "credits_reserved": None,
                                "is_test_key": False,
                            },
                        },
                        "rate_limit_exceeded_day": {
                            "summary": "Rate Limit Exceeded (Per-Day)",
                            "description": "Response includes X-RateLimit-*-Minute, X-RateLimit-*-Day, and Retry-After headers",
                            "value": {
                                "access": "denied",
                                "usage_id": None,
                                "message": "Rate limit exceeded. Limit: 500 requests/day. Try again in 3600 seconds.",
                                "credits_reserved": None,
                                "is_test_key": False,
                            },
                        },
                        "quota_exceeded": {
                            "summary": "Quota Exceeded",
                            "value": {
                                "access": "denied",
                                "usage_id": "550e8400-e29b-41d4-a716-446655440000",
                                "message": "Quota exceeded. Current usage: 5000.0000, limit: 5000.0000",
                                "credits_reserved": "1.0000",
                                "is_test_key": False,
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
    _: InternalAPIKeyDep,  # Validates X-Internal-API-Key header
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> JSONResponse:
    """
    Validate API key and log usage.

    Returns access status, usage_id (if logged), credits_reserved, and a message.

    The response status code reflects the validation result:
    - 200: Access granted (quota available) or idempotent request
    - 400: Invalid format (client_id or API key)
    - 401: API key not found/expired/revoked
    - 403: API key doesn't belong to workspace
    - 429: Quota exceeded
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

    async with session.begin():
        (
            access,
            usage_id,
            message,
            credits_reserved,
            status_code,
            is_test_key,
            rate_limit_info,
        ) = await quota_service.validate_and_log_usage(
            session=session,
            api_key=request.api_key,
            feature_key=request.feature_key,
            client_id=request.client_id,
            request_id=request.request_id,
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
        usage_id=usage_id,
        message=message,
        credits_reserved=credits_reserved,
        is_test_key=is_test_key,
    )

    headers: dict[str, str] = {}
    if rate_limit_info is not None:
        if rate_limit_info.limit_per_minute is not None:
            headers["X-RateLimit-Limit-Minute"] = str(rate_limit_info.limit_per_minute)
            headers["X-RateLimit-Remaining-Minute"] = str(
                rate_limit_info.remaining_per_minute
            )
            headers["X-RateLimit-Reset-Minute"] = str(rate_limit_info.reset_per_minute)
        if rate_limit_info.limit_per_day is not None:
            headers["X-RateLimit-Limit-Day"] = str(rate_limit_info.limit_per_day)
            headers["X-RateLimit-Remaining-Day"] = str(
                rate_limit_info.remaining_per_day
            )
            headers["X-RateLimit-Reset-Day"] = str(rate_limit_info.reset_per_day)

        # Add Retry-After header for rate limit exceeded responses
        if rate_limit_info.is_exceeded:
            if rate_limit_info.exceeded_window == "minute":
                retry_after = max(
                    0, (rate_limit_info.reset_per_minute or 0) - int(time.time())
                )
            else:
                retry_after = max(
                    0, (rate_limit_info.reset_per_day or 0) - int(time.time())
                )
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
    
    This endpoint is called by the external developer API after a request
    completes to mark the usage as SUCCESS (counts toward quota) or FAILED
    (does not count toward quota).
    
    **Async Alternative (RabbitMQ)**: Instead of calling this endpoint
    synchronously, the caller can publish the same `UsageCommitRequest`
    payload as a JSON message to the **`usage_commits`** RabbitMQ queue.
    The message will be processed asynchronously by the usage commit handler.
    - Retry queue: `usage_commits_retry` (30 s TTL, max 3 retries)
    - Dead-letter queue: `usage_commits_dead`
    
    **Metrics (optional)**: When `success=True`, you can optionally provide
    metrics about the request:
    - `model_used`: Model identifier (e.g., "gpt-4o")
    - `input_tokens`: Actual input tokens used (0-2,000,000)
    - `output_tokens`: Actual output tokens generated (0-2,000,000)
    - `latency_ms`: Request latency in milliseconds (0-3,600,000)
    
    **Failure Details (required when success=False)**: When `success=False`,
    you MUST provide failure details:
    - `failure_type`: Category of failure (internal_error, timeout, rate_limited,
      invalid_response, upstream_error, client_error, validation_error)
    - `reason`: Human-readable description of what went wrong (max 1000 chars)
    
    **Idempotent**: This operation is safe to retry. If the usage log
    is already committed or doesn't exist, success is still returned.
    
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
                                "message": "API key does not own this usage log.",
                            },
                        },
                    }
                }
            },
        },
        401: {"description": "Invalid or missing internal API key"},
        422: {
            "description": "Validation error (e.g., missing failure details when success=False)",
        },
    },
)
async def commit_usage(
    request: UsageCommitRequest,
    _: InternalAPIKeyDep,  # Validates X-Internal-API-Key header
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
        success, message = await quota_service.commit_usage(
            session=session,
            api_key=request.api_key,
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
