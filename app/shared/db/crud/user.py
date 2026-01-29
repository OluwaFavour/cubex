from sqlalchemy.orm import selectinload

from app.shared.db.crud import BaseDB
from app.shared.db.models import OAuthAccount, User


class UserDB(BaseDB):
    def __init__(self):
        super().__init__(model=User)
        self.oauth_accounts_loader = selectinload(User.oauth_accounts)


class OAuthAccountDB(BaseDB):
    def __init__(self):
        super().__init__(model=OAuthAccount)
        self.user_loader = selectinload(OAuthAccount.user)
