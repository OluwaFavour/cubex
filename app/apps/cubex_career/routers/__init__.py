"""API routers for cubex_career."""

from app.apps.cubex_career.routers.history import router as history_router
from app.apps.cubex_career.routers.profile import router as profile_router
from app.apps.cubex_career.routers.subscription import router as subscription_router
from app.apps.cubex_career.routers.internal import router as internal_router

__all__ = ["history_router", "profile_router", "subscription_router", "internal_router"]
