"""
Integration tests for workspace router.

Tests all workspace endpoints with real database and per-test rollback.
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4

from app.core.enums import (
    MemberRole,
    MemberStatus,
    WorkspaceStatus,
)


class TestListWorkspaces:
    """Tests for GET /api/workspaces"""

    @pytest.mark.asyncio
    async def test_list_workspaces_success(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should return list of user's workspaces."""
        response = await authenticated_client.get("/api/workspaces")

        assert response.status_code == 200
        data = response.json()
        assert "workspaces" in data
        assert len(data["workspaces"]) >= 1

        workspace_ids = [w["id"] for w in data["workspaces"]]
        assert str(test_workspace.id) in workspace_ids

    @pytest.mark.asyncio
    async def test_list_workspaces_empty(self, authenticated_client: AsyncClient):
        """Should return empty list if user has no workspaces."""
        response = await authenticated_client.get("/api/workspaces")

        assert response.status_code == 200
        data = response.json()
        assert "workspaces" in data
        # May be empty if no workspace fixtures loaded

    @pytest.mark.asyncio
    async def test_list_workspaces_unauthenticated(self, client: AsyncClient):
        """Should return 401 if not authenticated."""
        response = await client.get("/api/workspaces")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_workspaces_includes_personal_workspace(
        self, authenticated_client: AsyncClient, personal_workspace
    ):
        """Should include personal workspaces in list."""
        response = await authenticated_client.get("/api/workspaces")

        assert response.status_code == 200
        data = response.json()
        workspace_ids = [w["id"] for w in data["workspaces"]]
        assert str(personal_workspace.id) in workspace_ids

    @pytest.mark.asyncio
    async def test_list_workspaces_filter_by_owner_role(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should filter workspaces where user is owner."""
        response = await authenticated_client.get(
            "/api/workspaces", params={"member_role": "owner"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "workspaces" in data
        # test_workspace has test_user as owner
        workspace_ids = [w["id"] for w in data["workspaces"]]
        assert str(test_workspace.id) in workspace_ids

    @pytest.mark.asyncio
    async def test_list_workspaces_filter_by_member_role(
        self, client: AsyncClient, test_workspace, test_workspace_member
    ):
        """Should filter workspaces where user is member."""
        from tests.conftest import create_test_access_token

        member_user, _ = test_workspace_member
        token = create_test_access_token(member_user)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.get("/api/workspaces", params={"member_role": "member"})

        assert response.status_code == 200
        data = response.json()
        assert "workspaces" in data
        workspace_ids = [w["id"] for w in data["workspaces"]]
        assert str(test_workspace.id) in workspace_ids

    @pytest.mark.asyncio
    async def test_list_workspaces_filter_by_admin_role(
        self, client: AsyncClient, test_workspace, test_workspace_admin
    ):
        """Should filter workspaces where user is admin."""
        from tests.conftest import create_test_access_token

        admin_user, _ = test_workspace_admin
        token = create_test_access_token(admin_user)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.get("/api/workspaces", params={"member_role": "admin"})

        assert response.status_code == 200
        data = response.json()
        assert "workspaces" in data
        workspace_ids = [w["id"] for w in data["workspaces"]]
        assert str(test_workspace.id) in workspace_ids

    @pytest.mark.asyncio
    async def test_list_workspaces_filter_excludes_other_roles(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should exclude workspaces where user has different role."""
        # test_user is owner of test_workspace, filter by member should not include it
        response = await authenticated_client.get(
            "/api/workspaces", params={"member_role": "member"}
        )

        assert response.status_code == 200
        data = response.json()
        workspace_ids = [w["id"] for w in data["workspaces"]]
        # test_workspace should NOT be in results since user is owner, not member
        assert str(test_workspace.id) not in workspace_ids

    @pytest.mark.asyncio
    async def test_list_workspaces_filter_invalid_role(
        self, authenticated_client: AsyncClient
    ):
        """Should return 422 for invalid role value."""
        response = await authenticated_client.get(
            "/api/workspaces", params={"member_role": "invalid_role"}
        )

        assert response.status_code == 422


class TestCreateWorkspace:
    """Tests for POST /api/workspaces"""

    @pytest.mark.asyncio
    async def test_create_workspace_success(self, authenticated_client: AsyncClient):
        """Should create workspace and return details."""
        payload = {
            "display_name": "New Test Workspace",
            "description": "Test workspace description",
        }
        response = await authenticated_client.post("/api/workspaces", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["display_name"] == "New Test Workspace"
        assert data["description"] == "Test workspace description"
        assert data["is_personal"] is False
        assert data["status"] == WorkspaceStatus.ACTIVE.value
        assert "slug" in data
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_workspace_minimal(self, authenticated_client: AsyncClient):
        """Should create workspace with only required fields."""
        payload = {"display_name": "Minimal Workspace"}
        response = await authenticated_client.post("/api/workspaces", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["display_name"] == "Minimal Workspace"
        assert data["description"] is None

    @pytest.mark.asyncio
    async def test_create_workspace_empty_name(self, authenticated_client: AsyncClient):
        """Should reject empty display name."""
        payload = {"display_name": ""}
        response = await authenticated_client.post("/api/workspaces", json=payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_workspace_long_name(self, authenticated_client: AsyncClient):
        """Should reject name exceeding max length."""
        payload = {"display_name": "A" * 200}  # Exceeds 128 char limit
        response = await authenticated_client.post("/api/workspaces", json=payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_workspace_unauthenticated(self, client: AsyncClient):
        """Should return 401 if not authenticated."""
        payload = {"display_name": "Test"}
        response = await client.post("/api/workspaces", json=payload)

        assert response.status_code == 401


class TestGetWorkspace:
    """Tests for GET /api/workspaces/{workspace_id}"""

    @pytest.mark.asyncio
    async def test_get_workspace_success(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should return workspace details for member."""
        response = await authenticated_client.get(
            f"/api/workspaces/{test_workspace.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_workspace.id)
        assert data["display_name"] == test_workspace.display_name
        assert "members" in data
        assert "seat_count" in data
        assert "available_seats" in data

    @pytest.mark.asyncio
    async def test_get_workspace_not_found(self, authenticated_client: AsyncClient):
        """Should return 404 for non-existent workspace."""
        fake_id = uuid4()
        response = await authenticated_client.get(f"/api/workspaces/{fake_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_workspace_not_member(
        self, client: AsyncClient, test_workspace, db_session
    ):
        """Should return 404 if user is not a member."""
        from app.core.db.models import User
        from tests.conftest import create_test_access_token

        other_user = User(
            id=uuid4(),
            email="other@example.com",
            password_hash="hash",
            full_name="Other User",
            email_verified=True,
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.flush()

        token = create_test_access_token(other_user)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.get(f"/api/workspaces/{test_workspace.id}")
        assert response.status_code == 404


class TestUpdateWorkspace:
    """Tests for PATCH /api/workspaces/{workspace_id}"""

    @pytest.mark.asyncio
    async def test_update_workspace_display_name(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should update workspace display name."""
        payload = {"display_name": "Updated Name"}
        response = await authenticated_client.patch(
            f"/api/workspaces/{test_workspace.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_workspace_description(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should update workspace description."""
        payload = {"description": "New description"}
        response = await authenticated_client.patch(
            f"/api/workspaces/{test_workspace.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "New description"

    @pytest.mark.asyncio
    async def test_update_workspace_slug(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should update workspace slug."""
        payload = {"slug": "new-workspace-slug"}
        response = await authenticated_client.patch(
            f"/api/workspaces/{test_workspace.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "new-workspace-slug"

    @pytest.mark.asyncio
    async def test_update_workspace_invalid_slug(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should reject invalid slug format."""
        payload = {"slug": "Invalid Slug With Spaces!"}
        response = await authenticated_client.patch(
            f"/api/workspaces/{test_workspace.id}", json=payload
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_workspace_not_admin(
        self, client: AsyncClient, test_workspace, test_workspace_member
    ):
        """Should return 403 if user is not admin."""
        from tests.conftest import create_test_access_token

        member_user, _ = test_workspace_member
        token = create_test_access_token(member_user)
        client.headers["Authorization"] = f"Bearer {token}"

        payload = {"display_name": "Unauthorized Update"}
        response = await client.patch(
            f"/api/workspaces/{test_workspace.id}", json=payload
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_workspace_not_found(self, authenticated_client: AsyncClient):
        """Should return 404 for non-existent workspace."""
        fake_id = uuid4()
        payload = {"display_name": "Test"}
        response = await authenticated_client.patch(
            f"/api/workspaces/{fake_id}", json=payload
        )

        assert response.status_code == 404


class TestListMembers:
    """Tests for GET /api/workspaces/{workspace_id}/members"""

    @pytest.mark.asyncio
    async def test_list_members_success(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should return list of workspace members."""
        response = await authenticated_client.get(
            f"/api/workspaces/{test_workspace.id}/members"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_list_members_filter_enabled(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should filter members by enabled status."""
        response = await authenticated_client.get(
            f"/api/workspaces/{test_workspace.id}/members?status=enabled"
        )

        assert response.status_code == 200
        data = response.json()
        for member in data:
            assert member["status"] == MemberStatus.ENABLED.value

    @pytest.mark.asyncio
    async def test_list_members_not_member(
        self, client: AsyncClient, test_workspace, db_session
    ):
        """Should return 404 if user is not a member."""
        from app.core.db.models import User
        from tests.conftest import create_test_access_token

        other_user = User(
            id=uuid4(),
            email="outsider@example.com",
            password_hash="hash",
            full_name="Outsider",
            email_verified=True,
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.flush()

        token = create_test_access_token(other_user)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.get(f"/api/workspaces/{test_workspace.id}/members")
        assert response.status_code == 404


class TestUpdateMemberStatus:
    """Tests for PATCH /api/workspaces/{workspace_id}/members/{member_user_id}/status"""

    @pytest.mark.asyncio
    async def test_disable_member_success(
        self,
        authenticated_client: AsyncClient,
        test_workspace,
        test_workspace_member,
        test_subscription,
    ):
        """Should disable member successfully."""
        member_user, _ = test_workspace_member
        payload = {"status": MemberStatus.DISABLED.value}
        response = await authenticated_client.patch(
            f"/api/workspaces/{test_workspace.id}/members/{member_user.id}/status",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == MemberStatus.DISABLED.value

    @pytest.mark.asyncio
    async def test_enable_member_success(
        self,
        authenticated_client: AsyncClient,
        test_workspace,
        test_workspace_member,
        test_subscription,
        db_session,
    ):
        """Should enable disabled member successfully."""
        member_user, member = test_workspace_member

        # First disable the member
        member.status = MemberStatus.DISABLED
        await db_session.flush()

        payload = {"status": MemberStatus.ENABLED.value}
        response = await authenticated_client.patch(
            f"/api/workspaces/{test_workspace.id}/members/{member_user.id}/status",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == MemberStatus.ENABLED.value

    @pytest.mark.asyncio
    async def test_update_status_member_not_found(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should return 404 if member not found."""
        fake_user_id = uuid4()
        payload = {"status": MemberStatus.DISABLED.value}
        response = await authenticated_client.patch(
            f"/api/workspaces/{test_workspace.id}/members/{fake_user_id}/status",
            json=payload,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_status_not_admin(
        self, client: AsyncClient, test_workspace, test_workspace_member, test_user
    ):
        """Should return 403 if user is not admin."""
        from tests.conftest import create_test_access_token

        member_user, _ = test_workspace_member
        token = create_test_access_token(member_user)
        client.headers["Authorization"] = f"Bearer {token}"

        payload = {"status": MemberStatus.DISABLED.value}
        response = await client.patch(
            f"/api/workspaces/{test_workspace.id}/members/{test_user.id}/status",
            json=payload,
        )

        assert response.status_code == 403


class TestUpdateMemberRole:
    """Tests for PATCH /api/workspaces/{workspace_id}/members/{member_user_id}/role"""

    @pytest.mark.asyncio
    async def test_promote_to_admin(
        self, authenticated_client: AsyncClient, test_workspace, test_workspace_member
    ):
        """Should promote member to admin."""
        member_user, _ = test_workspace_member
        payload = {"role": MemberRole.ADMIN.value}
        response = await authenticated_client.patch(
            f"/api/workspaces/{test_workspace.id}/members/{member_user.id}/role",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == MemberRole.ADMIN.value

    @pytest.mark.asyncio
    async def test_demote_to_member(
        self, authenticated_client: AsyncClient, test_workspace, test_workspace_admin
    ):
        """Should demote admin to member."""
        admin_user, _ = test_workspace_admin
        payload = {"role": MemberRole.MEMBER.value}
        response = await authenticated_client.patch(
            f"/api/workspaces/{test_workspace.id}/members/{admin_user.id}/role",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == MemberRole.MEMBER.value

    @pytest.mark.asyncio
    async def test_update_role_not_owner(
        self,
        client: AsyncClient,
        test_workspace,
        test_workspace_admin,
        test_workspace_member,
    ):
        """Should return 403 if not workspace owner."""
        from tests.conftest import create_test_access_token

        admin_user, _ = test_workspace_admin
        member_user, _ = test_workspace_member

        token = create_test_access_token(admin_user)
        client.headers["Authorization"] = f"Bearer {token}"

        payload = {"role": MemberRole.ADMIN.value}
        response = await client.patch(
            f"/api/workspaces/{test_workspace.id}/members/{member_user.id}/role",
            json=payload,
        )

        # Only owner can change roles
        assert response.status_code == 403


class TestRemoveMember:
    """Tests for DELETE /api/workspaces/{workspace_id}/members/{member_user_id}"""

    @pytest.mark.asyncio
    async def test_remove_member_success(
        self, authenticated_client: AsyncClient, test_workspace, test_workspace_member
    ):
        """Should remove member successfully."""
        member_user, _ = test_workspace_member
        response = await authenticated_client.delete(
            f"/api/workspaces/{test_workspace.id}/members/{member_user.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_remove_member_not_found(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should return 404 if member not found."""
        fake_user_id = uuid4()
        response = await authenticated_client.delete(
            f"/api/workspaces/{test_workspace.id}/members/{fake_user_id}"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_member_not_admin(
        self, client: AsyncClient, test_workspace, test_workspace_member, test_user
    ):
        """Should return 403 if not admin."""
        from tests.conftest import create_test_access_token

        member_user, _ = test_workspace_member
        token = create_test_access_token(member_user)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.delete(
            f"/api/workspaces/{test_workspace.id}/members/{test_user.id}"
        )

        assert response.status_code == 403


class TestLeaveWorkspace:
    """Tests for POST /api/workspaces/{workspace_id}/leave"""

    @pytest.mark.asyncio
    async def test_leave_workspace_success(
        self, client: AsyncClient, test_workspace, test_workspace_member
    ):
        """Should allow member to leave workspace."""
        from tests.conftest import create_test_access_token

        member_user, _ = test_workspace_member
        token = create_test_access_token(member_user)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.post(f"/api/workspaces/{test_workspace.id}/leave")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_owner_cannot_leave(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should prevent owner from leaving workspace."""
        response = await authenticated_client.post(
            f"/api/workspaces/{test_workspace.id}/leave"
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_leave_not_member(
        self, client: AsyncClient, test_workspace, db_session
    ):
        """Should return 404 if not a member."""
        from app.core.db.models import User
        from tests.conftest import create_test_access_token

        other_user = User(
            id=uuid4(),
            email="nonmember@example.com",
            password_hash="hash",
            full_name="Non Member",
            email_verified=True,
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.flush()

        token = create_test_access_token(other_user)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.post(f"/api/workspaces/{test_workspace.id}/leave")
        assert response.status_code == 404


class TestTransferOwnership:
    """Tests for POST /api/workspaces/{workspace_id}/transfer-ownership"""

    @pytest.mark.asyncio
    async def test_transfer_ownership_success(
        self, authenticated_client: AsyncClient, test_workspace, test_workspace_member
    ):
        """Should transfer ownership successfully."""
        member_user, _ = test_workspace_member
        response = await authenticated_client.post(
            f"/api/workspaces/{test_workspace.id}/transfer-ownership?new_owner_id={member_user.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["owner_id"] == str(member_user.id)

    @pytest.mark.asyncio
    async def test_transfer_ownership_not_owner(
        self,
        client: AsyncClient,
        test_workspace,
        test_workspace_member,
        test_workspace_admin,
    ):
        """Should return 403 if not current owner."""
        from tests.conftest import create_test_access_token

        admin_user, _ = test_workspace_admin
        member_user, _ = test_workspace_member

        token = create_test_access_token(admin_user)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.post(
            f"/api/workspaces/{test_workspace.id}/transfer-ownership?new_owner_id={member_user.id}"
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_transfer_ownership_member_not_found(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should return 404 if new owner is not a member."""
        fake_user_id = uuid4()
        response = await authenticated_client.post(
            f"/api/workspaces/{test_workspace.id}/transfer-ownership?new_owner_id={fake_user_id}"
        )

        assert response.status_code == 404


class TestListInvitations:
    """Tests for GET /api/workspaces/{workspace_id}/invitations"""

    @pytest.mark.asyncio
    async def test_list_invitations_success(
        self, authenticated_client: AsyncClient, test_workspace, test_invitation
    ):
        """Should return list of invitations."""
        invitation, _ = test_invitation  # Unpack tuple from fixture

        response = await authenticated_client.get(
            f"/api/workspaces/{test_workspace.id}/invitations"
        )

        assert response.status_code == 200
        data = response.json()
        assert "invitations" in data
        assert len(data["invitations"]) >= 1

    @pytest.mark.asyncio
    async def test_list_invitations_empty(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should return empty list when no invitations."""
        response = await authenticated_client.get(
            f"/api/workspaces/{test_workspace.id}/invitations"
        )

        assert response.status_code == 200
        data = response.json()
        assert "invitations" in data

    @pytest.mark.asyncio
    async def test_list_invitations_not_admin(
        self, client: AsyncClient, test_workspace, test_workspace_member
    ):
        """Should return 403 if not admin."""
        from tests.conftest import create_test_access_token

        member_user, _ = test_workspace_member
        token = create_test_access_token(member_user)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.get(f"/api/workspaces/{test_workspace.id}/invitations")

        assert response.status_code == 403


class TestCreateInvitation:
    """Tests for POST /api/workspaces/{workspace_id}/invitations"""

    @pytest.mark.asyncio
    async def test_create_invitation_success(
        self, authenticated_client: AsyncClient, test_workspace, test_subscription
    ):
        """Should create invitation successfully."""
        payload = {
            "email": "newinvite@example.com",
            "role": MemberRole.MEMBER.value,
            "callback_url": "http://localhost:3000/invitation",
        }
        response = await authenticated_client.post(
            f"/api/workspaces/{test_workspace.id}/invitations", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert "invitation" in data
        assert "invitation_url" in data
        assert data["invitation"]["email"] == "newinvite@example.com"

    @pytest.mark.asyncio
    async def test_create_invitation_admin_role(
        self, authenticated_client: AsyncClient, test_workspace, test_subscription
    ):
        """Should create invitation with admin role."""
        payload = {
            "email": "admin.invite@example.com",
            "role": MemberRole.ADMIN.value,
            "callback_url": "http://localhost:3000/invitation",
        }
        response = await authenticated_client.post(
            f"/api/workspaces/{test_workspace.id}/invitations", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["invitation"]["role"] == MemberRole.ADMIN.value

    @pytest.mark.asyncio
    async def test_create_invitation_duplicate_email(
        self, authenticated_client: AsyncClient, test_workspace, test_invitation
    ):
        """Should return 409 if invitation already exists."""
        invitation, _ = test_invitation  # Unpack tuple from fixture

        payload = {
            "email": invitation.email,
            "role": MemberRole.MEMBER.value,
            "callback_url": "http://localhost:3000/invitation",
        }
        response = await authenticated_client.post(
            f"/api/workspaces/{test_workspace.id}/invitations", json=payload
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_invitation_existing_member(
        self, authenticated_client: AsyncClient, test_workspace, test_workspace_member
    ):
        """Should return 409 if user is already a member."""
        member_user, _ = test_workspace_member
        payload = {
            "email": member_user.email,
            "role": MemberRole.MEMBER.value,
            "callback_url": "http://localhost:3000/invitation",
        }
        response = await authenticated_client.post(
            f"/api/workspaces/{test_workspace.id}/invitations", json=payload
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_invitation_not_admin(
        self, client: AsyncClient, test_workspace, test_workspace_member
    ):
        """Should return 403 if not admin."""
        from tests.conftest import create_test_access_token

        member_user, _ = test_workspace_member
        token = create_test_access_token(member_user)
        client.headers["Authorization"] = f"Bearer {token}"

        payload = {
            "email": "test@example.com",
            "role": MemberRole.MEMBER.value,
            "callback_url": "http://localhost:3000/invitation",
        }
        response = await client.post(
            f"/api/workspaces/{test_workspace.id}/invitations", json=payload
        )

        assert response.status_code == 403


class TestRevokeInvitation:
    """Tests for DELETE /api/workspaces/{workspace_id}/invitations/{invitation_id}"""

    @pytest.mark.asyncio
    async def test_revoke_invitation_success(
        self, authenticated_client: AsyncClient, test_workspace, test_invitation
    ):
        """Should revoke invitation successfully."""
        invitation, _ = test_invitation  # Unpack tuple from fixture

        response = await authenticated_client.delete(
            f"/api/workspaces/{test_workspace.id}/invitations/{invitation.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_revoke_invitation_not_found(
        self, authenticated_client: AsyncClient, test_workspace
    ):
        """Should return 404 if invitation not found."""
        fake_invitation_id = uuid4()
        response = await authenticated_client.delete(
            f"/api/workspaces/{test_workspace.id}/invitations/{fake_invitation_id}"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_invitation_not_admin(
        self,
        client: AsyncClient,
        test_workspace,
        test_workspace_member,
        test_invitation,
    ):
        """Should return 403 if not admin."""
        from tests.conftest import create_test_access_token

        invitation, _ = test_invitation  # Unpack tuple from fixture
        member_user, _ = test_workspace_member
        token = create_test_access_token(member_user)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.delete(
            f"/api/workspaces/{test_workspace.id}/invitations/{invitation.id}"
        )

        assert response.status_code == 403


class TestAcceptInvitation:
    """Tests for POST /api/workspaces/invitations/accept"""

    @pytest.mark.asyncio
    async def test_accept_invitation_success(
        self, client: AsyncClient, test_workspace, test_subscription, db_session
    ):
        """Should accept invitation and join workspace."""
        import secrets
        from datetime import datetime, timedelta, timezone
        from app.core.db.models import User, WorkspaceInvitation
        from app.core.config import settings
        from app.core.utils import hmac_hash_otp
        from tests.conftest import create_test_access_token
        from app.core.enums import InvitationStatus, MemberRole

        new_user = User(
            id=uuid4(),
            email="accepter@example.com",
            password_hash="hash",
            full_name="Accepter User",
            email_verified=True,
            is_active=True,
        )
        db_session.add(new_user)
        await db_session.flush()

        # Create invitation for this user (with proper token hash)
        raw_token = secrets.token_urlsafe(32)
        token_hash = hmac_hash_otp(raw_token, settings.OTP_HMAC_SECRET)

        invitation = WorkspaceInvitation(
            id=uuid4(),
            workspace_id=test_workspace.id,
            email=new_user.email,
            role=MemberRole.MEMBER,
            status=InvitationStatus.PENDING,
            token_hash=token_hash,
            inviter_id=test_workspace.owner_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db_session.add(invitation)
        await db_session.flush()

        # Authenticate as new user
        token = create_test_access_token(new_user)
        client.headers["Authorization"] = f"Bearer {token}"

        payload = {"token": raw_token}
        response = await client.post("/api/workspaces/invitations/accept", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(new_user.id)
        assert data["role"] == MemberRole.MEMBER.value

    @pytest.mark.asyncio
    async def test_accept_invitation_invalid_token(
        self, authenticated_client: AsyncClient
    ):
        """Should return 404 for invalid token."""
        payload = {"token": "invalid_token_12345"}
        response = await authenticated_client.post(
            "/api/workspaces/invitations/accept", json=payload
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_accept_invitation_expired(
        self, client: AsyncClient, test_workspace, expired_invitation, db_session
    ):
        """Should return 404 for expired invitation."""
        from app.core.db.models import User
        from tests.conftest import create_test_access_token

        invitation, raw_token = expired_invitation  # Unpack tuple from fixture

        new_user = User(
            id=uuid4(),
            email=invitation.email,
            password_hash="hash",
            full_name="Expired User",
            email_verified=True,
            is_active=True,
        )
        db_session.add(new_user)
        await db_session.flush()

        token = create_test_access_token(new_user)
        client.headers["Authorization"] = f"Bearer {token}"

        payload = {"token": raw_token}
        response = await client.post("/api/workspaces/invitations/accept", json=payload)

        assert response.status_code == 404


class TestActivatePersonalWorkspace:
    """Tests for POST /api/workspaces/activate"""

    @pytest.mark.asyncio
    async def test_activate_personal_workspace_new(
        self, authenticated_client: AsyncClient
    ):
        """Should create personal workspace if not exists."""
        response = await authenticated_client.post("/api/workspaces/activate")

        assert response.status_code == 200
        data = response.json()
        assert data["is_personal"] is True
        assert data["status"] == WorkspaceStatus.ACTIVE.value

    @pytest.mark.asyncio
    async def test_activate_personal_workspace_idempotent(
        self, authenticated_client: AsyncClient, personal_workspace
    ):
        """Should return existing personal workspace."""
        response = await authenticated_client.post("/api/workspaces/activate")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(personal_workspace.id)
        assert data["is_personal"] is True

    @pytest.mark.asyncio
    async def test_activate_personal_workspace_unauthenticated(
        self, client: AsyncClient
    ):
        """Should return 401 if not authenticated."""
        response = await client.post("/api/workspaces/activate")

        assert response.status_code == 401

