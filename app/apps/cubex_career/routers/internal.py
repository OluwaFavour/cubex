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
    2. Verify the user has an active career subscription
    3. Check user-level rate limits (per-minute and per-day)
    4. Check user quota (credits used vs credits_allocation)
    5. Create a PENDING usage log for quota tracking
    6. Calculate and reserve credits for billing
    7. Return access granted/denied with a usage_id and credits_reserved

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

    **Note**: These headers are **not always present** (e.g., for idempotent
    requests or early validation failures like 402). Use `.get()` to safely
    access them.

    **Idempotency**: Uses request_id + fingerprint (computed from endpoint,
    method, payload_hash, usage_estimate, and feature_key) for true
    idempotency.
    - Same request_id + same fingerprint = return existing access_status
    - Same request_id + different fingerprint = create new record

    The caller must then call /usage/commit to mark the usage as SUCCESS
    or FAILED after the request completes. PENDING logs that are not
    committed will be expired by a scheduled job.

    **Quota Enforcement**: The system checks if the user has sufficient
    credits remaining in the current billing period. If quota is exceeded,
    access is denied with HTTP 429.

    **Usage Estimate Validation**: If `usage_estimate` is provided, at least
    one field must be set (input_chars, max_output_tokens, or model). Fields
    are validated with bounds: input_chars (0-10M), max_output_tokens (0-2M),
    model (max 100 chars).

    **Security**: Requires Bearer JWT token AND X-Internal-API-Key header.

    **Status Codes**:
    - 200: Access granted (quota available or idempotent request)
    - 402: No active career subscription found
    - 429: Rate limit exceeded (per-minute or per-day) OR quota exceeded
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
        402: {
            "description": "No active career subscription",
            "content": {
                "application/json": {
                    "examples": {
                        "no_subscription": {
                            "summary": "No Active Subscription",
                            "value": {
                                "access": "denied",
                                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                                "usage_id": None,
                                "message": "No active career subscription found.",
                                "credits_reserved": None,
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
## Commit Career Usage Log

Finalize a PENDING usage log created by `/usage/validate`. The AI tool
server calls this endpoint after every analysis request completes —
whether it succeeded or failed — so that quota and billing are accurate.

### Commit Flow

1. AI tool server calls `POST /internal/usage/validate` → receives `usage_id`
2. AI tool server performs the analysis
3. AI tool server calls **this endpoint** with the `usage_id` and outcome
4. On `success=true` with `result_data`, a **CareerAnalysisResult** record
   is persisted so the user can revisit the output via `GET /career/history`

### Authorization

| Header | Required | Description |
|--------|----------|-------------|
| `X-Internal-API-Key` | Yes | Authenticates the AI tool server |

No JWT required — `user_id` is passed in the request body and ownership
is verified against the usage log record.

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | UUID | Yes | The user who owns the usage log |
| `usage_id` | UUID | Yes | The PENDING usage log returned by `/usage/validate` |
| `success` | boolean | Yes | `true` = analysis succeeded (credits charged), `false` = failed (credits released) |
| `metrics` | object | No | Performance metrics (only meaningful when `success=true`) |
| `metrics.model_used` | string | No | Model identifier (e.g. `"gpt-4o"`, max 100 chars) |
| `metrics.input_tokens` | int | No | Actual input tokens consumed (0–2 000 000) |
| `metrics.output_tokens` | int | No | Output tokens generated (0–2 000 000) |
| `metrics.latency_ms` | int | No | End-to-end latency in milliseconds (0–3 600 000) |
| `failure` | object | Cond. | **Required** when `success=false` |
| `failure.failure_type` | string | Cond. | Category — see Failure Types below |
| `failure.reason` | string | Cond. | Human-readable description (max 1 000 chars) |
| `result_data` | object | No | Structured JSON analysis output from the AI tool — see Analysis History below |

### Failure Types

| Value | When to use |
|-------|-------------|
| `internal_error` | Unhandled server-side exception |
| `timeout` | Upstream model or service timed out |
| `rate_limited` | Upstream provider returned 429 |
| `invalid_response` | Model returned unparseable / malformed output |
| `upstream_error` | Non-timeout error from upstream provider |
| `client_error` | Bad input from the end user (4xx equivalent) |
| `validation_error` | Request failed schema validation |

### Analysis History (`result_data`)

When `success=true`, the caller **should** include `result_data` containing
the structured JSON response that was returned to the user. This data is
persisted as a **CareerAnalysisResult** row and powers the user-facing
history endpoints:

- `GET /career/history` — paginated list of past analyses
- `GET /career/history/{result_id}` — full detail including `result_data`
- `DELETE /career/history/{result_id}` — soft-delete

The `result_data` object is stored as-is (schemaless JSON). Its shape
depends on the `feature_key` of the original usage log — for example a
`career.job_match` commit might include `{"match_score": 0.85, ...}`,
while `career.career_path` might include `{"paths": [...]}`.

If `result_data` is omitted or `null`, no history record is created and
the commit still succeeds normally.

When `success=false`, `result_data` is ignored even if provided.

### Async Alternative (RabbitMQ)

Instead of calling this endpoint synchronously, publish the same
`UsageCommitRequest` payload as a JSON message to the
**`career_usage_commits`** queue.

| Queue | Purpose |
|-------|---------|
| `career_usage_commits` | Primary — processed by career usage handler |
| `career_usage_commits_retry` | Retry (30 s TTL, max 3 attempts) |
| `career_usage_commits_dead` | Dead-letter after retry exhaustion |

`result_data` is fully supported via the async path.

### Idempotency

This operation is safe to retry. If the usage log has already been
committed, or does not exist, the response returns `success=true` with
an explanatory message. No duplicate side-effects occur (analysis
history is only created on the first successful commit).

### Response

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | `true` if the operation completed without error |
| `message` | string | Human-readable outcome description |

### Status Codes

| Code | Reason |
|------|--------|
| `200` | Commit accepted (success, idempotent replay, or ownership mismatch) |
| `401` | Invalid or missing `X-Internal-API-Key` |
| `422` | Validation error (e.g. `failure` missing when `success=false`) |
""",
    responses={
        200: {
            "description": "Commit result",
            "content": {
                "application/json": {
                    "examples": {
                        "success_with_result_data": {
                            "summary": "Success with Analysis History",
                            "description": (
                                "Analysis succeeded, metrics and result_data provided. "
                                "A CareerAnalysisResult record is created for the user's history."
                            ),
                            "value": {
                                "success": True,
                                "message": "Usage committed as SUCCESS.",
                            },
                        },
                        "success_without_result_data": {
                            "summary": "Success without Analysis History",
                            "description": (
                                "Analysis succeeded but result_data was omitted. "
                                "No history record is created."
                            ),
                            "value": {
                                "success": True,
                                "message": "Usage committed as SUCCESS.",
                            },
                        },
                        "failed_with_details": {
                            "summary": "Failed with Failure Details",
                            "description": (
                                "Analysis failed. Credits are released back to the user's quota."
                            ),
                            "value": {
                                "success": True,
                                "message": "Usage committed as FAILED.",
                            },
                        },
                        "already_committed": {
                            "summary": "Already Committed (Idempotent)",
                            "description": (
                                "The usage log was already committed or does not exist. "
                                "Safe to ignore — no duplicate side-effects."
                            ),
                            "value": {
                                "success": True,
                                "message": "Usage log not found, but operation is idempotent.",
                            },
                        },
                        "ownership_mismatch": {
                            "summary": "Ownership Mismatch",
                            "description": (
                                "The user_id in the request does not match the user "
                                "who created the usage log."
                            ),
                            "value": {
                                "success": False,
                                "message": "User does not own this usage log.",
                            },
                        },
                    }
                }
            },
        },
        401: {"description": "Invalid or missing internal API key"},
        422: {
            "description": "Validation error (e.g. missing failure details when success=false)",
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
            result_data=request.result_data,
            commit_self=False,
        )

    return UsageCommitResponse(
        success=success,
        message=message,
    )


__all__ = ["router"]
