"""
Integration tests for Career analysis history router.

Tests all Career analysis history endpoints with real database
and per-test rollback.

Endpoints tested:
- GET /career/history — list analysis history (paginated)
- GET /career/history/{result_id} — get a single analysis result
- DELETE /career/history/{result_id} — soft-delete an analysis result

Run all tests:
    pytest tests/apps/cubex_career/routers/test_history.py -v

Run with coverage:
    pytest tests/apps/cubex_career/routers/test_history.py \
        --cov=app.apps.cubex_career.routers.history --cov-report=term-missing -v
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import FeatureKey

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def analysis_result(db_session: AsyncSession, test_user, career_subscription):
    """Create a single CareerAnalysisResult for test_user."""
    from app.apps.cubex_career.db.models import CareerUsageLog, CareerAnalysisResult
    from app.core.enums import AccessStatus, UsageLogStatus

    usage_log = CareerUsageLog(
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
    db_session.add(usage_log)
    await db_session.flush()

    result = CareerAnalysisResult(
        id=uuid4(),
        usage_log_id=usage_log.id,
        user_id=test_user.id,
        feature_key=FeatureKey.CAREER_JOB_MATCH,
        title="Job Match Analysis",
        result_data={"match_score": 0.85, "strengths": ["Python", "FastAPI"]},
    )
    db_session.add(result)
    await db_session.flush()
    return result


@pytest.fixture
async def multiple_results(db_session: AsyncSession, test_user, career_subscription):
    """Create 5 CareerAnalysisResults across different features for test_user."""
    from app.apps.cubex_career.db.models import CareerUsageLog, CareerAnalysisResult
    from app.core.enums import AccessStatus, UsageLogStatus

    features = [
        FeatureKey.CAREER_JOB_MATCH,
        FeatureKey.CAREER_CAREER_PATH,
        FeatureKey.CAREER_FEEDBACK_ANALYZER,
        FeatureKey.CAREER_JOB_MATCH,
        FeatureKey.CAREER_EXTRACT_KEYWORDS,
    ]

    results = []
    for i, fk in enumerate(features):
        usage_log = CareerUsageLog(
            id=uuid4(),
            user_id=test_user.id,
            subscription_id=career_subscription.id,
            request_id=str(uuid4()),
            feature_key=fk,
            fingerprint_hash=f"{i:064x}",
            access_status=AccessStatus.GRANTED,
            endpoint=f"/test/{fk.value}",
            method="POST",
            credits_reserved=Decimal("1.00"),
            status=UsageLogStatus.SUCCESS,
        )
        db_session.add(usage_log)
        await db_session.flush()

        ar = CareerAnalysisResult(
            id=uuid4(),
            usage_log_id=usage_log.id,
            user_id=test_user.id,
            feature_key=fk,
            title=f"Analysis {i}",
            result_data={"index": i, "feature": fk.value},
        )
        db_session.add(ar)
        await db_session.flush()
        results.append(ar)

    return results


@pytest.fixture
async def other_user_result(db_session: AsyncSession, career_subscription):
    """Create a CareerAnalysisResult owned by a different user."""
    from app.apps.cubex_career.db.models import CareerUsageLog, CareerAnalysisResult
    from app.core.db.models import User
    from app.core.enums import AccessStatus, UsageLogStatus

    other_user = User(
        id=uuid4(),
        email="other-history@example.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.vwPbgsgNJwKrWe",
        full_name="Other User",
        email_verified=True,
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.flush()

    usage_log = CareerUsageLog(
        id=uuid4(),
        user_id=other_user.id,
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
    db_session.add(usage_log)
    await db_session.flush()

    result = CareerAnalysisResult(
        id=uuid4(),
        usage_log_id=usage_log.id,
        user_id=other_user.id,
        feature_key=FeatureKey.CAREER_CAREER_PATH,
        title="Career Path Analysis",
        result_data={"path": "engineering"},
    )
    db_session.add(result)
    await db_session.flush()
    return result


# ---------------------------------------------------------------------------
# Router setup tests
# ---------------------------------------------------------------------------


class TestHistoryRouterSetup:

    def test_history_router_import(self):
        from app.apps.cubex_career.routers.history import router

        assert router is not None

    def test_history_router_export(self):
        from app.apps.cubex_career.routers import history_router

        assert history_router is not None

    def test_history_router_prefix(self):
        from app.apps.cubex_career.routers.history import router

        assert router.prefix == "/history"

    def test_history_router_has_list_endpoint(self):
        from app.apps.cubex_career.routers.history import router

        paths = [r.path for r in router.routes if hasattr(r, "path")]  # type: ignore[attr-defined]
        assert "/history" in paths

    def test_history_router_has_detail_endpoint(self):
        from app.apps.cubex_career.routers.history import router

        paths = [r.path for r in router.routes if hasattr(r, "path")]  # type: ignore[attr-defined]
        assert "/history/{result_id}" in paths

    def test_history_router_has_delete_endpoint(self):
        from app.apps.cubex_career.routers.history import router

        paths = [r.path for r in router.routes if hasattr(r, "path")]  # type: ignore[attr-defined]
        assert "/history/{result_id}" in paths


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------


class TestHistoryAuthentication:

    @pytest.mark.asyncio
    async def test_list_history_unauthenticated_returns_401(self, client: AsyncClient):
        response = await client.get("/career/history")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_result_unauthenticated_returns_401(self, client: AsyncClient):
        response = await client.get(f"/career/history/{uuid4()}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_result_unauthenticated_returns_401(self, client: AsyncClient):
        response = await client.delete(f"/career/history/{uuid4()}")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# List history tests
# ---------------------------------------------------------------------------


class TestListHistory:
    """Tests for GET /career/history"""

    @pytest.mark.asyncio
    async def test_list_history_empty_returns_200(
        self, authenticated_client: AsyncClient
    ):
        response = await authenticated_client.get("/career/history")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_list_history_returns_user_results(
        self, authenticated_client: AsyncClient, analysis_result
    ):
        response = await authenticated_client.get("/career/history")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["id"] == str(analysis_result.id)
        assert item["feature_key"] == FeatureKey.CAREER_JOB_MATCH.value
        assert item["title"] == "Job Match Analysis"
        assert "created_at" in item

    @pytest.mark.asyncio
    async def test_list_history_excludes_other_users(
        self, authenticated_client: AsyncClient, other_user_result
    ):
        response = await authenticated_client.get("/career/history")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    @pytest.mark.asyncio
    async def test_list_history_filter_by_feature_key(
        self, authenticated_client: AsyncClient, multiple_results
    ):
        response = await authenticated_client.get(
            "/career/history",
            params={"feature_key": FeatureKey.CAREER_JOB_MATCH.value},
        )

        assert response.status_code == 200
        data = response.json()
        # multiple_results has 2 JOB_MATCH results
        assert len(data["items"]) == 2
        for item in data["items"]:
            assert item["feature_key"] == FeatureKey.CAREER_JOB_MATCH.value

    @pytest.mark.asyncio
    async def test_list_history_filter_by_feature_key_no_match(
        self, authenticated_client: AsyncClient, analysis_result
    ):
        response = await authenticated_client.get(
            "/career/history",
            params={"feature_key": FeatureKey.CAREER_CAREER_PATH.value},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    @pytest.mark.asyncio
    async def test_list_history_respects_limit(
        self, authenticated_client: AsyncClient, multiple_results
    ):
        response = await authenticated_client.get(
            "/career/history",
            params={"limit": 2},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_list_history_pagination_cursor(
        self, authenticated_client: AsyncClient, multiple_results
    ):
        # First page
        response1 = await authenticated_client.get(
            "/career/history",
            params={"limit": 3},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["items"]) == 3
        assert data1["has_more"] is True

        # Second page using cursor
        response2 = await authenticated_client.get(
            "/career/history",
            params={"limit": 3, "before": data1["next_cursor"]},
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["items"]) == 2
        assert data2["has_more"] is False

        # No overlap between pages
        ids_page1 = {item["id"] for item in data1["items"]}
        ids_page2 = {item["id"] for item in data2["items"]}
        assert ids_page1.isdisjoint(ids_page2)

    @pytest.mark.asyncio
    async def test_list_history_ordered_newest_first(
        self, authenticated_client: AsyncClient, multiple_results
    ):
        response = await authenticated_client.get("/career/history")

        assert response.status_code == 200
        data = response.json()
        dates = [item["created_at"] for item in data["items"]]
        assert dates == sorted(dates, reverse=True)

    @pytest.mark.asyncio
    async def test_list_history_limit_validation_min(
        self, authenticated_client: AsyncClient
    ):
        response = await authenticated_client.get(
            "/career/history",
            params={"limit": 0},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_history_limit_validation_max(
        self, authenticated_client: AsyncClient
    ):
        response = await authenticated_client.get(
            "/career/history",
            params={"limit": 101},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Get result tests
# ---------------------------------------------------------------------------


class TestGetResult:
    """Tests for GET /career/history/{result_id}"""

    @pytest.mark.asyncio
    async def test_get_result_success(
        self, authenticated_client: AsyncClient, analysis_result
    ):
        response = await authenticated_client.get(
            f"/career/history/{analysis_result.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(analysis_result.id)
        assert data["usage_log_id"] == str(analysis_result.usage_log_id)
        assert data["feature_key"] == FeatureKey.CAREER_JOB_MATCH.value
        assert data["title"] == "Job Match Analysis"
        assert data["result_data"]["match_score"] == 0.85
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_get_result_not_found_returns_404(
        self, authenticated_client: AsyncClient
    ):
        response = await authenticated_client.get(f"/career/history/{uuid4()}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_result_other_users_result_returns_404(
        self, authenticated_client: AsyncClient, other_user_result
    ):
        response = await authenticated_client.get(
            f"/career/history/{other_user_result.id}"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_result_includes_full_result_data(
        self, authenticated_client: AsyncClient, analysis_result
    ):
        response = await authenticated_client.get(
            f"/career/history/{analysis_result.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "result_data" in data
        assert isinstance(data["result_data"], dict)
        assert data["result_data"]["strengths"] == ["Python", "FastAPI"]


# ---------------------------------------------------------------------------
# Delete result tests
# ---------------------------------------------------------------------------


class TestDeleteResult:
    """Tests for DELETE /career/history/{result_id}"""

    @pytest.mark.asyncio
    async def test_delete_result_success_returns_204(
        self, authenticated_client: AsyncClient, analysis_result
    ):
        response = await authenticated_client.delete(
            f"/career/history/{analysis_result.id}"
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_result_not_found_returns_404(
        self, authenticated_client: AsyncClient
    ):
        response = await authenticated_client.delete(f"/career/history/{uuid4()}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_result_other_users_result_returns_404(
        self, authenticated_client: AsyncClient, other_user_result
    ):
        response = await authenticated_client.delete(
            f"/career/history/{other_user_result.id}"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_deleted_result_excluded_from_list(
        self, authenticated_client: AsyncClient, analysis_result
    ):
        # Delete
        delete_resp = await authenticated_client.delete(
            f"/career/history/{analysis_result.id}"
        )
        assert delete_resp.status_code == 204

        # List should be empty
        list_resp = await authenticated_client.get("/career/history")
        assert list_resp.status_code == 200
        assert len(list_resp.json()["items"]) == 0

    @pytest.mark.asyncio
    async def test_deleted_result_returns_404_on_get(
        self, authenticated_client: AsyncClient, analysis_result
    ):
        # Delete
        delete_resp = await authenticated_client.delete(
            f"/career/history/{analysis_result.id}"
        )
        assert delete_resp.status_code == 204

        # Get should 404
        get_resp = await authenticated_client.get(
            f"/career/history/{analysis_result.id}"
        )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_is_idempotent_returns_404_on_second_call(
        self, authenticated_client: AsyncClient, analysis_result
    ):
        # First delete
        resp1 = await authenticated_client.delete(
            f"/career/history/{analysis_result.id}"
        )
        assert resp1.status_code == 204

        # Second delete returns 404 (already soft-deleted)
        resp2 = await authenticated_client.delete(
            f"/career/history/{analysis_result.id}"
        )
        assert resp2.status_code == 404
