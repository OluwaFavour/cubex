import logging
from logging.handlers import RotatingFileHandler
import os


# Configure the logger
def setup_logger(name: str, log_file: str, level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a logger with a specified name, log file, and logging level.
    This function configures a logger to write log messages to both a rotating file
    and the console. The log messages will include the timestamp, logger name,
    log level, and message.

    Args:
        name (str): The name of the logger.
        log_file (str): The file path where the log messages will be written.
        level (int, optional): The logging level (e.g., logging.INFO, logging.DEBUG). Defaults to logging.INFO.

    Returns:
        logging.Logger: The configured logger instance.
    """
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
