"""
Test suite for Quota CRUD operations.

Run tests:
    pytest tests/apps/cubex_api/test_quota_crud.py -v

Run with coverage:
    pytest tests/apps/cubex_api/test_quota_crud.py --cov=app.apps.cubex_api.db.crud.quota --cov-report=term-missing -v
"""

from app.core.db.crud.quota import (
    FeatureCostConfigDB,
    PlanPricingRuleDB,
    feature_cost_config_db,
    plan_pricing_rule_db,
)


class TestFeatureCostConfigDBImports:
    """Test suite for FeatureCostConfigDB imports and initialization."""

    def test_feature_cost_config_db_import(self):
        """Test that FeatureCostConfigDB class can be imported."""
        assert FeatureCostConfigDB is not None

    def test_feature_cost_config_db_instance_exists(self):
        """Test that the global instance exists."""
        assert feature_cost_config_db is not None

    def test_feature_cost_config_db_is_correct_type(self):
        """Test that global instance is correct type."""
        assert isinstance(feature_cost_config_db, FeatureCostConfigDB)

    def test_feature_cost_config_db_has_model(self):
        """Test that the CRUD class has the correct model."""
        from app.core.db.models.quota import FeatureCostConfig

        assert feature_cost_config_db.model == FeatureCostConfig


class TestFeatureCostConfigDBMethods:
    """Test suite for FeatureCostConfigDB method signatures."""

    def test_has_get_by_feature_key(self):
        """Test that get_by_feature_key method exists."""
        assert hasattr(feature_cost_config_db, "get_by_feature_key")
        assert callable(feature_cost_config_db.get_by_feature_key)

    def test_has_get_all_active_method(self):
        """Test that get_all_active method exists."""
        assert hasattr(feature_cost_config_db, "get_all_active")
        assert callable(feature_cost_config_db.get_all_active)

    def test_has_create_or_update_method(self):
        """Test that create_or_update method exists."""
        assert hasattr(feature_cost_config_db, "create_or_update")
        assert callable(feature_cost_config_db.create_or_update)

    def test_has_inherited_create_method(self):
        """Test that create method is inherited from BaseDB."""
        assert hasattr(feature_cost_config_db, "create")
        assert callable(feature_cost_config_db.create)

    def test_has_inherited_get_by_id_method(self):
        """Test that get_by_id method is inherited from BaseDB."""
        assert hasattr(feature_cost_config_db, "get_by_id")
        assert callable(feature_cost_config_db.get_by_id)

    def test_has_inherited_update_method(self):
        """Test that update method is inherited from BaseDB."""
        assert hasattr(feature_cost_config_db, "update")
        assert callable(feature_cost_config_db.update)

    def test_has_inherited_delete_method(self):
        """Test that delete method is inherited from BaseDB."""
        assert hasattr(feature_cost_config_db, "delete")
        assert callable(feature_cost_config_db.delete)


class TestPlanPricingRuleDBImports:
    """Test suite for PlanPricingRuleDB imports and initialization."""

    def test_plan_pricing_rule_db_import(self):
        """Test that PlanPricingRuleDB class can be imported."""
        assert PlanPricingRuleDB is not None

    def test_plan_pricing_rule_db_instance_exists(self):
        """Test that the global instance exists."""
        assert plan_pricing_rule_db is not None

    def test_plan_pricing_rule_db_is_correct_type(self):
        """Test that global instance is correct type."""
        assert isinstance(plan_pricing_rule_db, PlanPricingRuleDB)

    def test_plan_pricing_rule_db_has_model(self):
        """Test that the CRUD class has the correct model."""
        from app.core.db.models.quota import PlanPricingRule

        assert plan_pricing_rule_db.model == PlanPricingRule


class TestPlanPricingRuleDBMethods:
    """Test suite for PlanPricingRuleDB method signatures."""

    def test_has_get_by_plan_id_method(self):
        """Test that get_by_plan_id method exists."""
        assert hasattr(plan_pricing_rule_db, "get_by_plan_id")
        assert callable(plan_pricing_rule_db.get_by_plan_id)

    def test_has_get_all_active_method(self):
        """Test that get_all_active method exists."""
        assert hasattr(plan_pricing_rule_db, "get_all_active")
        assert callable(plan_pricing_rule_db.get_all_active)

    def test_has_create_or_update_method(self):
        """Test that create_or_update method exists."""
        assert hasattr(plan_pricing_rule_db, "create_or_update")
        assert callable(plan_pricing_rule_db.create_or_update)

    def test_has_inherited_create_method(self):
        """Test that create method is inherited from BaseDB."""
        assert hasattr(plan_pricing_rule_db, "create")
        assert callable(plan_pricing_rule_db.create)

    def test_has_inherited_get_by_id_method(self):
        """Test that get_by_id method is inherited from BaseDB."""
        assert hasattr(plan_pricing_rule_db, "get_by_id")
        assert callable(plan_pricing_rule_db.get_by_id)

    def test_has_inherited_update_method(self):
        """Test that update method is inherited from BaseDB."""
        assert hasattr(plan_pricing_rule_db, "update")
        assert callable(plan_pricing_rule_db.update)

    def test_has_inherited_delete_method(self):
        """Test that delete method is inherited from BaseDB."""
        assert hasattr(plan_pricing_rule_db, "delete")
        assert callable(plan_pricing_rule_db.delete)


class TestCRUDExportsFromInit:
    """Test suite for CRUD exports from __init__.py."""

    def test_feature_cost_config_db_exported(self):
        """Test that feature_cost_config_db is exported from crud init."""
        from app.core.db.crud import feature_cost_config_db as exported_db

        assert exported_db is feature_cost_config_db

    def test_plan_pricing_rule_db_exported(self):
        """Test that plan_pricing_rule_db is exported from crud init."""
        from app.core.db.crud import plan_pricing_rule_db as exported_db

        assert exported_db is plan_pricing_rule_db

    def test_feature_cost_config_db_class_exported(self):
        """Test that FeatureCostConfigDB class is exported from crud init."""
        from app.core.db.crud import (
            FeatureCostConfigDB as ExportedClass,
        )

        assert ExportedClass is FeatureCostConfigDB

    def test_plan_pricing_rule_db_class_exported(self):
        """Test that PlanPricingRuleDB class is exported from crud init."""
        from app.core.db.crud import (
            PlanPricingRuleDB as ExportedClass,
        )

        assert ExportedClass is PlanPricingRuleDB
