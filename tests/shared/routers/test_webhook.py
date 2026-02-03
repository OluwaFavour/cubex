"""
Integration tests for webhook router endpoints.

Tests all webhook endpoints with mocked Stripe signature verification
and message queue publishing.
"""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient


# ============================================================================
# Test Stripe Webhook Endpoint
# ============================================================================


class TestStripeWebhookEndpoint:
    """Tests for POST /webhooks/stripe"""

    @pytest.mark.asyncio
    async def test_webhook_missing_signature(self, client: AsyncClient):
        """Should return 400 when Stripe-Signature header is missing."""
        payload = {"type": "checkout.session.completed", "id": "evt_123"}
        response = await client.post(
            "/webhooks/stripe",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Missing Stripe-Signature header"

    @pytest.mark.asyncio
    async def test_webhook_invalid_signature(self, client: AsyncClient):
        """Should return 400 when signature verification fails."""
        payload = {"type": "checkout.session.completed", "id": "evt_123"}

        with patch(
            "app.shared.routers.webhook.Stripe.verify_webhook_signature",
            side_effect=Exception("Invalid signature"),
        ):
            response = await client.post(
                "/webhooks/stripe",
                content=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "invalid_signature",
                },
            )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid signature"

    @pytest.mark.asyncio
    async def test_webhook_missing_event_id(self, client: AsyncClient):
        """Should return 400 when event id is missing."""
        payload = {"type": "checkout.session.completed"}

        with patch(
            "app.shared.routers.webhook.Stripe.verify_webhook_signature",
            return_value={"type": "checkout.session.completed", "id": None},
        ):
            response = await client.post(
                "/webhooks/stripe",
                content=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "valid_signature",
                },
            )

        assert response.status_code == 400
        assert response.json()["detail"] == "Missing event id or type"

    @pytest.mark.asyncio
    async def test_webhook_missing_event_type(self, client: AsyncClient):
        """Should return 400 when event type is missing."""
        payload = {"id": "evt_123"}

        with patch(
            "app.shared.routers.webhook.Stripe.verify_webhook_signature",
            return_value={"id": "evt_123", "type": None},
        ):
            response = await client.post(
                "/webhooks/stripe",
                content=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "valid_signature",
                },
            )

        assert response.status_code == 400
        assert response.json()["detail"] == "Missing event id or type"

    @pytest.mark.asyncio
    async def test_webhook_unhandled_event_type(self, client: AsyncClient):
        """Should return ignored status for unhandled event types."""
        with patch(
            "app.shared.routers.webhook.Stripe.verify_webhook_signature",
            return_value={
                "id": "evt_123",
                "type": "unhandled.event.type",
                "data": {"object": {}},
            },
        ):
            response = await client.post(
                "/webhooks/stripe",
                content=json.dumps({}),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "valid_signature",
                },
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_webhook_checkout_session_completed(self, client: AsyncClient):
        """Should publish checkout.session.completed to queue."""
        event_data = {
            "id": "evt_checkout_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "subscription": "sub_123",
                    "customer": "cus_123",
                    "metadata": {
                        "workspace_id": "ws_123",
                        "plan_id": "plan_123",
                        "seat_count": "5",
                    },
                }
            },
        }

        with patch(
            "app.shared.routers.webhook.Stripe.verify_webhook_signature",
            return_value=event_data,
        ), patch(
            "app.shared.routers.webhook.publish_event",
            new_callable=AsyncMock,
        ) as mock_publish:
            response = await client.post(
                "/webhooks/stripe",
                content=json.dumps({}),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "valid_signature",
                },
            )

        assert response.status_code == 200
        assert response.json()["status"] == "received"

        # Verify publish was called with correct queue and message
        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        assert call_args[0][0] == "stripe_checkout_completed"
        message = call_args[0][1]
        assert message["event_id"] == "evt_checkout_123"
        assert message["stripe_subscription_id"] == "sub_123"
        assert message["stripe_customer_id"] == "cus_123"
        assert message["workspace_id"] == "ws_123"
        assert message["plan_id"] == "plan_123"
        assert message["seat_count"] == 5

    @pytest.mark.asyncio
    async def test_webhook_subscription_created(self, client: AsyncClient):
        """Should publish customer.subscription.created to queue."""
        event_data = {
            "id": "evt_sub_created_123",
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_new_123",
                }
            },
        }

        with patch(
            "app.shared.routers.webhook.Stripe.verify_webhook_signature",
            return_value=event_data,
        ), patch(
            "app.shared.routers.webhook.publish_event",
            new_callable=AsyncMock,
        ) as mock_publish:
            response = await client.post(
                "/webhooks/stripe",
                content=json.dumps({}),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "valid_signature",
                },
            )

        assert response.status_code == 200
        assert response.json()["status"] == "received"

        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        assert call_args[0][0] == "stripe_subscription_updated"
        message = call_args[0][1]
        assert message["event_id"] == "evt_sub_created_123"
        assert message["stripe_subscription_id"] == "sub_new_123"

    @pytest.mark.asyncio
    async def test_webhook_subscription_updated(self, client: AsyncClient):
        """Should publish customer.subscription.updated to queue."""
        event_data = {
            "id": "evt_sub_updated_123",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_updated_123",
                }
            },
        }

        with patch(
            "app.shared.routers.webhook.Stripe.verify_webhook_signature",
            return_value=event_data,
        ), patch(
            "app.shared.routers.webhook.publish_event",
            new_callable=AsyncMock,
        ) as mock_publish:
            response = await client.post(
                "/webhooks/stripe",
                content=json.dumps({}),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "valid_signature",
                },
            )

        assert response.status_code == 200
        assert response.json()["status"] == "received"

        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        assert call_args[0][0] == "stripe_subscription_updated"
        message = call_args[0][1]
        assert message["event_id"] == "evt_sub_updated_123"
        assert message["stripe_subscription_id"] == "sub_updated_123"

    @pytest.mark.asyncio
    async def test_webhook_subscription_deleted(self, client: AsyncClient):
        """Should publish customer.subscription.deleted to queue."""
        event_data = {
            "id": "evt_sub_deleted_123",
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_deleted_123",
                }
            },
        }

        with patch(
            "app.shared.routers.webhook.Stripe.verify_webhook_signature",
            return_value=event_data,
        ), patch(
            "app.shared.routers.webhook.publish_event",
            new_callable=AsyncMock,
        ) as mock_publish:
            response = await client.post(
                "/webhooks/stripe",
                content=json.dumps({}),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "valid_signature",
                },
            )

        assert response.status_code == 200
        assert response.json()["status"] == "received"

        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        assert call_args[0][0] == "stripe_subscription_deleted"
        message = call_args[0][1]
        assert message["event_id"] == "evt_sub_deleted_123"
        assert message["stripe_subscription_id"] == "sub_deleted_123"

    @pytest.mark.asyncio
    async def test_webhook_invoice_paid(self, client: AsyncClient):
        """Should publish invoice.paid to queue."""
        event_data = {
            "id": "evt_invoice_paid_123",
            "type": "invoice.paid",
            "data": {
                "object": {
                    "subscription": "sub_invoice_123",
                }
            },
        }

        with patch(
            "app.shared.routers.webhook.Stripe.verify_webhook_signature",
            return_value=event_data,
        ), patch(
            "app.shared.routers.webhook.publish_event",
            new_callable=AsyncMock,
        ) as mock_publish:
            response = await client.post(
                "/webhooks/stripe",
                content=json.dumps({}),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "valid_signature",
                },
            )

        assert response.status_code == 200
        assert response.json()["status"] == "received"

        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        assert call_args[0][0] == "stripe_subscription_updated"
        message = call_args[0][1]
        assert message["event_id"] == "evt_invoice_paid_123"
        assert message["stripe_subscription_id"] == "sub_invoice_123"

    @pytest.mark.asyncio
    async def test_webhook_invoice_payment_failed(self, client: AsyncClient):
        """Should publish invoice.payment_failed to queue."""
        event_data = {
            "id": "evt_payment_failed_123",
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "subscription": "sub_failed_123",
                    "customer_email": "customer@example.com",
                }
            },
        }

        with patch(
            "app.shared.routers.webhook.Stripe.verify_webhook_signature",
            return_value=event_data,
        ), patch(
            "app.shared.routers.webhook.publish_event",
            new_callable=AsyncMock,
        ) as mock_publish:
            response = await client.post(
                "/webhooks/stripe",
                content=json.dumps({}),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "valid_signature",
                },
            )

        assert response.status_code == 200
        assert response.json()["status"] == "received"

        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        assert call_args[0][0] == "stripe_payment_failed"
        message = call_args[0][1]
        assert message["event_id"] == "evt_payment_failed_123"
        assert message["stripe_subscription_id"] == "sub_failed_123"
        assert message["customer_email"] == "customer@example.com"

    @pytest.mark.asyncio
    async def test_webhook_publish_failure(self, client: AsyncClient):
        """Should return publish_failed status when queue publish fails."""
        event_data = {
            "id": "evt_fail_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "subscription": "sub_123",
                    "customer": "cus_123",
                    "metadata": {},
                }
            },
        }

        with patch(
            "app.shared.routers.webhook.Stripe.verify_webhook_signature",
            return_value=event_data,
        ), patch(
            "app.shared.routers.webhook.publish_event",
            side_effect=Exception("Queue connection failed"),
        ):
            response = await client.post(
                "/webhooks/stripe",
                content=json.dumps({}),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "valid_signature",
                },
            )

        # Should still return 200 to prevent Stripe retries
        assert response.status_code == 200
        assert response.json()["status"] == "publish_failed"


