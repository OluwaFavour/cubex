from app.core.db.models.otp import OTPToken
from app.core.db.models.plan import Plan, FeatureSchema
from app.core.db.models.quota import FeatureCostConfig, PlanPricingRule
from app.core.db.models.refresh_token import RefreshToken
from app.core.db.models.subscription import Subscription, StripeEventLog
from app.core.db.models.user import User, OAuthAccount

# Import app-specific models to ensure they are registered with SQLAlchemy
# before relationships are resolved
from app.apps.cubex_api.db.models.workspace import (
    Workspace,
    WorkspaceInvitation,
    WorkspaceMember,
)

# Import subscription contexts after workspace is registered
from app.core.db.models.subscription_context import (
    APISubscriptionContext,
    CareerSubscriptionContext,
)

# Import career models to ensure they are registered with SQLAlchemy
from app.apps.cubex_career.db.models.usage_log import CareerUsageLog

__all__ = [
    "APISubscriptionContext",
    "CareerSubscriptionContext",
    "CareerUsageLog",
    "FeatureSchema",
    "OAuthAccount",
    "OTPToken",
    "Plan",
    "FeatureCostConfig",
    "PlanPricingRule",
    "RefreshToken",
    "StripeEventLog",
    "Subscription",
    "User",
    "Workspace",
    "WorkspaceInvitation",
    "WorkspaceMember",
]
