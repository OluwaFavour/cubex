from functools import lru_cache
import logging
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.shared.logger import setup_logger


class Settings(BaseSettings):
    # Application settings
    ENVIRONMENT: str = "development"  # Options: development, production
    API_DOMAIN: str = "http://localhost:8000"
    APP_NAME: str = "CUEBEX"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = """
    CUEBEX
    """
    DEBUG: bool = True
    ROOT_PATH: str = "/v1"

    # CORS settings
    CORS_ALLOW_ORIGINS: list[str] = ["http://localhost:3000"]
    CORS_ALLOW_CREDENTIALS: bool = True

    # Session settings
    SESSION_COOKIE_NAME: str = "session"
    SESSION_SECRET_KEY: str = "supersecretkey"
    SESSION_SAME_SITE_COOKIE_POLICY: Literal["lax", "strict", "none"] = "lax"

    # JWT settings
    JWT_SECRET_KEY: str = "another_supersecret_key"
    JWT_ALGORITHM: str = "HS256"

    # Database settings
    DATABASE_URL: str
    TEST_DATABASE_URL: str = "sqlite+aiosqlite:///:memory:"

    # Cloudinary settings
    CLOUDINARY_CLOUD_NAME: str = "your_cloudinary_cloud_name"
    CLOUDINARY_API_KEY: str = "your_cloudinary_api_key"
    CLOUDINARY_API_SECRET: str = "your_cloudinary_api_secret"

    # Brevo settings
    BREVO_API_KEY: str = "your_brevo_api_key"
    BREVO_BASE_URL: str = "https://api.brevo.com/v3"
    BREVO_SENDER_EMAIL: str = "your_brevo_sender_email"
    BREVO_SENDER_NAME: str = "your_brevo_sender_name"

    # RabbitMQ settings
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672//"

    model_config: SettingsConfigDict = SettingsConfigDict(  # type: ignore
        env_file=".env",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()  # type: ignore


settings = get_settings()

# Configure loggers
app_logger = setup_logger(
    name="app_logger", log_file="logs/app.log", level=logging.INFO
)
database_logger = setup_logger(
    name="database_logger", log_file="logs/database.log", level=logging.INFO
)
request_logger = setup_logger(
    name="request_logger", log_file="logs/requests.log", level=logging.INFO
)
cloudinary_logger = setup_logger(
    name="cloudinary_logger",
    log_file="logs/cloudinary.log",
    level=logging.INFO,
)
brevo_logger = setup_logger(
    name="brevo_logger", log_file="logs/brevo.log", level=logging.INFO
)
rabbitmq_logger = setup_logger(
    name="rabbitmq_logger", log_file="logs/rabbitmq.log", level=logging.INFO
)
scheduler_logger = setup_logger(
    name="scheduler_logger", log_file="logs/scheduler.log", level=logging.INFO
)
utils_logger = setup_logger(
    name="utils_logger", log_file="logs/utils.log", level=logging.INFO
)

__all__ = [
    "settings",
    "app_logger",
    "database_logger",
    "request_logger",
    "cloudinary_logger",
    "brevo_logger",
    "rabbitmq_logger",
    "scheduler_logger",
    "utils_logger",
]