# ============================================================================
# Test Event Queue Mapping
# ============================================================================


class TestEventQueueMapping:
    """Tests for event type to queue mapping."""

    def test_checkout_session_completed_mapping(self):
        """Test checkout.session.completed maps to correct queue."""
        from app.shared.routers.webhook import EVENT_QUEUE_MAPPING

        assert (
            EVENT_QUEUE_MAPPING["checkout.session.completed"]
            == "stripe_checkout_completed"
        )

    def test_subscription_created_mapping(self):
        """Test customer.subscription.created maps to correct queue."""
        from app.shared.routers.webhook import EVENT_QUEUE_MAPPING

        assert (
            EVENT_QUEUE_MAPPING["customer.subscription.created"]
            == "stripe_subscription_updated"
        )

    def test_subscription_updated_mapping(self):
        """Test customer.subscription.updated maps to correct queue."""
        from app.shared.routers.webhook import EVENT_QUEUE_MAPPING

        assert (
            EVENT_QUEUE_MAPPING["customer.subscription.updated"]
            == "stripe_subscription_updated"
        )

    def test_subscription_deleted_mapping(self):
        """Test customer.subscription.deleted maps to correct queue."""
        from app.shared.routers.webhook import EVENT_QUEUE_MAPPING

        assert (
            EVENT_QUEUE_MAPPING["customer.subscription.deleted"]
            == "stripe_subscription_deleted"
        )

    def test_invoice_paid_mapping(self):
        """Test invoice.paid maps to correct queue."""
        from app.shared.routers.webhook import EVENT_QUEUE_MAPPING

        assert EVENT_QUEUE_MAPPING["invoice.paid"] == "stripe_subscription_updated"

    def test_invoice_payment_failed_mapping(self):
        """Test invoice.payment_failed maps to correct queue."""
        from app.shared.routers.webhook import EVENT_QUEUE_MAPPING

        assert EVENT_QUEUE_MAPPING["invoice.payment_failed"] == "stripe_payment_failed"


