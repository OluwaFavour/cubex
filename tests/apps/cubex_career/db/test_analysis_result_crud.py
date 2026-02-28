"""
Integration tests for CareerAnalysisResultDB CRUD operations.

Tests all CRUD methods against a real database session with per-test
transaction rollback.

Methods tested:
- create_from_commit  — row creation, auto-title, custom title
- get_by_usage_log_id — lookup by usage log FK, soft-delete exclusion
- get_user_result     — ownership check, soft-delete exclusion
- list_by_user        — pagination, feature_key filter, ordering, user isolation

Run all tests:
    pytest tests/apps/cubex_career/db/test_analysis_result_crud.py -v

Run with coverage:
    pytest tests/apps/cubex_career/db/test_analysis_result_crud.py \
        --cov=app.apps.cubex_career.db.crud.analysis_result \
        --cov-report=term-missing -v
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_career.db.crud.analysis_result import (
    CareerAnalysisResultDB,
    _default_title,
    _FEATURE_TITLES,
    career_analysis_result_db,
)
from app.core.enums import FeatureKey

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def crud() -> CareerAnalysisResultDB:
    """Return the global CRUD singleton."""
    return career_analysis_result_db


@pytest.fixture
async def usage_log(db_session: AsyncSession, test_user, career_subscription):
    """Create a committed CareerUsageLog for test_user."""
    from app.apps.cubex_career.db.models import CareerUsageLog
    from app.core.enums import AccessStatus, UsageLogStatus

    log = CareerUsageLog(
        id=uuid4(),
        user_id=test_user.id,
        subscription_id=career_subscription.id,
        request_id=str(uuid4()),
        feature_key=FeatureKey.CAREER_JOB_MATCH,
        fingerprint_hash="a" * 64,
        access_status=AccessStatus.GRANTED,
        endpoint="/test/job-match",
        method="POST",
        credits_reserved=Decimal("1.00"),
        status=UsageLogStatus.SUCCESS,
    )
    db_session.add(log)
    await db_session.flush()
    return log


@pytest.fixture
async def second_usage_log(db_session: AsyncSession, test_user, career_subscription):
    """Create a second committed CareerUsageLog (career_path) for test_user."""
    from app.apps.cubex_career.db.models import CareerUsageLog
    from app.core.enums import AccessStatus, UsageLogStatus

    log = CareerUsageLog(
        id=uuid4(),
        user_id=test_user.id,
        subscription_id=career_subscription.id,
        request_id=str(uuid4()),
        feature_key=FeatureKey.CAREER_CAREER_PATH,
        fingerprint_hash="b" * 64,
        access_status=AccessStatus.GRANTED,
        endpoint="/test/career-path",
        method="POST",
        credits_reserved=Decimal("1.00"),
        status=UsageLogStatus.SUCCESS,
    )
    db_session.add(log)
    await db_session.flush()
    return log


@pytest.fixture
async def other_user(db_session: AsyncSession):
    """Create a different user for isolation tests."""
    from app.core.db.models import User

    user = User(
        id=uuid4(),
        email="otheruser@example.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.vwPbgsgNJwKrWe",
        full_name="Other User",
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ---------------------------------------------------------------------------
# _default_title / _FEATURE_TITLES
# ---------------------------------------------------------------------------


class TestDefaultTitle:
    """Tests for the _default_title helper and _FEATURE_TITLES mapping."""

    def test_known_feature_keys_all_have_titles(self):
        """Every entry in _FEATURE_TITLES maps to a non-empty string."""
        for key, title in _FEATURE_TITLES.items():
            assert isinstance(title, str)
            assert len(title) > 0, f"{key} has an empty title"

    @pytest.mark.parametrize(
        "feature_key,expected_title",
        [
            (FeatureKey.CAREER_JOB_MATCH, "Job Match Analysis"),
            (FeatureKey.CAREER_CAREER_PATH, "Career Path Analysis"),
            (FeatureKey.CAREER_FEEDBACK_ANALYZER, "Feedback Analysis"),
            (FeatureKey.CAREER_GENERATE_FEEDBACK, "Feedback Generation"),
            (FeatureKey.CAREER_EXTRACT_KEYWORDS, "Keyword Extraction"),
            (FeatureKey.CAREER_EXTRACT_CUES_RESUME, "Resume Cue Extraction"),
            (FeatureKey.CAREER_EXTRACT_CUES_FEEDBACK, "Feedback Cue Extraction"),
            (FeatureKey.CAREER_EXTRACT_CUES_INTERVIEW, "Interview Cue Extraction"),
            (FeatureKey.CAREER_EXTRACT_CUES_ASSESSMENT, "Assessment Cue Extraction"),
            (FeatureKey.CAREER_REFRAME_FEEDBACK, "Feedback Reframing"),
        ],
    )
    def test_default_title_returns_mapped_value(self, feature_key, expected_title):
        assert _default_title(feature_key) == expected_title


# ---------------------------------------------------------------------------
# Imports & singleton
# ---------------------------------------------------------------------------


class TestCareerAnalysisResultDBImports:
    """Verify the CRUD module exports are intact."""

    def test_class_importable(self):
        assert CareerAnalysisResultDB is not None

    def test_singleton_instance_exists(self):
        assert career_analysis_result_db is not None

    def test_singleton_is_correct_type(self):
        assert isinstance(career_analysis_result_db, CareerAnalysisResultDB)

    def test_model_is_career_analysis_result(self):
        from app.apps.cubex_career.db.models.analysis_result import (
            CareerAnalysisResult,
        )

        assert career_analysis_result_db.model == CareerAnalysisResult

    def test_exported_from_crud_init(self):
        from app.apps.cubex_career.db.crud import (
            career_analysis_result_db as exported,
        )

        assert exported is career_analysis_result_db


# ---------------------------------------------------------------------------
# create_from_commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCreateFromCommit:
    """Tests for career_analysis_result_db.create_from_commit."""

    async def test_creates_row_with_correct_fields(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        test_user,
    ):
        result_data = {"match_score": 0.92, "skills": ["Python"]}
        row = await crud.create_from_commit(
            session=db_session,
            usage_log_id=usage_log.id,
            user_id=test_user.id,
            feature_key=FeatureKey.CAREER_JOB_MATCH,
            result_data=result_data,
            commit_self=False,
        )

        assert row.usage_log_id == usage_log.id
        assert row.user_id == test_user.id
        assert row.feature_key == FeatureKey.CAREER_JOB_MATCH
        assert row.result_data == result_data
        assert row.is_deleted is False
        assert row.id is not None

    async def test_auto_generates_title_from_feature_key(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        test_user,
    ):
        row = await crud.create_from_commit(
            session=db_session,
            usage_log_id=usage_log.id,
            user_id=test_user.id,
            feature_key=FeatureKey.CAREER_JOB_MATCH,
            result_data={"score": 1},
            commit_self=False,
        )
        assert row.title == "Job Match Analysis"

    async def test_custom_title_overrides_auto_title(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        test_user,
    ):
        row = await crud.create_from_commit(
            session=db_session,
            usage_log_id=usage_log.id,
            user_id=test_user.id,
            feature_key=FeatureKey.CAREER_JOB_MATCH,
            result_data={"score": 1},
            title="My Custom Title",
            commit_self=False,
        )
        assert row.title == "My Custom Title"


# ---------------------------------------------------------------------------
# get_by_usage_log_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetByUsageLogId:
    """Tests for career_analysis_result_db.get_by_usage_log_id."""

    async def test_returns_result_for_existing_log(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        test_user,
    ):
        created = await crud.create_from_commit(
            session=db_session,
            usage_log_id=usage_log.id,
            user_id=test_user.id,
            feature_key=FeatureKey.CAREER_JOB_MATCH,
            result_data={"data": True},
            commit_self=False,
        )

        found = await crud.get_by_usage_log_id(db_session, usage_log.id)
        assert found is not None
        assert found.id == created.id

    async def test_returns_none_for_unknown_log(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
    ):
        found = await crud.get_by_usage_log_id(db_session, uuid4())
        assert found is None

    async def test_excludes_soft_deleted(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        test_user,
    ):
        row = await crud.create_from_commit(
            session=db_session,
            usage_log_id=usage_log.id,
            user_id=test_user.id,
            feature_key=FeatureKey.CAREER_JOB_MATCH,
            result_data={"data": True},
            commit_self=False,
        )
        row.is_deleted = True
        await db_session.flush()

        found = await crud.get_by_usage_log_id(db_session, usage_log.id)
        assert found is None


# ---------------------------------------------------------------------------
# get_user_result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetUserResult:
    """Tests for career_analysis_result_db.get_user_result."""

    async def test_returns_result_when_owned(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        test_user,
    ):
        row = await crud.create_from_commit(
            session=db_session,
            usage_log_id=usage_log.id,
            user_id=test_user.id,
            feature_key=FeatureKey.CAREER_JOB_MATCH,
            result_data={"owned": True},
            commit_self=False,
        )

        found = await crud.get_user_result(db_session, row.id, test_user.id)
        assert found is not None
        assert found.id == row.id

    async def test_returns_none_for_different_user(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        test_user,
        other_user,
    ):
        row = await crud.create_from_commit(
            session=db_session,
            usage_log_id=usage_log.id,
            user_id=test_user.id,
            feature_key=FeatureKey.CAREER_JOB_MATCH,
            result_data={"owned": True},
            commit_self=False,
        )

        found = await crud.get_user_result(db_session, row.id, other_user.id)
        assert found is None

    async def test_returns_none_when_soft_deleted(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        test_user,
    ):
        row = await crud.create_from_commit(
            session=db_session,
            usage_log_id=usage_log.id,
            user_id=test_user.id,
            feature_key=FeatureKey.CAREER_JOB_MATCH,
            result_data={"deleted": True},
            commit_self=False,
        )
        row.is_deleted = True
        await db_session.flush()

        found = await crud.get_user_result(db_session, row.id, test_user.id)
        assert found is None

    async def test_returns_none_for_unknown_id(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        test_user,
    ):
        found = await crud.get_user_result(db_session, uuid4(), test_user.id)
        assert found is None


# ---------------------------------------------------------------------------
# list_by_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListByUser:
    """Tests for career_analysis_result_db.list_by_user."""

    async def _create_result(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        user,
        feature_key: FeatureKey = FeatureKey.CAREER_JOB_MATCH,
    ):
        """Helper to create a result and return it."""
        return await crud.create_from_commit(
            session=db_session,
            usage_log_id=usage_log.id,
            user_id=user.id,
            feature_key=feature_key,
            result_data={"k": "v"},
            commit_self=False,
        )

    async def test_returns_results_for_user(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        test_user,
    ):
        await self._create_result(crud, db_session, usage_log, test_user)

        rows = await crud.list_by_user(db_session, test_user.id)
        assert len(rows) == 1

    async def test_excludes_other_users_results(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        test_user,
        other_user,
    ):
        await self._create_result(crud, db_session, usage_log, test_user)

        rows = await crud.list_by_user(db_session, other_user.id)
        assert len(rows) == 0

    async def test_excludes_soft_deleted(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        test_user,
    ):
        row = await self._create_result(crud, db_session, usage_log, test_user)
        row.is_deleted = True
        await db_session.flush()

        rows = await crud.list_by_user(db_session, test_user.id)
        assert len(rows) == 0

    async def test_filters_by_feature_key(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        second_usage_log,
        test_user,
    ):
        await self._create_result(
            crud,
            db_session,
            usage_log,
            test_user,
            feature_key=FeatureKey.CAREER_JOB_MATCH,
        )
        await self._create_result(
            crud,
            db_session,
            second_usage_log,
            test_user,
            feature_key=FeatureKey.CAREER_CAREER_PATH,
        )

        rows = await crud.list_by_user(
            db_session,
            test_user.id,
            feature_key=FeatureKey.CAREER_JOB_MATCH,
        )
        assert len(rows) == 1
        assert rows[0].feature_key == FeatureKey.CAREER_JOB_MATCH

    async def test_respects_limit(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        second_usage_log,
        test_user,
    ):
        await self._create_result(crud, db_session, usage_log, test_user)
        await self._create_result(
            crud,
            db_session,
            second_usage_log,
            test_user,
            feature_key=FeatureKey.CAREER_CAREER_PATH,
        )

        rows = await crud.list_by_user(db_session, test_user.id, limit=1)
        assert len(rows) == 1

    async def test_cursor_pagination_with_before_id(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        second_usage_log,
        test_user,
    ):
        await self._create_result(crud, db_session, usage_log, test_user)
        await self._create_result(
            crud,
            db_session,
            second_usage_log,
            test_user,
            feature_key=FeatureKey.CAREER_CAREER_PATH,
        )

        # Get the full list (newest first)
        all_rows = await crud.list_by_user(db_session, test_user.id)
        assert len(all_rows) >= 2

        # Use the first item as cursor to get older results
        newest_id = all_rows[0].id
        page2 = await crud.list_by_user(
            db_session,
            test_user.id,
            before_id=newest_id,
        )
        # All items in page2 should be older than the cursor
        assert all(r.id != newest_id for r in page2)

    async def test_empty_when_no_results(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        test_user,
    ):
        rows = await crud.list_by_user(db_session, test_user.id)
        assert len(rows) == 0

    async def test_ordered_newest_first(
        self,
        crud: CareerAnalysisResultDB,
        db_session: AsyncSession,
        usage_log,
        second_usage_log,
        test_user,
    ):
        await self._create_result(crud, db_session, usage_log, test_user)
        await self._create_result(
            crud,
            db_session,
            second_usage_log,
            test_user,
            feature_key=FeatureKey.CAREER_CAREER_PATH,
        )

        rows = await crud.list_by_user(db_session, test_user.id)
        created_dates = [r.created_at for r in rows]
        assert created_dates == sorted(created_dates, reverse=True)
