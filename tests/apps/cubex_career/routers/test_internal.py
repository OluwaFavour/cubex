"""
Test suite for Career Internal API Router.

- POST /career/internal/usage/validate - validates user and logs usage
- POST /career/internal/usage/commit - commits usage as success or failure
- X-Internal-API-Key + Bearer JWT authentication

Run all tests:
    pytest tests/apps/cubex_career/routers/test_internal.py -v

Run with coverage:
    pytest tests/apps/cubex_career/routers/test_internal.py \
        --cov=app.apps.cubex_career.routers.internal --cov-report=term-missing -v
"""

import hashlib
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import AccessStatus, FeatureKey


def _generate_payload_hash(data: str = "") -> str:
    """Generate a valid 64-char hex payload hash."""
    if not data:
        data = str(uuid4())
    return hashlib.sha256(data.encode()).hexdigest()


def make_validate_request(
    request_id: str | None = None,
    feature_key: str = FeatureKey.CAREER_CAREER_PATH.value,
    endpoint: str = "/test/endpoint",
    method: str = "POST",
    payload_hash: str | None = None,
    **extra,
) -> dict:
    """Helper to create valid career usage validate request."""
    if request_id is None:
        request_id = str(uuid4())
    if payload_hash is None:
        payload_hash = _generate_payload_hash()
    return {
        "request_id": request_id,
        "feature_key": feature_key,
        "endpoint": endpoint,
        "method": method,
        "payload_hash": payload_hash,
        **extra,
    }


def _make_auth_headers(user) -> dict[str, str]:
    """Generate Bearer + Internal API key headers for a user."""
    from app.core.utils import create_jwt_token

    access_token = create_jwt_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "type": "access",
        },
        expires_delta=timedelta(minutes=15),
    )
    return {
        "Authorization": f"Bearer {access_token}",
        "X-Internal-API-Key": settings.INTERNAL_API_SECRET,
    }


class TestCareerInternalRouterSetup:

    def test_internal_router_import(self):
        from app.apps.cubex_career.routers.internal import router

        assert router is not None

    def test_internal_router_export(self):
        from app.apps.cubex_career.routers import internal_router

        assert internal_router is not None

    def test_internal_router_prefix(self):
        from app.apps.cubex_career.routers.internal import router

        assert router.prefix == "/internal"

    def test_internal_router_tags(self):
        from app.apps.cubex_career.routers.internal import router

        assert "Career - Internal API" in router.tags

    def test_internal_router_has_validate_endpoint(self):
        from app.apps.cubex_career.routers.internal import router

        paths = [r.path for r in router.routes if hasattr(r, "path")]  # type: ignore[attr-defined]
        assert "/internal/usage/validate" in paths

    def test_internal_router_has_commit_endpoint(self):
        from app.apps.cubex_career.routers.internal import router

        paths = [r.path for r in router.routes if hasattr(r, "path")]  # type: ignore[attr-defined]
        assert "/internal/usage/commit" in paths


class TestCareerInternalAuthentication:

    @pytest.mark.asyncio
    async def test_missing_both_headers_returns_401(self, client: AsyncClient):
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_internal_api_key_returns_401(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ):
        # Only Bearer token, no internal API key
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=auth_headers,
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_internal_api_key_returns_401(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ):
        headers = {**auth_headers, "X-Internal-API-Key": "wrong_key"}
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=headers,
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_bearer_token_returns_401(self, client: AsyncClient):
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=headers,
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_bearer_token_returns_401(self, client: AsyncClient):
        headers = {
            "Authorization": "Bearer invalid_token",
            "X-Internal-API-Key": settings.INTERNAL_API_SECRET,
        }
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=headers,
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_commit_missing_internal_api_key_returns_401(
        self, client: AsyncClient
    ):
        response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(uuid4()),
                "usage_id": str(uuid4()),
                "success": True,
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_commit_invalid_internal_api_key_returns_401(
        self, client: AsyncClient
    ):
        response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(uuid4()),
                "usage_id": str(uuid4()),
                "success": True,
            },
            headers={"X-Internal-API-Key": "wrong_key"},
        )
        assert response.status_code == 401


