"""Seed subscription plans data

Revision ID: f3a9b8c7d6e5
Revises: e2eb115ac408
Create Date: 2026-02-03 10:30:00.000000

"""

from decimal import Decimal
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.shared.config import settings


# revision identifiers, used by Alembic.
revision: str = "f3a9b8c7d6e5"
down_revision: Union[str, Sequence[str], None] = "870fa704996f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ============================================================================
# Plan Data
# ============================================================================

CUBEX_API_PLANS = [
    {
        "id": str(uuid4()),
        "name": "Free",
        "description": "For developers or small teams exploring the AI recruitment engine.",
        "price": Decimal("0.00"),
        "display_price": "$0/month",
        "stripe_price_id": None,
        "is_active": True,
        "trial_days": None,
        "type": "FREE",
        "product_type": "API",
        "min_seats": 1,
        "max_seats": 1,
        "features": [
            {
                "title": "Limited API calls",
                "description": "Limited API calls per month",
                "category": "Usage",
            },
            {
                "title": "Basic feedback endpoints",
                "description": "Access to basic candidate feedback endpoints",
                "category": "Features",
            },
            {
                "title": "Standard AI scoring",
                "description": "Standard AI scoring and ranking for up to 10 candidates per request",
                "category": "AI",
            },
            {
                "title": "Basic recommendation model",
                "description": "Basic recommendation model (general matching only)",
                "category": "AI",
            },
            {
                "title": "Sandbox environment",
                "description": "Access to test/sandbox environment",
                "category": "Development",
            },
            {
                "title": "Basic documentation",
                "description": "Basic API documentation access",
                "category": "Support",
            },
            {
                "title": "Standard rate limit",
                "description": "Standard response time and rate limit",
                "category": "Performance",
            },
            {
                "title": "Basic model accuracy",
                "description": "Basic model accuracy with limited learning data",
                "category": "AI",
            },
        ],
    },
    {
        "id": str(uuid4()),
        "name": "Basic",
        "description": "For growing companies and recruitment startups integrating AI insights into their hiring flow.",
        "price": Decimal("19.00"),
        "display_price": "$19/month",
        "stripe_price_id": settings.STRIPE_CUBEX_API_PRICE_BASIC,
        "is_active": True,
        "trial_days": 14,
        "type": "PAID",
        "product_type": "API",
        "min_seats": 1,
        "max_seats": 5,
        "features": [
            {
                "title": "Higher API quota",
                "description": "50,000 requests per month",
                "value": "50,000",
                "category": "Usage",
            },
            {
                "title": "All feedback endpoints",
                "description": "Access to all candidate feedback endpoints",
                "category": "Features",
            },
            {
                "title": "Improved AI models",
                "description": "Improved AI/ML model performance and adaptive learning",
                "category": "AI",
            },
            {
                "title": "Job-candidate scoring",
                "description": "Job-to-candidate recommendation scoring (skill, experience & culture fit)",
                "category": "AI",
            },
            {
                "title": "Recruiter feedback API",
                "description": "Access to recruiter feedback API for iterative model tuning",
                "category": "Features",
            },
            {
                "title": "Team access",
                "description": "Team access (up to 5 users)",
                "value": "5",
                "category": "Team",
            },
            {
                "title": "API versioning",
                "description": "API versioning and change notifications",
                "category": "Development",
            },
        ],
    },
    {
        "id": str(uuid4()),
        "name": "Professional",
        "description": "For enterprises, job platforms, and agencies needing full control, precision, and scalability.",
        "price": Decimal("39.00"),
        "display_price": "$39/month",
        "stripe_price_id": settings.STRIPE_CUBEX_API_PRICE_PROFESSIONAL,
        "is_active": True,
        "trial_days": 14,
        "type": "PAID",
        "product_type": "API",
        "min_seats": 1,
        "max_seats": None,
        "features": [
            {
                "title": "Unlimited API usage",
                "description": "Unlimited or high-volume API usage (1M+ requests/month)",
                "value": "1,000,000+",
                "category": "Usage",
            },
            {
                "title": "All premium features",
                "description": "Access to all endpoints and premium recommendation features",
                "category": "Features",
            },
            {
                "title": "AI customization",
                "description": "Advanced AI/ML customization (model fine-tuning with proprietary data)",
                "category": "AI",
            },
            {
                "title": "Bias detection",
                "description": "Bias detection and fairness optimization tools",
                "category": "AI",
            },
            {
                "title": "Predictive analytics",
                "description": "Predictive analytics for hiring success and retention",
                "category": "Analytics",
            },
            {
                "title": "Sentiment analysis",
                "description": "Sentiment and behavioral analysis from recruiter feedback",
                "category": "AI",
            },
            {
                "title": "Premium support",
                "description": "24/7 premium support and SLA (99.9% uptime)",
                "value": "99.9%",
                "category": "Support",
            },
            {
                "title": "Early access",
                "description": "Early access to experimental AI models and beta features",
                "category": "Features",
            },
        ],
    },
]

