from app.shared.db.crud.base import BaseDB
from app.shared.db.crud.otp import OTPTokenDB
from app.shared.db.crud.plan import PlanDB
from app.shared.db.crud.refresh_token import RefreshTokenDB
from app.shared.db.crud.subscription import SubscriptionDB, StripeEventLogDB
from app.shared.db.crud.subscription_context import (
    APISubscriptionContextDB,
    CareerSubscriptionContextDB,
)
from app.shared.db.crud.user import OAuthAccountDB, UserDB

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
    "OAuthAccountDB",
    "OTPTokenDB",
    "PlanDB",
    "RefreshTokenDB",
    "StripeEventLogDB",
    "SubscriptionDB",
    "UserDB",
    # Global instances (for actual usage)
    "api_subscription_context_db",
    "career_subscription_context_db",
    "user_db",
    "oauth_account_db",
    "otp_token_db",
    "refresh_token_db",
    "plan_db",
    "subscription_db",
    "stripe_event_log_db",
]
