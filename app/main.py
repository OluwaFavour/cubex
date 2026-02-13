from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request, status
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_async_session
from app.shared.config import settings, app_logger
from app.shared.exceptions.handlers import (
    authentication_exception_handler,
    bad_request_exception_handler,
    conflict_exception_handler,
    database_exception_handler,
    exception_schema,
    forbidden_exception_handler,
    general_exception_handler,
    idempotency_exception_handler,
    not_found_exception_handler,
    not_implemented_exception_handler,
    oauth_exception_handler,
    otp_expired_exception_handler,
    otp_invalid_exception_handler,
    payment_required_exception_handler,
    rate_limit_exception_handler,
    stripe_api_exception_handler,
    stripe_card_exception_handler,
    stripe_rate_limit_exception_handler,
    too_many_attempts_exception_handler,
)
from app.shared.exceptions.types import (
    AppException,
    AuthenticationException,
    BadRequestException,
    ConflictException,
    DatabaseException,
    ForbiddenException,
    IdempotencyException,
    NotFoundException,
    NotImplementedException,
    OAuthException,
    OTPExpiredException,
    OTPInvalidException,
    PaymentRequiredException,
    RateLimitException,
    RateLimitExceededException,
    StripeAPIException,
    StripeCardException,
    TooManyAttemptsException,
)
from app.infrastructure.messaging import start_consumers
from app.infrastructure.scheduler import scheduler, initialize_scheduler
from app.shared.services import BrevoService, CloudinaryService, Renderer, RedisService
from app.shared.services.auth import AuthService
from app.shared.services.oauth import GoogleOAuthService, GitHubOAuthService
from app.shared.routers import auth_router, webhook_router
from app.apps.cubex_api.routers import (
    internal_router,
    support_router,
    workspace_router,
    subscription_router as api_subscription_router,
)
from app.apps.cubex_career.routers import (
    subscription_router as career_subscription_router,
)
from app.apps.cubex_api.services import QuotaCacheService
from app.shared.db import AsyncSessionLocal
from app.shared.utils import generate_openapi_json, write_to_file_async
from app.admin import init_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_logger.info("Starting application...")
    consumer_connection = None

    # Initialize Redis service
    app_logger.info("Initializing Redis service...")
    await RedisService.init(settings.REDIS_URL)
    app_logger.info("Redis service initialized successfully.")

    # Initialize Quota Cache service
    app_logger.info("Initializing Quota Cache service...")
    async with AsyncSessionLocal() as session:
        # Use "redis" backend for distributed deployments, "memory" for single instance
        await QuotaCacheService.init(session, backend=settings.QUOTA_CACHE_BACKEND)
    app_logger.info("Quota Cache service initialized successfully.")

    # Initialize Auth service
    app_logger.info("Initializing Auth service...")
    AuthService.init()
    app_logger.info("Auth service initialized successfully.")

    # Initialize OAuth services
    app_logger.info("Initializing OAuth services...")
    await GoogleOAuthService.init(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
    )
    await GitHubOAuthService.init(
        client_id=settings.GITHUB_CLIENT_ID,
        client_secret=settings.GITHUB_CLIENT_SECRET,
    )
    app_logger.info("OAuth services initialized successfully.")

    # Start the scheduler (only if enabled)
    if settings.ENABLE_SCHEDULER:
        app_logger.info("Starting scheduler...")
        scheduler.start()
        app_logger.info("Scheduler started successfully.")
        initialize_scheduler()  # Schedule jobs after starting the scheduler
    else:
        app_logger.info("Scheduler disabled via ENABLE_SCHEDULER setting.")

    # Configure Cloudinary
    app_logger.info("Configuring Cloudinary...")
    CloudinaryService.init(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
    )
    app_logger.info("Cloudinary configured successfully.")

    # Initialize Brevo Service
    app_logger.info("Initializing Brevo service...")
    await BrevoService.init(
        api_key=settings.BREVO_API_KEY,
        sender_email=settings.BREVO_SENDER_EMAIL,
        sender_name=settings.BREVO_SENDER_NAME,
    )
    app_logger.info("Brevo service initialized successfully.")

    # Start message consumers (only if enabled)
    if settings.ENABLE_MESSAGING:
        app_logger.info("Starting message consumers...")
        consumer_connection = await start_consumers(keep_alive=False)
        app_logger.info("Message consumers started successfully.")
    else:
        app_logger.info("Messaging disabled via ENABLE_MESSAGING setting.")

    # Initialize template renderer
    app_logger.info("Initializing template renderer...")
    Renderer.initialize("app/templates")
    app_logger.info("Template renderer initialized successfully.")

    # Generate and write OpenAPI schema to file
    app_logger.info("Generating OpenAPI schema...")
    openapi_schema = generate_openapi_json(app)
    await write_to_file_async("openapi.json", openapi_schema)

    # Yield control back to the application
    yield

    # Cleanup on shutdown
    app_logger.info("Shutting down application...")

    # Stop message consumers
    if consumer_connection:
        app_logger.info("Closing message consumer connection...")
        await consumer_connection.close()
        app_logger.info("Message consumer connection closed successfully.")

    # Stop the scheduler
    if settings.ENABLE_SCHEDULER:
        app_logger.info("Stopping scheduler...")
        scheduler.shutdown()
        app_logger.info("Scheduler stopped successfully.")

    # Close OAuth services
    app_logger.info("Closing OAuth services...")
    await GoogleOAuthService.aclose()
    await GitHubOAuthService.aclose()
    app_logger.info("OAuth services closed successfully.")

    # Close Redis service
    app_logger.info("Closing Redis service...")
    await RedisService.aclose()
    app_logger.info("Redis service closed successfully.")


