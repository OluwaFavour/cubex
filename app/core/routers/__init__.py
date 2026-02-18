"""
Shared routers for the application.

This module exports all shared FastAPI routers that can be
included in the main application or app-specific routers.
"""

from app.core.routers.auth import router as auth_router
from app.core.routers.webhook import router as webhook_router

__all__ = ["auth_router", "webhook_router"]
