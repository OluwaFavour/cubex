"""
Routers for cubex_api.
"""

from app.apps.cubex_api.routers.subscription import router as subscription_router
from app.apps.cubex_api.routers.workspace import router as workspace_router

__all__ = [
    "subscription_router",
    "workspace_router",
]
