from contextlib import asynccontextmanager
import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Request, status
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_async_session
from app.shared.config import settings, app_logger
from app.shared.db import init_db, dispose_db
from app.shared.exceptions.handlers import (
    exception_schema,
)
from app.shared.exceptions.types import (
    AppException,
)
from app.infrastructure.messaging import start_consumers
from app.infrastructure.scheduler import scheduler
from app.shared.services import BrevoService, CloudinaryService, Renderer
from app.shared.utils import generate_openapi_json, write_to_file_async

logging.basicConfig(level=logging.INFO)
logging.getLogger("apscheduler").setLevel(logging.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_logger.info("Starting application...")
    # Initialize the database
    app_logger.info("Initializing database...")
    await init_db()
    app_logger.info("Database initialized successfully.")
    # Start the scheduler
    app_logger.info("Starting scheduler...")
    scheduler.start()
    app_logger.info("Scheduler started successfully.")
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
    # Start message consumers
    app_logger.info("Starting message consumers...")
    consumer_connection = await start_consumers(keep_alive=False)
    app_logger.info("Message consumers started successfully.")
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
    app_logger.info("Stopping scheduler...")
    scheduler.shutdown()
    app_logger.info("Scheduler stopped successfully.")
    app_logger.info("Disposing database...")
    await dispose_db()
    app_logger.info("Database disposed successfully.")
    app_logger.info("Application shutdown complete.")


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


@app.get("/", include_in_schema=False)
async def root(request: Request):
    base_url = request.base_url._url.rstrip("/")
    return {
        "message": "Welcome to Wander API",
        "documentations": {
            "swagger": f"{base_url}/docs",
            "redoc": f"{base_url}/redoc",
        },
        "version": "1.0.0",
    }


@app.head("/health", include_in_schema=False)
@app.get("/health")
async def health_check(session: Annotated[AsyncSession, Depends(get_async_session)]):
    """
    Health check endpoint to verify if the API is running.
    """
    async with session.begin():
        try:
            result = await session.execute(text("SELECT 1"))
            if result.scalar() == 1:
                pass
        except Exception as e:
            app_logger.error(f"Health check failed: {e}")
            raise AppException(
                "Wander API is not reachable.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
    return {"status": "ok", "message": "Wander API is running."}
