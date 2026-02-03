from app.shared.db.models.otp import OTPToken
from app.shared.db.models.plan import Plan, FeatureSchema
from app.shared.db.models.refresh_token import RefreshToken
from app.shared.db.models.subscription import Subscription, StripeEventLog
from app.shared.db.models.user import User, OAuthAccount

# Import app-specific models to ensure they are registered with SQLAlchemy
# before relationships are resolved
from app.apps.cubex_api.db.models.workspace import (
    Workspace,
    WorkspaceInvitation,
    WorkspaceMember,
)

# Import subscription contexts after workspace is registered
from app.shared.db.models.subscription_context import (
    APISubscriptionContext,
    CareerSubscriptionContext,
)

__all__ = [
    "APISubscriptionContext",
    "CareerSubscriptionContext",
    "FeatureSchema",
    "OAuthAccount",
    "OTPToken",
    "Plan",
    "RefreshToken",
    "StripeEventLog",
    "Subscription",
    "User",
    "Workspace",
    "WorkspaceInvitation",
    "WorkspaceMember",
]