app = FastAPI(
    lifespan=lifespan,
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    debug=settings.DEBUG,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    responses=exception_schema,
    root_path_in_servers=False,
    servers=[
        {
            "url": f"{settings.API_DOMAIN}",
        },
    ],
)

# Register exception handlers (order matters - more specific first)
app.add_exception_handler(OTPExpiredException, otp_expired_exception_handler)
app.add_exception_handler(OTPInvalidException, otp_invalid_exception_handler)
app.add_exception_handler(TooManyAttemptsException, too_many_attempts_exception_handler)
app.add_exception_handler(RateLimitExceededException, rate_limit_exception_handler)
app.add_exception_handler(OAuthException, oauth_exception_handler)
app.add_exception_handler(AuthenticationException, authentication_exception_handler)
app.add_exception_handler(ForbiddenException, forbidden_exception_handler)
app.add_exception_handler(PaymentRequiredException, payment_required_exception_handler)
app.add_exception_handler(NotFoundException, not_found_exception_handler)
app.add_exception_handler(ConflictException, conflict_exception_handler)
app.add_exception_handler(BadRequestException, bad_request_exception_handler)
app.add_exception_handler(DatabaseException, database_exception_handler)
# Stripe-specific exception handlers
app.add_exception_handler(StripeCardException, stripe_card_exception_handler)
app.add_exception_handler(IdempotencyException, idempotency_exception_handler)
app.add_exception_handler(RateLimitException, stripe_rate_limit_exception_handler)
app.add_exception_handler(StripeAPIException, stripe_api_exception_handler)
# Not implemented exception handler
app.add_exception_handler(NotImplementedException, not_implemented_exception_handler)
# Generic fallback
app.add_exception_handler(AppException, general_exception_handler)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware for session management
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    session_cookie=settings.SESSION_COOKIE_NAME,
    https_only=not settings.DEBUG,
    same_site=settings.SESSION_SAME_SITE_COOKIE_POLICY,
)

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(webhook_router, tags=["Webhooks"])
app.include_router(workspace_router, prefix="/api", tags=["API - Workspaces"])
app.include_router(api_subscription_router, prefix="/api", tags=["API - Subscriptions"])
app.include_router(support_router, prefix="/api", tags=["API - Support"])
app.include_router(internal_router, prefix="/api", tags=["API - Internal API"])
app.include_router(
    career_subscription_router, prefix="/career", tags=["Career - Subscriptions"]
)

# Mount admin interface
init_admin(app)


@app.get("/", include_in_schema=False)
async def root(request: Request):
    base_url = request.base_url._url.rstrip("/")
    return {
        "message": "Welcome to CueBX API",
        "documentations": {
            "swagger": f"{base_url}/docs",
            "redoc": f"{base_url}/redoc",
        },
        "version": settings.APP_VERSION,
    }


@app.head("/health", include_in_schema=False)
@app.get("/health")
async def health_check(session: Annotated[AsyncSession, Depends(get_async_session)]):
    """
    Health check endpoint to verify if the API is running.

    Checks:
        - Database connectivity
        - Redis connectivity
    """
    health_status = {
        "status": "ok",
        "message": "CueBX API is running.",
        "checks": {
            "database": "ok",
            "redis": "ok",
        },
    }

    # Check database connectivity
    try:
        async with session.begin():
            result = await session.execute(text("SELECT 1"))
            if result.scalar() != 1:
                health_status["checks"]["database"] = "unhealthy"
                health_status["status"] = "degraded"
    except Exception as e:
        app_logger.error(f"Database health check failed: {e}")
        health_status["checks"]["database"] = "unhealthy"
        health_status["status"] = "degraded"

    # Check Redis connectivity
    try:
        redis_ok = await RedisService.ping()
        if not redis_ok:
            health_status["checks"]["redis"] = "unhealthy"
            health_status["status"] = "degraded"
    except Exception as e:
        app_logger.error(f"Redis health check failed: {e}")
        health_status["checks"]["redis"] = "unhealthy"
        health_status["status"] = "degraded"

    # Return 503 if any check failed
    if health_status["status"] != "ok":
        raise AppException(
            "One or more health checks failed.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=health_status,
        )

    return health_status
