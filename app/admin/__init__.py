"""
SQLAdmin configuration for Cubex.

- Plans (subscription plans)
- FeatureCostConfig (API endpoint pricing)
- PlanPricingRule (plan multipliers and rate limits)
- Users (read-only view)
- Workspaces (read-only view)
- Subscriptions (view/manage)
"""

from app.admin.setup import admin, init_admin

__all__ = ["admin", "init_admin"]

