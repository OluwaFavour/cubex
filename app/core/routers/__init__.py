"""
Shared routers for the application.

"""

from app.core.routers.auth import router as auth_router
from app.core.routers.webhook import router as webhook_router

__all__ = ["auth_router", "webhook_router"]

