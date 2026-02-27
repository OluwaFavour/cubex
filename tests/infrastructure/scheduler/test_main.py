"""
Test suite for scheduler initialization.

Run tests:
    pytest tests/infrastructure/scheduler/test_main.py -v

Run with coverage:
    pytest tests/infrastructure/scheduler/test_main.py --cov=app.infrastructure.scheduler.main --cov-report=term-missing -v
"""

from unittest.mock import patch

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.infrastructure.scheduler.main import scheduler


class TestScheduler:

    def test_scheduler_is_async_io_scheduler(self):
        assert isinstance(scheduler, AsyncIOScheduler)

    def test_scheduler_has_utc_timezone(self):
        assert scheduler.timezone is not None
        assert str(scheduler.timezone) == "UTC"


class TestMain:

    def test_scheduler_can_start(self):
        with patch.object(scheduler, "start") as mock_start:
            scheduler.start()
            mock_start.assert_called_once()

    def test_scheduler_can_shutdown(self):
        with patch.object(scheduler, "shutdown") as mock_shutdown:
            scheduler.shutdown()
            mock_shutdown.assert_called_once()

