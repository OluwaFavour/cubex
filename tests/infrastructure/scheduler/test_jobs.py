"""
Test suite for scheduler jobs.

Run tests:
    pytest tests/infrastructure/scheduler/test_jobs.py -v

Run with coverage:
    pytest tests/infrastructure/scheduler/test_jobs.py --cov=app.infrastructure.scheduler.jobs --cov-report=term-missing -v
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.scheduler.jobs import cleanup_soft_deleted_users
from app.infrastructure.scheduler.main import schedule_cleanup_soft_deleted_users_job
from app.core.db.crud import user_db
from app.core.db.models import User


class TestCleanupSoftDeletedUsersJob:

    async def _get_user_by_id(self, session: AsyncSession, user_id) -> User | None:
        """Helper to get user by ID including deleted records."""
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def test_cleanup_soft_deleted_users_deletes_old_records(
        self, db_session: AsyncSession
    ):
        # Create a user that was soft-deleted 60 days ago (should be deleted with 30 day threshold)
        old_deleted_user = User(
            id=uuid4(),
            email="old_deleted@example.com",
            password_hash="hash",
            full_name="Old Deleted User",
            email_verified=True,
            is_active=False,
            is_deleted=True,
            deleted_at=datetime.now(timezone.utc) - timedelta(days=60),
        )
        db_session.add(old_deleted_user)
        await db_session.flush()

        user_before = await self._get_user_by_id(db_session, old_deleted_user.id)
        assert user_before is not None

        # Run cleanup with 30 day threshold
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        deleted_count = await user_db.permanently_delete_soft_deleted(
            db_session, cutoff_date, commit_self=False
        )

        assert deleted_count == 1
        user_after = await self._get_user_by_id(db_session, old_deleted_user.id)
        assert user_after is None

    async def test_cleanup_soft_deleted_users_preserves_recent_deleted(
        self, db_session: AsyncSession
    ):
        # Create a user that was soft-deleted 10 days ago (should NOT be deleted with 30 day threshold)
        recent_deleted_user = User(
            id=uuid4(),
            email="recent_deleted@example.com",
            password_hash="hash",
            full_name="Recent Deleted User",
            email_verified=True,
            is_active=False,
            is_deleted=True,
            deleted_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        db_session.add(recent_deleted_user)
        await db_session.flush()

        # Run cleanup with 30 day threshold
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        deleted_count = await user_db.permanently_delete_soft_deleted(
            db_session, cutoff_date, commit_self=False
        )

        assert deleted_count == 0
        user_after = await self._get_user_by_id(db_session, recent_deleted_user.id)
        assert user_after is not None

    async def test_cleanup_soft_deleted_users_preserves_active_users(
        self, db_session: AsyncSession
    ):
        active_user = User(
            id=uuid4(),
            email="active@example.com",
            password_hash="hash",
            full_name="Active User",
            email_verified=True,
            is_active=True,
            is_deleted=False,
            deleted_at=None,
        )
        db_session.add(active_user)
        await db_session.flush()

        # Run cleanup
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        deleted_count = await user_db.permanently_delete_soft_deleted(
            db_session, cutoff_date, commit_self=False
        )

        assert deleted_count == 0
        user_after = await user_db.get_by_id(db_session, active_user.id)
        assert user_after is not None

    async def test_cleanup_soft_deleted_users_handles_multiple_records(
        self, db_session: AsyncSession
    ):
        old_users = []
        for i in range(3):
            user = User(
                id=uuid4(),
                email=f"old_deleted_{i}@example.com",
                password_hash="hash",
                full_name=f"Old Deleted User {i}",
                email_verified=True,
                is_active=False,
                is_deleted=True,
                deleted_at=datetime.now(timezone.utc) - timedelta(days=60 + i),
            )
            db_session.add(user)
            old_users.append(user)
        await db_session.flush()

        # Run cleanup
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        deleted_count = await user_db.permanently_delete_soft_deleted(
            db_session, cutoff_date, commit_self=False
        )

        assert deleted_count == 3
        for user in old_users:
            user_after = await self._get_user_by_id(db_session, user.id)
            assert user_after is None

    async def test_cleanup_soft_deleted_users_handles_no_records(
        self, db_session: AsyncSession
    ):
        # Run cleanup on empty database
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        deleted_count = await user_db.permanently_delete_soft_deleted(
            db_session, cutoff_date, commit_self=False
        )

        assert deleted_count == 0

    async def test_cleanup_job_uses_correct_cutoff_date(self):
        with patch(
            "app.infrastructure.scheduler.jobs.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session = AsyncMock()
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_session
            mock_session_local.begin.return_value = mock_context

            with patch.object(
                user_db, "permanently_delete_soft_deleted", new_callable=AsyncMock
            ) as mock_delete:
                mock_delete.return_value = 5

                # Run the job with 30 day threshold
                await cleanup_soft_deleted_users(days_threshold=30)

                mock_delete.assert_called_once()
                call_args = mock_delete.call_args
                session_arg = call_args[0][0]
                cutoff_arg = call_args[0][1]
                commit_self_arg = call_args[1]["commit_self"]

                assert session_arg == mock_session
                assert commit_self_arg is False

                expected_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
                # Allow 5 seconds tolerance for test execution time
                assert abs((cutoff_arg - expected_cutoff).total_seconds()) < 5


class TestScheduleCleanupSoftDeletedUsersJob:

    def test_schedule_job_with_default_parameters(self):
        with patch("app.infrastructure.scheduler.main.scheduler") as mock_scheduler:
            schedule_cleanup_soft_deleted_users_job()

            mock_scheduler.add_job.assert_called_once()
            call_kwargs = mock_scheduler.add_job.call_args[1]

            assert call_kwargs["replace_existing"] is True
            assert call_kwargs["id"] == "cleanup_soft_deleted_users_job"
            assert call_kwargs["misfire_grace_time"] == 60 * 60  # 1 hour
            assert call_kwargs["kwargs"] == {"days_threshold": 30}
            assert call_kwargs["jobstore"] == "cleanups"

    def test_schedule_job_with_custom_parameters(self):
        with patch("app.infrastructure.scheduler.main.scheduler") as mock_scheduler:
            schedule_cleanup_soft_deleted_users_job(days_threshold=60)

            mock_scheduler.add_job.assert_called_once()
            call_kwargs = mock_scheduler.add_job.call_args[1]

            assert call_kwargs["kwargs"] == {"days_threshold": 60}

    def test_schedule_job_registers_correct_function(self):
        with patch("app.infrastructure.scheduler.main.scheduler") as mock_scheduler:
            schedule_cleanup_soft_deleted_users_job()

            # First positional arg should be the job function
            call_args = mock_scheduler.add_job.call_args[0]
            assert call_args[0] == cleanup_soft_deleted_users

    def test_schedule_job_logs_scheduling(self):
        with patch("app.infrastructure.scheduler.main.scheduler"):
            with patch(
                "app.infrastructure.scheduler.main.scheduler_logger"
            ) as mock_logger:
                schedule_cleanup_soft_deleted_users_job()

                # Should log start and completion
                assert mock_logger.info.call_count == 2
                first_call = mock_logger.info.call_args_list[0][0][0]
                second_call = mock_logger.info.call_args_list[1][0][0]

                assert "Scheduling" in first_call
                assert "3:00 AM UTC" in first_call
                assert "scheduled successfully" in second_call

