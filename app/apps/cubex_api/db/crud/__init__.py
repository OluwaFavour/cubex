"""
CRUD operations for cubex_api.
"""

from app.apps.cubex_api.db.crud.workspace import (
    WorkspaceDB,
    WorkspaceMemberDB,
    WorkspaceInvitationDB,
    workspace_db,
    workspace_member_db,
    workspace_invitation_db,
    slugify,
)

__all__ = [
    # Classes
    "WorkspaceDB",
    "WorkspaceMemberDB",
    "WorkspaceInvitationDB",
    # Global instances
    "workspace_db",
    "workspace_member_db",
    "workspace_invitation_db",
    # Utilities
    "slugify",
]