CUBEX_CAREER_PLANS = [
    {
        "id": str(uuid4()),
        "name": "Free",
        "description": "Perfect for individuals exploring basic AI-powered career guidance.",
        "price": Decimal("0.00"),
        "display_price": "$0/month",
        "stripe_price_id": None,
        "is_active": True,
        "trial_days": None,
        "type": "FREE",
        "product_type": "CAREER",
        "min_seats": 1,
        "max_seats": 1,
        "features": [
            {
                "title": "Basic career guidance",
                "description": "Basic AI-powered career guidance",
                "category": "Guidance",
            },
            {
                "title": "Limited path suggestions",
                "description": "Limited career path suggestions",
                "category": "Guidance",
            },
            {
                "title": "Resume reviews",
                "description": "3 resume reviews per month",
                "value": "3",
                "category": "Reviews",
            },
            {
                "title": "Job fit analysis",
                "description": "1 job fit analysis per month",
                "value": "1",
                "category": "Analysis",
            },
            {
                "title": "Basic insights",
                "description": "Basic feedback & insights",
                "category": "Insights",
            },
            {
                "title": "Skill-gap analysis",
                "description": "Limited access to skill-gap analysis",
                "category": "Analysis",
            },
            {
                "title": "Standard speed",
                "description": "Standard response speed",
                "category": "Performance",
            },
        ],
    },
    {
        "id": str(uuid4()),
        "name": "Plus Plan",
        "description": "For professionals who want deeper insight, personalized guidance, and faster responses.",
        "price": Decimal("20.00"),
        "display_price": "$20/month",
        "stripe_price_id": settings.STRIPE_CUBEX_CAREER_PRICE_PLUS,
        "is_active": True,
        "trial_days": 7,
        "type": "PAID",
        "product_type": "CAREER",
        "min_seats": 1,
        "max_seats": 1,
        "features": [
            {
                "title": "Everything in Free",
                "description": "All features from the Free plan",
                "category": "Included",
            },
            {
                "title": "Unlimited resume reviews",
                "description": "Unlimited resume reviews",
                "value": "Unlimited",
                "category": "Reviews",
            },
            {
                "title": "Unlimited job fit scoring",
                "description": "Unlimited job fit scoring",
                "value": "Unlimited",
                "category": "Analysis",
            },
            {
                "title": "Career trajectory mapping",
                "description": "Full career trajectory mapping",
                "category": "Guidance",
            },
            {
                "title": "Skill-gap analysis",
                "description": "Unlimited personalized skill-gap analysis",
                "value": "Unlimited",
                "category": "Analysis",
            },
            {
                "title": "Weekly recommendations",
                "description": "Weekly personalized growth recommendations",
                "category": "Guidance",
            },
            {
                "title": "Priority performance",
                "description": "Priority model performance (faster responses)",
                "category": "Performance",
            },
            {
                "title": "Premium templates",
                "description": "Access to premium templates: resumes, portfolios, cover letters",
                "category": "Templates",
            },
        ],
    },
    {
        "id": str(uuid4()),
        "name": "Pro Plan",
        "description": "Built for serious career transitions, upskillers, and job seekers who want comprehensive guidance.",
        "price": Decimal("40.00"),
        "display_price": "$40/month",
        "stripe_price_id": settings.STRIPE_CUBEX_CAREER_PRICE_PRO,
        "is_active": True,
        "trial_days": 7,
        "type": "PAID",
        "product_type": "CAREER",
        "min_seats": 1,
        "max_seats": 1,
        "features": [
            {
                "title": "Everything in Plus",
                "description": "All features from the Plus plan",
                "category": "Included",
            },
            {
                "title": "Multi-path exploration",
                "description": "Advanced multi-path career exploration",
                "category": "Guidance",
            },
            {
                "title": "Custom roadmaps",
                "description": "Custom upskilling roadmaps tailored to goals, budget, and timeframe",
                "category": "Guidance",
            },
            {
                "title": "Personality analysis",
                "description": "Behavioral & personality alignment analysis",
                "category": "Analysis",
            },
            {
                "title": "Market intelligence",
                "description": "Real-time job market intelligence & role matching",
                "category": "Insights",
            },
            {
                "title": "Fastest processing",
                "description": "Fastest model processing speed",
                "category": "Performance",
            },
            {
                "title": "Multiple goals",
                "description": "Ability to track multiple career goals simultaneously",
                "category": "Features",
            },
        ],
    },
]


def upgrade() -> None:
    """Seed plan data."""
    from datetime import datetime, timezone

    plans_table = sa.table(
        "plans",
        sa.column("id", UUID),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("price", sa.Numeric),
        sa.column("display_price", sa.String),
        sa.column("stripe_price_id", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("trial_days", sa.Integer),
        sa.column("type", sa.String),
        sa.column("product_type", sa.String),
        sa.column("features", JSONB),
        sa.column("min_seats", sa.Integer),
        sa.column("max_seats", sa.Integer),
        sa.column("is_deleted", sa.Boolean),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    now = datetime.now(timezone.utc)
    all_plans = CUBEX_API_PLANS + CUBEX_CAREER_PLANS

    for plan in all_plans:
        op.execute(
            plans_table.insert().values(
                id=plan["id"],
                name=plan["name"],
                description=plan["description"],
                price=plan["price"],
                display_price=plan["display_price"],
                stripe_price_id=plan["stripe_price_id"],
                is_active=plan["is_active"],
                trial_days=plan["trial_days"],
                type=plan["type"],
                product_type=plan["product_type"],
                features=plan["features"],
                min_seats=plan["min_seats"],
                max_seats=plan["max_seats"],
                is_deleted=False,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    """Remove seeded plan data."""
    op.execute(
        """
        DELETE FROM plans 
        WHERE (product_type = 'API' AND name IN ('Free', 'Basic', 'Professional'))
           OR (product_type = 'CAREER' AND name IN ('Free', 'Plus Plan', 'Pro Plan'))
        """
    )
