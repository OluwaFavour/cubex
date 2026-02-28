"""
Career usage commit message handler for async processing.

The payload schema matches UsageCommitRequest from the career internal schemas.
"""

from typing import Any

from pydantic import ValidationError

from app.core.config import usage_logger
from app.core.db import AsyncSessionLocal
from app.apps.cubex_career.schemas.internal import UsageCommitRequest
from app.apps.cubex_career.services.quota import career_quota_service
from app.core.services.email_manager import EmailManagerService


async def handle_career_usage_commit(event: dict[str, Any]) -> None:
    """
    Handle a career usage commit message from the queue.

    Validates the payload against the career UsageCommitRequest schema
    and calls career_quota_service.commit_usage() to process the commit.

    On validation error: sends alert email and returns success (no retry).
    On processing error: raises exception to trigger retry.

    Args:
        event: Dictionary payload matching career UsageCommitRequest schema.
            Required fields:
            - user_id: str (UUID) - The user who made the original request
            - usage_id: str (UUID) - The usage log ID to commit
            - success: bool - True if request succeeded, False if failed
            Optional fields:
            - metrics: dict - Optional metrics for successful requests
            - failure: dict - Required when success=False

    Raises:
        Exception: On processing errors (triggers retry).
    """
    usage_logger.info(
        f"Processing career usage commit message: {event.get('usage_id', 'unknown')}"
    )

    try:
        request = UsageCommitRequest(**event)
    except ValidationError as e:
        # Invalid payload - send alert and return success (no retry)
        usage_logger.error(f"Invalid career usage commit payload: {e.errors()}")
        await EmailManagerService.send_invalid_payload_alert(
            queue_name="career_usage_commits",
            message_body=event,
            validation_errors=[dict(err) for err in e.errors()],
        )
        return  # Don't retry - payload will never be valid

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

    # Process the commit
    try:
        async with AsyncSessionLocal.begin() as session:
            success, message = await career_quota_service.commit_usage(
                session=session,
                user_id=request.user_id,
                usage_id=request.usage_id,
                success=request.success,
                metrics=metrics,
                failure=failure,
                commit_self=False,  # Transaction is managed by context manager
            )

        if success:
            usage_logger.info(
                f"Career usage commit processed: usage_id={request.usage_id}, "
                f"message={message}"
            )
        else:
            usage_logger.warning(
                f"Career usage commit rejected: usage_id={request.usage_id}, "
                f"message={message}"
            )
            # Note: We don't retry on rejection (e.g., ownership mismatch)
            # as it won't succeed on retry

    except Exception as e:
        usage_logger.error(
            f"Error processing career usage commit: "
            f"usage_id={request.usage_id}, error={e}"
        )
        raise  # Re-raise to trigger retry


__all__ = ["handle_career_usage_commit"]
