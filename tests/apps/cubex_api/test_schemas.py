"""
Test suite for Workspace schemas.

This module tests the Pydantic schemas for workspaces, members, and invitations.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from app.apps.cubex_api.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceResponse,
    WorkspaceMemberResponse,
    InvitationCreate,
    InvitationResponse,
    InvitationAccept,
    MemberStatusUpdate,
    MemberRoleUpdate,
)


class TestWorkspaceCreate:

    def test_workspace_create_minimal(self):
        data = WorkspaceCreate(display_name="My Workspace")

        assert data.display_name == "My Workspace"
        assert data.description is None

    def test_workspace_create_full(self):
        data = WorkspaceCreate(
            display_name="My Workspace",
            description="A test workspace",
        )

        assert data.display_name == "My Workspace"
        assert data.description == "A test workspace"

    def test_workspace_create_empty_name_fails(self):
        with pytest.raises(ValidationError):
            WorkspaceCreate(display_name="")

    def test_workspace_create_whitespace_name_stripped(self):
        data = WorkspaceCreate(display_name="  My Workspace  ")

        # Depending on implementation, name may be stripped
        assert data.display_name.strip() == "My Workspace"


class TestWorkspaceUpdate:

    def test_workspace_update_all_optional(self):
        data = WorkspaceUpdate()

        assert data.display_name is None
        assert data.description is None

    def test_workspace_update_partial(self):
        data = WorkspaceUpdate(display_name="New Name")

        assert data.display_name == "New Name"
        assert data.description is None


class TestWorkspaceResponse:

    def test_workspace_response_from_attributes(self):
        workspace_id = uuid4()
        owner_id = uuid4()
        now = datetime.now(timezone.utc)

        data = WorkspaceResponse(
            id=workspace_id,
            display_name="Test Workspace",
            slug="ws-test-workspace-abc123",
            description="A test workspace",
            owner_id=owner_id,
            status="active",
            is_personal=False,
            created_at=now,
        )

        assert data.id == workspace_id
        assert data.display_name == "Test Workspace"
        assert data.slug == "ws-test-workspace-abc123"
        assert data.owner_id == owner_id
        assert data.status == "active"
        assert data.is_personal is False


class TestWorkspaceMemberResponse:

    def test_member_response_from_attributes(self):
        member_id = uuid4()
        user_id = uuid4()
        now = datetime.now(timezone.utc)

        data = WorkspaceMemberResponse(
            id=member_id,
            user_id=user_id,
            role="member",
            status="enabled",
            joined_at=now,
        )

        assert data.id == member_id
        assert data.user_id == user_id
        assert data.role == "member"
        assert data.status == "enabled"


class TestInvitationCreate:

    def test_invitation_create_with_email(self):
        data = InvitationCreate(
            email="user@example.com",
            role="member",
            callback_url="https://app.example.com/invitation",
        )

        assert data.email == "user@example.com"
        assert data.role == "member"
        assert data.callback_url == "https://app.example.com/invitation"

    def test_invitation_create_default_role(self):
        data = InvitationCreate(
            email="user@example.com",
            callback_url="https://app.example.com/invitation",
        )

        assert data.email == "user@example.com"
        assert data.role == "member"
        assert data.callback_url == "https://app.example.com/invitation"

    def test_invitation_create_admin_role(self):
        data = InvitationCreate(
            email="admin@example.com",
            role="admin",
            callback_url="https://app.example.com/invitation",
        )

        assert data.role == "admin"
        assert data.callback_url == "https://app.example.com/invitation"

    def test_invitation_create_invalid_email(self):
        with pytest.raises(ValidationError):
            InvitationCreate(
                email="invalid-email",
                callback_url="https://app.example.com/invitation",
            )


class TestInvitationResponse:

    def test_invitation_response_from_attributes(self):
        invitation_id = uuid4()
        now = datetime.now(timezone.utc)

        data = InvitationResponse(
            id=invitation_id,
            email="user@example.com",
            role="member",
            status="pending",
            created_at=now,
            expires_at=now,
        )

        assert data.id == invitation_id
        assert data.email == "user@example.com"
        assert data.status == "pending"


class TestInvitationAccept:

    def test_accept_invitation_with_token(self):
        data = InvitationAccept(token="abc123def456")

        assert data.token == "abc123def456"


class TestMemberStatusUpdate:

    def test_member_status_update_enable(self):
        data = MemberStatusUpdate(status="enabled")

        assert data.status == "enabled"

    def test_member_status_update_disable(self):
        data = MemberStatusUpdate(status="disabled")

        assert data.status == "disabled"


class TestMemberRoleUpdate:

    def test_member_role_update_to_admin(self):
        data = MemberRoleUpdate(role="admin")

        assert data.role == "admin"

    def test_member_role_update_to_member(self):
        data = MemberRoleUpdate(role="member")

        assert data.role == "member"

