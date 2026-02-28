"""
Test suite for DLQ admin view configuration and metrics endpoint.

Run tests:
    pytest tests/admin/test_dlq.py -v

Run with coverage:
    pytest tests/admin/test_dlq.py --cov=app.admin.dlq_router --cov=app.admin.views --cov-report=term-missing -v
"""

import json
from unittest.mock import MagicMock

import pytest

from app.admin.views import DLQMessageAdmin, _format_json_field

# ---------------------------------------------------------------------------
# DLQMessageAdmin view configuration
# ---------------------------------------------------------------------------


class TestDLQMessageAdminConfiguration:

    def test_model_binding(self):
        from app.core.db.models.dlq_message import DLQMessage

        assert DLQMessageAdmin.model is DLQMessage

    def test_name_and_plural(self):
        assert DLQMessageAdmin.name == "DLQ Message"
        assert DLQMessageAdmin.name_plural == "DLQ Messages"

    def test_icon(self):
        assert DLQMessageAdmin.icon == "fa-solid fa-skull-crossbones"

    def test_read_only_permissions(self):
        assert DLQMessageAdmin.can_create is False
        assert DLQMessageAdmin.can_edit is False
        assert DLQMessageAdmin.can_delete is False

    def test_view_and_export_enabled(self):
        assert DLQMessageAdmin.can_view_details is True
        assert DLQMessageAdmin.can_export is True

    def test_column_list_fields(self):
        col_names = [c.key for c in DLQMessageAdmin.column_list]
        assert "id" in col_names
        assert "queue_name" in col_names
        assert "status" in col_names
        assert "attempt_count" in col_names
        assert "error_message" in col_names
        assert "created_at" in col_names

    def test_column_details_includes_payload(self):
        col_names = [c.key for c in DLQMessageAdmin.column_details_list]
        assert "message_body" in col_names
        assert "headers" in col_names

    def test_column_searchable_list(self):
        assert "queue_name" in DLQMessageAdmin.column_searchable_list
        assert "error_message" in DLQMessageAdmin.column_searchable_list

    def test_column_sortable_list(self):
        sortable_names = [c.key for c in DLQMessageAdmin.column_sortable_list]
        assert "queue_name" in sortable_names
        assert "status" in sortable_names
        assert "created_at" in sortable_names

    def test_default_sort_newest_first(self):
        from app.core.db.models.dlq_message import DLQMessage

        sort_col, desc = DLQMessageAdmin.column_default_sort[0]
        assert sort_col is DLQMessage.created_at
        assert desc is True

    def test_page_size(self):
        assert DLQMessageAdmin.page_size == 50
        assert 100 in DLQMessageAdmin.page_size_options

    def test_status_filter_configured(self):
        from sqladmin.filters import StaticValuesFilter

        assert len(DLQMessageAdmin.column_filters) >= 1
        status_filter = DLQMessageAdmin.column_filters[0]
        assert isinstance(status_filter, StaticValuesFilter)

    def test_error_message_formatter_truncates(self):
        from app.core.db.models.dlq_message import DLQMessage

        formatter = DLQMessageAdmin.column_formatters[DLQMessage.error_message]

        # Long message should be truncated
        long_msg = MagicMock()
        long_msg.error_message = "x" * 200
        result = formatter(long_msg, None)
        assert len(result) <= 125  # 120 + "…" (3 bytes)
        assert result.endswith("…")

    def test_error_message_formatter_short_preserved(self):
        from app.core.db.models.dlq_message import DLQMessage

        formatter = DLQMessageAdmin.column_formatters[DLQMessage.error_message]

        short_msg = MagicMock()
        short_msg.error_message = "Connection refused"
        result = formatter(short_msg, None)
        assert result == "Connection refused"

    def test_error_message_formatter_none(self):
        from app.core.db.models.dlq_message import DLQMessage

        formatter = DLQMessageAdmin.column_formatters[DLQMessage.error_message]

        null_msg = MagicMock()
        null_msg.error_message = None
        result = formatter(null_msg, None)
        assert result == "-"