class TestCareerInternalRequestValidation:

    @pytest.fixture
    def headers(self, test_user) -> dict[str, str]:
        return _make_auth_headers(test_user)

    @pytest.mark.asyncio
    async def test_validate_missing_request_id(
        self, client: AsyncClient, headers: dict[str, str]
    ):
        response = await client.post(
            "/career/internal/usage/validate",
            json={
                "feature_key": FeatureKey.CAREER_CAREER_PATH.value,
                "endpoint": "/test",
                "method": "POST",
                "payload_hash": _generate_payload_hash(),
            },
            headers=headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validate_missing_feature_key(
        self, client: AsyncClient, headers: dict[str, str]
    ):
        response = await client.post(
            "/career/internal/usage/validate",
            json={
                "request_id": str(uuid4()),
                "endpoint": "/test",
                "method": "POST",
                "payload_hash": _generate_payload_hash(),
            },
            headers=headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validate_invalid_feature_key(
        self, client: AsyncClient, headers: dict[str, str]
    ):
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(feature_key="invalid.feature_key"),
            headers=headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validate_invalid_payload_hash_format(
        self, client: AsyncClient, headers: dict[str, str]
    ):
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(payload_hash="not_a_valid_hash"),
            headers=headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validate_with_valid_usage_estimate(
        self, client: AsyncClient, headers: dict[str, str]
    ):
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(
                usage_estimate={
                    "input_chars": 1000,
                    "max_output_tokens": 500,
                    "model": "gpt-4o",
                }
            ),
            headers=headers,
        )
        # Should not fail on validation; may be 402 (no subscription)
        assert response.status_code != 422

    @pytest.mark.asyncio
    async def test_validate_with_empty_usage_estimate_fails(
        self, client: AsyncClient, headers: dict[str, str]
    ):
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(usage_estimate={}),
            headers=headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_commit_missing_user_id(self, client: AsyncClient):
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        response = await client.post(
            "/career/internal/usage/commit",
            json={
                "usage_id": str(uuid4()),
                "success": True,
            },
            headers=headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_commit_missing_usage_id(self, client: AsyncClient):
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(uuid4()),
                "success": True,
            },
            headers=headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_commit_invalid_uuid_usage_id(self, client: AsyncClient):
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(uuid4()),
                "usage_id": "not-a-uuid",
                "success": True,
            },
            headers=headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_commit_missing_success_field(self, client: AsyncClient):
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(uuid4()),
                "usage_id": str(uuid4()),
            },
            headers=headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_commit_failure_without_details_returns_422(
        self, client: AsyncClient
    ):
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(uuid4()),
                "usage_id": str(uuid4()),
                "success": False,
                # Missing failure details
            },
            headers=headers,
        )
        assert response.status_code == 422


class TestCareerInternalResponseFormat:

    @pytest.fixture
    def headers(self, test_user) -> dict[str, str]:
        return _make_auth_headers(test_user)

    @pytest.mark.asyncio
    async def test_validate_response_has_access_field(
        self, client: AsyncClient, headers: dict[str, str]
    ):
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=headers,
        )
        data = response.json()
        assert "access" in data
        assert data["access"] in [
            AccessStatus.GRANTED.value,
            AccessStatus.DENIED.value,
        ]

    @pytest.mark.asyncio
    async def test_validate_response_has_user_id_field(
        self, client: AsyncClient, headers: dict[str, str]
    ):
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=headers,
        )
        data = response.json()
        assert "user_id" in data

    @pytest.mark.asyncio
    async def test_validate_response_has_message_field(
        self, client: AsyncClient, headers: dict[str, str]
    ):
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=headers,
        )
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_validate_response_has_credits_reserved_field(
        self, client: AsyncClient, headers: dict[str, str]
    ):
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=headers,
        )
        data = response.json()
        assert "credits_reserved" in data

    @pytest.mark.asyncio
    async def test_commit_response_has_success_field(self, client: AsyncClient):
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(uuid4()),
                "usage_id": str(uuid4()),
                "success": True,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert isinstance(data["success"], bool)

    @pytest.mark.asyncio
    async def test_commit_response_has_message_field(self, client: AsyncClient):
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(uuid4()),
                "usage_id": str(uuid4()),
                "success": True,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert isinstance(data["message"], str)


