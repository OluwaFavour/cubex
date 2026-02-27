"""
CRUD operations for cubex_api.
"""

from app.apps.cubex_api.db.crud.support import (
    SalesRequestDB,
    sales_request_db,
)
from app.apps.cubex_api.db.crud.workspace import (
    APIKeyDB,
    UsageLogDB,
    WorkspaceDB,
    WorkspaceMemberDB,
    WorkspaceInvitationDB,
    api_key_db,
    usage_log_db,
    workspace_db,
    workspace_member_db,
    workspace_invitation_db,
    slugify,
)

__all__ = [
    # Support
    "SalesRequestDB",
    "sales_request_db",
    # Classes
    "APIKeyDB",
    "UsageLogDB",
    "WorkspaceDB",
    "WorkspaceMemberDB",
    "WorkspaceInvitationDB",
    # Global instances
    "api_key_db",
    "usage_log_db",
    "workspace_db",
    "workspace_member_db",
    "workspace_invitation_db",
    # Utilities
    "slugify",
]

