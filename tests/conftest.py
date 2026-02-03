"""
Pytest configuration and shared fixtures.

Provides fixtures for integration tests using real test database with per-test rollback.
All fixtures are function-scoped for complete test isolation.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


# ============================================================================
# Test Utilities
# ============================================================================


def create_test_access_token(user) -> str:
    """Create a test access token for a user."""
    from app.shared.utils import create_jwt_token

    return create_jwt_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "type": "access",
        },
        expires_delta=timedelta(minutes=15),
    )


# ============================================================================
# Pytest Configuration
# ============================================================================


def pytest_configure(config):
    """Configure pytest with custom settings."""
    os.environ["ENVIRONMENT"] = "test"

    # Point DATABASE_URL to TEST_DATABASE_URL so the app uses the test database
    test_db_url = os.environ.get("TEST_DATABASE_URL")
    if test_db_url:
        os.environ["DATABASE_URL"] = test_db_url

    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require real database)",
    )


# ============================================================================
# Session-Scoped Database Setup (runs once per test session)
# ============================================================================


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default event loop policy for the session."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session", autouse=True)
def setup_test_database(event_loop_policy):
    """Run database migrations at session start and clear tables at session end.

    This fixture:
    1. Runs alembic migrations to ensure test database has correct schema
    2. After all tests complete, truncates all tables to clean up

    Uses autouse=True so it runs automatically for every test session.
    """
    import asyncio
    import subprocess
    import sys

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.shared.config import settings

    if not settings.TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not configured")

    # Save the original DATABASE_URL to restore later
    original_database_url = os.environ.get("DATABASE_URL")

    # Set the database URL for alembic to use
    os.environ["DATABASE_URL"] = settings.TEST_DATABASE_URL

    try:
        # Run migrations using alembic CLI
        print("\n[TEST] Running database migrations for test database...")
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,  # Project root
        )

        if result.returncode != 0:
            print(f"[TEST] Migration failed: {result.stderr}")
            pytest.fail(f"Database migration failed: {result.stderr}")
        else:
            print("[TEST] Database migrations completed successfully")

        # Yield the test database URL for tests that need it
        yield settings.TEST_DATABASE_URL

        # Cleanup: Truncate all tables after tests complete (except seed data tables)
        print("\n[TEST] Cleaning up test database...")

        async def cleanup_database():
            engine = create_async_engine(
                settings.TEST_DATABASE_URL,
                echo=False,
            )

            # Tables to preserve (contain seed data from migrations)
            preserved_tables = {"alembic_version", "plans"}

            async with engine.begin() as conn:
                # Get all table names (excluding preserved tables)
                result = await conn.execute(
                    text(
                        """
                        SELECT tablename FROM pg_tables
                        WHERE schemaname = 'public'
                    """
                    )
                )
                all_tables = [row[0] for row in result.fetchall()]
                tables = [t for t in all_tables if t not in preserved_tables]

                if tables:
                    # Truncate all tables with CASCADE to handle foreign keys
                    table_list = ", ".join(f'"{t}"' for t in tables)
                    await conn.execute(
                        text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")
                    )
                    print(
                        f"[TEST] Truncated {len(tables)} tables (preserved: {preserved_tables})"
                    )
                else:
                    print("[TEST] No tables to truncate")

            await engine.dispose()

        # Run the async cleanup
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cleanup_database())
        finally:
            loop.close()

        print("[TEST] Test database cleanup completed")

    finally:
        # ALWAYS restore the original DATABASE_URL, even if an error occurred
        if original_database_url is not None:
            os.environ["DATABASE_URL"] = original_database_url
            print("[TEST] Restored original DATABASE_URL")
        elif "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
            print("[TEST] Removed temporary DATABASE_URL")


# ============================================================================
# Database Fixtures (all function-scoped for isolation)
# ============================================================================


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session with transaction rollback.

    Strategy:
    1. Create connection and start an outer transaction (for final rollback)
    2. Create session bound to that connection
    3. The test fixtures use this session directly (within the outer transaction)
    4. When routers call `async with session.begin():`, we intercept it to use
       begin_nested() which creates a savepoint within our outer transaction
    5. After the test, we rollback the outer transaction

    This allows:
    - Test fixtures to add data (within the outer transaction)
    - Routers to use their normal begin() calls (converted to savepoints)
    - Complete rollback after each test
    """
    from app.shared.config import settings

    if not settings.TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not configured")

    # Create a fresh engine for this test
    engine = create_async_engine(
        settings.TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

    # Create connection
    connection = await engine.connect()

    # Start outer transaction for final rollback
    outer_transaction = await connection.begin()

    # Create session bound to this connection
    # autobegin=True so test fixtures can use session without manual begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        autobegin=True,  # Allow test fixtures to work without explicit begin()
    )

    # Store the original begin method and patch it
    # When the app calls session.begin(), use begin_nested() (savepoint) instead
    # This allows router code with `async with session.begin():` to work
    # while keeping everything within our outer transaction
    _original_begin = session.begin

    def _patched_begin():
        return session.begin_nested()

    session.begin = _patched_begin

    try:
        yield session
    finally:
        # Rollback the outer transaction (undoes all test changes)
        await session.close()
        await outer_transaction.rollback()
        await connection.close()
        await engine.dispose()


