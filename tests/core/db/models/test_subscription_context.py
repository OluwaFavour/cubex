"""
Test suite for Subscription Context models.

This module contains comprehensive tests for the APISubscriptionContext
and CareerSubscriptionContext SQLAlchemy models.

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
    """Test suite for APISubscriptionContext model import."""

    def test_import_api_subscription_context(self):
        """Test that APISubscriptionContext can be imported."""
        assert APISubscriptionContext is not None

    def test_import_from_models_module(self):
        """Test that APISubscriptionContext can be imported from models module."""
        from app.core.db.models import APISubscriptionContext as ImportedModel

        assert ImportedModel is not None
        assert ImportedModel is APISubscriptionContext

    def test_tablename(self):
        """Test that APISubscriptionContext has correct table name."""
        assert APISubscriptionContext.__tablename__ == "api_subscription_contexts"


class TestCareerSubscriptionContextModelImport:
    """Test suite for CareerSubscriptionContext model import."""

    def test_import_career_subscription_context(self):
        """Test that CareerSubscriptionContext can be imported."""
        assert CareerSubscriptionContext is not None

    def test_import_from_models_module(self):
        """Test that CareerSubscriptionContext can be imported from models module."""
        from app.core.db.models import CareerSubscriptionContext as ImportedModel

        assert ImportedModel is not None
        assert ImportedModel is CareerSubscriptionContext

    def test_tablename(self):
        """Test that CareerSubscriptionContext has correct table name."""
        assert CareerSubscriptionContext.__tablename__ == "career_subscription_contexts"


class TestAPISubscriptionContextModelAttributes:
    """Test suite for APISubscriptionContext model attributes."""

    def test_has_subscription_id_attribute(self):
        """Test that APISubscriptionContext has subscription_id attribute."""
        context = APISubscriptionContext()
        assert hasattr(context, "subscription_id")

    def test_has_workspace_id_attribute(self):
        """Test that APISubscriptionContext has workspace_id attribute."""
        context = APISubscriptionContext()
        assert hasattr(context, "workspace_id")

    def test_has_subscription_relationship(self):
        """Test that APISubscriptionContext has subscription relationship."""
        context = APISubscriptionContext()
        assert hasattr(context, "subscription")

    def test_has_workspace_relationship(self):
        """Test that APISubscriptionContext has workspace relationship."""
        context = APISubscriptionContext()
        assert hasattr(context, "workspace")

    def test_context_creation_with_ids(self):
        """Test creating APISubscriptionContext with IDs."""
        workspace_id = uuid4()
        subscription_id = uuid4()

        context = APISubscriptionContext(
            workspace_id=workspace_id,
            subscription_id=subscription_id,
        )

        assert context.workspace_id == workspace_id
        assert context.subscription_id == subscription_id


class TestCareerSubscriptionContextModelAttributes:
    """Test suite for CareerSubscriptionContext model attributes."""

    def test_has_subscription_id_attribute(self):
        """Test that CareerSubscriptionContext has subscription_id attribute."""
        context = CareerSubscriptionContext()
        assert hasattr(context, "subscription_id")

    def test_has_user_id_attribute(self):
        """Test that CareerSubscriptionContext has user_id attribute."""
        context = CareerSubscriptionContext()
        assert hasattr(context, "user_id")

    def test_has_subscription_relationship(self):
        """Test that CareerSubscriptionContext has subscription relationship."""
        context = CareerSubscriptionContext()
        assert hasattr(context, "subscription")

    def test_has_user_relationship(self):
        """Test that CareerSubscriptionContext has user relationship."""
        context = CareerSubscriptionContext()
        assert hasattr(context, "user")

    def test_context_creation_with_ids(self):
        """Test creating CareerSubscriptionContext with IDs."""
        user_id = uuid4()
        subscription_id = uuid4()

        context = CareerSubscriptionContext(
            user_id=user_id,
            subscription_id=subscription_id,
        )

        assert context.user_id == user_id
        assert context.subscription_id == subscription_id


class TestAPISubscriptionContextTableConstraints:
    """Test suite for APISubscriptionContext table constraints."""

    def test_has_table_args(self):
        """Test that APISubscriptionContext has __table_args__."""
        assert hasattr(APISubscriptionContext, "__table_args__")
        assert APISubscriptionContext.__table_args__ is not None

    def test_subscription_id_unique_constraint(self):
        """Test that subscription_id has unique constraint."""
        # Get the table object
        table = APISubscriptionContext.__table__

        # Check for unique constraint on subscription_id column
        subscription_col = table.c.subscription_id
        assert subscription_col.unique is True

    def test_workspace_id_unique_constraint(self):
        """Test that workspace_id has unique constraint."""
        # Get the table object
        table = APISubscriptionContext.__table__

        # Check for unique constraint on workspace_id column
        workspace_col = table.c.workspace_id
        assert workspace_col.unique is True


class TestCareerSubscriptionContextTableConstraints:
    """Test suite for CareerSubscriptionContext table constraints."""

    def test_has_table_args(self):
        """Test that CareerSubscriptionContext has __table_args__."""
        assert hasattr(CareerSubscriptionContext, "__table_args__")
        assert CareerSubscriptionContext.__table_args__ is not None

    def test_subscription_id_unique_constraint(self):
        """Test that subscription_id has unique constraint."""
        # Get the table object
        table = CareerSubscriptionContext.__table__

        # Check for unique constraint on subscription_id column
        subscription_col = table.c.subscription_id
        assert subscription_col.unique is True

    def test_user_id_unique_constraint(self):
        """Test that user_id has unique constraint."""
        # Get the table object
        table = CareerSubscriptionContext.__table__

        # Check for unique constraint on user_id column
        user_col = table.c.user_id
        assert user_col.unique is True


class TestAPISubscriptionContextForeignKeys:
    """Test suite for APISubscriptionContext foreign keys."""

    def test_subscription_id_foreign_key(self):
        """Test that subscription_id references subscriptions table."""
        table = APISubscriptionContext.__table__
        subscription_col = table.c.subscription_id

        # Get foreign key info
        fks = list(subscription_col.foreign_keys)
        assert len(fks) == 1
        assert "subscriptions.id" in str(fks[0].target_fullname)

    def test_workspace_id_foreign_key(self):
        """Test that workspace_id references workspaces table."""
        table = APISubscriptionContext.__table__
        workspace_col = table.c.workspace_id

        # Get foreign key info
        fks = list(workspace_col.foreign_keys)
        assert len(fks) == 1
        assert "workspaces.id" in str(fks[0].target_fullname)


class TestCareerSubscriptionContextForeignKeys:
    """Test suite for CareerSubscriptionContext foreign keys."""

    def test_subscription_id_foreign_key(self):
        """Test that subscription_id references subscriptions table."""
        table = CareerSubscriptionContext.__table__
        subscription_col = table.c.subscription_id

        # Get foreign key info
        fks = list(subscription_col.foreign_keys)
        assert len(fks) == 1
        assert "subscriptions.id" in str(fks[0].target_fullname)

    def test_user_id_foreign_key(self):
        """Test that user_id references users table."""
        table = CareerSubscriptionContext.__table__
        user_col = table.c.user_id

        # Get foreign key info
        fks = list(user_col.foreign_keys)
        assert len(fks) == 1
        assert "users.id" in str(fks[0].target_fullname)


class TestSubscriptionContextInheritance:
    """Test that context models inherit from BaseModel correctly."""

    def test_api_context_inherits_base_model(self):
        """Test that APISubscriptionContext inherits from BaseModel."""
        from app.core.db.models.base import BaseModel

        assert issubclass(APISubscriptionContext, BaseModel)

    def test_career_context_inherits_base_model(self):
        """Test that CareerSubscriptionContext inherits from BaseModel."""
        from app.core.db.models.base import BaseModel

        assert issubclass(CareerSubscriptionContext, BaseModel)

    def test_api_context_has_base_attributes(self):
        """Test that APISubscriptionContext has base model attributes."""
        context = APISubscriptionContext()

        # BaseModel attributes
        assert hasattr(context, "id")
        assert hasattr(context, "created_at")
        assert hasattr(context, "updated_at")
        assert hasattr(context, "is_deleted")

    def test_career_context_has_base_attributes(self):
        """Test that CareerSubscriptionContext has base model attributes."""
        context = CareerSubscriptionContext()

        # BaseModel attributes
        assert hasattr(context, "id")
        assert hasattr(context, "created_at")
        assert hasattr(context, "updated_at")
        assert hasattr(context, "is_deleted")


class TestSubscriptionContextAllExport:
    """Test that __all__ exports are correct."""

    def test_all_exports_defined(self):
        """Test that __all__ is defined in subscription_context module."""
        from app.core.db.models import subscription_context

        assert hasattr(subscription_context, "__all__")

    def test_all_exports_contains_api_context(self):
        """Test that __all__ contains APISubscriptionContext."""
        from app.core.db.models import subscription_context

        assert "APISubscriptionContext" in subscription_context.__all__

    def test_all_exports_contains_career_context(self):
        """Test that __all__ contains CareerSubscriptionContext."""
        from app.core.db.models import subscription_context

        assert "CareerSubscriptionContext" in subscription_context.__all__
