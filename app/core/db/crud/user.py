from sqlalchemy.orm import selectinload

from app.core.db.crud import BaseDB
from app.core.db.models import OAuthAccount, User


class UserDB(BaseDB[User]):
    def __init__(self):
        super().__init__(model=User)
        self.oauth_accounts_loader = selectinload(User.oauth_accounts)


class OAuthAccountDB(BaseDB[OAuthAccount]):
    def __init__(self):
        super().__init__(model=OAuthAccount)
        self.user_loader = selectinload(OAuthAccount.user)
