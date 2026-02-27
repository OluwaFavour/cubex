"""
Routers for cubex_api.
"""

from app.apps.cubex_api.routers.internal import router as internal_router
from app.apps.cubex_api.routers.subscription import router as subscription_router
from app.apps.cubex_api.routers.support import router as support_router
from app.apps.cubex_api.routers.workspace import router as workspace_router

__all__ = [
    "internal_router",
    "subscription_router",
    "support_router",
    "workspace_router",
]

