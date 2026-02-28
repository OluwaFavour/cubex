"""
Test suite for Stripe webhook message handlers.

Tests the four public handlers exported from
app.infrastructure.messaging.handlers.stripe:
    - handle_stripe_checkout_completed
    - handle_stripe_subscription_updated
    - handle_stripe_subscription_deleted
    - handle_stripe_payment_failed

Covers idempotency (Redis dedup), Career/API routing, email notifications,
and error propagation for each handler.

Run all tests:
    pytest tests/infrastructure/messaging/test_stripe_handler.py -v

Run with coverage:
    pytest tests/infrastructure/messaging/test_stripe_handler.py \
        --cov=app.infrastructure.messaging.handlers.stripe \
        --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.enums import ProductType

HANDLER_MODULE = "app.infrastructure.messaging.handlers.stripe"


def _make_plan(product_type: ProductType = ProductType.API, name: str = "Pro"):
    """Create a mock Plan object."""
    plan = MagicMock()
    plan.product_type = product_type
    plan.name = name
    plan.id = uuid4()
    return plan


def _make_subscription(
    product_type: ProductType = ProductType.API,
    plan_name: str = "Pro",
    stripe_sub_id: str = "sub_test_123",
):
    """Create a mock Subscription object with plan relationship."""
    plan = _make_plan(product_type, plan_name)
    sub = MagicMock()
    sub.id = uuid4()
    sub.plan = plan
    sub.plan_id = plan.id
    sub.product_type = product_type
    sub.stripe_subscription_id = stripe_sub_id
    return sub


class TestStripeHandlerImports:

    def test_handle_checkout_completed_import(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_checkout_completed,
        )

        assert handle_stripe_checkout_completed is not None
        assert callable(handle_stripe_checkout_completed)

    def test_handle_subscription_updated_import(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_subscription_updated,
        )

        assert handle_stripe_subscription_updated is not None
        assert callable(handle_stripe_subscription_updated)

    def test_handle_subscription_deleted_import(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_subscription_deleted,
        )

        assert handle_stripe_subscription_deleted is not None
        assert callable(handle_stripe_subscription_deleted)

    def test_handle_payment_failed_import(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_payment_failed,
        )

        assert handle_stripe_payment_failed is not None
        assert callable(handle_stripe_payment_failed)

    def test_all_exports(self):
        from app.infrastructure.messaging.handlers import stripe

        assert "handle_stripe_checkout_completed" in stripe.__all__
        assert "handle_stripe_subscription_updated" in stripe.__all__
        assert "handle_stripe_subscription_deleted" in stripe.__all__
        assert "handle_stripe_payment_failed" in stripe.__all__

    def test_registered_in_queue_configs(self):
        from app.infrastructure.messaging.queues import get_queue_configs

        get_queue_configs.cache_clear()
        configs = get_queue_configs()
        queue_names = [c.name for c in configs]
        assert "stripe_checkout_completed" in queue_names
        assert "stripe_subscription_updated" in queue_names
        assert "stripe_subscription_deleted" in queue_names
        assert "stripe_payment_failed" in queue_names


class TestIdempotency:

    @pytest.mark.asyncio
    async def test_checkout_completed_skips_duplicate(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_checkout_completed,
        )

        event = {
            "event_id": "evt_dup_checkout",
            "stripe_subscription_id": "sub_123",
            "stripe_customer_id": "cus_123",
            "product_type": "api",
            "plan_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "seat_count": 1,
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_check,
            patch(
                f"{HANDLER_MODULE}._process_api_checkout",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            await handle_stripe_checkout_completed(event)

            mock_check.assert_called_once_with("evt_dup_checkout")
            mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscription_updated_skips_duplicate(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_subscription_updated,
        )

        event = {
            "event_id": "evt_dup_update",
            "stripe_subscription_id": "sub_123",
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_check,
            patch(
                f"{HANDLER_MODULE}._process_subscription_update",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            await handle_stripe_subscription_updated(event)

            mock_check.assert_called_once_with("evt_dup_update")
            mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscription_deleted_skips_duplicate(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_subscription_deleted,
        )

        event = {
            "event_id": "evt_dup_delete",
            "stripe_subscription_id": "sub_123",
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_check,
            patch(
                f"{HANDLER_MODULE}._process_subscription_deletion",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            await handle_stripe_subscription_deleted(event)

            mock_check.assert_called_once_with("evt_dup_delete")
            mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_payment_failed_skips_duplicate(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_payment_failed,
        )

        event = {
            "event_id": "evt_dup_payment",
            "stripe_subscription_id": "sub_123",
            "customer_email": "test@example.com",
            "amount_due": 2999,
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_check,
            patch(
                f"{HANDLER_MODULE}._process_payment_failure",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            await handle_stripe_payment_failed(event)

            mock_check.assert_called_once_with("evt_dup_payment")
            mock_process.assert_not_called()


class TestHandleCheckoutCompleted:

    @pytest.mark.asyncio
    async def test_routes_to_api_checkout(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_checkout_completed,
        )

        ws_id = str(uuid4())
        plan_id = str(uuid4())
        event = {
            "event_id": "evt_api_checkout",
            "stripe_subscription_id": "sub_api_123",
            "stripe_customer_id": "cus_api_123",
            "product_type": "api",
            "plan_id": plan_id,
            "workspace_id": ws_id,
            "seat_count": 5,
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                f"{HANDLER_MODULE}._mark_event_as_processed",
                new_callable=AsyncMock,
            ) as mock_mark,
            patch(
                f"{HANDLER_MODULE}._process_api_checkout",
                new_callable=AsyncMock,
            ) as mock_api,
            patch(
                f"{HANDLER_MODULE}._process_career_checkout",
                new_callable=AsyncMock,
            ) as mock_career,
        ):
            await handle_stripe_checkout_completed(event)

            mock_api.assert_called_once()
            args = mock_api.call_args[0]
            assert args[0] == "sub_api_123"
            assert args[1] == "cus_api_123"
            assert str(args[2]) == ws_id
            assert str(args[3]) == plan_id
            assert args[4] == 5
            mock_career.assert_not_called()
            mock_mark.assert_called_once_with("evt_api_checkout")

    @pytest.mark.asyncio
    async def test_routes_to_career_checkout(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_checkout_completed,
        )

        user_id = str(uuid4())
        plan_id = str(uuid4())
        event = {
            "event_id": "evt_career_checkout",
            "stripe_subscription_id": "sub_career_123",
            "stripe_customer_id": "cus_career_123",
            "product_type": "career",
            "plan_id": plan_id,
            "user_id": user_id,
            "seat_count": 1,
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                f"{HANDLER_MODULE}._mark_event_as_processed",
                new_callable=AsyncMock,
            ) as mock_mark,
            patch(
                f"{HANDLER_MODULE}._process_career_checkout",
                new_callable=AsyncMock,
            ) as mock_career,
            patch(
                f"{HANDLER_MODULE}._process_api_checkout",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            await handle_stripe_checkout_completed(event)

            mock_career.assert_called_once()
            args = mock_career.call_args[0]
            assert args[0] == "sub_career_123"
            assert args[1] == "cus_career_123"
            assert str(args[2]) == user_id
            assert str(args[3]) == plan_id
            mock_api.assert_not_called()
            mock_mark.assert_called_once_with("evt_career_checkout")

    @pytest.mark.asyncio
    async def test_defaults_to_api_when_product_type_missing(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_checkout_completed,
        )

        event = {
            "event_id": "evt_default_checkout",
            "stripe_subscription_id": "sub_123",
            "stripe_customer_id": "cus_123",
            "plan_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "seat_count": 1,
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                f"{HANDLER_MODULE}._mark_event_as_processed",
                new_callable=AsyncMock,
            ),
            patch(
                f"{HANDLER_MODULE}._process_api_checkout",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            await handle_stripe_checkout_completed(event)
            mock_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_propagates_without_marking_processed(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_checkout_completed,
        )

        event = {
            "event_id": "evt_error_checkout",
            "stripe_subscription_id": "sub_err_123",
            "stripe_customer_id": "cus_err_123",
            "product_type": "api",
            "plan_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "seat_count": 1,
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                f"{HANDLER_MODULE}._mark_event_as_processed",
                new_callable=AsyncMock,
            ) as mock_mark,
            patch(
                f"{HANDLER_MODULE}._process_api_checkout",
                new_callable=AsyncMock,
                side_effect=Exception("DB error"),
            ),
        ):
            with pytest.raises(Exception, match="DB error"):
                await handle_stripe_checkout_completed(event)

            mock_mark.assert_not_called()


class TestHandleSubscriptionUpdated:

    @pytest.mark.asyncio
    async def test_processes_and_marks_done(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_subscription_updated,
        )

        event = {
            "event_id": "evt_update_123",
            "stripe_subscription_id": "sub_update_123",
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                f"{HANDLER_MODULE}._process_subscription_update",
                new_callable=AsyncMock,
            ) as mock_update,
            patch(
                f"{HANDLER_MODULE}._mark_event_as_processed",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            await handle_stripe_subscription_updated(event)

            mock_update.assert_called_once_with("sub_update_123")
            mock_mark.assert_called_once_with("evt_update_123")

    @pytest.mark.asyncio
    async def test_error_propagates_without_marking_processed(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_subscription_updated,
        )

        event = {
            "event_id": "evt_update_err",
            "stripe_subscription_id": "sub_update_err",
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                f"{HANDLER_MODULE}._process_subscription_update",
                new_callable=AsyncMock,
                side_effect=Exception("Service error"),
            ),
            patch(
                f"{HANDLER_MODULE}._mark_event_as_processed",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            with pytest.raises(Exception, match="Service error"):
                await handle_stripe_subscription_updated(event)

            mock_mark.assert_not_called()


class TestHandleSubscriptionDeleted:

    @pytest.mark.asyncio
    async def test_processes_and_marks_done(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_subscription_deleted,
        )

        event = {
            "event_id": "evt_delete_123",
            "stripe_subscription_id": "sub_delete_123",
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                f"{HANDLER_MODULE}._process_subscription_deletion",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch(
                f"{HANDLER_MODULE}._mark_event_as_processed",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            await handle_stripe_subscription_deleted(event)

            mock_delete.assert_called_once_with("sub_delete_123")
            mock_mark.assert_called_once_with("evt_delete_123")

    @pytest.mark.asyncio
    async def test_error_propagates_without_marking_processed(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_subscription_deleted,
        )

        event = {
            "event_id": "evt_delete_err",
            "stripe_subscription_id": "sub_delete_err",
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                f"{HANDLER_MODULE}._process_subscription_deletion",
                new_callable=AsyncMock,
                side_effect=Exception("Deletion failed"),
            ),
            patch(
                f"{HANDLER_MODULE}._mark_event_as_processed",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            with pytest.raises(Exception, match="Deletion failed"):
                await handle_stripe_subscription_deleted(event)

            mock_mark.assert_not_called()


class TestHandlePaymentFailed:

    @pytest.mark.asyncio
    async def test_processes_and_marks_done(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_payment_failed,
        )

        event = {
            "event_id": "evt_pf_123",
            "stripe_subscription_id": "sub_pf_123",
            "customer_email": "user@example.com",
            "amount_due": 4999,
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                f"{HANDLER_MODULE}._process_payment_failure",
                new_callable=AsyncMock,
            ) as mock_process,
            patch(
                f"{HANDLER_MODULE}._mark_event_as_processed",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            await handle_stripe_payment_failed(event)

            mock_process.assert_called_once_with("sub_pf_123", 4999)
            mock_mark.assert_called_once_with("evt_pf_123")

    @pytest.mark.asyncio
    async def test_marks_done_even_on_email_error(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_payment_failed,
        )

        event = {
            "event_id": "evt_pf_email_err",
            "stripe_subscription_id": "sub_pf_123",
            "customer_email": "user@example.com",
            "amount_due": 2999,
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                f"{HANDLER_MODULE}._process_payment_failure",
                new_callable=AsyncMock,
                side_effect=Exception("Email queue down"),
            ),
            patch(
                f"{HANDLER_MODULE}._mark_event_as_processed",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            await handle_stripe_payment_failed(event)

            mock_mark.assert_called_once_with("evt_pf_email_err")

    @pytest.mark.asyncio
    async def test_handles_none_amount_due(self):
        from app.infrastructure.messaging.handlers.stripe import (
            handle_stripe_payment_failed,
        )

        event = {
            "event_id": "evt_pf_no_amount",
            "stripe_subscription_id": "sub_pf_123",
            "customer_email": "user@example.com",
        }

        with (
            patch(
                f"{HANDLER_MODULE}._is_event_already_processed",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                f"{HANDLER_MODULE}._process_payment_failure",
                new_callable=AsyncMock,
            ) as mock_process,
            patch(
                f"{HANDLER_MODULE}._mark_event_as_processed",
                new_callable=AsyncMock,
            ),
        ):
            await handle_stripe_payment_failed(event)

            mock_process.assert_called_once_with("sub_pf_123", None)


class TestProcessSubscriptionUpdate:

    @pytest.mark.asyncio
    async def test_routes_to_career_service(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_subscription_update,
        )

        sub = _make_subscription(ProductType.CAREER, "Plus")

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal.begin",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.subscription_db.get_by_stripe_subscription_id",
                new_callable=AsyncMock,
                return_value=sub,
            ),
            patch(
                f"{HANDLER_MODULE}.career_subscription_service.handle_subscription_updated",
                new_callable=AsyncMock,
                return_value=sub,
            ) as mock_career,
            patch(
                f"{HANDLER_MODULE}.api_subscription_service.handle_subscription_updated",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            await _process_subscription_update("sub_career_update")

            mock_career.assert_called_once_with(
                mock_session,
                stripe_subscription_id="sub_career_update",
                commit_self=False,
            )
            mock_api.assert_not_called()

    @pytest.mark.asyncio
    async def test_routes_to_api_service(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_subscription_update,
        )

        sub = _make_subscription(ProductType.API, "Professional")

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal.begin",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.subscription_db.get_by_stripe_subscription_id",
                new_callable=AsyncMock,
                return_value=sub,
            ),
            patch(
                f"{HANDLER_MODULE}.api_subscription_service.handle_subscription_updated",
                new_callable=AsyncMock,
                return_value=sub,
            ) as mock_api,
            patch(
                f"{HANDLER_MODULE}.career_subscription_service.handle_subscription_updated",
                new_callable=AsyncMock,
            ) as mock_career,
        ):
            await _process_subscription_update("sub_api_update")

            mock_api.assert_called_once_with(
                mock_session,
                stripe_subscription_id="sub_api_update",
                commit_self=False,
            )
            mock_career.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_subscription_not_found(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_subscription_update,
        )

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal.begin",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.subscription_db.get_by_stripe_subscription_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                f"{HANDLER_MODULE}.api_subscription_service.handle_subscription_updated",
                new_callable=AsyncMock,
            ) as mock_api,
            patch(
                f"{HANDLER_MODULE}.career_subscription_service.handle_subscription_updated",
                new_callable=AsyncMock,
            ) as mock_career,
        ):
            await _process_subscription_update("sub_not_found")

            mock_api.assert_not_called()
            mock_career.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_email_on_plan_change(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_subscription_update,
        )

        old_plan_id = uuid4()
        new_plan_id = uuid4()

        sub = _make_subscription(ProductType.API, "Basic")
        sub.plan_id = old_plan_id

        updated_sub = _make_subscription(ProductType.API, "Professional")
        updated_sub.plan_id = new_plan_id

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal.begin",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.subscription_db.get_by_stripe_subscription_id",
                new_callable=AsyncMock,
                return_value=sub,
            ),
            patch(
                f"{HANDLER_MODULE}.api_subscription_service.handle_subscription_updated",
                new_callable=AsyncMock,
                return_value=updated_sub,
            ),
            patch(
                f"{HANDLER_MODULE}._send_subscription_activated_email",
                new_callable=AsyncMock,
            ) as mock_email,
        ):
            await _process_subscription_update("sub_plan_change")

            mock_email.assert_called_once_with(mock_session, updated_sub, "Basic")

    @pytest.mark.asyncio
    async def test_no_email_when_plan_unchanged(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_subscription_update,
        )

        plan_id = uuid4()
        sub = _make_subscription(ProductType.API, "Pro")
        sub.plan_id = plan_id

        updated_sub = _make_subscription(ProductType.API, "Pro")
        updated_sub.plan_id = plan_id

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal.begin",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.subscription_db.get_by_stripe_subscription_id",
                new_callable=AsyncMock,
                return_value=sub,
            ),
            patch(
                f"{HANDLER_MODULE}.api_subscription_service.handle_subscription_updated",
                new_callable=AsyncMock,
                return_value=updated_sub,
            ),
            patch(
                f"{HANDLER_MODULE}._send_subscription_activated_email",
                new_callable=AsyncMock,
            ) as mock_email,
        ):
            await _process_subscription_update("sub_no_change")

            mock_email.assert_not_called()


class TestProcessSubscriptionDeletion:

    @pytest.mark.asyncio
    async def test_routes_to_career_service(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_subscription_deletion,
        )

        plan = _make_plan(ProductType.CAREER, "Plus")
        sub = _make_subscription(ProductType.CAREER, "Plus")

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal.begin",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.subscription_db.get_by_stripe_subscription_id",
                new_callable=AsyncMock,
                return_value=sub,
            ),
            patch(
                f"{HANDLER_MODULE}.plan_db.get_by_id",
                new_callable=AsyncMock,
                return_value=plan,
            ),
            patch(
                f"{HANDLER_MODULE}.career_subscription_service.handle_subscription_deleted",
                new_callable=AsyncMock,
            ) as mock_career,
            patch(
                f"{HANDLER_MODULE}.api_subscription_service.handle_subscription_deleted",
                new_callable=AsyncMock,
            ) as mock_api,
            patch(
                f"{HANDLER_MODULE}._send_subscription_canceled_email",
                new_callable=AsyncMock,
            ),
        ):
            await _process_subscription_deletion("sub_career_del")

            mock_career.assert_called_once_with(
                mock_session,
                stripe_subscription_id="sub_career_del",
                commit_self=False,
            )
            mock_api.assert_not_called()

    @pytest.mark.asyncio
    async def test_routes_to_api_service(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_subscription_deletion,
        )

        plan = _make_plan(ProductType.API, "Professional")
        sub = _make_subscription(ProductType.API, "Professional")

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal.begin",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.subscription_db.get_by_stripe_subscription_id",
                new_callable=AsyncMock,
                return_value=sub,
            ),
            patch(
                f"{HANDLER_MODULE}.plan_db.get_by_id",
                new_callable=AsyncMock,
                return_value=plan,
            ),
            patch(
                f"{HANDLER_MODULE}.api_subscription_service.handle_subscription_deleted",
                new_callable=AsyncMock,
            ) as mock_api,
            patch(
                f"{HANDLER_MODULE}.career_subscription_service.handle_subscription_deleted",
                new_callable=AsyncMock,
            ) as mock_career,
            patch(
                f"{HANDLER_MODULE}._send_subscription_canceled_email",
                new_callable=AsyncMock,
            ),
        ):
            await _process_subscription_deletion("sub_api_del")

            mock_api.assert_called_once_with(
                mock_session,
                stripe_subscription_id="sub_api_del",
                commit_self=False,
            )
            mock_career.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_subscription_not_found(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_subscription_deletion,
        )

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal.begin",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.subscription_db.get_by_stripe_subscription_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                f"{HANDLER_MODULE}.api_subscription_service.handle_subscription_deleted",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            await _process_subscription_deletion("sub_not_found")
            mock_api.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_cancellation_email(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_subscription_deletion,
        )

        plan = _make_plan(ProductType.API, "Professional")
        sub = _make_subscription(ProductType.API, "Professional")

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal.begin",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.subscription_db.get_by_stripe_subscription_id",
                new_callable=AsyncMock,
                return_value=sub,
            ),
            patch(
                f"{HANDLER_MODULE}.plan_db.get_by_id",
                new_callable=AsyncMock,
                return_value=plan,
            ),
            patch(
                f"{HANDLER_MODULE}.api_subscription_service.handle_subscription_deleted",
                new_callable=AsyncMock,
            ),
            patch(
                f"{HANDLER_MODULE}._send_subscription_canceled_email",
                new_callable=AsyncMock,
            ) as mock_email,
        ):
            await _process_subscription_deletion("sub_email_del")

            mock_email.assert_called_once_with(mock_session, sub, "Professional")


class TestProcessPaymentFailure:

    @pytest.mark.asyncio
    async def test_returns_early_when_no_subscription_id(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_payment_failure,
        )

        with patch(
            f"{HANDLER_MODULE}.AsyncSessionLocal",
        ) as mock_session_cls:
            await _process_payment_failure(None, 2999)
            mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_when_subscription_not_found(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_payment_failure,
        )

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.subscription_db.get_by_stripe_subscription_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                f"{HANDLER_MODULE}._send_payment_failed_email",
                new_callable=AsyncMock,
            ) as mock_email,
        ):
            await _process_payment_failure("sub_not_found", 2999)
            mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_formats_amount_and_sends_email(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_payment_failure,
        )

        plan = _make_plan(ProductType.API, "Professional")
        sub = _make_subscription(ProductType.API, "Professional")

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.subscription_db.get_by_stripe_subscription_id",
                new_callable=AsyncMock,
                return_value=sub,
            ),
            patch(
                f"{HANDLER_MODULE}.plan_db.get_by_id",
                new_callable=AsyncMock,
                return_value=plan,
            ),
            patch(
                f"{HANDLER_MODULE}._send_payment_failed_email",
                new_callable=AsyncMock,
            ) as mock_email,
        ):
            await _process_payment_failure("sub_pf_123", 4999)

            mock_email.assert_called_once_with(
                mock_session, sub, "Professional", "$49.99"
            )

    @pytest.mark.asyncio
    async def test_none_amount_passes_none_string(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_payment_failure,
        )

        plan = _make_plan(ProductType.CAREER, "Plus")
        sub = _make_subscription(ProductType.CAREER, "Plus")

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.subscription_db.get_by_stripe_subscription_id",
                new_callable=AsyncMock,
                return_value=sub,
            ),
            patch(
                f"{HANDLER_MODULE}.plan_db.get_by_id",
                new_callable=AsyncMock,
                return_value=plan,
            ),
            patch(
                f"{HANDLER_MODULE}._send_payment_failed_email",
                new_callable=AsyncMock,
            ) as mock_email,
        ):
            await _process_payment_failure("sub_no_amount", None)

            mock_email.assert_called_once_with(mock_session, sub, "Plus", None)


class TestProcessCheckoutHelpers:

    @pytest.mark.asyncio
    async def test_process_career_checkout_calls_service(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_career_checkout,
        )

        user_id = uuid4()
        plan_id = uuid4()

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal.begin",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.career_subscription_service.handle_checkout_completed",
                new_callable=AsyncMock,
            ) as mock_service,
        ):
            await _process_career_checkout(
                "sub_career_co", "cus_career_co", user_id, plan_id
            )

            mock_service.assert_called_once_with(
                mock_session,
                stripe_subscription_id="sub_career_co",
                stripe_customer_id="cus_career_co",
                user_id=user_id,
                plan_id=plan_id,
                commit_self=False,
            )

    @pytest.mark.asyncio
    async def test_process_api_checkout_calls_service(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _process_api_checkout,
        )

        ws_id = uuid4()
        plan_id = uuid4()

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                f"{HANDLER_MODULE}.AsyncSessionLocal.begin",
                return_value=mock_ctx,
            ),
            patch(
                f"{HANDLER_MODULE}.api_subscription_service.handle_checkout_completed",
                new_callable=AsyncMock,
            ) as mock_service,
        ):
            await _process_api_checkout("sub_api_co", "cus_api_co", ws_id, plan_id, 5)

            mock_service.assert_called_once_with(
                mock_session,
                stripe_subscription_id="sub_api_co",
                stripe_customer_id="cus_api_co",
                workspace_id=ws_id,
                plan_id=plan_id,
                seat_count=5,
                commit_self=False,
            )


class TestEmailHelpers:

    @pytest.mark.asyncio
    async def test_send_activated_email_career(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _send_subscription_activated_email,
        )

        sub = _make_subscription(ProductType.CAREER, "Plus")

        mock_session = AsyncMock()
        user = MagicMock()
        user.email = "career@example.com"
        user.full_name = "Test User"

        context = MagicMock()
        context.user_id = uuid4()

        with (
            patch(
                f"{HANDLER_MODULE}.career_subscription_context_db.get_by_subscription",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                f"{HANDLER_MODULE}.user_db.get_by_id",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(
                f"{HANDLER_MODULE}.publish_event",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await _send_subscription_activated_email(mock_session, sub, "Free")

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][0] == "subscription_activated_emails"
            payload = call_args[0][1]
            assert payload["email"] == "career@example.com"
            assert payload["plan_name"] == "Plus"
            assert payload["product_type"] == ProductType.CAREER.value

    @pytest.mark.asyncio
    async def test_send_activated_email_api(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _send_subscription_activated_email,
        )

        sub = _make_subscription(ProductType.API, "Professional")

        mock_session = AsyncMock()
        owner = MagicMock()
        owner.email = "owner@example.com"
        owner.full_name = "Workspace Owner"

        workspace = MagicMock()
        workspace.owner = owner
        workspace.display_name = "My Workspace"

        context = MagicMock()
        context.workspace_id = uuid4()

        with (
            patch(
                f"{HANDLER_MODULE}.api_subscription_context_db.get_by_subscription",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                f"{HANDLER_MODULE}.workspace_db.get_by_id",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch(
                f"{HANDLER_MODULE}.publish_event",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await _send_subscription_activated_email(mock_session, sub, "Basic")

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][0] == "subscription_activated_emails"
            payload = call_args[0][1]
            assert payload["email"] == "owner@example.com"
            assert payload["workspace_name"] == "My Workspace"
            assert payload["product_type"] == ProductType.API.value

    @pytest.mark.asyncio
    async def test_send_canceled_email_career(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _send_subscription_canceled_email,
        )

        sub = _make_subscription(ProductType.CAREER, "Plus")

        mock_session = AsyncMock()
        user = MagicMock()
        user.email = "career@example.com"
        user.full_name = "Test User"

        context = MagicMock()
        context.user_id = uuid4()

        with (
            patch(
                f"{HANDLER_MODULE}.career_subscription_context_db.get_by_subscription",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                f"{HANDLER_MODULE}.user_db.get_by_id",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(
                f"{HANDLER_MODULE}.publish_event",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await _send_subscription_canceled_email(mock_session, sub, "Plus")

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][0] == "subscription_canceled_emails"
            payload = call_args[0][1]
            assert payload["email"] == "career@example.com"
            assert payload["plan_name"] == "Plus"
            assert payload["product_name"] == "CueBX Career"
            assert payload["workspace_name"] is None

    @pytest.mark.asyncio
    async def test_send_canceled_email_api(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _send_subscription_canceled_email,
        )

        sub = _make_subscription(ProductType.API, "Professional")

        mock_session = AsyncMock()
        owner = MagicMock()
        owner.email = "owner@example.com"
        owner.full_name = "Workspace Owner"

        workspace = MagicMock()
        workspace.owner = owner
        workspace.display_name = "Team WS"

        context = MagicMock()
        context.workspace_id = uuid4()

        with (
            patch(
                f"{HANDLER_MODULE}.api_subscription_context_db.get_by_subscription",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                f"{HANDLER_MODULE}.workspace_db.get_by_id",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch(
                f"{HANDLER_MODULE}.publish_event",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await _send_subscription_canceled_email(mock_session, sub, "Professional")

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][0] == "subscription_canceled_emails"
            payload = call_args[0][1]
            assert payload["email"] == "owner@example.com"
            assert payload["workspace_name"] == "Team WS"
            assert payload["product_name"] == "CueBX API"

    @pytest.mark.asyncio
    async def test_send_payment_failed_email_career(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _send_payment_failed_email,
        )

        sub = _make_subscription(ProductType.CAREER, "Plus")

        mock_session = AsyncMock()
        user = MagicMock()
        user.email = "career@example.com"
        user.full_name = "Test User"

        context = MagicMock()
        context.user_id = uuid4()

        with (
            patch(
                f"{HANDLER_MODULE}.career_subscription_context_db.get_by_subscription",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                f"{HANDLER_MODULE}.user_db.get_by_id",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(
                f"{HANDLER_MODULE}.publish_event",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await _send_payment_failed_email(mock_session, sub, "Plus", "$29.99")

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][0] == "payment_failed_emails"
            payload = call_args[0][1]
            assert payload["email"] == "career@example.com"
            assert payload["amount"] == "$29.99"
            assert payload["product_name"] == "CueBX Career"

    @pytest.mark.asyncio
    async def test_send_payment_failed_email_api(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _send_payment_failed_email,
        )

        sub = _make_subscription(ProductType.API, "Professional")

        mock_session = AsyncMock()
        owner = MagicMock()
        owner.email = "owner@example.com"
        owner.full_name = "Owner"

        workspace = MagicMock()
        workspace.owner = owner
        workspace.display_name = "Prod WS"

        context = MagicMock()
        context.workspace_id = uuid4()

        with (
            patch(
                f"{HANDLER_MODULE}.api_subscription_context_db.get_by_subscription",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                f"{HANDLER_MODULE}.workspace_db.get_by_id",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch(
                f"{HANDLER_MODULE}.publish_event",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await _send_payment_failed_email(
                mock_session, sub, "Professional", "$99.99"
            )

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][0] == "payment_failed_emails"
            payload = call_args[0][1]
            assert payload["email"] == "owner@example.com"
            assert payload["workspace_name"] == "Prod WS"
            assert payload["product_name"] == "CueBX API"

    @pytest.mark.asyncio
    async def test_email_skipped_when_no_context(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _send_subscription_activated_email,
        )

        sub = _make_subscription(ProductType.CAREER, "Plus")
        mock_session = AsyncMock()

        with (
            patch(
                f"{HANDLER_MODULE}.career_subscription_context_db.get_by_subscription",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                f"{HANDLER_MODULE}.publish_event",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await _send_subscription_activated_email(mock_session, sub, "Free")

            mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_skipped_when_no_user(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _send_subscription_activated_email,
        )

        sub = _make_subscription(ProductType.CAREER, "Plus")
        mock_session = AsyncMock()

        context = MagicMock()
        context.user_id = uuid4()

        with (
            patch(
                f"{HANDLER_MODULE}.career_subscription_context_db.get_by_subscription",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                f"{HANDLER_MODULE}.user_db.get_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                f"{HANDLER_MODULE}.publish_event",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await _send_subscription_activated_email(mock_session, sub, "Free")

            mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_skipped_when_no_workspace_owner(self):
        from app.infrastructure.messaging.handlers.stripe import (
            _send_subscription_activated_email,
        )

        sub = _make_subscription(ProductType.API, "Pro")
        mock_session = AsyncMock()

        context = MagicMock()
        context.workspace_id = uuid4()

        workspace = MagicMock()
        workspace.owner = None

        with (
            patch(
                f"{HANDLER_MODULE}.api_subscription_context_db.get_by_subscription",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                f"{HANDLER_MODULE}.workspace_db.get_by_id",
                new_callable=AsyncMock,
                return_value=workspace,
            ),
            patch(
                f"{HANDLER_MODULE}.publish_event",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await _send_subscription_activated_email(mock_session, sub, "Free")

            mock_publish.assert_not_called()