class TestCareerInternalNoSubscription:

    @pytest.fixture
    def headers(self, test_user) -> dict[str, str]:
        return _make_auth_headers(test_user)

    @pytest.mark.asyncio
    async def test_validate_no_subscription_returns_402(
        self, client: AsyncClient, headers: dict[str, str]
    ):
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=headers,
        )
        assert response.status_code == 402
        data = response.json()
        assert data["access"] == AccessStatus.DENIED.value
        assert "subscription" in data["message"].lower()


class TestCareerInternalCommitEndpoint:

    @pytest.mark.asyncio
    async def test_commit_nonexistent_usage_returns_idempotent(
        self, client: AsyncClient
    ):
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(uuid4()),
                "usage_id": str(uuid4()),
                "success": True,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "idempotent" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_commit_with_metrics(self, client: AsyncClient):
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(uuid4()),
                "usage_id": str(uuid4()),
                "success": True,
                "metrics": {
                    "model_used": "gpt-4o",
                    "input_tokens": 1500,
                    "output_tokens": 500,
                    "latency_ms": 1200,
                },
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_commit_failure_with_details(self, client: AsyncClient):
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(uuid4()),
                "usage_id": str(uuid4()),
                "success": False,
                "failure": {
                    "failure_type": "internal_error",
                    "reason": "Model API returned 500 Internal Server Error",
                },
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True  # Idempotent success (usage doesn't exist)


class TestCareerValidateUsageE2E:

    @pytest.fixture
    async def career_pricing_rule(self, db_session: AsyncSession, free_career_plan):
        """Create a PlanPricingRule for the free career plan."""
        from sqlalchemy import select

        from app.core.db.models import PlanPricingRule

        result = await db_session.execute(
            select(PlanPricingRule).where(
                PlanPricingRule.plan_id == free_career_plan.id
            )
        )
        pricing_rule = result.scalar_one_or_none()

        if pricing_rule is None:
            pricing_rule = PlanPricingRule(
                id=uuid4(),
                plan_id=free_career_plan.id,
                multiplier=Decimal("1.0"),
                credits_allocation=Decimal("100.00"),
                rate_limit_per_minute=20,
                rate_limit_per_day=500,
            )
            db_session.add(pricing_rule)
            await db_session.flush()

        return pricing_rule

    @pytest.mark.asyncio
    async def test_validate_with_subscription_grants_access(
        self,
        client: AsyncClient,
        test_user,
        career_subscription,
        career_pricing_rule,
    ):
        headers = _make_auth_headers(test_user)
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["access"] == AccessStatus.GRANTED.value
        assert data["user_id"] == str(test_user.id)
        assert data["usage_id"] is not None
        assert data["credits_reserved"] is not None

    @pytest.mark.asyncio
    async def test_validate_returns_rate_limit_headers(
        self,
        client: AsyncClient,
        test_user,
        career_subscription,
        career_pricing_rule,
    ):
        headers = _make_auth_headers(test_user)
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=headers,
        )
        assert response.status_code == 200
        assert "X-RateLimit-Limit-Minute" in response.headers
        assert "X-RateLimit-Remaining-Minute" in response.headers
        assert "X-RateLimit-Reset-Minute" in response.headers
        assert "X-RateLimit-Limit-Day" in response.headers
        assert "X-RateLimit-Remaining-Day" in response.headers
        assert "X-RateLimit-Reset-Day" in response.headers

    @pytest.mark.asyncio
    async def test_validate_idempotent_same_fingerprint(
        self,
        client: AsyncClient,
        test_user,
        career_subscription,
        career_pricing_rule,
    ):
        headers = _make_auth_headers(test_user)
        request_id = str(uuid4())
        payload_hash = _generate_payload_hash("same_payload")

        response1 = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(
                request_id=request_id,
                endpoint="/test",
                method="POST",
                payload_hash=payload_hash,
            ),
            headers=headers,
        )
        assert response1.status_code == 200
        usage_id_1 = response1.json()["usage_id"]

        response2 = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(
                request_id=request_id,
                endpoint="/test",
                method="POST",
                payload_hash=payload_hash,
            ),
            headers=headers,
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["usage_id"] == usage_id_1
        assert "idempotent" in data2["message"].lower()

    @pytest.mark.asyncio
    async def test_validate_different_fingerprint_creates_new_record(
        self,
        client: AsyncClient,
        test_user,
        career_subscription,
        career_pricing_rule,
    ):
        headers = _make_auth_headers(test_user)
        request_id = str(uuid4())

        response1 = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(
                request_id=request_id,
                payload_hash=_generate_payload_hash("payload_1"),
            ),
            headers=headers,
        )
        assert response1.status_code == 200
        usage_id_1 = response1.json()["usage_id"]

        response2 = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(
                request_id=request_id,
                payload_hash=_generate_payload_hash("payload_2"),
            ),
            headers=headers,
        )
        assert response2.status_code == 200
        usage_id_2 = response2.json()["usage_id"]
        assert usage_id_2 != usage_id_1

    @pytest.mark.asyncio
    async def test_validate_quota_exceeded_returns_429(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
        career_subscription,
        career_pricing_rule,
    ):
        from sqlalchemy import select

        from app.core.db.models import CareerSubscriptionContext

        # Exhaust the quota
        result = await db_session.execute(
            select(CareerSubscriptionContext).where(
                CareerSubscriptionContext.user_id == test_user.id
            )
        )
        context = result.scalar_one()
        context.credits_used = career_pricing_rule.credits_allocation
        await db_session.flush()

        headers = _make_auth_headers(test_user)
        response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=headers,
        )
        assert response.status_code == 429
        data = response.json()
        assert data["access"] == AccessStatus.DENIED.value
        assert (
            "quota" in data["message"].lower() or "exceeded" in data["message"].lower()
        )


