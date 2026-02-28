import logging
from logging.handlers import RotatingFileHandler
import os
from typing import Optional

# Track if Sentry has been initialized (global singleton)
_sentry_initialized = False


def init_sentry(
    dsn: str,
    environment: str = "development",
    traces_sample_rate: float = 1.0,
) -> bool:
    """
    Initialize Sentry SDK globally (should be called once at application startup).

    Sentry SDK is a global singleton - initializing it multiple times is unnecessary.
    This function ensures Sentry is initialized only once.

    Args:
        dsn (str): Sentry DSN for error tracking.
        environment (str): Sentry environment name (development/production).
        traces_sample_rate (float): Performance monitoring sample rate (0.0 to 1.0).
            When > 0, performance tracing is automatically enabled.

    Returns:
        bool: True if Sentry was initialized, False if already initialized or SDK not available.
    """
    global _sentry_initialized

    if _sentry_initialized:
        return False

    if not dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.asyncio import AsyncioIntegration

        # Configure Sentry logging integration
        sentry_logging = LoggingIntegration(
            level=logging.INFO,  # Capture info and above as breadcrumbs
            event_level=logging.ERROR,  # Send errors as events
        )

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=traces_sample_rate,
            integrations=[sentry_logging, AsyncioIntegration()],
        )

        _sentry_initialized = True
        return True
    except ImportError:
        # Sentry SDK not installed
        return False


def setup_logger(
    name: str,
    log_file: str,
    level: int = logging.INFO,
    sentry_tag: Optional[str] = None,
) -> logging.Logger:
    """
    Sets up a logger with a specified name, log file, and logging level.
    This function configures a logger to write log messages to both a rotating file
    and the console. The log messages will include the timestamp, logger name,
    log level, and message.

    For Sentry error tracking, use init_sentry() once at application startup,
    then use sentry_tag to differentiate components in Sentry.

    Args:
        name (str): The name of the logger.
        log_file (str): The file path where the log messages will be written.
        level (int, optional): The logging level. Defaults to logging.INFO.
        sentry_tag (str, optional): Tag to identify this component in Sentry (e.g., "database", "api").

    Returns:
        logging.Logger: The configured logger instance.
    """
    if sentry_tag and _sentry_initialized:
        try:
            import sentry_sdk

            sentry_sdk.set_tag("component", sentry_tag)
        except ImportError:
            pass

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Define the log format
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    handlers = []
    # File handler (with rotation)
    os.makedirs("logs", exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler.stream.reconfigure(encoding="utf-8")
    handlers.append(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    # Add handlers to the logger
    for handler in handlers:
        logger.addHandler(handler)

    return logger