# ============================================================================
# Test Build Queue Message Function
# ============================================================================


class TestBuildQueueMessage:
    """Tests for _build_queue_message helper function."""

    def test_build_checkout_session_completed_message(self):
        """Test building message for checkout.session.completed."""
        from app.shared.routers.webhook import _build_queue_message

        obj = {
            "subscription": "sub_123",
            "customer": "cus_456",
            "metadata": {
                "workspace_id": "ws_789",
                "plan_id": "plan_abc",
                "seat_count": "10",
            },
        }

        message = _build_queue_message("evt_123", "checkout.session.completed", obj)

        assert message["event_id"] == "evt_123"
        assert message["stripe_subscription_id"] == "sub_123"
        assert message["stripe_customer_id"] == "cus_456"
        assert message["workspace_id"] == "ws_789"
        assert message["plan_id"] == "plan_abc"
        assert message["seat_count"] == 10

    def test_build_checkout_session_completed_default_seat_count(self):
        """Test default seat count of 1 when not provided."""
        from app.shared.routers.webhook import _build_queue_message

        obj = {
            "subscription": "sub_123",
            "customer": "cus_456",
            "metadata": {},
        }

        message = _build_queue_message("evt_123", "checkout.session.completed", obj)

        assert message["seat_count"] == 1

    def test_build_subscription_created_message(self):
        """Test building message for customer.subscription.created."""
        from app.shared.routers.webhook import _build_queue_message

        obj = {"id": "sub_new_123"}

        message = _build_queue_message("evt_456", "customer.subscription.created", obj)

        assert message["event_id"] == "evt_456"
        assert message["stripe_subscription_id"] == "sub_new_123"

    def test_build_subscription_updated_message(self):
        """Test building message for customer.subscription.updated."""
        from app.shared.routers.webhook import _build_queue_message

        obj = {"id": "sub_updated_123"}

        message = _build_queue_message("evt_789", "customer.subscription.updated", obj)

        assert message["event_id"] == "evt_789"
        assert message["stripe_subscription_id"] == "sub_updated_123"

    def test_build_subscription_deleted_message(self):
        """Test building message for customer.subscription.deleted."""
        from app.shared.routers.webhook import _build_queue_message

        obj = {"id": "sub_deleted_123"}

        message = _build_queue_message(
            "evt_del_123", "customer.subscription.deleted", obj
        )

        assert message["event_id"] == "evt_del_123"
        assert message["stripe_subscription_id"] == "sub_deleted_123"

    def test_build_invoice_paid_message(self):
        """Test building message for invoice.paid."""
        from app.shared.routers.webhook import _build_queue_message

        obj = {"subscription": "sub_invoice_123"}

        message = _build_queue_message("evt_inv_123", "invoice.paid", obj)

        assert message["event_id"] == "evt_inv_123"
        assert message["stripe_subscription_id"] == "sub_invoice_123"

    def test_build_invoice_payment_failed_message(self):
        """Test building message for invoice.payment_failed."""
        from app.shared.routers.webhook import _build_queue_message

        obj = {
            "subscription": "sub_failed_123",
            "customer_email": "failed@example.com",
        }

        message = _build_queue_message("evt_fail_123", "invoice.payment_failed", obj)

        assert message["event_id"] == "evt_fail_123"
        assert message["stripe_subscription_id"] == "sub_failed_123"
        assert message["customer_email"] == "failed@example.com"


