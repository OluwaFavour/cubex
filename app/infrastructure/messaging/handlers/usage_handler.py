"""
Usage commit message handler for async processing.

The payload schema matches UsageCommitRequest from the HTTP endpoint.
"""

from typing import Any

from pydantic import ValidationError

from app.core.config import usage_logger
from app.core.db import AsyncSessionLocal
from app.apps.cubex_api.schemas.workspace import UsageCommitRequest
from app.apps.cubex_api.services.quota import quota_service
from app.core.services.email_manager import EmailManagerService


async def handle_usage_commit(event: dict[str, Any]) -> None:
    """
    Handle a usage commit message from the queue.

    Validates the payload against UsageCommitRequest schema and calls
    quota_service.commit_usage() to process the commit.

    On validation error: sends alert email and returns success (no retry).
    On processing error: raises exception to trigger retry.

    Args:
        event: Dictionary payload matching UsageCommitRequest schema.
            Required fields:
            - api_key: str - The API key that made the original request
            - usage_id: str (UUID) - The usage log ID to commit
            - success: bool - True if request succeeded, False if failed
            Optional fields:
            - metrics: dict - Optional metrics for successful requests
            - failure: dict - Required when success=False

    Raises:
        Exception: On processing errors (triggers retry).
    """
    usage_logger.info(
        f"Processing usage commit message: {event.get('usage_id', 'unknown')}"
    )

    try:
        request = UsageCommitRequest(**event)
    except ValidationError as e:
        # Invalid payload - send alert and return success (no retry)
        usage_logger.error(f"Invalid usage commit payload: {e.errors()}")
        await EmailManagerService.send_invalid_payload_alert(
            queue_name="usage_commits",
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
            success, message = await quota_service.commit_usage(
                session=session,
                api_key=request.api_key,
                usage_id=request.usage_id,
                success=request.success,
                metrics=metrics,
                failure=failure,
                commit_self=False,  # Transaction is managed by context manager
            )

        if success:
            usage_logger.info(
                f"Usage commit processed: usage_id={request.usage_id}, message={message}"
            )
        else:
            usage_logger.warning(
                f"Usage commit rejected: usage_id={request.usage_id}, message={message}"
            )
            # Note: We don't retry on rejection (e.g., ownership mismatch)
            # as it won't succeed on retry

    except Exception as e:
        usage_logger.error(
            f"Error processing usage commit: usage_id={request.usage_id}, error={e}"
        )
        raise  # Re-raise to trigger retry


__all__ = ["handle_usage_commit"]
