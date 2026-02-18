"""
Test suite for logger configuration and Sentry integration.

Run tests:
    pytest app/tests/core/test_logger.py -v

Run with coverage:
    pytest app/tests/core/test_logger.py --cov=app.core.logger --cov-report=term-missing -v
"""

import logging
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.core.logger import setup_logger, init_sentry


@pytest.fixture(autouse=True)
def reset_sentry_state():
    """Reset Sentry initialization state before each test."""
    import app.core.logger as logger_module

    logger_module._sentry_initialized = False
    yield
    logger_module._sentry_initialized = False


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for log files."""
    import shutil

    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    # Close all handlers to release file locks on Windows
    logging.shutdown()
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


class TestInitSentry:
    """Test suite for init_sentry function."""

    def test_init_sentry_with_valid_dsn(self):
        """Test Sentry initialization with valid DSN."""
        mock_sentry = MagicMock()
        mock_logging_integration = MagicMock()
        mock_asyncio_integration = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "sentry_sdk": mock_sentry,
                "sentry_sdk.integrations.logging": MagicMock(
                    LoggingIntegration=mock_logging_integration
                ),
                "sentry_sdk.integrations.asyncio": MagicMock(
                    AsyncioIntegration=mock_asyncio_integration
                ),
            },
        ):
            result = init_sentry(
                dsn="https://test@sentry.io/123",
                environment="production",
                traces_sample_rate=0.5,
            )

            # Verify initialization was successful
            assert result is True

            # Verify sentry_sdk.init was called
            mock_sentry.init.assert_called_once()
            call_kwargs = mock_sentry.init.call_args.kwargs
            assert call_kwargs["dsn"] == "https://test@sentry.io/123"
            assert call_kwargs["environment"] == "production"
            assert call_kwargs["traces_sample_rate"] == 0.5

    def test_init_sentry_already_initialized(self):
        """Test that Sentry initialization is skipped if already initialized."""
        import app.core.logger as logger_module

        logger_module._sentry_initialized = True

        result = init_sentry(dsn="https://test@sentry.io/123")

        # Should return False when already initialized
        assert result is False

    def test_init_sentry_empty_dsn(self):
        """Test that empty DSN prevents initialization."""
        result = init_sentry(dsn="")

        assert result is False

    def test_init_sentry_none_dsn(self):
        """Test that None DSN prevents initialization."""
        result = init_sentry(dsn=None)  # type: ignore

        # Should handle None gracefully
        assert result is False

    def test_init_sentry_missing_sdk(self):
        """Test graceful handling when Sentry SDK is not installed."""
        with patch(
            "builtins.__import__",
            side_effect=ImportError("No module named 'sentry_sdk'"),
        ):
            result = init_sentry(dsn="https://test@sentry.io/123")

            # Should return False when SDK not available
            assert result is False

    def test_init_sentry_sets_global_flag(self):
        """Test that successful initialization sets global flag."""
        import app.core.logger as logger_module

        mock_sentry = MagicMock()
        mock_logging_integration = MagicMock()
        mock_asyncio_integration = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "sentry_sdk": mock_sentry,
                "sentry_sdk.integrations.logging": MagicMock(
                    LoggingIntegration=mock_logging_integration
                ),
                "sentry_sdk.integrations.asyncio": MagicMock(
                    AsyncioIntegration=mock_asyncio_integration
                ),
            },
        ):
            init_sentry(dsn="https://test@sentry.io/123")

            # Verify global flag was set
            assert logger_module._sentry_initialized is True


class TestSetupLogger:
    """Test suite for setup_logger function."""

    def test_setup_logger_basic(self, temp_log_dir):
        """Test basic logger setup."""
        log_file = os.path.join(temp_log_dir, "test.log")

        logger = setup_logger(
            name="test_logger",
            log_file=log_file,
            level=logging.INFO,
        )

        # Verify logger configuration
        assert logger.name == "test_logger"
        assert logger.level == logging.INFO
        assert len(logger.handlers) >= 2  # File + Console handlers

    def test_setup_logger_creates_log_directory(self, temp_log_dir):
        """Test that logger creates 'logs' directory if it doesn't exist."""
        # Mock os.makedirs to verify it's called
        with patch("app.core.logger.os.makedirs") as mock_makedirs:
            log_file = os.path.join(temp_log_dir, "test.log")
            setup_logger(name="test_logger", log_file=log_file)

            # Verify os.makedirs was called with "logs" directory
            mock_makedirs.assert_called_once_with("logs", exist_ok=True)

    def test_setup_logger_file_handler(self, temp_log_dir):
        """Test that file handler is configured correctly."""
        log_file = os.path.join(temp_log_dir, "test.log")

        logger = setup_logger(name="test_logger", log_file=log_file)

        # Find the rotating file handler
        file_handler = None
        for handler in logger.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                file_handler = handler
                break

        assert file_handler is not None
        assert file_handler.maxBytes == 5 * 1024 * 1024  # 5MB
        assert file_handler.backupCount == 3

    def test_setup_logger_console_handler(self, temp_log_dir):
        """Test that console handler is configured."""
        log_file = os.path.join(temp_log_dir, "test.log")

        logger = setup_logger(name="test_logger", log_file=log_file)

        # Find the stream handler (console)
        console_handler = None
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(
                handler, logging.handlers.RotatingFileHandler
            ):
                console_handler = handler
                break

        assert console_handler is not None

    def test_setup_logger_custom_level(self, temp_log_dir):
        """Test logger with custom logging level."""
        log_file = os.path.join(temp_log_dir, "test.log")

        logger = setup_logger(
            name="debug_logger",
            log_file=log_file,
            level=logging.DEBUG,
        )

        assert logger.level == logging.DEBUG

    def test_setup_logger_with_sentry_tag_not_initialized(self, temp_log_dir):
        """Test sentry_tag when Sentry is not initialized."""
        log_file = os.path.join(temp_log_dir, "test.log")

        # Should not raise error even with sentry_tag
        logger = setup_logger(
            name="test_logger",
            log_file=log_file,
            sentry_tag="test_component",
        )

        assert logger is not None

    def test_setup_logger_with_sentry_tag_initialized(self, temp_log_dir):
        """Test sentry_tag when Sentry is initialized."""
        import app.core.logger as logger_module

        logger_module._sentry_initialized = True

        log_file = os.path.join(temp_log_dir, "test.log")

        mock_sentry = MagicMock()
        with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
            logger = setup_logger(
                name="test_logger",
                log_file=log_file,
                sentry_tag="database",
            )

            # Verify Sentry tag was set
            mock_sentry.set_tag.assert_called_once_with("component", "database")
            assert logger is not None

    def test_setup_logger_sentry_tag_import_error(self, temp_log_dir):
        """Test graceful handling when Sentry SDK not available with tag."""
        import app.core.logger as logger_module

        logger_module._sentry_initialized = True

        log_file = os.path.join(temp_log_dir, "test.log")

        with patch(
            "builtins.__import__",
            side_effect=ImportError("No module named 'sentry_sdk'"),
        ):
            # Should not raise error
            logger = setup_logger(
                name="test_logger",
                log_file=log_file,
                sentry_tag="test",
            )

            assert logger is not None

    def test_setup_logger_multiple_calls_same_name(self, temp_log_dir):
        """Test that multiple calls with same name return same logger."""
        log_file = os.path.join(temp_log_dir, "test.log")

        logger1 = setup_logger(name="same_logger", log_file=log_file)
        logger2 = setup_logger(name="same_logger", log_file=log_file)

        # Should return the same logger instance
        assert logger1 is logger2

    def test_setup_logger_writes_to_file(self, temp_log_dir):
        """Test that logger actually writes to file."""
        log_file = os.path.join(temp_log_dir, "test.log")

        logger = setup_logger(name="write_test", log_file=log_file)
        logger.info("Test message")

        # Flush handlers to ensure write
        for handler in logger.handlers:
            handler.flush()

        # Verify file was created and has content
        assert os.path.exists(log_file)
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Test message" in content

    def test_setup_logger_formatter(self, temp_log_dir):
        """Test that logger uses correct formatter."""
        log_file = os.path.join(temp_log_dir, "test.log")

        logger = setup_logger(name="format_test", log_file=log_file)

        # Check that handlers have formatters
        for handler in logger.handlers:
            assert handler.formatter is not None
            # Format should include timestamp, name, level, message
            format_str = handler.formatter._fmt
            assert "%(asctime)s" in format_str
            assert "%(name)s" in format_str
            assert "%(levelname)s" in format_str
            assert "%(message)s" in format_str
