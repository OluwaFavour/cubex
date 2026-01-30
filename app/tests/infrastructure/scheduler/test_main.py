"""
Test suite for scheduler initialization.

Run tests:
    pytest app/tests/infrastructure/scheduler/test_main.py -v

Run with coverage:
    pytest app/tests/infrastructure/scheduler/test_main.py --cov=app.infrastructure.scheduler.main --cov-report=term-missing -v
"""

from unittest.mock import MagicMock, patch

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.infrastructure.scheduler.main import scheduler, main


class TestScheduler:
    """Test suite for scheduler instance."""

    def test_scheduler_is_async_io_scheduler(self):
        """Test that scheduler is an AsyncIOScheduler instance."""
        assert isinstance(scheduler, AsyncIOScheduler)

    def test_scheduler_has_utc_timezone(self):
        """Test that scheduler is configured with UTC timezone."""
        assert scheduler.timezone is not None
        assert str(scheduler.timezone) == "UTC"


class TestMain:
    """Test suite for main function."""

    def test_main_starts_scheduler(self):
        """Test that main function starts the scheduler."""
        with patch.object(scheduler, "start") as mock_start, patch(
            "app.infrastructure.scheduler.main.scheduler_logger"
        ) as mock_logger:
            main()

            # Verify logger was called
            assert mock_logger.info.call_count == 2
            assert "Starting scheduler" in str(mock_logger.info.call_args_list[0])
            assert "Scheduler started successfully" in str(
                mock_logger.info.call_args_list[1]
            )

            # Verify scheduler.start was called
            mock_start.assert_called_once()

    def test_main_logs_startup_messages(self):
        """Test that main function logs appropriate startup messages."""
        with patch.object(scheduler, "start"), patch(
            "app.infrastructure.scheduler.main.scheduler_logger"
        ) as mock_logger:
            main()

            # Check that both log messages were called
            calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("Starting scheduler" in call for call in calls)
            assert any("started successfully" in call for call in calls)
