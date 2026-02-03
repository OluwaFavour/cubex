"""
Tests for the Stripe service.

This module contains tests for the Stripe payment service, including
the _flatten_to_payload helper function.
"""

import pytest
from typing import Any

from app.shared.services.payment.stripe.main import Stripe


class TestFlattenToPayload:
    """Tests for the _flatten_to_payload helper method."""

    def test_simple_flat_dict(self):
        """Test flattening a simple flat dictionary."""
        payload: dict[str, Any] = {}
        data = {"key1": "value1", "key2": "value2"}

        Stripe._flatten_to_payload(payload, "prefix", data)

        assert payload == {
            "prefix[key1]": "value1",
            "prefix[key2]": "value2",
        }

    def test_metadata_flattening(self):
        """Test flattening metadata dict (common Stripe use case)."""
        payload: dict[str, Any] = {}
        data = {"user_id": "123", "plan_id": "456"}

        Stripe._flatten_to_payload(payload, "metadata", data)

        assert payload == {
            "metadata[user_id]": "123",
            "metadata[plan_id]": "456",
        }

    def test_nested_dict(self):
        """Test flattening nested dictionaries."""
        payload: dict[str, Any] = {}
        data = {
            "metadata": {
                "workspace_id": "ws-123",
                "plan_id": "plan-456",
            }
        }

        Stripe._flatten_to_payload(payload, "subscription_data", data)

        assert payload == {
            "subscription_data[metadata][workspace_id]": "ws-123",
            "subscription_data[metadata][plan_id]": "plan-456",
        }

    def test_deeply_nested_dict(self):
        """Test flattening deeply nested dictionaries."""
        payload: dict[str, Any] = {}
        data = {
            "level1": {
                "level2": {
                    "level3": "deep_value",
                }
            }
        }

        Stripe._flatten_to_payload(payload, "root", data)

        assert payload == {
            "root[level1][level2][level3]": "deep_value",
        }

    def test_max_depth_limit(self):
        """Test that max_depth prevents infinite recursion."""
        payload: dict[str, Any] = {}
        # Create a 5-level deep dict, but set max_depth to 2
        data = {
            "l1": {
                "l2": {
                    "l3": {
                        "l4": "too_deep",
                    }
                }
            }
        }

        Stripe._flatten_to_payload(payload, "root", data, max_depth=2)

        # At depth 2, it should stringify the remaining dict
        assert "root[l1][l2][l3]" in payload
        # The value should be a string representation of the remaining dict
        assert payload["root[l1][l2][l3]"] == "{'l4': 'too_deep'}"

    def test_list_of_dicts(self):
        """Test flattening a list of dictionaries (like line_items)."""
        payload: dict[str, Any] = {}
        data = {
            "items": [
                {"price": "price_123", "quantity": 1},
                {"price": "price_456", "quantity": 2},
            ]
        }

        Stripe._flatten_to_payload(payload, "line", data)

        assert payload == {
            "line[items][0][price]": "price_123",
            "line[items][0][quantity]": "1",
            "line[items][1][price]": "price_456",
            "line[items][1][quantity]": "2",
        }

    def test_list_of_primitives(self):
        """Test flattening a list of primitive values."""
        payload: dict[str, Any] = {}
        data = {"tags": ["tag1", "tag2", "tag3"]}

        Stripe._flatten_to_payload(payload, "product", data)

        assert payload == {
            "product[tags][0]": "tag1",
            "product[tags][1]": "tag2",
            "product[tags][2]": "tag3",
        }

    def test_none_values_become_empty_string(self):
        """Test that None values are converted to empty strings."""
        payload: dict[str, Any] = {}
        data = {"key1": "value1", "key2": None, "key3": "value3"}

        Stripe._flatten_to_payload(payload, "prefix", data)

        assert payload == {
            "prefix[key1]": "value1",
            "prefix[key2]": "",
            "prefix[key3]": "value3",
        }

    def test_numeric_values_become_strings(self):
        """Test that numeric values are converted to strings."""
        payload: dict[str, Any] = {}
        data = {"count": 5, "price": 19.99, "active": True}

        Stripe._flatten_to_payload(payload, "item", data)

        assert payload == {
            "item[count]": "5",
            "item[price]": "19.99",
            "item[active]": "True",
        }

    def test_empty_dict(self):
        """Test flattening an empty dictionary."""
        payload: dict[str, Any] = {}
        data: dict[str, Any] = {}

        Stripe._flatten_to_payload(payload, "empty", data)

        assert payload == {}

    def test_preserves_existing_payload_keys(self):
        """Test that existing payload keys are preserved."""
        payload: dict[str, Any] = {"existing_key": "existing_value"}
        data = {"new_key": "new_value"}

        Stripe._flatten_to_payload(payload, "prefix", data)

        assert payload == {
            "existing_key": "existing_value",
            "prefix[new_key]": "new_value",
        }

    def test_subscription_data_with_metadata(self):
        """Test real-world subscription_data flattening."""
        payload: dict[str, Any] = {}
        subscription_data = {
            "trial_period_days": 14,
            "metadata": {
                "workspace_id": "ws-abc-123",
                "plan_id": "plan-xyz-789",
                "seat_count": "5",
                "product_type": "api",
            },
        }

        Stripe._flatten_to_payload(payload, "subscription_data", subscription_data)

        assert payload == {
            "subscription_data[trial_period_days]": "14",
            "subscription_data[metadata][workspace_id]": "ws-abc-123",
            "subscription_data[metadata][plan_id]": "plan-xyz-789",
            "subscription_data[metadata][seat_count]": "5",
            "subscription_data[metadata][product_type]": "api",
        }

    def test_payment_intent_data_with_metadata(self):
        """Test real-world payment_intent_data flattening."""
        payload: dict[str, Any] = {}
        payment_intent_data = {
            "description": "One-time payment",
            "metadata": {
                "order_id": "order-123",
                "user_id": "user-456",
            },
        }

        Stripe._flatten_to_payload(payload, "payment_intent_data", payment_intent_data)

        assert payload == {
            "payment_intent_data[description]": "One-time payment",
            "payment_intent_data[metadata][order_id]": "order-123",
            "payment_intent_data[metadata][user_id]": "user-456",
        }

    def test_currency_options_nested_structure(self):
        """Test currency_options nested structure flattening."""
        payload: dict[str, Any] = {}
        # Simulating: currency_options[usd][unit_amount] = 1000
        options = {"unit_amount": 1000, "tax_behavior": "exclusive"}

        Stripe._flatten_to_payload(payload, "currency_options[usd]", options)

        assert payload == {
            "currency_options[usd][unit_amount]": "1000",
            "currency_options[usd][tax_behavior]": "exclusive",
        }

    def test_mixed_nested_and_flat_keys(self):
        """Test a dict with both nested and flat keys."""
        payload: dict[str, Any] = {}
        data = {
            "simple_key": "simple_value",
            "nested": {
                "inner_key": "inner_value",
            },
            "another_simple": "another_value",
        }

        Stripe._flatten_to_payload(payload, "prefix", data)

        assert payload == {
            "prefix[simple_key]": "simple_value",
            "prefix[nested][inner_key]": "inner_value",
            "prefix[another_simple]": "another_value",
        }

    def test_uuid_values_converted_to_string(self):
        """Test that UUID values are properly converted to strings."""
        from uuid import UUID

        payload: dict[str, Any] = {}
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        data = {"workspace_id": str(test_uuid)}

        Stripe._flatten_to_payload(payload, "metadata", data)

        assert payload == {
            "metadata[workspace_id]": "12345678-1234-5678-1234-567812345678",
        }
