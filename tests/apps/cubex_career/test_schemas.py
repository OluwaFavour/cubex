"""
Test suite for Career schemas.

This module tests the Pydantic schemas for career usage commit
(cross-field validation) and analysis history responses.

Run all tests:
    pytest tests/apps/cubex_career/test_schemas.py -v
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.apps.cubex_career.schemas.internal import (
    FailureDetails,
    UsageCommitRequest,
    UsageMetrics,
)
from app.apps.cubex_career.schemas.history import (
    AnalysisHistoryDetail,
    AnalysisHistoryItem,
    AnalysisHistoryListResponse,
)
from app.core.enums import FailureType, FeatureKey

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = uuid4()
_USAGE_ID = uuid4()


def _commit_kwargs(**overrides) -> dict:
    """Return minimal valid kwargs for UsageCommitRequest, merged with overrides."""
    base = {
        "user_id": _USER_ID,
        "usage_id": _USAGE_ID,
        "success": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# UsageCommitRequest — success path
# ---------------------------------------------------------------------------


class TestUsageCommitRequestSuccess:

    def test_success_minimal(self):
        req = UsageCommitRequest(**_commit_kwargs())

        assert req.success is True
        assert req.metrics is None
        assert req.failure is None
        assert req.result_data is None

    def test_success_with_metrics(self):
        req = UsageCommitRequest(
            **_commit_kwargs(
                metrics={
                    "model_used": "gpt-4o",
                    "input_tokens": 1500,
                    "output_tokens": 500,
                    "latency_ms": 1200,
                }
            )
        )

        assert req.metrics is not None
        assert req.metrics.model_used == "gpt-4o"

    def test_success_with_result_data(self):
        result = {"match_score": 0.85, "strengths": ["Python"]}
        req = UsageCommitRequest(**_commit_kwargs(result_data=result))

        assert req.result_data == result

    def test_success_with_metrics_and_result_data(self):
        req = UsageCommitRequest(
            **_commit_kwargs(
                metrics={"model_used": "gpt-4o"},
                result_data={"score": 0.9},
            )
        )

        assert req.metrics is not None
        assert req.result_data == {"score": 0.9}

    def test_success_with_failure_raises(self):
        """failure must not be provided when success=True."""
        with pytest.raises(ValidationError, match="must not be provided"):
            UsageCommitRequest(
                **_commit_kwargs(
                    failure={
                        "failure_type": "internal_error",
                        "reason": "should not be here",
                    }
                )
            )

    def test_success_with_result_data_none_is_valid(self):
        req = UsageCommitRequest(**_commit_kwargs(result_data=None))

        assert req.result_data is None


# ---------------------------------------------------------------------------
# UsageCommitRequest — failure path
# ---------------------------------------------------------------------------


class TestUsageCommitRequestFailure:

    def test_failure_with_details(self):
        req = UsageCommitRequest(
            **_commit_kwargs(
                success=False,
                failure={
                    "failure_type": "internal_error",
                    "reason": "Model API 500",
                },
            )
        )

        assert req.success is False
        assert req.failure is not None
        assert req.failure.failure_type == FailureType.INTERNAL_ERROR

    def test_failure_missing_details_raises(self):
        """failure details are required when success=False."""
        with pytest.raises(ValidationError, match="failure details are required"):
            UsageCommitRequest(**_commit_kwargs(success=False))

    def test_failure_discards_result_data(self):
        """result_data is silently ignored (set to None) on failures."""
        req = UsageCommitRequest(
            **_commit_kwargs(
                success=False,
                failure={
                    "failure_type": "rate_limited",
                    "reason": "Too many requests",
                },
                result_data={"should": "be discarded"},
            )
        )

        assert req.result_data is None

    def test_failure_discards_result_data_not_raises(self):
        """Sending result_data with success=False should not raise, just discard."""
        req = UsageCommitRequest(
            **_commit_kwargs(
                success=False,
                failure={
                    "failure_type": "timeout",
                    "reason": "Request timed out",
                },
                result_data={"anything": True},
            )
        )

        assert req.success is False
        assert req.result_data is None


# ---------------------------------------------------------------------------
# UsageMetrics
# ---------------------------------------------------------------------------


class TestUsageMetrics:

    def test_metrics_all_fields(self):
        m = UsageMetrics(
            model_used="gpt-4o",
            input_tokens=1500,
            output_tokens=500,
            latency_ms=1200,
        )

        assert m.model_used == "gpt-4o"
        assert m.input_tokens == 1500

    def test_metrics_all_optional(self):
        m = UsageMetrics()

        assert m.model_used is None
        assert m.input_tokens is None
        assert m.output_tokens is None
        assert m.latency_ms is None

    def test_metrics_negative_tokens_raises(self):
        with pytest.raises(ValidationError):
            UsageMetrics(input_tokens=-1)

    def test_metrics_tokens_above_limit_raises(self):
        with pytest.raises(ValidationError):
            UsageMetrics(input_tokens=3_000_000)

    def test_metrics_latency_above_limit_raises(self):
        with pytest.raises(ValidationError):
            UsageMetrics(latency_ms=4_000_000)


# ---------------------------------------------------------------------------
# FailureDetails
# ---------------------------------------------------------------------------


class TestFailureDetails:

    def test_failure_details_valid(self):
        fd = FailureDetails(
            failure_type="internal_error",  # type: ignore[arg-type]
            reason="Something went wrong",
        )

        assert fd.failure_type == FailureType.INTERNAL_ERROR
        assert fd.reason == "Something went wrong"

    def test_failure_details_empty_reason_raises(self):
        with pytest.raises(ValidationError):
            FailureDetails(failure_type="internal_error", reason="")  # type: ignore[arg-type]

    def test_failure_details_reason_too_long_raises(self):
        with pytest.raises(ValidationError):
            FailureDetails(failure_type="internal_error", reason="x" * 1001)  # type: ignore[arg-type]

    def test_failure_details_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            FailureDetails(failure_type="not_a_real_type", reason="oops")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AnalysisHistoryItem
# ---------------------------------------------------------------------------


class TestAnalysisHistoryItem:

    def test_history_item_full(self):
        now = datetime.now(timezone.utc)
        item = AnalysisHistoryItem(
            id=uuid4(),
            feature_key=FeatureKey.CAREER_JOB_MATCH,
            title="Job Match Analysis",
            result_data={"match_score": 0.85, "strengths": ["Python"]},
            created_at=now,
        )

        assert item.feature_key == FeatureKey.CAREER_JOB_MATCH
        assert item.title == "Job Match Analysis"
        assert item.result_data["match_score"] == 0.85
        assert item.created_at == now

    def test_history_item_null_title(self):
        item = AnalysisHistoryItem(
            id=uuid4(),
            feature_key=FeatureKey.CAREER_CAREER_PATH,
            title=None,
            result_data={"paths": []},
            created_at=datetime.now(timezone.utc),
        )

        assert item.title is None

    def test_history_item_missing_result_data_raises(self):
        with pytest.raises(ValidationError):
            AnalysisHistoryItem(  # type: ignore[call-arg]
                id=uuid4(),
                feature_key=FeatureKey.CAREER_JOB_MATCH,
                title="Job Match",
                created_at=datetime.now(timezone.utc),
            )

    def test_history_item_invalid_feature_key_raises(self):
        with pytest.raises(ValidationError):
            AnalysisHistoryItem(
                id=uuid4(),
                feature_key="invalid.key",  # type: ignore[arg-type]
                title="Nope",
                result_data={},
                created_at=datetime.now(timezone.utc),
            )


# ---------------------------------------------------------------------------
# AnalysisHistoryDetail
# ---------------------------------------------------------------------------


class TestAnalysisHistoryDetail:

    def test_detail_full(self):
        now = datetime.now(timezone.utc)
        detail = AnalysisHistoryDetail(
            id=uuid4(),
            usage_log_id=uuid4(),
            feature_key=FeatureKey.CAREER_FEEDBACK_ANALYZER,
            title="Feedback Analysis",
            result_data={"sentiment": "positive", "themes": ["leadership"]},
            created_at=now,
        )

        assert detail.feature_key == FeatureKey.CAREER_FEEDBACK_ANALYZER
        assert detail.result_data["sentiment"] == "positive"

    def test_detail_null_title(self):
        detail = AnalysisHistoryDetail(
            id=uuid4(),
            usage_log_id=uuid4(),
            feature_key=FeatureKey.CAREER_EXTRACT_KEYWORDS,
            title=None,
            result_data={"keywords": []},
            created_at=datetime.now(timezone.utc),
        )

        assert detail.title is None

    def test_detail_missing_usage_log_id_raises(self):
        with pytest.raises(ValidationError):
            AnalysisHistoryDetail(  # type: ignore[call-arg]
                id=uuid4(),
                feature_key=FeatureKey.CAREER_JOB_MATCH,
                title="Job Match",
                result_data={"score": 0.5},
                created_at=datetime.now(timezone.utc),
            )


# ---------------------------------------------------------------------------
# AnalysisHistoryListResponse
# ---------------------------------------------------------------------------


class TestAnalysisHistoryListResponse:

    def test_list_response_with_items(self):
        now = datetime.now(timezone.utc)
        item_id = uuid4()
        resp = AnalysisHistoryListResponse(
            items=[
                AnalysisHistoryItem(
                    id=item_id,
                    feature_key=FeatureKey.CAREER_JOB_MATCH,
                    title="Job Match Analysis",
                    result_data={"match_score": 0.85},
                    created_at=now,
                )
            ],
            next_cursor=item_id,
            has_more=True,
        )

        assert len(resp.items) == 1
        assert resp.has_more is True
        assert resp.next_cursor == item_id

    def test_list_response_empty(self):
        resp = AnalysisHistoryListResponse(
            items=[],
            next_cursor=None,
            has_more=False,
        )

        assert resp.items == []
        assert resp.has_more is False
        assert resp.next_cursor is None

    def test_list_response_missing_has_more_raises(self):
        with pytest.raises(ValidationError):
            AnalysisHistoryListResponse(  # type: ignore[call-arg]
                items=[],
                next_cursor=None,
            )

    def test_list_response_items_contain_result_data(self):
        """Ensure each item in the list carries result_data."""
        now = datetime.now(timezone.utc)
        resp = AnalysisHistoryListResponse(
            items=[
                AnalysisHistoryItem(
                    id=uuid4(),
                    feature_key=FeatureKey.CAREER_CAREER_PATH,
                    title="Career Path Analysis",
                    result_data={
                        "paths": ["Senior Engineer"],
                        "recommended": "Senior Engineer",
                    },
                    created_at=now,
                ),
                AnalysisHistoryItem(
                    id=uuid4(),
                    feature_key=FeatureKey.CAREER_EXTRACT_KEYWORDS,
                    title="Keyword Extraction",
                    result_data={"keywords": ["Python", "FastAPI"]},
                    created_at=now,
                ),
            ],
            next_cursor=None,
            has_more=False,
        )

        assert resp.items[0].result_data["paths"] == ["Senior Engineer"]
        assert resp.items[1].result_data["keywords"] == ["Python", "FastAPI"]
