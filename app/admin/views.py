"""
SQLAdmin model views for Cubex.

Defines admin views for managing application models:
- PlanAdmin: Full CRUD for subscription plans
- FeatureCostConfigAdmin: Manage feature pricing
- PlanPricingRuleAdmin: Manage plan multipliers and rate limits
- UserAdmin: Read-only user view
- WorkspaceAdmin: Read-only workspace view
- SubscriptionAdmin: View/edit subscriptions
- UsageLogAdmin: Read-only usage log view- DLQMessageAdmin: DLQ monitoring with retry/discard actions
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List, Tuple

from sqladmin import ModelView, action
from sqladmin.filters import BooleanFilter, StaticValuesFilter
from sqlalchemy.sql.expression import Select
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.core.db.crud.quota import plan_pricing_rule_db
from app.core.db.models.dlq_message import DLQMessage
from app.core.db.models.quota import FeatureCostConfig, PlanPricingRule
from app.apps.cubex_api.db.models.workspace import UsageLog, Workspace, WorkspaceMember
from app.core.db.models.plan import Plan
from app.core.db.models.subscription import Subscription
from app.core.db.models.user import User
from app.core.enums import (
    AccessStatus,
    DLQMessageStatus,
    FailureType,
    MemberRole,
    MemberStatus,
    PlanType,
    ProductType,
    SubscriptionStatus,
    UsageLogStatus,
    WorkspaceStatus,
)


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
        Plan.rank,
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
        Plan.rank,
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
        Plan.rank,
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
        Plan.rank,
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
        Plan.rank: "Rank",
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

    # Permissions - Plans are immutable except for is_active and features
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True

    # Only allow editing is_active (to deactivate plans), and features fields
    form_edit_rules = ["is_active", "features"]

    # Provide guidance on features field format
    form_args = {
        "features": {
            "description": (
                "Define plan features in JSON format. "
                "Each feature can have a title, description, "
                "value (boolean or string), and category for grouping."
            ),
        },
    }

    # Make the features field wider in the form
    form_widget_args = {
        "features": {
            "rows": 15,
            "style": "width: 100%; font-family: monospace;",
            "placeholder": """Example features JSON format:
