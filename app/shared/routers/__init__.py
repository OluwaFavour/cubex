"""
Shared routers for the application.

This module exports all shared FastAPI routers that can be
included in the main application or app-specific routers.
"""

from app.shared.routers.auth import router as auth_router

__all__ = ["auth_router"]
