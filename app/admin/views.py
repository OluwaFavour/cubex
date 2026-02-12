"""
SQLAdmin model views for Cubex.

Defines admin views for managing application models:
- PlanAdmin: Full CRUD for subscription plans
- EndpointCostConfigAdmin: Manage API endpoint pricing
- PlanPricingRuleAdmin: Manage plan multipliers and rate limits
- UserAdmin: Read-only user view
- WorkspaceAdmin: Read-only workspace view
- SubscriptionAdmin: View/edit subscriptions
"""

from sqladmin import ModelView
from sqladmin.filters import BooleanFilter, StaticValuesFilter

from app.apps.cubex_api.db.models.quota import EndpointCostConfig, PlanPricingRule
from app.apps.cubex_api.db.models.workspace import Workspace, WorkspaceMember
from app.shared.db.models.plan import Plan
from app.shared.db.models.subscription import Subscription
from app.shared.db.models.user import User
from app.shared.enums import (
    MemberRole,
    MemberStatus,
    PlanType,
    ProductType,
    SubscriptionStatus,
    WorkspaceStatus,
)


# ============================================================================
# Plan Management
# ============================================================================


class PlanAdmin(ModelView, model=Plan):
    """Admin view for subscription plans."""

    name = "Plan"
    name_plural = "Plans"
    icon = "fa-solid fa-tags"

    # List view configuration
    column_list = [
        Plan.id,
        Plan.name,
        Plan.type,
        Plan.product_type,
        Plan.price,
        Plan.seat_price,
        Plan.is_active,
        Plan.max_seats,
        Plan.min_seats,
        Plan.created_at,
    ]

    column_searchable_list = ["name", "description"]
    column_sortable_list = [
        Plan.name,
        Plan.price,
        Plan.is_active,
        Plan.type,
        Plan.product_type,
        Plan.created_at,
    ]
    column_default_sort = [(Plan.created_at, True)]

    # Filters
    column_filters = [
        StaticValuesFilter(
            Plan.type,
            values=[(e.value, e.value.title()) for e in PlanType],
            title="Plan Type",
        ),
        StaticValuesFilter(
            Plan.product_type,
            values=[(e.value, e.value.upper()) for e in ProductType],
            title="Product",
        ),
        BooleanFilter(Plan.is_active, title="Active"),
    ]

    # Form configuration
    form_columns = [
        Plan.name,
        Plan.description,
        Plan.type,
        Plan.product_type,
        Plan.price,
        Plan.display_price,
        Plan.stripe_price_id,
        Plan.seat_price,
        Plan.seat_display_price,
        Plan.seat_stripe_price_id,
        Plan.is_active,
        Plan.trial_days,
        Plan.features,
        Plan.max_seats,
        Plan.min_seats,
    ]

    # Detail view
    column_details_list = [
        Plan.id,
        Plan.name,
        Plan.description,
        Plan.type,
        Plan.product_type,
        Plan.price,
        Plan.display_price,
        Plan.stripe_price_id,
        Plan.seat_price,
        Plan.seat_display_price,
        Plan.seat_stripe_price_id,
        Plan.is_active,
        Plan.trial_days,
        Plan.features,
        Plan.max_seats,
        Plan.min_seats,
        Plan.created_at,
        Plan.updated_at,
    ]

    # Labels
    column_labels = {
        Plan.id: "ID",
        Plan.name: "Plan Name",
        Plan.description: "Description",
        Plan.type: "Plan Type",
        Plan.product_type: "Product",
        Plan.price: "Base Price ($)",
        Plan.display_price: "Display Price",
        Plan.stripe_price_id: "Stripe Price ID",
        Plan.seat_price: "Seat Price ($)",
        Plan.seat_display_price: "Seat Display Price",
        Plan.seat_stripe_price_id: "Stripe Seat Price ID",
        Plan.is_active: "Active",
        Plan.trial_days: "Trial Days",
        Plan.features: "Features (JSON)",
        Plan.max_seats: "Max Seats",
        Plan.min_seats: "Min Seats",
        Plan.created_at: "Created",
        Plan.updated_at: "Updated",
    }

    # Formatting
    column_formatters = {
        Plan.price: lambda m, a: f"${m.price:.2f}",
        Plan.seat_price: lambda m, a: f"${m.seat_price:.2f}",
    }

    # Permissions - Plans are immutable except for is_active
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True

    # Only allow editing is_active field (to deactivate plans)
    form_edit_rules = ["is_active"]


# ============================================================================
# Quota Configuration
# ============================================================================


