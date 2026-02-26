from functools import lru_cache
import logging
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.logger import setup_logger, init_sentry


class Settings(BaseSettings):
    # Application settings
    ENVIRONMENT: str = "development"  # Options: development, production
    API_DOMAIN: str = "http://localhost:8000"
    APP_NAME: str = "CueBX"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = """
    CueBX
    """
    DEBUG: bool = True
    ROOT_PATH: str = "/v1"

    # Cleanup settings
    USER_SOFT_DELETE_RETENTION_DAYS: int = 30

    # Usage log settings
    USAGE_LOG_PENDING_TIMEOUT_MINUTES: int = 15  # Expire pending logs after this

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

    # Redis settings
    REDIS_URL: str = "redis://localhost:6379/0"

    # Rate limiting settings
    RATE_LIMIT_BACKEND: Literal["memory", "redis"] = "memory"
    RATE_LIMIT_DEFAULT_REQUESTS: int = 100
    RATE_LIMIT_DEFAULT_WINDOW: int = 60  # seconds

    # Quota cache settings
    QUOTA_CACHE_BACKEND: Literal["memory", "redis"] = "memory"

    # OTP settings
    OTP_LENGTH: int = 6
    OTP_EXPIRY_MINUTES: int = 10
    OTP_HMAC_SECRET: str = "otp_hmac_secret_key_change_in_production"
    OTP_MAX_ATTEMPTS: int = 5

    # OAuth settings
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    OAUTH_REDIRECT_BASE_URI: str = "http://localhost:8000/auth"

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

    # Infrastructure flags (for Docker separation)
    ENABLE_SCHEDULER: bool = True
    ENABLE_MESSAGING: bool = True

    # Sentry settings
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_TRACES_SAMPLE_RATE: float = 1.0

    # Stripe settings
    STRIPE_API_KEY: str = "your_stripe_api_key"
    STRIPE_WEBHOOK_SECRET: str = "your_stripe_webhook_secret"
    STRIPE_API_BASE_URL: str = "https://api.stripe.com"
    ## Stripe price settings
    STRIPE_CUBEX_API_PRICE_PROFESSIONAL: str = "price_1NEXAMPLEPROFESSIONAL"
    STRIPE_CUBEX_API_PRICE_BASIC: str = "price_1NEXAMPLEBASIC"
    STRIPE_CUBEX_API_SEAT_PRICE_PROFESSIONAL: str = "price_1NEXAMPLEPROFESSIONALSEAT"
    STRIPE_CUBEX_API_SEAT_PRICE_BASIC: str = "price_1NEXAMPLEBASICSEAT"
    ## Stripe price settings - Cubex Career
    STRIPE_CUBEX_CAREER_PRICE_PLUS: str = "price_1NEXAMPLECAREERPLUS"
    STRIPE_CUBEX_CAREER_PRICE_PRO: str = "price_1NEXAMPLECAREERPRO"

    # Internal API settings (for external API communication)
    INTERNAL_API_SECRET: str = "internal_api_secret_change_in_production"

    # Admin settings
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin_password_change_in_production"
    ADMIN_ALERT_EMAIL: str | None = (
        None  # Email for system alerts (DLQ, validation errors)
    )

    model_config: SettingsConfigDict = SettingsConfigDict(  # type: ignore
        env_file=".env",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()  # type: ignore


settings = get_settings()

# Initialize Sentry once globally (non-blocking, runs in background threads)
init_sentry(
    dsn=settings.SENTRY_DSN,
    environment=settings.SENTRY_ENVIRONMENT,
    traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
)

# Configure loggers with component-specific Sentry tags for separation of concerns
# Each logger gets its own log file and Sentry tag for easy filtering
app_logger = setup_logger(
    name="app_logger",
    log_file="logs/app.log",
    level=logging.INFO,
    sentry_tag="app",
)
database_logger = setup_logger(
    name="database_logger",
    log_file="logs/database.log",
    level=logging.INFO,
    sentry_tag="database",
)
request_logger = setup_logger(
    name="request_logger",
    log_file="logs/requests.log",
    level=logging.INFO,
    sentry_tag="request",
)
cloudinary_logger = setup_logger(
    name="cloudinary_logger",
    log_file="logs/cloudinary.log",
    level=logging.INFO,
    sentry_tag="cloudinary",
)
brevo_logger = setup_logger(
    name="brevo_logger",
    log_file="logs/brevo.log",
    level=logging.INFO,
    sentry_tag="email",
)
rabbitmq_logger = setup_logger(
    name="rabbitmq_logger",
    log_file="logs/rabbitmq.log",
    level=logging.INFO,
    sentry_tag="messaging",
)
scheduler_logger = setup_logger(
    name="scheduler_logger",
    log_file="logs/scheduler.log",
    level=logging.INFO,
    sentry_tag="scheduler",
)
utils_logger = setup_logger(
    name="utils_logger",
    log_file="logs/utils.log",
    level=logging.INFO,
    sentry_tag="utils",
)
auth_logger = setup_logger(
    name="auth_logger",
    log_file="logs/auth.log",
    level=logging.INFO,
    sentry_tag="auth",
)
redis_logger = setup_logger(
    name="redis_logger",
    log_file="logs/redis.log",
    level=logging.INFO,
    sentry_tag="redis",
)
rate_limit_logger = setup_logger(
    name="rate_limit_logger",
    log_file="logs/rate_limit.log",
    level=logging.INFO,
    sentry_tag="rate_limit",
)
email_manager_logger = setup_logger(
    name="email_manager_logger",
    log_file="logs/email_manager.log",
    level=logging.INFO,
    sentry_tag="email_manager",
)
stripe_logger = setup_logger(
    name="stripe_logger",
    log_file="logs/stripe.log",
    level=logging.INFO,
    sentry_tag="stripe",
)
plan_logger = setup_logger(
    name="plan_logger",
    log_file="logs/plan.log",
    level=logging.INFO,
    sentry_tag="plan",
)
workspace_logger = setup_logger(
    name="workspace_logger",
    log_file="logs/workspace.log",
    level=logging.INFO,
    sentry_tag="workspace",
)
webhook_logger = setup_logger(
    name="webhook_logger",
    log_file="logs/webhook.log",
    level=logging.INFO,
    sentry_tag="webhook",
)
usage_logger = setup_logger(
    name="usage_logger",
    log_file="logs/usage.log",
    level=logging.INFO,
    sentry_tag="usage",
)
career_logger = setup_logger(
    name="career_logger",
    log_file="logs/career.log",
    level=logging.INFO,
    sentry_tag="career",
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
    "auth_logger",
    "redis_logger",
    "rate_limit_logger",
    "email_manager_logger",
    "stripe_logger",
    "plan_logger",
    "workspace_logger",
    "webhook_logger",
    "usage_logger",
    "career_logger",
]
