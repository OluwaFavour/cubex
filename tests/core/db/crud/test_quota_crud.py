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

    def test_feature_cost_config_db_import(self):
        assert FeatureCostConfigDB is not None

    def test_feature_cost_config_db_instance_exists(self):
        assert feature_cost_config_db is not None

    def test_feature_cost_config_db_is_correct_type(self):
        assert isinstance(feature_cost_config_db, FeatureCostConfigDB)

    def test_feature_cost_config_db_has_model(self):
        from app.core.db.models.quota import FeatureCostConfig

        assert feature_cost_config_db.model == FeatureCostConfig


class TestFeatureCostConfigDBMethods:

    def test_has_get_by_feature_key(self):
        assert hasattr(feature_cost_config_db, "get_by_feature_key")
        assert callable(feature_cost_config_db.get_by_feature_key)

    def test_has_get_all_active_method(self):
        assert hasattr(feature_cost_config_db, "get_all_active")
        assert callable(feature_cost_config_db.get_all_active)

    def test_has_create_or_update_method(self):
        assert hasattr(feature_cost_config_db, "create_or_update")
        assert callable(feature_cost_config_db.create_or_update)

    def test_has_inherited_create_method(self):
        assert hasattr(feature_cost_config_db, "create")
        assert callable(feature_cost_config_db.create)

    def test_has_inherited_get_by_id_method(self):
        assert hasattr(feature_cost_config_db, "get_by_id")
        assert callable(feature_cost_config_db.get_by_id)

    def test_has_inherited_update_method(self):
        assert hasattr(feature_cost_config_db, "update")
        assert callable(feature_cost_config_db.update)

    def test_has_inherited_delete_method(self):
        assert hasattr(feature_cost_config_db, "delete")
        assert callable(feature_cost_config_db.delete)


class TestPlanPricingRuleDBImports:

    def test_plan_pricing_rule_db_import(self):
        assert PlanPricingRuleDB is not None

    def test_plan_pricing_rule_db_instance_exists(self):
        assert plan_pricing_rule_db is not None

    def test_plan_pricing_rule_db_is_correct_type(self):
        assert isinstance(plan_pricing_rule_db, PlanPricingRuleDB)

    def test_plan_pricing_rule_db_has_model(self):
        from app.core.db.models.quota import PlanPricingRule

        assert plan_pricing_rule_db.model == PlanPricingRule


class TestPlanPricingRuleDBMethods:

    def test_has_get_by_plan_id_method(self):
        assert hasattr(plan_pricing_rule_db, "get_by_plan_id")
        assert callable(plan_pricing_rule_db.get_by_plan_id)

    def test_has_get_all_active_method(self):
        assert hasattr(plan_pricing_rule_db, "get_all_active")
        assert callable(plan_pricing_rule_db.get_all_active)

    def test_has_create_or_update_method(self):
        assert hasattr(plan_pricing_rule_db, "create_or_update")
        assert callable(plan_pricing_rule_db.create_or_update)

    def test_has_inherited_create_method(self):
        assert hasattr(plan_pricing_rule_db, "create")
        assert callable(plan_pricing_rule_db.create)

    def test_has_inherited_get_by_id_method(self):
        assert hasattr(plan_pricing_rule_db, "get_by_id")
        assert callable(plan_pricing_rule_db.get_by_id)

    def test_has_inherited_update_method(self):
        assert hasattr(plan_pricing_rule_db, "update")
        assert callable(plan_pricing_rule_db.update)

    def test_has_inherited_delete_method(self):
        assert hasattr(plan_pricing_rule_db, "delete")
        assert callable(plan_pricing_rule_db.delete)


class TestCRUDExportsFromInit:

    def test_feature_cost_config_db_exported(self):
        from app.core.db.crud import feature_cost_config_db as exported_db

        assert exported_db is feature_cost_config_db

    def test_plan_pricing_rule_db_exported(self):
        from app.core.db.crud import plan_pricing_rule_db as exported_db

        assert exported_db is plan_pricing_rule_db

    def test_feature_cost_config_db_class_exported(self):
        from app.core.db.crud import (
            FeatureCostConfigDB as ExportedClass,
        )

        assert ExportedClass is FeatureCostConfigDB

    def test_plan_pricing_rule_db_class_exported(self):
        from app.core.db.crud import (
            PlanPricingRuleDB as ExportedClass,
        )

        assert ExportedClass is PlanPricingRuleDB
