"""
Test suite for API usage commit message handler.

Tests the handle_usage_commit function which processes usage commit
messages from the RabbitMQ 'usage_commits' queue.

Run all tests:
    pytest tests/infrastructure/messaging/test_usage_handler.py -v

Run with coverage:
    pytest tests/infrastructure/messaging/test_usage_handler.py \
        --cov=app.infrastructure.messaging.handlers.usage_handler \
        --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


class TestUsageHandlerImports:

    def test_handle_usage_commit_import(self):
        from app.infrastructure.messaging.handlers.usage_handler import (
            handle_usage_commit,
        )

        assert handle_usage_commit is not None
        assert callable(handle_usage_commit)

    def test_handle_usage_commit_in_all(self):
        from app.infrastructure.messaging.handlers import usage_handler

        assert "handle_usage_commit" in usage_handler.__all__

    def test_registered_in_queue_config(self):
        from app.infrastructure.messaging.queues import get_queue_configs

        get_queue_configs.cache_clear()
        configs = get_queue_configs()
        queue_names = [c.name for c in configs]
        assert "usage_commits" in queue_names

        config = next(c for c in configs if c.name == "usage_commits")
        assert config.retry_queue == "usage_commits_retry"
        assert config.dead_letter_queue == "usage_commits_dead"
        assert config.max_retries == 3


class TestUsageHandlerValidation:

    @pytest.mark.asyncio
    async def test_invalid_payload_sends_alert_and_returns(self):
        from app.infrastructure.messaging.handlers.usage_handler import (
            handle_usage_commit,
        )

        invalid_event = {"bad_field": "value"}

        with patch(
            "app.infrastructure.messaging.handlers.usage_handler.EmailManagerService.send_invalid_payload_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await handle_usage_commit(invalid_event)

            mock_alert.assert_called_once()
            call_kwargs = mock_alert.call_args
            assert call_kwargs.kwargs["queue_name"] == "usage_commits"
            assert call_kwargs.kwargs["message_body"] == invalid_event

    @pytest.mark.asyncio
    async def test_missing_api_key_sends_alert(self):
        from app.infrastructure.messaging.handlers.usage_handler import (
            handle_usage_commit,
        )

        event = {
            "usage_id": str(uuid4()),
            "success": True,
        }

        with patch(
            "app.infrastructure.messaging.handlers.usage_handler.EmailManagerService.send_invalid_payload_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await handle_usage_commit(event)
            mock_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_usage_id_sends_alert(self):
        from app.infrastructure.messaging.handlers.usage_handler import (
            handle_usage_commit,
        )

        event = {
            "api_key": "cbx_live_test123abc",
            "success": True,
        }

        with patch(
            "app.infrastructure.messaging.handlers.usage_handler.EmailManagerService.send_invalid_payload_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await handle_usage_commit(event)
            mock_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_without_details_sends_alert(self):
        from app.infrastructure.messaging.handlers.usage_handler import (
            handle_usage_commit,
        )

        event = {
            "api_key": "cbx_live_test123abc",
            "usage_id": str(uuid4()),
            "success": False,
            # Missing failure details
        }

        with patch(
            "app.infrastructure.messaging.handlers.usage_handler.EmailManagerService.send_invalid_payload_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await handle_usage_commit(event)
            mock_alert.assert_called_once()


class TestUsageHandlerProcessing:

    @pytest.mark.asyncio
    async def test_valid_success_commit_calls_service(self):
        from app.infrastructure.messaging.handlers.usage_handler import (
            handle_usage_commit,
        )

        usage_id = uuid4()
        event = {
            "api_key": "cbx_live_test123abc",
            "usage_id": str(usage_id),
            "success": True,
        }

        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.infrastructure.messaging.handlers.usage_handler.AsyncSessionLocal.begin",
                return_value=mock_context_manager,
            ),
            patch(
                "app.infrastructure.messaging.handlers.usage_handler.quota_service.commit_usage",
                new_callable=AsyncMock,
                return_value=(True, "Usage committed as SUCCESS."),
            ) as mock_commit,
        ):
            await handle_usage_commit(event)

            mock_commit.assert_called_once_with(
                session=mock_session,
                api_key="cbx_live_test123abc",
                usage_id=usage_id,
                success=True,
                metrics=None,
                failure=None,
                commit_self=False,
            )

    @pytest.mark.asyncio
    async def test_valid_success_with_metrics(self):
        from app.infrastructure.messaging.handlers.usage_handler import (
            handle_usage_commit,
        )

        usage_id = uuid4()
        event = {
            "api_key": "cbx_live_test123abc",
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
                "app.infrastructure.messaging.handlers.usage_handler.AsyncSessionLocal.begin",
                return_value=mock_context_manager,
            ),
            patch(
                "app.infrastructure.messaging.handlers.usage_handler.quota_service.commit_usage",
                new_callable=AsyncMock,
                return_value=(True, "Usage committed as SUCCESS."),
            ) as mock_commit,
        ):
            await handle_usage_commit(event)

            call_kwargs = mock_commit.call_args.kwargs
            assert call_kwargs["metrics"] == {
                "model_used": "gpt-4o",
                "input_tokens": 1500,
                "output_tokens": 500,
                "latency_ms": 1200,
            }

    @pytest.mark.asyncio
    async def test_valid_failure_with_details(self):
        from app.infrastructure.messaging.handlers.usage_handler import (
            handle_usage_commit,
        )

        usage_id = uuid4()
        event = {
            "api_key": "cbx_live_test123abc",
            "usage_id": str(usage_id),
            "success": False,
            "failure": {
                "failure_type": "internal_error",
                "reason": "Model API returned 500",
            },
        }

        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.infrastructure.messaging.handlers.usage_handler.AsyncSessionLocal.begin",
                return_value=mock_context_manager,
            ),
            patch(
                "app.infrastructure.messaging.handlers.usage_handler.quota_service.commit_usage",
                new_callable=AsyncMock,
                return_value=(True, "Usage committed as FAILED."),
            ) as mock_commit,
        ):
            await handle_usage_commit(event)

            call_kwargs = mock_commit.call_args.kwargs
            assert call_kwargs["success"] is False
            assert call_kwargs["failure"] == {
                "failure_type": "internal_error",
                "reason": "Model API returned 500",
            }

    @pytest.mark.asyncio
    async def test_commit_rejected_does_not_raise(self):
        from app.infrastructure.messaging.handlers.usage_handler import (
            handle_usage_commit,
        )

        event = {
            "api_key": "cbx_live_test123abc",
            "usage_id": str(uuid4()),
            "success": True,
        }

        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.infrastructure.messaging.handlers.usage_handler.AsyncSessionLocal.begin",
                return_value=mock_context_manager,
            ),
            patch(
                "app.infrastructure.messaging.handlers.usage_handler.quota_service.commit_usage",
                new_callable=AsyncMock,
                return_value=(False, "API key does not own this usage log."),
            ),
        ):
            # Should not raise (rejection is not retried)
            await handle_usage_commit(event)


class TestUsageHandlerErrorHandling:

    @pytest.mark.asyncio
    async def test_processing_error_raises_for_retry(self):
        from app.infrastructure.messaging.handlers.usage_handler import (
            handle_usage_commit,
        )

        event = {
            "api_key": "cbx_live_test123abc",
            "usage_id": str(uuid4()),
            "success": True,
        }

        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.infrastructure.messaging.handlers.usage_handler.AsyncSessionLocal.begin",
                return_value=mock_context_manager,
            ),
            patch(
                "app.infrastructure.messaging.handlers.usage_handler.quota_service.commit_usage",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Database connection lost"),
            ),
        ):
            with pytest.raises(RuntimeError, match="Database connection lost"):
                await handle_usage_commit(event)

    @pytest.mark.asyncio
    async def test_session_creation_error_raises_for_retry(self):
        from app.infrastructure.messaging.handlers.usage_handler import (
            handle_usage_commit,
        )

        event = {
            "api_key": "cbx_live_test123abc",
            "usage_id": str(uuid4()),
            "success": True,
        }

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(
            side_effect=RuntimeError("Cannot connect to DB")
        )
        mock_context_manager.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.infrastructure.messaging.handlers.usage_handler.AsyncSessionLocal.begin",
            return_value=mock_context_manager,
        ):
            with pytest.raises(RuntimeError, match="Cannot connect to DB"):
                await handle_usage_commit(event)
