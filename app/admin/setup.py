"""
SQLAdmin setup and initialization.

Creates the Admin instance and provides initialization function
to mount the admin interface on the FastAPI application.
"""

from fastapi import FastAPI
from sqladmin import Admin

from app.admin.auth import admin_auth
from app.admin.views import (
    FeatureCostConfigAdmin,
    PlanAdmin,
    PlanPricingRuleAdmin,
    SubscriptionAdmin,
    UsageLogAdmin,
    UserAdmin,
    WorkspaceAdmin,
    WorkspaceMemberAdmin,
)
from app.core.db import async_engine

# Admin instance will be created when init_admin is called
admin: Admin | None = None


def init_admin(app: FastAPI) -> None:
    """
    Initialize and mount the admin interface on the FastAPI app.

    Args:
        app: The FastAPI application instance.
    """
    global admin

    admin = Admin(
        app=app,
        engine=async_engine,
        title="CueBX Admin",
        base_url="/admin",
        authentication_backend=admin_auth,
    )

    # Register model views
    admin.add_view(PlanAdmin)
    admin.add_view(FeatureCostConfigAdmin)
    admin.add_view(PlanPricingRuleAdmin)
    admin.add_view(UserAdmin)
    admin.add_view(WorkspaceAdmin)
    admin.add_view(WorkspaceMemberAdmin)
    admin.add_view(SubscriptionAdmin)
    admin.add_view(UsageLogAdmin)


__all__ = ["admin", "init_admin"]