[
    {
        "title": "Feature 1",
        "description": "Description of feature 1",
        "value": true,
        "category": "General"
    },
    {
        "title": "Feature 2",
        "description": "Description of feature 2",
        "value": "Some value",
        "category": "Limits"
    },
    {
        "title": "Feature 3",
        "description": "Description of feature 3",
        "category": "Integrations"
    }
]
            """,
        }
    }


class FeatureCostConfigAdmin(ModelView, model=FeatureCostConfig):
    """Admin view for feature pricing configuration."""

    name = "Feature Cost"
    name_plural = "Feature Costs"
    icon = "fa-solid fa-server"

    column_list = [
        FeatureCostConfig.id,
        FeatureCostConfig.feature_key,
        FeatureCostConfig.internal_cost_credits,
        FeatureCostConfig.created_at,
        FeatureCostConfig.updated_at,
    ]

    column_searchable_list = ["feature_key"]
    column_sortable_list = [
        FeatureCostConfig.feature_key,
        FeatureCostConfig.internal_cost_credits,
        FeatureCostConfig.created_at,
    ]
    column_default_sort = [(FeatureCostConfig.feature_key, False)]

    form_columns = [
        FeatureCostConfig.feature_key,
        FeatureCostConfig.internal_cost_credits,
    ]

    column_labels = {
        FeatureCostConfig.id: "ID",
        FeatureCostConfig.feature_key: "Feature Key",
        FeatureCostConfig.internal_cost_credits: "Cost (Credits)",
        FeatureCostConfig.created_at: "Created",
        FeatureCostConfig.updated_at: "Updated",
    }

    column_formatters = {
        FeatureCostConfig.internal_cost_credits: lambda m, a: f"{m.internal_cost_credits:.4f}",
    }

    form_args = {
        "feature_key": {"description": "Feature key (e.g., api.resume)."},
        "internal_cost_credits": {
            "description": "Internal credit cost for calling this endpoint.",
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
        PlanPricingRule.rate_limit_per_day,
        PlanPricingRule.created_at,
    ]

    column_sortable_list = [
        PlanPricingRule.multiplier,
        PlanPricingRule.credits_allocation,
        PlanPricingRule.rate_limit_per_minute,
        PlanPricingRule.rate_limit_per_day,
        PlanPricingRule.created_at,
    ]

    form_columns = [
        PlanPricingRule.plan,
        PlanPricingRule.multiplier,
        PlanPricingRule.credits_allocation,
        PlanPricingRule.rate_limit_per_minute,
        PlanPricingRule.rate_limit_per_day,
    ]

    column_labels = {
        PlanPricingRule.id: "ID",
        PlanPricingRule.plan: "Plan",
        PlanPricingRule.multiplier: "Price Multiplier",
        PlanPricingRule.credits_allocation: "Credits Allocation",
        PlanPricingRule.rate_limit_per_minute: "Rate Limit/min",
        PlanPricingRule.rate_limit_per_day: "Rate Limit/day",
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
            "description": "Total credits allocated per billing period",
        },
        "rate_limit_per_minute": {
            "description": "Maximum requests per minute (leave empty for unlimited)",
        },
        "rate_limit_per_day": {
            "description": "Maximum requests per day (leave empty for unlimited)",
        },
    }

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True

    def details_query(self, request):
        return super().details_query(request).options(plan_pricing_rule_db.plan_loader)


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


class SubscriptionAdmin(ModelView, model=Subscription):
    """Admin view for subscriptions."""

    name = "Subscription"
    name_plural = "Subscriptions"
    icon = "fa-solid fa-credit-card"

    column_list = [
        Subscription.id,
        Subscription.plan,
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
            values=[
                (e.value, e.value.replace("_", " ").title()) for e in SubscriptionStatus
            ],
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
        Subscription.plan: "Plan",
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


class DateRangeFilter:
    """Custom filter for date range filtering on datetime columns."""

    has_operator = False

    def __init__(
        self,
        column: Any,
        title: str | None = None,
        parameter_name: str | None = None,
    ):
        self.column = column
        self.title = title or "Date Range"
        self.parameter_name = parameter_name or "date_range"

    async def lookups(
        self,
        request: Request,
        model: Any,
        run_query: Callable[[Select], Any],
    ) -> List[Tuple[str, str]]:
        return [
            ("", "All Time"),
            ("today", "Today"),
            ("yesterday", "Yesterday"),
            ("last_7_days", "Last 7 Days"),
            ("last_30_days", "Last 30 Days"),
            ("this_month", "This Month"),
            ("last_month", "Last Month"),
        ]

    async def get_filtered_query(self, query: Select, value: Any, model: Any) -> Select:
        if not value or value == "":
            return query

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if value == "today":
            return query.filter(self.column >= today_start)
        elif value == "yesterday":
            yesterday_start = today_start - timedelta(days=1)
            return query.filter(
                self.column >= yesterday_start, self.column < today_start
            )
        elif value == "last_7_days":
            start = today_start - timedelta(days=7)
            return query.filter(self.column >= start)
        elif value == "last_30_days":
            start = today_start - timedelta(days=30)
            return query.filter(self.column >= start)
        elif value == "this_month":
            month_start = today_start.replace(day=1)
            return query.filter(self.column >= month_start)
        elif value == "last_month":
            this_month_start = today_start.replace(day=1)
            last_month_end = this_month_start - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            return query.filter(
                self.column >= last_month_start, self.column < this_month_start
            )

        return query


class UsageLogAdmin(ModelView, model=UsageLog):
    """Admin view for API usage logs (read-only)."""

    name = "Usage Log"
    name_plural = "Usage Logs"
    icon = "fa-solid fa-chart-line"

    # List view configuration
    column_list = [
        UsageLog.id,
        UsageLog.workspace_id,
        UsageLog.api_key_id,
        UsageLog.endpoint,
        UsageLog.method,
        UsageLog.access_status,
        UsageLog.status,
        UsageLog.credits_reserved,
        UsageLog.credits_charged,
        UsageLog.created_at,
    ]

    column_searchable_list = ["request_id", "endpoint", "client_ip"]
    column_sortable_list = [
        UsageLog.endpoint,
        UsageLog.method,
        UsageLog.access_status,
        UsageLog.status,
        UsageLog.credits_reserved,
        UsageLog.credits_charged,
        UsageLog.created_at,
    ]
    column_default_sort = [(UsageLog.created_at, True)]  # Newest first

    # Filters
    column_filters = [
        StaticValuesFilter(
            UsageLog.status,
            values=[(e.value, e.value.title()) for e in UsageLogStatus],
            title="Status",
        ),
        StaticValuesFilter(
            UsageLog.access_status,
            values=[(e.value, e.value.title()) for e in AccessStatus],
            title="Access",
        ),
        StaticValuesFilter(
            UsageLog.failure_type,
            values=[(e.value, e.value.replace("_", " ").title()) for e in FailureType],
            title="Failure Type",
        ),
        DateRangeFilter(UsageLog.created_at, title="Created"),
    ]

    # Detail view - includes all fields including metrics
    column_details_list = [
        UsageLog.id,
        UsageLog.workspace_id,
        UsageLog.api_key_id,
        UsageLog.request_id,
        UsageLog.fingerprint_hash,
        UsageLog.endpoint,
        UsageLog.method,
        UsageLog.access_status,
        UsageLog.status,
        UsageLog.client_ip,
        UsageLog.client_user_agent,
        UsageLog.usage_estimate,
        UsageLog.credits_reserved,
        UsageLog.credits_charged,
        UsageLog.committed_at,
        # Metrics (populated on successful commit)
        UsageLog.model_used,
        UsageLog.input_tokens,
        UsageLog.output_tokens,
        UsageLog.latency_ms,
        # Failure details (populated on failed commit)
        UsageLog.failure_type,
        UsageLog.failure_reason,
        UsageLog.created_at,
        UsageLog.updated_at,
    ]

    # Labels
    column_labels = {
        UsageLog.id: "ID",
        UsageLog.workspace_id: "Workspace",
        UsageLog.api_key_id: "API Key",
        UsageLog.request_id: "Request ID",
        UsageLog.fingerprint_hash: "Fingerprint",
        UsageLog.endpoint: "Endpoint",
        UsageLog.method: "Method",
        UsageLog.access_status: "Access",
        UsageLog.status: "Status",
        UsageLog.client_ip: "Client IP",
        UsageLog.client_user_agent: "User Agent",
        UsageLog.usage_estimate: "Usage Estimate",
        UsageLog.credits_reserved: "Credits Reserved",
        UsageLog.credits_charged: "Credits Charged",
        UsageLog.committed_at: "Committed At",
        UsageLog.model_used: "Model Used",
        UsageLog.input_tokens: "Input Tokens",
        UsageLog.output_tokens: "Output Tokens",
        UsageLog.latency_ms: "Latency (ms)",
        UsageLog.failure_type: "Failure Type",
        UsageLog.failure_reason: "Failure Reason",
        UsageLog.created_at: "Created",
        UsageLog.updated_at: "Updated",
    }

    # Formatting
    column_formatters = {
        UsageLog.credits_reserved: lambda m, a: f"{m.credits_reserved:.4f}",
        UsageLog.credits_charged: lambda m, a: (
            f"{m.credits_charged:.4f}" if m.credits_charged else "-"
        ),
        UsageLog.latency_ms: lambda m, a: (
            f"{m.latency_ms:,} ms" if m.latency_ms else "-"
        ),
        UsageLog.input_tokens: lambda m, a: (
            f"{m.input_tokens:,}" if m.input_tokens else "-"
        ),
        UsageLog.output_tokens: lambda m, a: (
            f"{m.output_tokens:,}" if m.output_tokens else "-"
        ),
    }

    # Read-only - usage logs are immutable
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
    can_export = True

    # Increase page size for logs
    page_size = 50
    page_size_options = [25, 50, 100, 200]


class DLQMessageAdmin(ModelView, model=DLQMessage):
    """Admin view for dead-letter queue messages.

    Read-only with retry and discard bulk actions.
    """

    name = "DLQ Message"
    name_plural = "DLQ Messages"
    icon = "fa-solid fa-skull-crossbones"

    # List view configuration
    column_list = [
        DLQMessage.id,
        DLQMessage.queue_name,
        DLQMessage.status,
        DLQMessage.attempt_count,
        DLQMessage.error_message,
        DLQMessage.created_at,
    ]

    column_searchable_list = ["queue_name", "error_message"]
    column_sortable_list = [
        DLQMessage.queue_name,
        DLQMessage.status,
        DLQMessage.attempt_count,
        DLQMessage.created_at,
    ]
    column_default_sort = [(DLQMessage.created_at, True)]  # Newest first

    # Filters
    column_filters = [
        StaticValuesFilter(
            DLQMessage.status,
            values=[(e.value, e.value.title()) for e in DLQMessageStatus],
            title="Status",
        ),
    ]

    # Detail view — expose all fields including full payload
    column_details_list = [
        DLQMessage.id,
        DLQMessage.queue_name,
        DLQMessage.status,
        DLQMessage.attempt_count,
        DLQMessage.error_message,
        DLQMessage.message_body,
        DLQMessage.headers,
        DLQMessage.created_at,
        DLQMessage.updated_at,
    ]

    # Labels
    column_labels = {
        DLQMessage.id: "ID",
        DLQMessage.queue_name: "Queue",
        DLQMessage.status: "Status",
        DLQMessage.attempt_count: "Attempts",
        DLQMessage.error_message: "Error",
        DLQMessage.message_body: "Message Body",
        DLQMessage.headers: "Headers",
        DLQMessage.created_at: "Created",
        DLQMessage.updated_at: "Updated",
    }

    # Formatting — truncate large text on the list view
    column_formatters = {
        DLQMessage.error_message: lambda m, a: (
            (m.error_message[:120] + "…")
            if m.error_message and len(m.error_message) > 120
            else m.error_message or "-"
        ),
    }

    # Pretty-print JSON on detail view
    column_formatters_detail = {
        DLQMessage.message_body: lambda m, a: _format_json_field(m.message_body),
        DLQMessage.headers: lambda m, a: _format_json_field(m.headers),
    }

    # Read-only — mutations only through actions
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
    can_export = True

    page_size = 50
    page_size_options = [25, 50, 100, 200]

    @action(
        name="retry_messages",
        label="Retry",
        confirmation_message="Re-publish selected messages to their original queues?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def action_retry(self, request: Request) -> RedirectResponse:
        """Re-publish selected DLQ messages to their original queues."""
        import json
        from uuid import UUID

        from app.core.db import AsyncSessionLocal
        from app.core.db.crud.dlq_message import dlq_message_db
        from app.infrastructure.messaging.publisher import publish_event

        pks = request.query_params.get("pks", "").split(",")
        pks = [pk for pk in pks if pk]

        async with AsyncSessionLocal() as session:
            for pk in pks:
                msg = await dlq_message_db.get_by_id(session, UUID(pk))
                if not msg or msg.status != DLQMessageStatus.PENDING:
                    continue

                # Determine the original queue to re-publish to
                original_queue = (
                    (msg.headers or {}).get("x-original-queue") if msg.headers else None
                )
                if not original_queue and msg.queue_name.endswith("_dead"):
                    original_queue = msg.queue_name[: -len("_dead")]

                if original_queue:
                    try:
                        payload = json.loads(msg.message_body)
                    except (json.JSONDecodeError, TypeError):
                        payload = {"raw": msg.message_body}

                    await publish_event(original_queue, payload)

                msg.status = DLQMessageStatus.RETRIED
            await session.commit()

        referer = request.headers.get("referer", "/admin/dlq-message/list")
        return RedirectResponse(referer, status_code=302)

    @action(
        name="discard_messages",
        label="Discard",
        confirmation_message="Mark selected messages as discarded? This cannot be undone.",
        add_in_detail=True,
        add_in_list=True,
    )
    async def action_discard(self, request: Request) -> RedirectResponse:
        """Mark selected DLQ messages as discarded."""
        from uuid import UUID

        from app.core.db import AsyncSessionLocal
        from app.core.db.crud.dlq_message import dlq_message_db

        pks = request.query_params.get("pks", "").split(",")
        pks = [pk for pk in pks if pk]

        async with AsyncSessionLocal() as session:
            for pk in pks:
                msg = await dlq_message_db.get_by_id(session, UUID(pk))
                if not msg or msg.status != DLQMessageStatus.PENDING:
                    continue
                msg.status = DLQMessageStatus.DISCARDED
            await session.commit()

        referer = request.headers.get("referer", "/admin/dlq-message/list")
        return RedirectResponse(referer, status_code=302)


def _format_json_field(value: Any) -> str:
    """Pretty-print a JSON-serialisable value for the detail view."""
    import json as _json

    if value is None:
        return "-"
    if isinstance(value, str):
        try:
            parsed = _json.loads(value)
            return _json.dumps(parsed, indent=2, ensure_ascii=False)
        except (ValueError, TypeError):
            return value
    if isinstance(value, dict):
        return _json.dumps(value, indent=2, ensure_ascii=False)
    return str(value)


# Export all admin views
__all__ = [
    "PlanAdmin",
    "FeatureCostConfigAdmin",
    "PlanPricingRuleAdmin",
    "UserAdmin",
    "WorkspaceAdmin",
    "WorkspaceMemberAdmin",
    "SubscriptionAdmin",
    "UsageLogAdmin",
    "DLQMessageAdmin",
]
