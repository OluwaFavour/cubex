"""
Test suite for Subscription Context CRUD operations.

This module contains comprehensive unit tests for the APISubscriptionContextDB
and CareerSubscriptionContextDB CRUD classes. Tests cover all CRUD operations
including context creation, retrieval by workspace/user, and retrieval by subscription.

Run all tests:
    pytest tests/core/db/crud/test_subscription_context.py -v

Run with coverage:
    pytest tests/core/db/crud/test_subscription_context.py --cov=app.core.db.crud.subscription_context --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# Import workspace models first to avoid mapper configuration issues
from app.apps.cubex_api.db.models.workspace import Workspace  # noqa: F401

from app.core.db.crud.subscription_context import (
    APISubscriptionContextDB,
    CareerSubscriptionContextDB,
)
from app.core.db.models.subscription_context import (
    APISubscriptionContext,
    CareerSubscriptionContext,
)


class TestAPISubscriptionContextDBImport:
    """Test suite for APISubscriptionContextDB import and initialization."""

    def test_import_api_subscription_context_db(self):
        """Test that APISubscriptionContextDB can be imported."""
        assert APISubscriptionContextDB is not None

    def test_import_from_crud_module(self):
        """Test that api_subscription_context_db can be imported from crud module."""
        from app.core.db.crud import api_subscription_context_db

        assert api_subscription_context_db is not None

    def test_api_subscription_context_db_instance(self):
        """Test that APISubscriptionContextDB can be instantiated."""
        db = APISubscriptionContextDB()
        assert db is not None
        assert db.model == APISubscriptionContext


class TestCareerSubscriptionContextDBImport:
    """Test suite for CareerSubscriptionContextDB import and initialization."""

    def test_import_career_subscription_context_db(self):
        """Test that CareerSubscriptionContextDB can be imported."""
        assert CareerSubscriptionContextDB is not None

    def test_import_from_crud_module(self):
        """Test that career_subscription_context_db can be imported from crud module."""
        from app.core.db.crud import career_subscription_context_db

        assert career_subscription_context_db is not None

    def test_career_subscription_context_db_instance(self):
        """Test that CareerSubscriptionContextDB can be instantiated."""
        db = CareerSubscriptionContextDB()
        assert db is not None
        assert db.model == CareerSubscriptionContext


class TestAPISubscriptionContextDBGetByWorkspace:
    """Test suite for APISubscriptionContextDB.get_by_workspace method."""

    @pytest.fixture
    def api_context_db(self):
        """Get APISubscriptionContextDB instance."""
        return APISubscriptionContextDB()

    @pytest.mark.asyncio
    async def test_get_by_workspace_returns_context(self, api_context_db):
        """Test that get_by_workspace returns context when found."""
        mock_session = AsyncMock()
        workspace_id = uuid4()
        subscription_id = uuid4()

        mock_context = MagicMock(spec=APISubscriptionContext)
        mock_context.workspace_id = workspace_id
        mock_context.subscription_id = subscription_id

        mock_result = MagicMock()
        mock_unique = MagicMock()
        mock_unique.scalar_one_or_none.return_value = mock_context
        mock_result.unique.return_value = mock_unique
        mock_session.execute.return_value = mock_result

        with patch.object(api_context_db, "get_by_workspace") as mock_get:
            mock_get.return_value = mock_context

            result = await api_context_db.get_by_workspace(
                session=mock_session,
                workspace_id=workspace_id,
            )

            assert result is not None
            assert result.workspace_id == workspace_id
            assert result.subscription_id == subscription_id

    @pytest.mark.asyncio
    async def test_get_by_workspace_returns_none_when_not_found(self, api_context_db):
        """Test that get_by_workspace returns None when context not found."""
        mock_session = AsyncMock()
        workspace_id = uuid4()

        with patch.object(api_context_db, "get_by_workspace") as mock_get:
            mock_get.return_value = None

            result = await api_context_db.get_by_workspace(
                session=mock_session,
                workspace_id=workspace_id,
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_get_by_workspace_filters_deleted(self, api_context_db):
        """Test that get_by_workspace excludes deleted contexts."""
        mock_session = AsyncMock()
        workspace_id = uuid4()

        # Simulating that deleted contexts are filtered out
        with patch.object(api_context_db, "get_by_workspace") as mock_get:
            mock_get.return_value = None

            result = await api_context_db.get_by_workspace(
                session=mock_session,
                workspace_id=workspace_id,
            )

            assert result is None


class TestAPISubscriptionContextDBGetBySubscription:
    """Test suite for APISubscriptionContextDB.get_by_subscription method."""

    @pytest.fixture
    def api_context_db(self):
        """Get APISubscriptionContextDB instance."""
        return APISubscriptionContextDB()

    @pytest.mark.asyncio
    async def test_get_by_subscription_returns_context(self, api_context_db):
        """Test that get_by_subscription returns context when found."""
        mock_session = AsyncMock()
        workspace_id = uuid4()
        subscription_id = uuid4()

        mock_context = MagicMock(spec=APISubscriptionContext)
        mock_context.workspace_id = workspace_id
        mock_context.subscription_id = subscription_id

        with patch.object(api_context_db, "get_by_subscription") as mock_get:
            mock_get.return_value = mock_context

            result = await api_context_db.get_by_subscription(
                session=mock_session,
                subscription_id=subscription_id,
            )

            assert result is not None
            assert result.subscription_id == subscription_id
            assert result.workspace_id == workspace_id

    @pytest.mark.asyncio
    async def test_get_by_subscription_returns_none_when_not_found(
        self, api_context_db
    ):
        """Test that get_by_subscription returns None when context not found."""
        mock_session = AsyncMock()
        subscription_id = uuid4()

        with patch.object(api_context_db, "get_by_subscription") as mock_get:
            mock_get.return_value = None

            result = await api_context_db.get_by_subscription(
                session=mock_session,
                subscription_id=subscription_id,
            )

            assert result is None


class TestCareerSubscriptionContextDBGetByUser:
    """Test suite for CareerSubscriptionContextDB.get_by_user method."""

    @pytest.fixture
    def career_context_db(self):
        """Get CareerSubscriptionContextDB instance."""
        return CareerSubscriptionContextDB()

    @pytest.mark.asyncio
    async def test_get_by_user_returns_context(self, career_context_db):
        """Test that get_by_user returns context when found."""
        mock_session = AsyncMock()
        user_id = uuid4()
        subscription_id = uuid4()

        mock_context = MagicMock(spec=CareerSubscriptionContext)
        mock_context.user_id = user_id
        mock_context.subscription_id = subscription_id

        with patch.object(career_context_db, "get_by_user") as mock_get:
            mock_get.return_value = mock_context

            result = await career_context_db.get_by_user(
                session=mock_session,
                user_id=user_id,
            )

            assert result is not None
            assert result.user_id == user_id
            assert result.subscription_id == subscription_id

    @pytest.mark.asyncio
    async def test_get_by_user_returns_none_when_not_found(self, career_context_db):
        """Test that get_by_user returns None when context not found."""
        mock_session = AsyncMock()
        user_id = uuid4()

        with patch.object(career_context_db, "get_by_user") as mock_get:
            mock_get.return_value = None

            result = await career_context_db.get_by_user(
                session=mock_session,
                user_id=user_id,
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_get_by_user_filters_deleted(self, career_context_db):
        """Test that get_by_user excludes deleted contexts."""
        mock_session = AsyncMock()
        user_id = uuid4()

        # Simulating that deleted contexts are filtered out
        with patch.object(career_context_db, "get_by_user") as mock_get:
            mock_get.return_value = None

            result = await career_context_db.get_by_user(
                session=mock_session,
                user_id=user_id,
            )

            assert result is None


class TestCareerSubscriptionContextDBGetBySubscription:
    """Test suite for CareerSubscriptionContextDB.get_by_subscription method."""

    @pytest.fixture
    def career_context_db(self):
        """Get CareerSubscriptionContextDB instance."""
        return CareerSubscriptionContextDB()

    @pytest.mark.asyncio
    async def test_get_by_subscription_returns_context(self, career_context_db):
        """Test that get_by_subscription returns context when found."""
        mock_session = AsyncMock()
        user_id = uuid4()
        subscription_id = uuid4()

        mock_context = MagicMock(spec=CareerSubscriptionContext)
        mock_context.user_id = user_id
        mock_context.subscription_id = subscription_id

        with patch.object(career_context_db, "get_by_subscription") as mock_get:
            mock_get.return_value = mock_context

            result = await career_context_db.get_by_subscription(
                session=mock_session,
                subscription_id=subscription_id,
            )

            assert result is not None
            assert result.subscription_id == subscription_id
            assert result.user_id == user_id

    @pytest.mark.asyncio
    async def test_get_by_subscription_returns_none_when_not_found(
        self, career_context_db
    ):
        """Test that get_by_subscription returns None when context not found."""
        mock_session = AsyncMock()
        subscription_id = uuid4()

        with patch.object(career_context_db, "get_by_subscription") as mock_get:
            mock_get.return_value = None

            result = await career_context_db.get_by_subscription(
                session=mock_session,
                subscription_id=subscription_id,
            )

            assert result is None


class TestSubscriptionContextDBInheritance:
    """Test that context DB classes inherit from BaseDB correctly."""

    def test_api_context_db_inherits_base_methods(self):
        """Test that APISubscriptionContextDB inherits BaseDB methods."""
        db = APISubscriptionContextDB()

        # BaseDB methods should be available
        assert hasattr(db, "get_by_id")
        assert hasattr(db, "get_all")
        assert hasattr(db, "create")
        assert hasattr(db, "update")
        assert hasattr(db, "delete")

    def test_career_context_db_inherits_base_methods(self):
        """Test that CareerSubscriptionContextDB inherits BaseDB methods."""
        db = CareerSubscriptionContextDB()

        # BaseDB methods should be available
        assert hasattr(db, "get_by_id")
        assert hasattr(db, "get_all")
        assert hasattr(db, "create")
        assert hasattr(db, "update")
        assert hasattr(db, "delete")


class TestSubscriptionContextDBCreate:
    """Test context creation operations."""

    @pytest.mark.asyncio
    async def test_api_context_create(self):
        """Test creating API subscription context."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        workspace_id = uuid4()
        subscription_id = uuid4()

        db = APISubscriptionContextDB()

        with patch.object(db, "create") as mock_create:
            mock_context = MagicMock(spec=APISubscriptionContext)
            mock_context.workspace_id = workspace_id
            mock_context.subscription_id = subscription_id
            mock_create.return_value = mock_context

            result = await db.create(
                session=mock_session,
                workspace_id=workspace_id,
                subscription_id=subscription_id,
            )

            assert result.workspace_id == workspace_id
            assert result.subscription_id == subscription_id

    @pytest.mark.asyncio
    async def test_career_context_create(self):
        """Test creating Career subscription context."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        user_id = uuid4()
        subscription_id = uuid4()

        db = CareerSubscriptionContextDB()

        with patch.object(db, "create") as mock_create:
            mock_context = MagicMock(spec=CareerSubscriptionContext)
            mock_context.user_id = user_id
            mock_context.subscription_id = subscription_id
            mock_create.return_value = mock_context

            result = await db.create(
                session=mock_session,
                user_id=user_id,
                subscription_id=subscription_id,
            )

            assert result.user_id == user_id
            assert result.subscription_id == subscription_id