class TestCareerCommitUsageE2E:

    @pytest.fixture
    async def career_pricing_rule(self, db_session: AsyncSession, free_career_plan):
        """Create a PlanPricingRule for the free career plan."""
        from sqlalchemy import select

        from app.core.db.models import PlanPricingRule

        result = await db_session.execute(
            select(PlanPricingRule).where(
                PlanPricingRule.plan_id == free_career_plan.id
            )
        )
        pricing_rule = result.scalar_one_or_none()

        if pricing_rule is None:
            pricing_rule = PlanPricingRule(
                id=uuid4(),
                plan_id=free_career_plan.id,
                multiplier=Decimal("1.0"),
                credits_allocation=Decimal("100.00"),
                rate_limit_per_minute=20,
                rate_limit_per_day=500,
            )
            db_session.add(pricing_rule)
            await db_session.flush()

        return pricing_rule

    @pytest.mark.asyncio
    async def test_commit_after_validate_success(
        self,
        client: AsyncClient,
        test_user,
        career_subscription,
        career_pricing_rule,
    ):
        auth_headers = _make_auth_headers(test_user)

        # Step 1: Validate
        validate_response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=auth_headers,
        )
        assert validate_response.status_code == 200
        usage_id = validate_response.json()["usage_id"]

        # Step 2: Commit as success
        internal_headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        commit_response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(test_user.id),
                "usage_id": usage_id,
                "success": True,
                "metrics": {
                    "model_used": "gpt-4o",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "latency_ms": 500,
                },
            },
            headers=internal_headers,
        )
        assert commit_response.status_code == 200
        data = commit_response.json()
        assert data["success"] is True
        assert "success" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_commit_after_validate_failure(
        self,
        client: AsyncClient,
        test_user,
        career_subscription,
        career_pricing_rule,
    ):
        auth_headers = _make_auth_headers(test_user)

        # Step 1: Validate
        validate_response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=auth_headers,
        )
        assert validate_response.status_code == 200
        usage_id = validate_response.json()["usage_id"]

        # Step 2: Commit as failure
        internal_headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        commit_response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(test_user.id),
                "usage_id": usage_id,
                "success": False,
                "failure": {
                    "failure_type": "timeout",
                    "reason": "Request timed out after 30s",
                },
            },
            headers=internal_headers,
        )
        assert commit_response.status_code == 200
        data = commit_response.json()
        assert data["success"] is True
        assert "failed" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_commit_ownership_mismatch(
        self,
        client: AsyncClient,
        test_user,
        career_subscription,
        career_pricing_rule,
    ):
        auth_headers = _make_auth_headers(test_user)

        # Step 1: Validate
        validate_response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=auth_headers,
        )
        assert validate_response.status_code == 200
        usage_id = validate_response.json()["usage_id"]

        # Step 2: Commit with wrong user_id
        internal_headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        commit_response = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(uuid4()),  # Wrong user
                "usage_id": usage_id,
                "success": True,
            },
            headers=internal_headers,
        )
        assert commit_response.status_code == 200
        data = commit_response.json()
        assert data["success"] is False
        assert "does not own" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_commit_is_idempotent(
        self,
        client: AsyncClient,
        test_user,
        career_subscription,
        career_pricing_rule,
    ):
        auth_headers = _make_auth_headers(test_user)

        # Validate
        validate_response = await client.post(
            "/career/internal/usage/validate",
            json=make_validate_request(),
            headers=auth_headers,
        )
        assert validate_response.status_code == 200
        usage_id = validate_response.json()["usage_id"]

        # Commit first time
        internal_headers = {"X-Internal-API-Key": settings.INTERNAL_API_SECRET}
        commit1 = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(test_user.id),
                "usage_id": usage_id,
                "success": True,
            },
            headers=internal_headers,
        )
        assert commit1.status_code == 200
        assert commit1.json()["success"] is True

        # Commit second time (idempotent)
        commit2 = await client.post(
            "/career/internal/usage/commit",
            json={
                "user_id": str(test_user.id),
                "usage_id": usage_id,
                "success": True,
            },
            headers=internal_headers,
        )
        assert commit2.status_code == 200
        assert commit2.json()["success"] is True


