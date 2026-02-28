from app.core.db.crud.base import BaseDB
from app.core.db.crud.dlq_message import DLQMessageDB, dlq_message_db
from app.core.db.crud.otp import OTPTokenDB
from app.core.db.crud.plan import PlanDB
from app.core.db.crud.quota import (
    FeatureCostConfigDB,
    PlanPricingRuleDB,
    feature_cost_config_db,
    plan_pricing_rule_db,
)
from app.core.db.crud.refresh_token import RefreshTokenDB
from app.core.db.crud.subscription import SubscriptionDB, StripeEventLogDB
from app.core.db.crud.subscription_context import (
    APISubscriptionContextDB,
    CareerSubscriptionContextDB,
)
from app.core.db.crud.user import OAuthAccountDB, UserDB

# Global CRUD instances - use these instead of creating new instances
user_db = UserDB()
oauth_account_db = OAuthAccountDB()
otp_token_db = OTPTokenDB()
refresh_token_db = RefreshTokenDB()
plan_db = PlanDB()
subscription_db = SubscriptionDB()
stripe_event_log_db = StripeEventLogDB()
api_subscription_context_db = APISubscriptionContextDB()
career_subscription_context_db = CareerSubscriptionContextDB()

__all__ = [
    # Classes (for type hints and subclassing)
    "APISubscriptionContextDB",
    "BaseDB",
    "CareerSubscriptionContextDB",
    "DLQMessageDB",
    "OAuthAccountDB",
    "OTPTokenDB",
    "PlanDB",
    # Quota
    "FeatureCostConfigDB",
    "PlanPricingRuleDB",
    "RefreshTokenDB",
    "StripeEventLogDB",
    "SubscriptionDB",
    "UserDB",
    # Global instances (for actual usage)
    "api_subscription_context_db",
    "career_subscription_context_db",
    "dlq_message_db",
    "feature_cost_config_db",
    "plan_pricing_rule_db",
    "user_db",
    "oauth_account_db",
    "otp_token_db",
    "refresh_token_db",
    "plan_db",
    "subscription_db",
    "stripe_event_log_db",
]
