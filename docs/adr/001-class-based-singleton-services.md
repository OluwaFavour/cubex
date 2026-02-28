# ADR-001: Class-Based Singleton Services

**Status:** Accepted
**Date:** 2026-02

## Context

CueBX has ~10 core services (Auth, Redis, Brevo, Cloudinary, OAuth providers, QuotaCache, EmailManager, RateLimiter, Renderer). These services need to:

1. Be available in request handlers (routers)
2. Be available in non-request contexts (scheduler jobs, message consumers)
3. Initialize once at startup with configuration
4. Shut down gracefully when the process exits

## Decision

Use **class-based singletons** with `@classmethod` methods and an explicit `init()` / `aclose()` lifecycle. All state is stored at the class level (`ClassVar`). No instances are created.

```python
class RedisService:
    _client: ClassVar[Redis | None] = None
    _initialized: ClassVar[bool] = False

    @classmethod
    def init(cls, url: str) -> None:
        cls._client = Redis.from_url(url)
        cls._initialized = True

    @classmethod
    async def get(cls, key: str) -> str | None:
        if not cls._initialized:
            raise RuntimeError("RedisService not initialized")
        return await cls._client.get(key)
```

Services are initialized in the FastAPI `lifespan` function and torn down in reverse order.

## Alternatives Considered

| Alternative | Why not |
| --- | --- |
| **FastAPI `Depends()` injection** | Doesn't work outside request context (scheduler, consumers). Would require two initialization paths. |
| **Module-level globals** | Harder to test, unclear initialization order, no `_initialized` guard. |
| **DI container (python-inject, dependency-injector)** | Adds framework lock-in and boilerplate for a relatively simple need. |
| **Instance-per-request** | Wasteful for stateful clients (Redis connections, HTTP sessions). |

## Consequences

**Positive:**

- Works identically in routers, scheduler, and consumer contexts
- Clear initialization order in one place (lifespan function)
- Easy to mock in tests (`ServiceClass._initialized = True`)
- No per-request overhead

**Negative:**

- Class-level mutable state is technically global state (harder to isolate in parallel tests)
- ~~`_initialized` guard adds boilerplate to every method~~ — mitigated: boilerplate extracted into a `SingletonService` base class (`app/core/services/base.py`) that provides `_initialized`, `_ensure_initialized()`, and `_reset()`; services now inherit from it
- Cannot have two instances with different configs (not needed currently)

> **Update (2026-02):** An autouse `_reset_singletons` test fixture now calls `ServiceClass._reset()` on all singletons after each test, ensuring clean state isolation without manual `_initialized = True` hacks.