class TestCareerRateLimitE2E:

    @pytest.fixture
    async def career_pricing_rule_low_limit(
        self, db_session: AsyncSession, free_career_plan
    ):
        """Create a PlanPricingRule with a very low rate limit for testing."""
        from sqlalchemy import select

        from app.core.db.models import PlanPricingRule

        result = await db_session.execute(
            select(PlanPricingRule).where(
                PlanPricingRule.plan_id == free_career_plan.id
            )
        )
        pricing_rule = result.scalar_one_or_none()

        if pricing_rule is None:
            pricing_rule = PlanPricingRule(
                id=uuid4(),
                plan_id=free_career_plan.id,
                multiplier=Decimal("1.0"),
                credits_allocation=Decimal("1000.00"),
                rate_limit_per_minute=3,
                rate_limit_per_day=1000,
            )
            db_session.add(pricing_rule)
        else:
            pricing_rule.rate_limit_per_minute = 3
            pricing_rule.rate_limit_per_day = 1000

        await db_session.flush()
        return pricing_rule

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_429(
        self,
        client: AsyncClient,
        test_user,
        career_subscription,
        career_pricing_rule_low_limit,
    ):
        from unittest.mock import AsyncMock, patch

        from freezegun import freeze_time

        rate_limit = career_pricing_rule_low_limit.rate_limit_per_minute
        rate_limit_day = career_pricing_rule_low_limit.rate_limit_per_day

        # (the pricing rule lives in an uncommitted test transaction invisible
        # to the QuotaCacheService's own DB connection)
        with (
            freeze_time("2026-02-26 12:00:00"),
            patch(
                "app.apps.cubex_career.services.quota.QuotaCacheService.get_plan_rate_limit",
                new_callable=AsyncMock,
                return_value=rate_limit,
            ),
            patch(
                "app.apps.cubex_career.services.quota.QuotaCacheService.get_plan_rate_day_limit",
                new_callable=AsyncMock,
                return_value=rate_limit_day,
            ),
        ):
            headers = _make_auth_headers(test_user)

            # Make requests up to the limit
            for i in range(rate_limit):
                response = await client.post(
                    "/career/internal/usage/validate",
                    json=make_validate_request(),
                    headers=headers,
                )
                assert (
                    response.status_code == 200
                ), f"Request {i + 1} failed unexpectedly: {response.json()}"

            # Next request should be rate limited
            response = await client.post(
                "/career/internal/usage/validate",
                json=make_validate_request(),
                headers=headers,
            )
            assert response.status_code == 429
            data = response.json()
            assert data["access"] == AccessStatus.DENIED.value
            assert "rate limit" in data["message"].lower()
            assert "Retry-After" in response.headers

