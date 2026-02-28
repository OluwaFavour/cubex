"""
Test suite for Workspace models and enums.

This module tests workspace-related enums and Pydantic validators.
"""

from app.core.enums import (
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

    def test_plan_type_values(self):
        assert PlanType.FREE.value == "free"
        assert PlanType.PAID.value == "paid"

    def test_plan_type_iteration(self):
        plan_types = list(PlanType)
        assert len(plan_types) == 2

    def test_plan_type_from_value(self):
        assert PlanType("free") == PlanType.FREE
        assert PlanType("paid") == PlanType.PAID


class TestSubscriptionStatus:

    def test_subscription_status_values(self):
        assert SubscriptionStatus.ACTIVE.value == "active"
        assert SubscriptionStatus.PAST_DUE.value == "past_due"
        assert SubscriptionStatus.CANCELED.value == "canceled"
        assert SubscriptionStatus.INCOMPLETE.value == "incomplete"
        assert SubscriptionStatus.INCOMPLETE_EXPIRED.value == "incomplete_expired"
        assert SubscriptionStatus.TRIALING.value == "trialing"
        assert SubscriptionStatus.UNPAID.value == "unpaid"
        assert SubscriptionStatus.PAUSED.value == "paused"

    def test_subscription_status_from_value(self):
        assert SubscriptionStatus("active") == SubscriptionStatus.ACTIVE
        assert SubscriptionStatus("canceled") == SubscriptionStatus.CANCELED


class TestWorkspaceStatus:

    def test_workspace_status_values(self):
        assert WorkspaceStatus.ACTIVE.value == "active"
        assert WorkspaceStatus.FROZEN.value == "frozen"
        assert WorkspaceStatus.SUSPENDED.value == "suspended"

    def test_workspace_status_from_value(self):
        assert WorkspaceStatus("active") == WorkspaceStatus.ACTIVE
        assert WorkspaceStatus("frozen") == WorkspaceStatus.FROZEN


class TestMemberStatus:

    def test_member_status_values(self):
        assert MemberStatus.ENABLED.value == "enabled"
        assert MemberStatus.DISABLED.value == "disabled"

    def test_member_status_from_value(self):
        assert MemberStatus("enabled") == MemberStatus.ENABLED
        assert MemberStatus("disabled") == MemberStatus.DISABLED


class TestMemberRole:

    def test_member_role_values(self):
        assert MemberRole.OWNER.value == "owner"
        assert MemberRole.ADMIN.value == "admin"
        assert MemberRole.MEMBER.value == "member"

    def test_member_role_from_value(self):
        assert MemberRole("owner") == MemberRole.OWNER
        assert MemberRole("admin") == MemberRole.ADMIN
        assert MemberRole("member") == MemberRole.MEMBER


class TestInvitationStatus:

    def test_invitation_status_values(self):
        assert InvitationStatus.PENDING.value == "pending"
        assert InvitationStatus.ACCEPTED.value == "accepted"
        assert InvitationStatus.EXPIRED.value == "expired"
        assert InvitationStatus.REVOKED.value == "revoked"

    def test_invitation_status_from_value(self):
        assert InvitationStatus("pending") == InvitationStatus.PENDING
        assert InvitationStatus("accepted") == InvitationStatus.ACCEPTED


class TestProductType:

    def test_product_type_values(self):
        assert ProductType.API.value == "api"
        assert ProductType.CAREER.value == "career"

    def test_product_type_iteration(self):
        product_types = list(ProductType)
        assert len(product_types) == 2

    def test_product_type_from_value(self):
        assert ProductType("api") == ProductType.API
        assert ProductType("career") == ProductType.CAREER

    def test_product_type_api_is_default(self):
        # API should be the default for existing subscriptions
        product_types = list(ProductType)
        assert product_types[0] == ProductType.API


class TestAPIPlanName:

    def test_api_plan_name_values(self):
        assert APIPlanName.FREE.value == "Free"
        assert APIPlanName.BASIC.value == "Basic"
        assert APIPlanName.PROFESSIONAL.value == "Professional"

    def test_api_plan_name_iteration(self):
        plan_names = list(APIPlanName)
        assert len(plan_names) == 3

    def test_api_plan_name_from_value(self):
        assert APIPlanName("Free") == APIPlanName.FREE
        assert APIPlanName("Basic") == APIPlanName.BASIC
        assert APIPlanName("Professional") == APIPlanName.PROFESSIONAL


class TestCareerPlanName:

    def test_career_plan_name_values(self):
        assert CareerPlanName.FREE.value == "Free"
        assert CareerPlanName.PLUS.value == "Plus Plan"
        assert CareerPlanName.PRO.value == "Pro Plan"

    def test_career_plan_name_iteration(self):
        plan_names = list(CareerPlanName)
        assert len(plan_names) == 3

    def test_career_plan_name_from_value(self):
        assert CareerPlanName("Free") == CareerPlanName.FREE
        assert CareerPlanName("Plus Plan") == CareerPlanName.PLUS
        assert CareerPlanName("Pro Plan") == CareerPlanName.PRO
