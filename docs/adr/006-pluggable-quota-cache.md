# ADR-006: Pluggable Quota Cache

**Status:** Accepted
**Date:** 2025-02

## Context

Every authenticated API request checks the workspace's subscription quota (e.g., max projects, max members). Querying the database on every request adds latency and load. We needed a caching layer, but:

- Local development shouldn't require Redis.
- Production should use Redis so that all API replicas share the same cache.
- When a workspace's plan changes (upgrade, downgrade, cancellation) or resources are consumed (project created, member added), the cache must be invalidated immediately — stale quota means users can exceed their plan.

## Decision

Implement a **pluggable cache backend** via an abstract base class:

```text
QuotaCacheBackend (ABC)
├── MemoryCacheBackend      # dict-based, single-process dev/test
└── RedisCacheBackend       # Redis-backed, multi-replica production
```

Key behaviours:

- **Warm start** — on first access, load from DB and cache; subsequent hits are cache-only.
- **ORM event-driven invalidation** — SQLAlchemy `after_insert`, `after_update`, and `after_delete` listeners on relevant models (`Subscription`, `Workspace`, project/member tables) call `cache.invalidate(workspace_id)`.
- **Frozen dataclass return types** — cache returns `@dataclass(frozen=True)` quota snapshots to prevent accidental mutation.

Backend selection is config-driven (`QUOTA_CACHE_BACKEND`):

- `memory` (default) → `MemoryCacheBackend`
- `redis` → `RedisCacheBackend`

## Alternatives Considered

| Alternative | Why not |
| --- | --- |
| **No cache** | Quota check hits DB on every request; unacceptable under load |
| **Redis only** | Forces Redis dependency in dev/test; slower test suite |
| **TTL-based expiry** | Risk of serving stale quotas for up to TTL window; users could exceed plan |
| **In-app signal/event bus** | Only invalidates the local replica; other replicas serve stale data (doesn't apply to Redis backend) |

## Consequences

**Positive:**

- Zero-latency quota checks after warm-up
- Immediate invalidation means quotas are always accurate
- Swap backends with a single env var; tests use memory backend for speed
- Frozen dataclasses prevent quota mutation bugs

**Negative:**

- ORM event listeners add coupling between models and cache layer
- Memory backend is per-process — fine for dev, but would give inconsistent results if accidentally used in multi-replica production
- Event listeners must be registered at app startup; forgetting a new quota-affecting model means stale cache