# ============================================================================
# Test Router Configuration
# ============================================================================


class TestRouterConfiguration:
    """Tests for router setup and configuration."""

    def test_router_is_api_router(self):
        """Test that router is an APIRouter instance."""
        from fastapi import APIRouter
        from app.shared.routers.webhook import router

        assert isinstance(router, APIRouter)

    def test_router_prefix(self):
        """Test that router has correct prefix."""
        from app.shared.routers.webhook import router

        assert router.prefix == "/webhooks"

    def test_router_has_stripe_endpoint(self):
        """Test that router has /stripe endpoint."""
        from app.shared.routers.webhook import router

        paths = [route.path for route in router.routes]
        # Path includes prefix /webhooks
        assert any("/stripe" in path for path in paths)


# ============================================================================
# Test Module Exports
# ============================================================================


class TestModuleExports:
    """Tests for module exports."""

    def test_router_is_exported(self):
        """Test that router is exported from module."""
        from app.shared.routers.webhook import router

        assert router is not None

    def test_event_queue_mapping_exported(self):
        """Test that EVENT_QUEUE_MAPPING is accessible."""
        from app.shared.routers.webhook import EVENT_QUEUE_MAPPING

        assert isinstance(EVENT_QUEUE_MAPPING, dict)
        assert len(EVENT_QUEUE_MAPPING) > 0