class TestDLQMessageAdminActions:

    def test_has_retry_action(self):
        assert hasattr(DLQMessageAdmin, "action_retry")

    def test_has_discard_action(self):
        assert hasattr(DLQMessageAdmin, "action_discard")

    def test_action_retry_signature_takes_request_only(self):
        """SQLAdmin 0.22.0 calls action(request) — pks come from query params."""
        import inspect

        sig = inspect.signature(DLQMessageAdmin.action_retry)
        params = list(sig.parameters.keys())
        # Should be (self, request) — no 'pks' parameter
        assert "pks" not in params
        assert "request" in params

    def test_action_discard_signature_takes_request_only(self):
        import inspect

        sig = inspect.signature(DLQMessageAdmin.action_discard)
        params = list(sig.parameters.keys())
        assert "pks" not in params
        assert "request" in params

    def test_discard_uses_bulk_operation(self):
        """Discard action should delegate to bulk_discard, not loop per-row."""
        import ast
        import inspect
        import textwrap

        source = inspect.getsource(DLQMessageAdmin.action_discard)
        source = textwrap.dedent(source)
        tree = ast.parse(source)

        source_text = ast.dump(tree)
        assert "bulk_discard" in source_text or "bulk_discard" in source
        # Should NOT contain a for-loop over pks with get_by_id
        assert "get_by_id" not in source


# ---------------------------------------------------------------------------
# _format_json_field helper
# ---------------------------------------------------------------------------


class TestFormatJsonField:

    def test_none_returns_dash(self):
        assert _format_json_field(None) == "-"

    def test_valid_json_string_pretty_printed(self):
        raw = '{"key": "value"}'
        result = _format_json_field(raw)
        parsed = json.loads(result)
        assert parsed == {"key": "value"}
        # Should be indented
        assert "\n" in result

    def test_invalid_json_string_returned_as_is(self):
        raw = "not json at all"
        assert _format_json_field(raw) == "not json at all"

    def test_dict_pretty_printed(self):
        data = {"a": 1, "b": [2, 3]}
        result = _format_json_field(data)
        assert json.loads(result) == data

    def test_other_type_stringified(self):
        assert _format_json_field(42) == "42"


# ---------------------------------------------------------------------------
# DLQ Metrics endpoint
# ---------------------------------------------------------------------------


class TestDLQMetricsEndpoint:

    def test_router_import(self):
        from app.admin.dlq_router import router

        assert router is not None

    def test_schemas_import(self):
        from app.admin.dlq_router import DLQMetricsItem, DLQMetricsResponse

        item = DLQMetricsItem(
            queue_name="otp_emails_dead",
            status="PENDING",
            count=5,
        )
        assert item.queue_name == "otp_emails_dead"
        assert item.count == 5

        response = DLQMetricsResponse(
            total=5,
            by_status={"PENDING": 5},
            by_queue={"otp_emails_dead": {"PENDING": 5}},
            items=[item],
        )
        assert response.total == 5
        assert response.items[0].queue_name == "otp_emails_dead"

    def test_require_admin_auth_dependency_exists(self):
        from app.admin.dlq_router import require_admin_auth

        assert callable(require_admin_auth)

    @pytest.mark.asyncio
    async def test_require_admin_auth_raises_on_failure(self):
        from app.admin.dlq_router import require_admin_auth
        from app.core.exceptions.types import AuthenticationException

        mock_request = MagicMock()
        mock_request.session = {}
        mock_request.url_for = MagicMock(return_value="/admin/login")

        with pytest.raises(AuthenticationException):
            await require_admin_auth(mock_request)

    @pytest.mark.asyncio
    async def test_require_admin_auth_passes_with_valid_token(self):
        from app.admin.auth import AdminAuth
        from app.admin.dlq_router import require_admin_auth
        from app.core.config import settings

        token = AdminAuth._create_token(settings.SESSION_SECRET_KEY)

        mock_request = MagicMock()
        mock_request.session = {"admin_token": token}

        # Should not raise
        result = await require_admin_auth(mock_request)
        assert result is None

    def test_dlq_metrics_route_registered(self):
        from app.admin.dlq_router import router

        routes = [r.path for r in router.routes]
        assert "/dlq/metrics" in routes

    def test_dlq_metrics_is_get(self):
        from app.admin.dlq_router import router

        for route in router.routes:
            if hasattr(route, "path") and route.path == "/dlq/metrics":
                assert "GET" in route.methods
                break
        else:
            pytest.fail("/dlq/metrics route not found")


# ---------------------------------------------------------------------------
# DLQ admin registered in setup
# ---------------------------------------------------------------------------


class TestDLQAdminSetup:

    def test_dlq_message_admin_importable_from_views(self):
        from app.admin.views import DLQMessageAdmin

        assert DLQMessageAdmin is not None

    def test_dlq_admin_registered_in_setup(self):
        """init_admin should register DLQMessageAdmin."""
        mock_app = MagicMock()

        from app.admin.setup import init_admin

        init_admin(mock_app)

        from app.admin.setup import admin

        # Check that admin.views contains a DLQMessageAdmin instance
        view_types = [type(v).__name__ for v in admin.views]
        assert (
            "DLQMessageAdmin" in view_types
        ), f"DLQMessageAdmin not found in admin views: {view_types}"