class EndpointCostConfigAdmin(ModelView, model=EndpointCostConfig):
    """Admin view for API endpoint pricing configuration."""

    name = "Endpoint Cost"
    name_plural = "Endpoint Costs"
    icon = "fa-solid fa-server"

    column_list = [
        EndpointCostConfig.id,
        EndpointCostConfig.endpoint,
        EndpointCostConfig.internal_cost_credits,
        EndpointCostConfig.created_at,
        EndpointCostConfig.updated_at,
    ]

    column_searchable_list = ["endpoint"]
    column_sortable_list = [
        EndpointCostConfig.endpoint,
        EndpointCostConfig.internal_cost_credits,
        EndpointCostConfig.created_at,
    ]
    column_default_sort = [(EndpointCostConfig.endpoint, False)]

    form_columns = [
        EndpointCostConfig.endpoint,
        EndpointCostConfig.internal_cost_credits,
    ]

    column_labels = {
        EndpointCostConfig.id: "ID",
        EndpointCostConfig.endpoint: "Endpoint Path",
        EndpointCostConfig.internal_cost_credits: "Cost (Credits)",
        EndpointCostConfig.created_at: "Created",
        EndpointCostConfig.updated_at: "Updated",
    }

    column_formatters = {
        EndpointCostConfig.internal_cost_credits: lambda m, a: f"{m.internal_cost_credits:.4f}",
    }

    form_args = {
        "endpoint": {
            "description": "API endpoint path (e.g., /v1/extract-cues/resume). "
            "Will be normalized to lowercase.",
        },
        "internal_cost_credits": {
            "description": "Internal credit cost for calling this endpoint. "
            "Default is 1.0 credit per call.",
        },
    }

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True


class PlanPricingRuleAdmin(ModelView, model=PlanPricingRule):
    """Admin view for plan pricing rules (multipliers, credits, rate limits)."""

    name = "Plan Pricing Rule"
    name_plural = "Plan Pricing Rules"
    icon = "fa-solid fa-calculator"

    column_list = [
        PlanPricingRule.id,
        PlanPricingRule.plan_id,
        PlanPricingRule.multiplier,
        PlanPricingRule.credits_allocation,
        PlanPricingRule.rate_limit_per_minute,
        PlanPricingRule.created_at,
    ]

    column_sortable_list = [
        PlanPricingRule.multiplier,
        PlanPricingRule.credits_allocation,
        PlanPricingRule.rate_limit_per_minute,
        PlanPricingRule.created_at,
    ]

    form_columns = [
        PlanPricingRule.plan_id,
        PlanPricingRule.multiplier,
        PlanPricingRule.credits_allocation,
        PlanPricingRule.rate_limit_per_minute,
    ]

    column_labels = {
        PlanPricingRule.id: "ID",
        PlanPricingRule.plan_id: "Plan",
        PlanPricingRule.multiplier: "Price Multiplier",
        PlanPricingRule.credits_allocation: "Credits Allocation",
        PlanPricingRule.rate_limit_per_minute: "Rate Limit/min",
        PlanPricingRule.created_at: "Created",
    }

    column_formatters = {
        PlanPricingRule.multiplier: lambda m, a: f"{m.multiplier:.4f}x",
        PlanPricingRule.credits_allocation: lambda m, a: f"{m.credits_allocation:.0f}",
    }

    form_args = {
        "multiplier": {
            "description": "Pricing multiplier (1.0 = standard rate, 0.8 = 20% discount)",
        },
        "credits_allocation": {
            "description": "Total credits allocated to workspaces on this plan per billing period",
        },
        "rate_limit_per_minute": {
            "description": "Maximum API requests allowed per minute",
        },
    }

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True


# ============================================================================
# User Management (Read-Only)
# ============================================================================


class UserAdmin(ModelView, model=User):
    """Admin view for users (read-only)."""

    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-users"

    column_list = [
        User.id,
        User.email,
        User.full_name,
        User.is_active,
        User.email_verified,
        User.stripe_customer_id,
        User.created_at,
    ]

    column_searchable_list = ["email", "full_name"]
    column_sortable_list = [
        User.email,
        User.full_name,
        User.is_active,
        User.email_verified,
        User.created_at,
    ]
    column_default_sort = [(User.created_at, True)]

    column_filters = [
        BooleanFilter(User.is_active, title="Active"),
        BooleanFilter(User.email_verified, title="Email Verified"),
    ]

    column_labels = {
        User.id: "ID",
        User.email: "Email",
        User.full_name: "Full Name",
        User.is_active: "Active",
        User.email_verified: "Email Verified",
        User.stripe_customer_id: "Stripe Customer",
        User.created_at: "Created",
    }

    # Read-only - disable create/edit/delete
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
    can_export = True


# ============================================================================
# Workspace Management (Read-Only)
# ============================================================================


