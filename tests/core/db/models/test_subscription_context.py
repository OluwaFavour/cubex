"""
Test suite for Subscription Context models.

Run all tests:
    pytest tests/core/db/models/test_subscription_context.py -v

Run with coverage:
    pytest tests/core/db/models/test_subscription_context.py --cov=app.core.db.models.subscription_context --cov-report=term-missing -v
"""

from uuid import uuid4

import pytest

# Import workspace models first to avoid mapper configuration issues
from app.apps.cubex_api.db.models.workspace import Workspace  # noqa: F401

from app.core.db.models.subscription_context import (
    APISubscriptionContext,
    CareerSubscriptionContext,
)


class TestAPISubscriptionContextModelImport:

    def test_import_api_subscription_context(self):
        assert APISubscriptionContext is not None

    def test_import_from_models_module(self):
        from app.core.db.models import APISubscriptionContext as ImportedModel

        assert ImportedModel is not None
        assert ImportedModel is APISubscriptionContext

    def test_tablename(self):
        assert APISubscriptionContext.__tablename__ == "api_subscription_contexts"


class TestCareerSubscriptionContextModelImport:

    def test_import_career_subscription_context(self):
        assert CareerSubscriptionContext is not None

    def test_import_from_models_module(self):
        from app.core.db.models import CareerSubscriptionContext as ImportedModel

        assert ImportedModel is not None
        assert ImportedModel is CareerSubscriptionContext

    def test_tablename(self):
        assert CareerSubscriptionContext.__tablename__ == "career_subscription_contexts"


class TestAPISubscriptionContextModelAttributes:

    def test_has_subscription_id_attribute(self):
        context = APISubscriptionContext()
        assert hasattr(context, "subscription_id")

    def test_has_workspace_id_attribute(self):
        context = APISubscriptionContext()
        assert hasattr(context, "workspace_id")

    def test_has_subscription_relationship(self):
        context = APISubscriptionContext()
        assert hasattr(context, "subscription")

    def test_has_workspace_relationship(self):
        context = APISubscriptionContext()
        assert hasattr(context, "workspace")

    def test_context_creation_with_ids(self):
        workspace_id = uuid4()
        subscription_id = uuid4()

        context = APISubscriptionContext(
            workspace_id=workspace_id,
            subscription_id=subscription_id,
        )

        assert context.workspace_id == workspace_id
        assert context.subscription_id == subscription_id


class TestCareerSubscriptionContextModelAttributes:

    def test_has_subscription_id_attribute(self):
        context = CareerSubscriptionContext()
        assert hasattr(context, "subscription_id")

    def test_has_user_id_attribute(self):
        context = CareerSubscriptionContext()
        assert hasattr(context, "user_id")

    def test_has_subscription_relationship(self):
        context = CareerSubscriptionContext()
        assert hasattr(context, "subscription")

    def test_has_user_relationship(self):
        context = CareerSubscriptionContext()
        assert hasattr(context, "user")

    def test_context_creation_with_ids(self):
        user_id = uuid4()
        subscription_id = uuid4()

        context = CareerSubscriptionContext(
            user_id=user_id,
            subscription_id=subscription_id,
        )

        assert context.user_id == user_id
        assert context.subscription_id == subscription_id


class TestAPISubscriptionContextTableConstraints:

    def test_has_table_args(self):
        assert hasattr(APISubscriptionContext, "__table_args__")
        assert APISubscriptionContext.__table_args__ is not None

    def test_subscription_id_unique_constraint(self):
        table = APISubscriptionContext.__table__

        subscription_col = table.c.subscription_id
        assert subscription_col.unique is True

    def test_workspace_id_unique_constraint(self):
        table = APISubscriptionContext.__table__

        workspace_col = table.c.workspace_id
        assert workspace_col.unique is True


class TestCareerSubscriptionContextTableConstraints:

    def test_has_table_args(self):
        assert hasattr(CareerSubscriptionContext, "__table_args__")
        assert CareerSubscriptionContext.__table_args__ is not None

    def test_subscription_id_unique_constraint(self):
        table = CareerSubscriptionContext.__table__

        subscription_col = table.c.subscription_id
        assert subscription_col.unique is True

    def test_user_id_unique_constraint(self):
        table = CareerSubscriptionContext.__table__

        user_col = table.c.user_id
        assert user_col.unique is True


class TestAPISubscriptionContextForeignKeys:

    def test_subscription_id_foreign_key(self):
        table = APISubscriptionContext.__table__
        subscription_col = table.c.subscription_id

        fks = list(subscription_col.foreign_keys)
        assert len(fks) == 1
        assert "subscriptions.id" in str(fks[0].target_fullname)

    def test_workspace_id_foreign_key(self):
        table = APISubscriptionContext.__table__
        workspace_col = table.c.workspace_id

        fks = list(workspace_col.foreign_keys)
        assert len(fks) == 1
        assert "workspaces.id" in str(fks[0].target_fullname)


class TestCareerSubscriptionContextForeignKeys:

    def test_subscription_id_foreign_key(self):
        table = CareerSubscriptionContext.__table__
        subscription_col = table.c.subscription_id

        fks = list(subscription_col.foreign_keys)
        assert len(fks) == 1
        assert "subscriptions.id" in str(fks[0].target_fullname)

    def test_user_id_foreign_key(self):
        table = CareerSubscriptionContext.__table__
        user_col = table.c.user_id

        fks = list(user_col.foreign_keys)
        assert len(fks) == 1
        assert "users.id" in str(fks[0].target_fullname)


class TestSubscriptionContextInheritance:

    def test_api_context_inherits_base_model(self):
        from app.core.db.models.base import BaseModel

        assert issubclass(APISubscriptionContext, BaseModel)

    def test_career_context_inherits_base_model(self):
        from app.core.db.models.base import BaseModel

        assert issubclass(CareerSubscriptionContext, BaseModel)

    def test_api_context_has_base_attributes(self):
        context = APISubscriptionContext()

        # BaseModel attributes
        assert hasattr(context, "id")
        assert hasattr(context, "created_at")
        assert hasattr(context, "updated_at")
        assert hasattr(context, "is_deleted")

    def test_career_context_has_base_attributes(self):
        context = CareerSubscriptionContext()

        # BaseModel attributes
        assert hasattr(context, "id")
        assert hasattr(context, "created_at")
        assert hasattr(context, "updated_at")
        assert hasattr(context, "is_deleted")


class TestSubscriptionContextAllExport:

    def test_all_exports_defined(self):
        from app.core.db.models import subscription_context

        assert hasattr(subscription_context, "__all__")

    def test_all_exports_contains_api_context(self):
        from app.core.db.models import subscription_context

        assert "APISubscriptionContext" in subscription_context.__all__

    def test_all_exports_contains_career_context(self):
        from app.core.db.models import subscription_context

        assert "CareerSubscriptionContext" in subscription_context.__all__

