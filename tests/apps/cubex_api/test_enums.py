"""
Test suite for Workspace models and enums.

This module tests workspace-related enums and Pydantic validators.
"""

from app.shared.enums import (
    APIPlanName,
    CareerPlanName,
    PlanType,
    ProductType,
    SubscriptionStatus,
    WorkspaceStatus,
    MemberStatus,
    MemberRole,
    InvitationStatus,
)


class TestPlanType:
    """Test suite for PlanType enum."""

    def test_plan_type_values(self):
        """Test that PlanType has expected values."""
        assert PlanType.FREE.value == "free"
        assert PlanType.PAID.value == "paid"

    def test_plan_type_iteration(self):
        """Test that all plan types can be iterated."""
        plan_types = list(PlanType)
        assert len(plan_types) == 2

    def test_plan_type_from_value(self):
        """Test creating PlanType from string value."""
        assert PlanType("free") == PlanType.FREE
        assert PlanType("paid") == PlanType.PAID


class TestSubscriptionStatus:
    """Test suite for SubscriptionStatus enum."""

    def test_subscription_status_values(self):
        """Test that SubscriptionStatus has expected values."""
        assert SubscriptionStatus.ACTIVE.value == "active"
        assert SubscriptionStatus.PAST_DUE.value == "past_due"
        assert SubscriptionStatus.CANCELED.value == "canceled"
        assert SubscriptionStatus.INCOMPLETE.value == "incomplete"
        assert SubscriptionStatus.INCOMPLETE_EXPIRED.value == "incomplete_expired"
        assert SubscriptionStatus.TRIALING.value == "trialing"
        assert SubscriptionStatus.UNPAID.value == "unpaid"
        assert SubscriptionStatus.PAUSED.value == "paused"

    def test_subscription_status_from_value(self):
        """Test creating SubscriptionStatus from string value."""
        assert SubscriptionStatus("active") == SubscriptionStatus.ACTIVE
        assert SubscriptionStatus("canceled") == SubscriptionStatus.CANCELED


class TestWorkspaceStatus:
    """Test suite for WorkspaceStatus enum."""

    def test_workspace_status_values(self):
        """Test that WorkspaceStatus has expected values."""
        assert WorkspaceStatus.ACTIVE.value == "active"
        assert WorkspaceStatus.FROZEN.value == "frozen"
        assert WorkspaceStatus.SUSPENDED.value == "suspended"

    def test_workspace_status_from_value(self):
        """Test creating WorkspaceStatus from string value."""
        assert WorkspaceStatus("active") == WorkspaceStatus.ACTIVE
        assert WorkspaceStatus("frozen") == WorkspaceStatus.FROZEN


class TestMemberStatus:
    """Test suite for MemberStatus enum."""

    def test_member_status_values(self):
        """Test that MemberStatus has expected values."""
        assert MemberStatus.ENABLED.value == "enabled"
        assert MemberStatus.DISABLED.value == "disabled"

    def test_member_status_from_value(self):
        """Test creating MemberStatus from string value."""
        assert MemberStatus("enabled") == MemberStatus.ENABLED
        assert MemberStatus("disabled") == MemberStatus.DISABLED


class TestMemberRole:
    """Test suite for MemberRole enum."""

    def test_member_role_values(self):
        """Test that MemberRole has expected values."""
        assert MemberRole.OWNER.value == "owner"
        assert MemberRole.ADMIN.value == "admin"
        assert MemberRole.MEMBER.value == "member"

    def test_member_role_from_value(self):
        """Test creating MemberRole from string value."""
        assert MemberRole("owner") == MemberRole.OWNER
        assert MemberRole("admin") == MemberRole.ADMIN
        assert MemberRole("member") == MemberRole.MEMBER


class TestInvitationStatus:
    """Test suite for InvitationStatus enum."""

    def test_invitation_status_values(self):
        """Test that InvitationStatus has expected values."""
        assert InvitationStatus.PENDING.value == "pending"
        assert InvitationStatus.ACCEPTED.value == "accepted"
        assert InvitationStatus.EXPIRED.value == "expired"
        assert InvitationStatus.REVOKED.value == "revoked"

    def test_invitation_status_from_value(self):
        """Test creating InvitationStatus from string value."""
        assert InvitationStatus("pending") == InvitationStatus.PENDING
        assert InvitationStatus("accepted") == InvitationStatus.ACCEPTED


class TestProductType:
    """Test suite for ProductType enum."""

    def test_product_type_values(self):
        """Test that ProductType has expected values."""
        assert ProductType.API.value == "api"
        assert ProductType.CAREER.value == "career"

    def test_product_type_iteration(self):
        """Test that all product types can be iterated."""
        product_types = list(ProductType)
        assert len(product_types) == 2

    def test_product_type_from_value(self):
        """Test creating ProductType from string value."""
        assert ProductType("api") == ProductType.API
        assert ProductType("career") == ProductType.CAREER

    def test_product_type_api_is_default(self):
        """Test that API is the first/default product type."""
        # API should be the default for existing subscriptions
        product_types = list(ProductType)
        assert product_types[0] == ProductType.API


class TestAPIPlanName:
    """Test suite for APIPlanName enum."""

    def test_api_plan_name_values(self):
        """Test that APIPlanName has expected values."""
        assert APIPlanName.FREE.value == "Free"
        assert APIPlanName.BASIC.value == "Basic"
        assert APIPlanName.PROFESSIONAL.value == "Professional"

    def test_api_plan_name_iteration(self):
        """Test that all API plan names can be iterated."""
        plan_names = list(APIPlanName)
        assert len(plan_names) == 3

    def test_api_plan_name_from_value(self):
        """Test creating APIPlanName from string value."""
        assert APIPlanName("Free") == APIPlanName.FREE
        assert APIPlanName("Basic") == APIPlanName.BASIC
        assert APIPlanName("Professional") == APIPlanName.PROFESSIONAL


class TestCareerPlanName:
    """Test suite for CareerPlanName enum."""

    def test_career_plan_name_values(self):
        """Test that CareerPlanName has expected values."""
        assert CareerPlanName.FREE.value == "Free"
        assert CareerPlanName.PLUS.value == "Plus Plan"
        assert CareerPlanName.PRO.value == "Pro Plan"

    def test_career_plan_name_iteration(self):
        """Test that all Career plan names can be iterated."""
        plan_names = list(CareerPlanName)
        assert len(plan_names) == 3

    def test_career_plan_name_from_value(self):
        """Test creating CareerPlanName from string value."""
        assert CareerPlanName("Free") == CareerPlanName.FREE
        assert CareerPlanName("Plus Plan") == CareerPlanName.PLUS
        assert CareerPlanName("Pro Plan") == CareerPlanName.PRO
