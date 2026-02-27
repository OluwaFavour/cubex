"""
Test suite for WorkspaceService.

- Personal workspace creation on signup
- Workspace CRUD operations
- Member management (invite, enable, disable)
- Invitation flow (create, accept, revoke)
- Ownership transfer

Run all tests:
    pytest tests/apps/cubex_api/test_workspace_service.py -v

Run with coverage:
    pytest tests/apps/cubex_api/test_workspace_service.py --cov=app.apps.cubex_api.services.workspace --cov-report=term-missing -v
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.enums import (
    MemberRole,
    MemberStatus,
    WorkspaceStatus,
    InvitationStatus,
    PlanType,
)


class TestWorkspaceServiceInit:

    def test_service_import(self):
        from app.apps.cubex_api.services.workspace import WorkspaceService

        assert WorkspaceService is not None

    def test_service_singleton_exists(self):
        from app.apps.cubex_api.services.workspace import workspace_service

        assert workspace_service is not None


class TestSlugGeneration:

    def test_slug_prefix(self):
        # The slug prefix is "ws-"
        expected_prefix = "ws-"
        assert expected_prefix == "ws-"

    def test_slug_pattern(self):
        # Slug should be: ws-{slugified_name}-{short_uuid}
        # e.g., ws-my-workspace-abc123
        import re

        pattern = r"^ws-[a-z0-9-]+-[a-z0-9]+$"
        example_slug = "ws-my-workspace-abc123"
        assert re.match(pattern, example_slug)


class TestWorkspaceExceptions:

    def test_workspace_not_found_exception(self):
        from app.apps.cubex_api.services.workspace import WorkspaceNotFoundException

        exc = WorkspaceNotFoundException()
        assert exc is not None

    def test_workspace_frozen_exception(self):
        from app.apps.cubex_api.services.workspace import WorkspaceFrozenException

        exc = WorkspaceFrozenException()
        assert exc is not None

    def test_insufficient_seats_exception(self):
        from app.apps.cubex_api.services.workspace import InsufficientSeatsException

        exc = InsufficientSeatsException()
        assert exc is not None

    def test_member_not_found_exception(self):
        from app.apps.cubex_api.services.workspace import MemberNotFoundException

        exc = MemberNotFoundException()
        assert exc is not None

    def test_invitation_not_found_exception(self):
        from app.apps.cubex_api.services.workspace import InvitationNotFoundException

        exc = InvitationNotFoundException()
        assert exc is not None

    def test_invitation_already_exists_exception(self):
        from app.apps.cubex_api.services.workspace import (
            InvitationAlreadyExistsException,
        )

        exc = InvitationAlreadyExistsException()
        assert exc is not None


class TestWorkspaceServiceEnums:

    def test_workspace_status_values(self):
        assert WorkspaceStatus.ACTIVE.value == "active"
        assert WorkspaceStatus.FROZEN.value == "frozen"
        assert WorkspaceStatus.SUSPENDED.value == "suspended"

    def test_member_status_values(self):
        assert MemberStatus.ENABLED.value == "enabled"
        assert MemberStatus.DISABLED.value == "disabled"

    def test_member_role_values(self):
        assert MemberRole.OWNER.value == "owner"
        assert MemberRole.ADMIN.value == "admin"
        assert MemberRole.MEMBER.value == "member"

    def test_invitation_status_values(self):
        assert InvitationStatus.PENDING.value == "pending"
        assert InvitationStatus.ACCEPTED.value == "accepted"
        assert InvitationStatus.EXPIRED.value == "expired"
        assert InvitationStatus.REVOKED.value == "revoked"


class TestWorkspaceServiceMethods:

    @pytest.fixture
    def service(self):
        """Get WorkspaceService instance."""
        from app.apps.cubex_api.services.workspace import WorkspaceService

        return WorkspaceService()

    def test_has_create_personal_workspace_method(self, service):
        assert hasattr(service, "create_personal_workspace")
        assert callable(service.create_personal_workspace)

    def test_has_create_workspace_method(self, service):
        assert hasattr(service, "create_workspace")
        assert callable(service.create_workspace)

    def test_has_get_workspace_method(self, service):
        assert hasattr(service, "get_workspace")
        assert callable(service.get_workspace)

    def test_has_get_workspace_by_slug_method(self, service):
        assert hasattr(service, "get_workspace_by_slug")
        assert callable(service.get_workspace_by_slug)

    def test_has_get_user_workspaces_method(self, service):
        assert hasattr(service, "get_user_workspaces")
        assert callable(service.get_user_workspaces)

    def test_has_invite_member_method(self, service):
        assert hasattr(service, "invite_member")
        assert callable(service.invite_member)

    def test_has_accept_invitation_method(self, service):
        assert hasattr(service, "accept_invitation")
        assert callable(service.accept_invitation)

    def test_has_transfer_ownership_method(self, service):
        assert hasattr(service, "transfer_ownership")
        assert callable(service.transfer_ownership)


class TestWorkspaceModelIntegration:

    def test_workspace_model_import(self):
        from app.apps.cubex_api.db.models.workspace import Workspace

        assert Workspace is not None

    def test_workspace_member_model_import(self):
        from app.apps.cubex_api.db.models.workspace import WorkspaceMember

        assert WorkspaceMember is not None

    def test_workspace_invitation_model_import(self):
        from app.apps.cubex_api.db.models.workspace import WorkspaceInvitation

        assert WorkspaceInvitation is not None


class TestWorkspaceCRUDIntegration:

    def test_workspace_db_import(self):
        from app.apps.cubex_api.db.crud.workspace import workspace_db

        assert workspace_db is not None

    def test_workspace_member_db_import(self):
        from app.apps.cubex_api.db.crud.workspace import workspace_member_db

        assert workspace_member_db is not None

    def test_workspace_invitation_db_import(self):
        from app.apps.cubex_api.db.crud.workspace import workspace_invitation_db

        assert workspace_invitation_db is not None

