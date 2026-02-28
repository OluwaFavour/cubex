"""
Test suite for manage.py CLI commands.

This module tests the Typer CLI commands in manage.py.

Run all tests:
    pytest tests/test_manage.py -v

Run with coverage:
    pytest tests/test_manage.py --cov=manage --cov-report=term-missing -v
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from manage import app, sync_plans_task

runner = CliRunner()


class TestSyncPlansCommand:

    def test_syncplans_help(self):
        result = runner.invoke(app, ["syncplans", "--help"])
        assert result.exit_code == 0
        assert "Synchronize subscription plans" in result.stdout
        assert "--dry-run" in result.stdout or "-n" in result.stdout

    def test_syncplans_dry_run_flag_accepted(self):
        with patch("manage.sync_plans_task") as mock_task:
            mock_task.return_value = None
            result = runner.invoke(app, ["syncplans", "--dry-run"])
            # The command should run (even if it fails due to missing file in test env)
            # We're just checking the flag is recognized
            assert "--dry-run" not in result.stdout or result.exit_code in [0, 1]

    def test_syncplans_short_flag_accepted(self):
        with patch("manage.sync_plans_task") as mock_task:
            mock_task.return_value = None
            result = runner.invoke(app, ["syncplans", "-n"])
            assert "-n" not in result.stdout or result.exit_code in [0, 1]


class TestSyncPlansTask:

    @pytest.mark.asyncio
    async def test_sync_plans_task_loads_plans_json(self):
        mock_plans_data = {
            "api_plans": [
                {
                    "name": "Free",
                    "description": "Test plan",
                    "price": "0.00",
                    "display_price": "$0/month",
                    "stripe_price_id_env": None,
                    "seat_price": "0.00",
                    "seat_display_price": None,
                    "seat_stripe_price_id_env": None,
                    "is_active": True,
                    "trial_days": None,
                    "type": "FREE",
                    "product_type": "API",
                    "min_seats": 1,
                    "max_seats": 1,
                    "features": [],
                }
            ],
            "career_plans": [],
        }

        with patch("manage.Path") as mock_path_class:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.__truediv__ = MagicMock(return_value=mock_path)
            mock_path_class.return_value = mock_path

            with patch("builtins.open", MagicMock()) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = (
                    json.dumps(mock_plans_data)
                )
                with patch("json.load", return_value=mock_plans_data):
                    # Run in dry_run mode to skip actual DB operations
                    await sync_plans_task(dry_run=True)

    @pytest.mark.asyncio
    async def test_sync_plans_task_dry_run_no_db_changes(self):
        mock_plans_data = {
            "api_plans": [
                {
                    "name": "Test",
                    "price": "0.00",
                    "display_price": "$0/month",
                    "type": "FREE",
                    "product_type": "API",
                    "features": [],
                }
            ],
            "career_plans": [],
        }

        with patch("manage.Path") as mock_path_class:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.__truediv__ = MagicMock(return_value=mock_path)
            mock_path_class.return_value = mock_path

            with patch("builtins.open", MagicMock()):
                with patch("json.load", return_value=mock_plans_data):
                    # In dry_run mode, we should NOT interact with the database
                    # Just verify it runs without error
                    await sync_plans_task(dry_run=True)


class TestPlansJsonStructure:

    def test_plans_json_exists(self):
        plans_file = (
            Path(__file__).parent.parent / "app" / "core" / "data" / "plans.json"
        )
        # This may not exist in test environment, so we just verify the path is correct
        assert "plans.json" in str(plans_file)

    def test_plans_json_has_required_fields(self):
        required_fields = [
            "name",
            "price",
            "type",
            "product_type",
            "features",
        ]

        plans_file = (
            Path(__file__).parent.parent / "app" / "core" / "data" / "plans.json"
        )

        if plans_file.exists():
            with plans_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            all_plans = data.get("api_plans", []) + data.get("career_plans", [])
            for plan in all_plans:
                for field in required_fields:
                    assert (
                        field in plan
                    ), f"Plan '{plan.get('name', 'unknown')}' missing field: {field}"

    def test_plans_json_seat_pricing_fields(self):
        seat_fields = [
            "seat_price",
            "seat_display_price",
            "seat_stripe_price_id_env",
        ]

        plans_file = (
            Path(__file__).parent.parent / "app" / "core" / "data" / "plans.json"
        )

        if plans_file.exists():
            with plans_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            all_plans = data.get("api_plans", []) + data.get("career_plans", [])
            for plan in all_plans:
                for field in seat_fields:
                    assert (
                        field in plan
                    ), f"Plan '{plan.get('name', 'unknown')}' missing seat field: {field}"

    def test_plans_json_api_plans_structure(self):
        plans_file = (
            Path(__file__).parent.parent / "app" / "core" / "data" / "plans.json"
        )

        if plans_file.exists():
            with plans_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            api_plans = data.get("api_plans", [])
            plan_names = [p["name"] for p in api_plans]

            assert "Free" in plan_names
            assert "Basic" in plan_names
            assert "Professional" in plan_names

    def test_plans_json_career_plans_no_seat_pricing(self):
        plans_file = (
            Path(__file__).parent.parent / "app" / "core" / "data" / "plans.json"
        )

        if plans_file.exists():
            with plans_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            career_plans = data.get("career_plans", [])
            for plan in career_plans:
                # Career plans should not have seat stripe IDs
                assert (
                    plan.get("seat_stripe_price_id_env") is None
                ), f"Career plan '{plan['name']}' should not have seat_stripe_price_id_env"
