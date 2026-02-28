from app.core.services.auth import AuthService
from app.core.services.base import SingletonService
from app.core.services.brevo import BrevoService
from app.core.services.cloudinary import CloudinaryService
from app.core.services.email_manager import EmailManagerService
from app.core.services.quota_cache import (
    FeatureConfig,
    PlanConfig,
    QuotaCacheService,
    QuotaCacheBackend,
    MemoryBackend as QuotaMemoryBackend,
    RedisBackend as QuotaRedisBackend,
)
from app.core.services.rate_limit import (
    MemoryBackend,
    RateLimitBackend,
    RateLimiter,
    RateLimitResult,
    RedisBackend,
    rate_limit_by_email,
    rate_limit_by_endpoint,
    rate_limit_by_ip,
    rate_limit_by_user,
)
from app.core.services.redis_service import RedisService
from app.core.services.template import Renderer

# OAuth providers
from app.core.services.oauth import (
    BaseOAuthProvider,
    GitHubOAuthService,
    GoogleOAuthService,
    OAuthTokens,
    OAuthUserInfo,
    generate_state,
)

__all__ = [
    # Core services
    "AuthService",
    "SingletonService",
    "BrevoService",
    "CloudinaryService",
    "EmailManagerService",
    "RedisService",
    "Renderer",
    # Rate limiting
    "MemoryBackend",
    "RateLimitBackend",
    "RateLimiter",
    "RateLimitResult",
    "RedisBackend",
    "rate_limit_by_email",
    "rate_limit_by_endpoint",
    "rate_limit_by_ip",
    "rate_limit_by_user",
    # OAuth
    "BaseOAuthProvider",
    "GitHubOAuthService",
    "GoogleOAuthService",
    "OAuthTokens",
    "OAuthUserInfo",
    "generate_state",
    # Quota cache service
    "QuotaCacheService",
    "QuotaCacheBackend",
    "QuotaMemoryBackend",
    "QuotaRedisBackend",
    "PlanConfig",
    "FeatureConfig",
]
