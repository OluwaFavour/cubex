"""
Test suite for FeatureCostConfig model validators.

Run tests:
    pytest tests/core/db/models/test_quota.py -v

Run with coverage:
    pytest tests/core/db/models/test_quota.py --cov=app.core.db.models.quota --cov-report=term-missing -v
"""

from decimal import Decimal

import pytest

from app.core.db.models.quota import FeatureCostConfig
from app.core.enums import FeatureKey, ProductType


class TestDeriveProductType:
    """Tests for FeatureCostConfig._derive_product_type validator."""

    @pytest.mark.parametrize(
        "feature_key",
        [fk for fk in FeatureKey if fk.name.startswith("API_")],
    )
    def test_api_feature_keys_set_product_type_api(self, feature_key: FeatureKey):
        config = FeatureCostConfig(
            feature_key=feature_key,
            internal_cost_credits=Decimal("1.00"),
        )
        assert config.product_type == ProductType.API

    @pytest.mark.parametrize(
        "feature_key",
        [fk for fk in FeatureKey if fk.name.startswith("CAREER_")],
    )
    def test_career_feature_keys_set_product_type_career(self, feature_key: FeatureKey):
        config = FeatureCostConfig(
            feature_key=feature_key,
            internal_cost_credits=Decimal("1.00"),
        )
        assert config.product_type == ProductType.CAREER

    def test_accepts_string_value_for_api(self):
        config = FeatureCostConfig(
            feature_key="api.career_path",
            internal_cost_credits=Decimal("5.00"),
        )
        assert config.feature_key == FeatureKey.API_CAREER_PATH
        assert config.product_type == ProductType.API

    def test_accepts_string_value_for_career(self):
        config = FeatureCostConfig(
            feature_key="career.career_path",
            internal_cost_credits=Decimal("5.00"),
        )
        assert config.feature_key == FeatureKey.CAREER_CAREER_PATH
        assert config.product_type == ProductType.CAREER

    def test_accepts_enum_name_string_for_api(self):
        """SQLAdmin sends enum names (e.g. 'API_CAREER_PATH') not values."""
        config = FeatureCostConfig(
            feature_key="API_CAREER_PATH",
            internal_cost_credits=Decimal("18.00"),
        )
        assert config.feature_key == FeatureKey.API_CAREER_PATH
        assert config.product_type == ProductType.API

    def test_accepts_enum_name_string_for_career(self):
        config = FeatureCostConfig(
            feature_key="CAREER_JOB_MATCH",
            internal_cost_credits=Decimal("10.00"),
        )
        assert config.feature_key == FeatureKey.CAREER_JOB_MATCH
        assert config.product_type == ProductType.CAREER

    def test_invalid_string_raises_error(self):
        with pytest.raises((ValueError, KeyError)):
            FeatureCostConfig(
                feature_key="invalid.key",
                internal_cost_credits=Decimal("1.00"),
            )

    def test_product_type_overwritten_on_feature_key_change(self):
        config = FeatureCostConfig(
            feature_key=FeatureKey.API_CAREER_PATH,
            internal_cost_credits=Decimal("1.00"),
        )
        assert config.product_type == ProductType.API

        config.feature_key = FeatureKey.CAREER_CAREER_PATH
        assert config.product_type == ProductType.CAREER