class WorkspaceAdmin(ModelView, model=Workspace):
    """Admin view for workspaces (read-only)."""

    name = "Workspace"
    name_plural = "Workspaces"
    icon = "fa-solid fa-building"

    column_list = [
        Workspace.id,
        Workspace.display_name,
        Workspace.status,
        Workspace.owner_id,
        Workspace.created_at,
    ]

    column_searchable_list = ["display_name"]
    column_sortable_list = [
        Workspace.display_name,
        Workspace.status,
        Workspace.created_at,
    ]
    column_default_sort = [(Workspace.created_at, True)]

    column_filters = [
        StaticValuesFilter(
            Workspace.status,
            values=[(e.value, e.value.title()) for e in WorkspaceStatus],
            title="Status",
        ),
    ]

    column_labels = {
        Workspace.id: "ID",
        Workspace.display_name: "Name",
        Workspace.status: "Status",
        Workspace.owner_id: "Owner",
        Workspace.created_at: "Created",
    }

    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
    can_export = True


class WorkspaceMemberAdmin(ModelView, model=WorkspaceMember):
    """Admin view for workspace members (read-only)."""

    name = "Workspace Member"
    name_plural = "Workspace Members"
    icon = "fa-solid fa-user-group"

    column_list = [
        WorkspaceMember.id,
        WorkspaceMember.workspace_id,
        WorkspaceMember.user_id,
        WorkspaceMember.role,
        WorkspaceMember.status,
        WorkspaceMember.created_at,
    ]

    column_sortable_list = [
        WorkspaceMember.role,
        WorkspaceMember.status,
        WorkspaceMember.created_at,
    ]

    column_filters = [
        StaticValuesFilter(
            WorkspaceMember.role,
            values=[(e.value, e.value.title()) for e in MemberRole],
            title="Role",
        ),
        StaticValuesFilter(
            WorkspaceMember.status,
            values=[(e.value, e.value.title()) for e in MemberStatus],
            title="Status",
        ),
    ]

    column_labels = {
        WorkspaceMember.id: "ID",
        WorkspaceMember.workspace_id: "Workspace",
        WorkspaceMember.user_id: "User",
        WorkspaceMember.role: "Role",
        WorkspaceMember.status: "Status",
        WorkspaceMember.created_at: "Joined",
    }

    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
    can_export = True


# ============================================================================
# Subscription Management
# ============================================================================


class SubscriptionAdmin(ModelView, model=Subscription):
    """Admin view for subscriptions."""

    name = "Subscription"
    name_plural = "Subscriptions"
    icon = "fa-solid fa-credit-card"

    column_list = [
        Subscription.id,
        Subscription.plan_id,
        Subscription.status,
        Subscription.product_type,
        Subscription.seat_count,
        Subscription.current_period_start,
        Subscription.current_period_end,
        Subscription.cancel_at_period_end,
        Subscription.created_at,
    ]

    column_searchable_list = ["stripe_subscription_id"]
    column_sortable_list = [
        Subscription.status,
        Subscription.product_type,
        Subscription.seat_count,
        Subscription.current_period_start,
        Subscription.current_period_end,
        Subscription.created_at,
    ]
    column_default_sort = [(Subscription.created_at, True)]

    column_filters = [
        StaticValuesFilter(
            Subscription.status,
            values=[(e.value, e.value.replace("_", " ").title()) for e in SubscriptionStatus],
            title="Status",
        ),
        StaticValuesFilter(
            Subscription.product_type,
            values=[(e.value, e.value.upper()) for e in ProductType],
            title="Product",
        ),
        BooleanFilter(Subscription.cancel_at_period_end, title="Cancel at End"),
    ]

    # Allow editing status and cancel_at_period_end only
    form_columns = [
        Subscription.status,
        Subscription.seat_count,
        Subscription.cancel_at_period_end,
    ]

    column_labels = {
        Subscription.id: "ID",
        Subscription.plan_id: "Plan",
        Subscription.status: "Status",
        Subscription.product_type: "Product",
        Subscription.seat_count: "Seats",
        Subscription.current_period_start: "Period Start",
        Subscription.current_period_end: "Period End",
        Subscription.cancel_at_period_end: "Cancel at End",
        Subscription.stripe_subscription_id: "Stripe ID",
        Subscription.created_at: "Created",
    }

    can_create = False  # Subscriptions created via checkout
    can_edit = True  # Allow status/seat updates
    can_delete = False  # Don't allow deletion
    can_view_details = True
    can_export = True


# Export all admin views
__all__ = [
    "PlanAdmin",
    "EndpointCostConfigAdmin",
    "PlanPricingRuleAdmin",
    "UserAdmin",
    "WorkspaceAdmin",
    "WorkspaceMemberAdmin",
    "SubscriptionAdmin",
]
