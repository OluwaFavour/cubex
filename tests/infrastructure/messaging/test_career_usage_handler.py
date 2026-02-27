"""
Test suite for Career usage commit message handler.

Tests the handle_career_usage_commit function which processes career usage
commit messages from the RabbitMQ 'career_usage_commits' queue.

Run all tests:
    pytest tests/infrastructure/messaging/test_career_usage_handler.py -v

Run with coverage:
    pytest tests/infrastructure/messaging/test_career_usage_handler.py \
        --cov=app.infrastructure.messaging.handlers.career_usage_handler \
        --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


class TestCareerUsageHandlerImports:

    def test_handle_career_usage_commit_import(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        assert handle_career_usage_commit is not None
        assert callable(handle_career_usage_commit)

    def test_handle_career_usage_commit_in_all(self):
        from app.infrastructure.messaging.handlers import career_usage_handler

        assert "handle_career_usage_commit" in career_usage_handler.__all__

    def test_exported_from_handlers_init(self):
        from app.infrastructure.messaging.handlers import (
            handle_career_usage_commit,
        )

        assert handle_career_usage_commit is not None

    def test_registered_in_queue_config(self):
        from app.infrastructure.messaging.queues import get_queue_configs

        get_queue_configs.cache_clear()
        configs = get_queue_configs()
        queue_names = [c.name for c in configs]
        assert "career_usage_commits" in queue_names

        config = next(c for c in configs if c.name == "career_usage_commits")
        assert config.retry_queue == "career_usage_commits_retry"
        assert config.dead_letter_queue == "career_usage_commits_dead"
        assert config.max_retries == 3
        assert config.retry_ttl == 30_000


class TestCareerUsageHandlerValidation:

    @pytest.mark.asyncio
    async def test_invalid_payload_sends_alert_and_returns(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        invalid_event = {"bad_field": "value"}

        with patch(
            "app.infrastructure.messaging.handlers.career_usage_handler.EmailManagerService.send_invalid_payload_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await handle_career_usage_commit(invalid_event)

            mock_alert.assert_called_once()
            call_kwargs = mock_alert.call_args
            assert call_kwargs.kwargs["queue_name"] == "career_usage_commits"
            assert call_kwargs.kwargs["message_body"] == invalid_event

    @pytest.mark.asyncio
    async def test_missing_user_id_sends_alert(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        event = {
            "usage_id": str(uuid4()),
            "success": True,
        }

        with patch(
            "app.infrastructure.messaging.handlers.career_usage_handler.EmailManagerService.send_invalid_payload_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await handle_career_usage_commit(event)
            mock_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_usage_id_sends_alert(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        event = {
            "user_id": str(uuid4()),
            "success": True,
        }

        with patch(
            "app.infrastructure.messaging.handlers.career_usage_handler.EmailManagerService.send_invalid_payload_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await handle_career_usage_commit(event)
            mock_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_without_details_sends_alert(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        event = {
            "user_id": str(uuid4()),
            "usage_id": str(uuid4()),
            "success": False,
            # Missing failure details
        }

        with patch(
            "app.infrastructure.messaging.handlers.career_usage_handler.EmailManagerService.send_invalid_payload_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await handle_career_usage_commit(event)
            mock_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_user_id_format_sends_alert(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        event = {
            "user_id": "not-a-uuid",
            "usage_id": str(uuid4()),
            "success": True,
        }

        with patch(
            "app.infrastructure.messaging.handlers.career_usage_handler.EmailManagerService.send_invalid_payload_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await handle_career_usage_commit(event)
            mock_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_event_sends_alert(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        with patch(
            "app.infrastructure.messaging.handlers.career_usage_handler.EmailManagerService.send_invalid_payload_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await handle_career_usage_commit({})
            mock_alert.assert_called_once()


class TestCareerUsageHandlerProcessing:

    @pytest.mark.asyncio
    async def test_valid_success_commit_calls_service(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        user_id = uuid4()
        usage_id = uuid4()
        event = {
            "user_id": str(user_id),
            "usage_id": str(usage_id),
            "success": True,
        }

        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.infrastructure.messaging.handlers.career_usage_handler.AsyncSessionLocal.begin",
                return_value=mock_context_manager,
            ),
            patch(
                "app.infrastructure.messaging.handlers.career_usage_handler.career_quota_service.commit_usage",
                new_callable=AsyncMock,
                return_value=(True, "Usage committed as SUCCESS."),
            ) as mock_commit,
        ):
            await handle_career_usage_commit(event)

            mock_commit.assert_called_once_with(
                session=mock_session,
                user_id=user_id,
                usage_id=usage_id,
                success=True,
                metrics=None,
                failure=None,
                commit_self=False,
            )

    @pytest.mark.asyncio
    async def test_valid_success_with_metrics(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        user_id = uuid4()
        usage_id = uuid4()
        event = {
            "user_id": str(user_id),
            "usage_id": str(usage_id),
            "success": True,
            "metrics": {
                "model_used": "gpt-4o",
                "input_tokens": 1500,
                "output_tokens": 500,
                "latency_ms": 1200,
            },
        }

        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.infrastructure.messaging.handlers.career_usage_handler.AsyncSessionLocal.begin",
                return_value=mock_context_manager,
            ),
            patch(
                "app.infrastructure.messaging.handlers.career_usage_handler.career_quota_service.commit_usage",
                new_callable=AsyncMock,
                return_value=(True, "Usage committed as SUCCESS."),
            ) as mock_commit,
        ):
            await handle_career_usage_commit(event)

            call_kwargs = mock_commit.call_args.kwargs
            assert call_kwargs["metrics"] == {
                "model_used": "gpt-4o",
                "input_tokens": 1500,
                "output_tokens": 500,
                "latency_ms": 1200,
            }

    @pytest.mark.asyncio
    async def test_valid_failure_with_details(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        user_id = uuid4()
        usage_id = uuid4()
        event = {
            "user_id": str(user_id),
            "usage_id": str(usage_id),
            "success": False,
            "failure": {
                "failure_type": "timeout",
                "reason": "Request timed out after 30s",
            },
        }

        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.infrastructure.messaging.handlers.career_usage_handler.AsyncSessionLocal.begin",
                return_value=mock_context_manager,
            ),
            patch(
                "app.infrastructure.messaging.handlers.career_usage_handler.career_quota_service.commit_usage",
                new_callable=AsyncMock,
                return_value=(True, "Usage committed as FAILED."),
            ) as mock_commit,
        ):
            await handle_career_usage_commit(event)

            call_kwargs = mock_commit.call_args.kwargs
            assert call_kwargs["success"] is False
            assert call_kwargs["failure"] == {
                "failure_type": "timeout",
                "reason": "Request timed out after 30s",
            }
            assert call_kwargs["user_id"] == user_id

    @pytest.mark.asyncio
    async def test_commit_rejected_does_not_raise(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        event = {
            "user_id": str(uuid4()),
            "usage_id": str(uuid4()),
            "success": True,
        }

        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.infrastructure.messaging.handlers.career_usage_handler.AsyncSessionLocal.begin",
                return_value=mock_context_manager,
            ),
            patch(
                "app.infrastructure.messaging.handlers.career_usage_handler.career_quota_service.commit_usage",
                new_callable=AsyncMock,
                return_value=(False, "User does not own this usage log."),
            ),
        ):
            # Should not raise (rejection is not retried)
            await handle_career_usage_commit(event)

    @pytest.mark.asyncio
    async def test_success_commit_with_partial_metrics(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        event = {
            "user_id": str(uuid4()),
            "usage_id": str(uuid4()),
            "success": True,
            "metrics": {
                "model_used": "gpt-4o-mini",
            },
        }

        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.infrastructure.messaging.handlers.career_usage_handler.AsyncSessionLocal.begin",
                return_value=mock_context_manager,
            ),
            patch(
                "app.infrastructure.messaging.handlers.career_usage_handler.career_quota_service.commit_usage",
                new_callable=AsyncMock,
                return_value=(True, "Usage committed as SUCCESS."),
            ) as mock_commit,
        ):
            await handle_career_usage_commit(event)

            call_kwargs = mock_commit.call_args.kwargs
            assert call_kwargs["metrics"]["model_used"] == "gpt-4o-mini"
            assert call_kwargs["metrics"]["input_tokens"] is None
            assert call_kwargs["metrics"]["output_tokens"] is None
            assert call_kwargs["metrics"]["latency_ms"] is None


class TestCareerUsageHandlerErrorHandling:

    @pytest.mark.asyncio
    async def test_processing_error_raises_for_retry(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        event = {
            "user_id": str(uuid4()),
            "usage_id": str(uuid4()),
            "success": True,
        }

        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.infrastructure.messaging.handlers.career_usage_handler.AsyncSessionLocal.begin",
                return_value=mock_context_manager,
            ),
            patch(
                "app.infrastructure.messaging.handlers.career_usage_handler.career_quota_service.commit_usage",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Database connection lost"),
            ),
        ):
            with pytest.raises(RuntimeError, match="Database connection lost"):
                await handle_career_usage_commit(event)

    @pytest.mark.asyncio
    async def test_session_creation_error_raises_for_retry(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        event = {
            "user_id": str(uuid4()),
            "usage_id": str(uuid4()),
            "success": True,
        }

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(
            side_effect=RuntimeError("Cannot connect to DB")
        )
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.infrastructure.messaging.handlers.career_usage_handler.AsyncSessionLocal.begin",
            return_value=mock_context_manager,
        ):
            with pytest.raises(RuntimeError, match="Cannot connect to DB"):
                await handle_career_usage_commit(event)

    @pytest.mark.asyncio
    async def test_different_failure_types_accepted(self):
        from app.infrastructure.messaging.handlers.career_usage_handler import (
            handle_career_usage_commit,
        )

        failure_types = [
            "internal_error",
            "timeout",
            "rate_limited",
            "invalid_response",
            "upstream_error",
            "client_error",
            "validation_error",
        ]

        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        for failure_type in failure_types:
            event = {
                "user_id": str(uuid4()),
                "usage_id": str(uuid4()),
                "success": False,
                "failure": {
                    "failure_type": failure_type,
                    "reason": f"Test failure: {failure_type}",
                },
            }

            with (
                patch(
                    "app.infrastructure.messaging.handlers.career_usage_handler.AsyncSessionLocal.begin",
                    return_value=mock_context_manager,
                ),
                patch(
                    "app.infrastructure.messaging.handlers.career_usage_handler.career_quota_service.commit_usage",
                    new_callable=AsyncMock,
                    return_value=(True, "Usage committed as FAILED."),
                ),
            ):
                await handle_career_usage_commit(event)

