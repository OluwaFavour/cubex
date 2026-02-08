"""
Internal API router for external developer API communication.

This module provides endpoints for:
- Usage validation and logging
- Usage reverting (for error recovery)

These endpoints are protected by internal API key authentication
(X-Internal-API-Key header) and are not meant for public consumption.

Security layers:
1. X-Internal-API-Key header validation
2. CORS configuration (separate from public API)
3. IP-level restrictions (configured at infrastructure level)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_api.dependencies import InternalAPIKeyDep
from app.apps.cubex_api.schemas.workspace import (
    UsageRevertRequest,
    UsageRevertResponse,
    UsageValidateRequest,
    UsageValidateResponse,
)
from app.apps.cubex_api.services.quota import quota_service
from app.core.dependencies import get_async_session


router = APIRouter(prefix="/internal", tags=["Internal API"])


@router.post(
    "/usage/validate",
    response_model=UsageValidateResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate API key and log usage",
    description="""
    Validate an API key and log usage for quota tracking.
    
    This endpoint is called by the external developer API to:
    1. Validate the API key is valid, active, and not expired
    2. Verify the API key belongs to the specified workspace (client_id)
    3. Log the usage for quota tracking
    4. Return access granted/denied with a usage_id
    
    **Note**: Currently returns DENIED with 501 message as quota system
    is not yet implemented. The usage is still logged for future quota
    enforcement.
    
    **Security**: Requires X-Internal-API-Key header.
    """,
    responses={
        200: {
            "description": "Validation result",
            "content": {
                "application/json": {
                    "examples": {
                        "denied_not_implemented": {
                            "summary": "Denied - Not Implemented",
                            "value": {
                                "access": "denied",
                                "usage_id": "550e8400-e29b-41d4-a716-446655440000",
                                "message": "Quota system is not yet implemented.",
                            },
                        },
                        "denied_invalid_key": {
                            "summary": "Denied - Invalid Key",
                            "value": {
                                "access": "denied",
                                "usage_id": None,
                                "message": "API key not found, expired, or revoked.",
                            },
                        },
                        "denied_invalid_client_id": {
                            "summary": "Denied - Invalid Client ID",
                            "value": {
                                "access": "denied",
                                "usage_id": None,
                                "message": "Invalid client_id format.",
                            },
                        },
                    }
                }
            },
        },
        401: {"description": "Invalid or missing internal API key"},
    },
)
async def validate_usage(
    request: UsageValidateRequest,
    _: InternalAPIKeyDep,  # Validates X-Internal-API-Key header
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> UsageValidateResponse:
    """
    Validate API key and log usage.

    Returns access status, usage_id (if logged), and a message.
    Currently always returns DENIED as quota system is not implemented.
    """
    async with session.begin():
        access, usage_id, message = await quota_service.validate_and_log_usage(
            session=session,
            api_key=request.api_key,
            client_id=request.client_id,
            cost=request.cost,
            commit_self=False,
        )

    return UsageValidateResponse(
        access=access,
        usage_id=usage_id,
        message=message,
    )


@router.post(
    "/usage/revert",
    response_model=UsageRevertResponse,
    status_code=status.HTTP_200_OK,
    summary="Revert a usage log",
    description="""
    Revert a usage log entry (idempotent).
    
    This endpoint is called by the external developer API when an error
    occurs and the usage should not count against the user's quota.
    
    **Idempotent**: This operation is safe to retry. If the usage log
    is already reverted or doesn't exist, success is still returned.
    
    **Security**: Requires X-Internal-API-Key header.
    """,
    responses={
        200: {
            "description": "Revert result",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "Successfully Reverted",
                            "value": {
                                "success": True,
                                "message": "Usage successfully reverted.",
                            },
                        },
                        "already_reverted": {
                            "summary": "Already Reverted (Idempotent)",
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
    },
)
async def revert_usage(
    request: UsageRevertRequest,
    _: InternalAPIKeyDep,  # Validates X-Internal-API-Key header
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> UsageRevertResponse:
    """
    Revert a usage log entry.

    This is idempotent - if the log is already reverted or doesn't exist,
    success is still returned.
    """
    async with session.begin():
        success, message = await quota_service.revert_usage(
            session=session,
            api_key=request.api_key,
            usage_id=request.usage_id,
            commit_self=False,
        )

    return UsageRevertResponse(
        success=success,
        message=message,
    )


__all__ = ["router"]
