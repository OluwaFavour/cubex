from app.shared.db.crud.base import BaseDB
from app.shared.db.crud.otp import OTPTokenDB
from app.shared.db.crud.refresh_token import RefreshTokenDB
from app.shared.db.crud.user import OAuthAccountDB, UserDB

# Global CRUD instances - use these instead of creating new instances
user_db = UserDB()
oauth_account_db = OAuthAccountDB()
otp_token_db = OTPTokenDB()
refresh_token_db = RefreshTokenDB()

__all__ = [
    # Classes (for type hints and subclassing)
    "BaseDB",
    "OAuthAccountDB",
    "OTPTokenDB",
    "RefreshTokenDB",
    "UserDB",
    # Global instances (for actual usage)
    "user_db",
    "oauth_account_db",
    "otp_token_db",
    "refresh_token_db",
]