# ============================================================================
# Application Fixtures
# ============================================================================


@pytest.fixture
def app():
    """Create FastAPI application for testing."""
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture
async def client(app, db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide async HTTP client with session override.

    Overrides the app's session dependency so the app uses the same
    session as the test fixtures. This allows tests to set up data
    that the app can see within the same transaction.
    """
    from app.core.dependencies import get_async_session

    # Override to yield the test session (no transaction management here)
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_async_session, None)


# ============================================================================
# Stripe Mock Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def mock_stripe():
    """Auto-mock Stripe API calls to prevent real HTTP requests.

    This fixture automatically applies to all tests to prevent:
    1. Real Stripe API calls during integration tests
    2. Async cleanup issues ("Event loop is closed" errors)
    3. Test flakiness from network failures

    We mock at the service layer to avoid Pydantic validation complexity.
    """

    # Create a mock that returns the subscription model unchanged
    async def mock_cancel_subscription(subscription_id, **kwargs):
        """Mock cancel_subscription that doesn't call Stripe."""
        return AsyncMock(
            id=subscription_id,
            status="canceled",
            cancel_at_period_end=kwargs.get("cancel_at_period_end", False),
        )

    with patch(
        "app.shared.services.payment.stripe.main.Stripe.cancel_subscription",
        side_effect=mock_cancel_subscription,
    ), patch(
        "app.shared.services.payment.stripe.main.Stripe.create_checkout_session",
        new_callable=AsyncMock,
    ), patch(
        "app.shared.services.payment.stripe.main.Stripe.create_customer_portal_session",
        new_callable=AsyncMock,
    ), patch(
        "app.shared.services.payment.stripe.main.Stripe._request",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture(autouse=True)
def mock_email_service():
    """Auto-mock email/messaging services to prevent real sends and async issues.

    This fixture mocks:
    1. The message queue publisher to prevent RabbitMQ connections
    2. Avoid async event loop cleanup issues

    Note: We must patch publish_event in each module that imports it,
    because Python binds the import to the module's namespace.
    """

    async def mock_publish_event(*args, **kwargs):
        """Mock publish_event that doesn't use RabbitMQ."""
        return None

    with patch(
        "app.infrastructure.messaging.publisher.publish_event",
        side_effect=mock_publish_event,
    ), patch(
        "app.shared.services.auth.publish_event",
        side_effect=mock_publish_event,
    ), patch(
        "app.apps.cubex_api.services.workspace.publish_event",
        side_effect=mock_publish_event,
    ), patch(
        "app.apps.cubex_api.services.subscription.publish_event",
        side_effect=mock_publish_event,
    ), patch(
        "app.apps.cubex_career.services.subscription.publish_event",
        side_effect=mock_publish_event,
    ), patch(
        "app.shared.routers.webhook.publish_event",
        side_effect=mock_publish_event,
    ), patch(
        "app.infrastructure.messaging.handlers.stripe.publish_event",
        side_effect=mock_publish_event,
    ):
        yield


# ============================================================================
# User Fixtures
# ============================================================================


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user in the database."""
    from app.shared.db.models import User

    user = User(
        id=uuid4(),
        email="testuser@example.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.vwPbgsgNJwKrWe",
        full_name="Test User",
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def test_user_unverified(db_session: AsyncSession):
    """Create an unverified test user."""
    from app.shared.db.models import User

    user = User(
        id=uuid4(),
        email="unverified@example.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.vwPbgsgNJwKrWe",
        full_name="Unverified User",
        email_verified=False,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def auth_headers(test_user) -> dict[str, str]:
    """Generate authentication headers for test user."""
    from datetime import timedelta

    from app.shared.utils import create_jwt_token

    access_token = create_jwt_token(
        data={
            "sub": str(test_user.id),
            "email": test_user.email,
            "type": "access",
        },
        expires_delta=timedelta(minutes=15),
    )
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def authenticated_client(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> AsyncClient:
    """Provide authenticated async client."""
    client.headers.update(auth_headers)
    return client


# ============================================================================
# Plan Fixtures
# ============================================================================


@pytest.fixture
async def free_api_plan(db_session: AsyncSession):
    """Get the free API plan from seeded data."""
    from sqlalchemy import select

    from app.shared.db.models import Plan
    from app.shared.enums import PlanType, ProductType

    result = await db_session.execute(
        select(Plan).where(
            Plan.product_type == ProductType.API,
            Plan.type == PlanType.FREE,
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        pytest.skip("Free API plan not seeded")
    return plan


@pytest.fixture
async def basic_api_plan(db_session: AsyncSession):
    """Get the basic API plan from seeded data."""
    from sqlalchemy import select

    from app.shared.db.models import Plan
    from app.shared.enums import ProductType

    result = await db_session.execute(
        select(Plan).where(
            Plan.product_type == ProductType.API,
            Plan.name == "Basic",
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        pytest.skip("Basic API plan not seeded")
    return plan


@pytest.fixture
async def professional_api_plan(db_session: AsyncSession):
    """Get the professional API plan from seeded data."""
    from sqlalchemy import select

    from app.shared.db.models import Plan
    from app.shared.enums import ProductType

    result = await db_session.execute(
        select(Plan).where(
            Plan.product_type == ProductType.API,
            Plan.name == "Professional",
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        pytest.skip("Professional API plan not seeded")
    return plan


@pytest.fixture
async def free_career_plan(db_session: AsyncSession):
    """Get the free Career plan from seeded data."""
    from sqlalchemy import select

    from app.shared.db.models import Plan
    from app.shared.enums import PlanType, ProductType

    result = await db_session.execute(
        select(Plan).where(
            Plan.product_type == ProductType.CAREER,
            Plan.type == PlanType.FREE,
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        pytest.skip("Free Career plan not seeded")
    return plan


@pytest.fixture
async def plus_career_plan(db_session: AsyncSession):
    """Get the Plus Career plan from seeded data."""
    from sqlalchemy import select

    from app.shared.db.models import Plan
    from app.shared.enums import ProductType

    result = await db_session.execute(
        select(Plan).where(
            Plan.product_type == ProductType.CAREER,
            Plan.name == "Plus Plan",
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        pytest.skip("Plus Career plan not seeded")
    return plan


@pytest.fixture
async def pro_career_plan(db_session: AsyncSession):
    """Get the Pro Career plan from seeded data."""
    from sqlalchemy import select

    from app.shared.db.models import Plan
    from app.shared.enums import ProductType

    result = await db_session.execute(
        select(Plan).where(
            Plan.product_type == ProductType.CAREER,
            Plan.name == "Pro Plan",
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        pytest.skip("Pro Career plan not seeded")
    return plan


# ============================================================================
# Workspace Fixtures
# ============================================================================


@pytest.fixture
async def test_workspace(db_session: AsyncSession, test_user):
    """Create a test workspace owned by test_user."""
    from app.shared.db.models import Workspace, WorkspaceMember
    from app.shared.enums import MemberRole, MemberStatus, WorkspaceStatus

    workspace = Workspace(
        id=uuid4(),
        display_name="Test Workspace",
        slug="test-workspace",
        status=WorkspaceStatus.ACTIVE,
        is_personal=False,
        owner_id=test_user.id,
    )
    db_session.add(workspace)
    await db_session.flush()

    member = WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=test_user.id,
        role=MemberRole.OWNER,
        status=MemberStatus.ENABLED,
        joined_at=datetime.now(timezone.utc),
    )
    db_session.add(member)
    await db_session.flush()

    return workspace


@pytest.fixture
async def personal_workspace(db_session: AsyncSession, test_user, free_api_plan):
    """Create a personal workspace for test_user with a free subscription."""
    from app.shared.db.models import (
        APISubscriptionContext,
        Subscription,
        Workspace,
        WorkspaceMember,
    )
    from app.shared.enums import (
        MemberRole,
        MemberStatus,
        SubscriptionStatus,
        WorkspaceStatus,
    )

    workspace = Workspace(
        id=uuid4(),
        display_name=f"{test_user.full_name}'s Workspace",
        slug=f"personal-{test_user.id.hex[:8]}",
        status=WorkspaceStatus.ACTIVE,
        is_personal=True,
        owner_id=test_user.id,
    )
    db_session.add(workspace)
    await db_session.flush()

    member = WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=test_user.id,
        role=MemberRole.OWNER,
        status=MemberStatus.ENABLED,
        joined_at=datetime.now(timezone.utc),
    )
    db_session.add(member)
    await db_session.flush()

    # Create subscription for personal workspace
    subscription = Subscription(
        id=uuid4(),
        plan_id=free_api_plan.id,
        status=SubscriptionStatus.ACTIVE,
        seat_count=1,
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(subscription)
    await db_session.flush()

    context = APISubscriptionContext(
        id=uuid4(),
        subscription_id=subscription.id,
        workspace_id=workspace.id,
    )
    db_session.add(context)
    await db_session.flush()

    return workspace


@pytest.fixture
async def test_workspace_member(db_session: AsyncSession, test_workspace):
    """Create another user who is a member of test_workspace."""
    from app.shared.db.models import User, WorkspaceMember
    from app.shared.enums import MemberRole, MemberStatus

    user = User(
        id=uuid4(),
        email="member@example.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.vwPbgsgNJwKrWe",
        full_name="Workspace Member",
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    member = WorkspaceMember(
        id=uuid4(),
        workspace_id=test_workspace.id,
        user_id=user.id,
        role=MemberRole.MEMBER,
        status=MemberStatus.ENABLED,
        joined_at=datetime.now(timezone.utc),
    )
    db_session.add(member)
    await db_session.flush()

    return user, member


@pytest.fixture
async def test_workspace_admin(db_session: AsyncSession, test_workspace):
    """Create another user who is an admin of test_workspace."""
    from app.shared.db.models import User, WorkspaceMember
    from app.shared.enums import MemberRole, MemberStatus

    user = User(
        id=uuid4(),
        email="admin@example.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.vwPbgsgNJwKrWe",
        full_name="Workspace Admin",
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    member = WorkspaceMember(
        id=uuid4(),
        workspace_id=test_workspace.id,
        user_id=user.id,
        role=MemberRole.ADMIN,
        status=MemberStatus.ENABLED,
        joined_at=datetime.now(timezone.utc),
    )
    db_session.add(member)
    await db_session.flush()

    return user, member


# ============================================================================
# Subscription Fixtures
# ============================================================================


@pytest.fixture
async def test_subscription(db_session: AsyncSession, test_workspace, basic_api_plan):
    """Create a test subscription for the workspace."""
    from app.shared.db.models import APISubscriptionContext, Subscription
    from app.shared.enums import SubscriptionStatus

    subscription = Subscription(
        id=uuid4(),
        plan_id=basic_api_plan.id,
        status=SubscriptionStatus.ACTIVE,
        stripe_subscription_id=f"sub_test_{uuid4().hex[:12]}",
        stripe_customer_id=f"cus_test_{uuid4().hex[:12]}",
        seat_count=5,
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(subscription)
    await db_session.flush()

    context = APISubscriptionContext(
        id=uuid4(),
        subscription_id=subscription.id,
        workspace_id=test_workspace.id,
    )
    db_session.add(context)
    await db_session.flush()

    return subscription


@pytest.fixture
async def career_subscription(db_session: AsyncSession, test_user, free_career_plan):
    """Create a career subscription for test user."""
    from app.shared.db.models import CareerSubscriptionContext, Subscription
    from app.shared.enums import ProductType, SubscriptionStatus

    subscription = Subscription(
        id=uuid4(),
        plan_id=free_career_plan.id,
        product_type=ProductType.CAREER,  # Must set for career subscriptions!
        status=SubscriptionStatus.ACTIVE,
        seat_count=1,
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(subscription)
    await db_session.flush()

    context = CareerSubscriptionContext(
        id=uuid4(),
        subscription_id=subscription.id,
        user_id=test_user.id,
    )
    db_session.add(context)
    await db_session.flush()

    return subscription


@pytest.fixture
async def paid_career_subscription(
    db_session: AsyncSession, test_user, plus_career_plan
):
    """Create a paid career subscription for test user."""
    from app.shared.db.models import CareerSubscriptionContext, Subscription
    from app.shared.enums import ProductType, SubscriptionStatus

    subscription = Subscription(
        id=uuid4(),
        plan_id=plus_career_plan.id,
        product_type=ProductType.CAREER,  # Must set for career subscriptions!
        status=SubscriptionStatus.ACTIVE,
        stripe_subscription_id=f"sub_test_{uuid4().hex[:12]}",
        stripe_customer_id=f"cus_test_{uuid4().hex[:12]}",
        seat_count=1,
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(subscription)
    await db_session.flush()

    context = CareerSubscriptionContext(
        id=uuid4(),
        subscription_id=subscription.id,
        user_id=test_user.id,
    )
    db_session.add(context)
    await db_session.flush()

    return subscription


# ============================================================================
# Invitation Fixtures
# ============================================================================


@pytest.fixture
async def test_invitation(db_session: AsyncSession, test_workspace, test_user):
    """Create a test workspace invitation.

    Returns a tuple of (invitation, raw_token) so tests can use the raw token.
    """
    import secrets

    from app.shared.config import settings
    from app.shared.db.models import WorkspaceInvitation
    from app.shared.enums import InvitationStatus, MemberRole
    from app.shared.utils import hmac_hash_otp

    # Generate raw token and its hash (same as WorkspaceService._generate_secure_token)
    raw_token = secrets.token_urlsafe(32)
    token_hash = hmac_hash_otp(raw_token, settings.OTP_HMAC_SECRET)

    invitation = WorkspaceInvitation(
        id=uuid4(),
        workspace_id=test_workspace.id,
        email="invited@example.com",
        role=MemberRole.MEMBER,
        status=InvitationStatus.PENDING,
        token_hash=token_hash,
        inviter_id=test_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(invitation)
    await db_session.flush()

    # Return both invitation and raw token for test use
    return invitation, raw_token


@pytest.fixture
async def expired_invitation(db_session: AsyncSession, test_workspace, test_user):
    """Create an expired workspace invitation.

    Returns a tuple of (invitation, raw_token) so tests can use the raw token.
    """
    import secrets

    from app.shared.config import settings
    from app.shared.db.models import WorkspaceInvitation
    from app.shared.enums import InvitationStatus, MemberRole
    from app.shared.utils import hmac_hash_otp

    # Generate raw token and its hash
    raw_token = secrets.token_urlsafe(32)
    token_hash = hmac_hash_otp(raw_token, settings.OTP_HMAC_SECRET)

    invitation = WorkspaceInvitation(
        id=uuid4(),
        workspace_id=test_workspace.id,
        email="expired@example.com",
        role=MemberRole.MEMBER,
        status=InvitationStatus.PENDING,
        token_hash=token_hash,
        inviter_id=test_user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(invitation)
    await db_session.flush()

    # Return both invitation and raw token for test use
    return invitation, raw_token


# ============================================================================
# Path Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def app_root(project_root: Path) -> Path:
    """Return the app root directory."""
    return project_root / "app"


# ============================================================================
# Mock Settings Fixture
# ============================================================================


@pytest.fixture
def mock_settings():
    """Provide mock settings for testing."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.JWT_SECRET_KEY = "test_secret_key_for_testing_only"
    settings.JWT_ALGORITHM = "HS256"
    settings.ENVIRONMENT = "test"
    settings.DEBUG = True
    settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"

    return settings
