# ADR-002: Async-First SQLAlchemy 2.0

**Status:** Accepted
**Date:** 2026-02

## Context

CueBX is an I/O-bound API serving AI feature requests. The majority of latency comes from database queries, Redis lookups, HTTP calls to Stripe/Brevo, and message publishing. We needed to choose between sync and async database access.

## Decision

Use **SQLAlchemy 2.0 async** with `asyncpg` as the PostgreSQL driver:

- `create_async_engine` with tuned pool: `pool_size=20`, `max_overflow=30`, `pool_pre_ping=True`, `pool_recycle=3600`
- `async_sessionmaker` with `expire_on_commit=False` and `autoflush=False`
- `Base` extends both `AsyncAttrs` and `DeclarativeBase`

Key configuration choices:

| Setting | Value | Reason |
| --------- | ------- | -------- |
| `expire_on_commit=False` | — | Prevents `MissingGreenlet` errors when accessing attributes after commit in async context |
| `autoflush=False` | — | Avoids implicit I/O during attribute access |
| `pool_pre_ping=True` | — | Detects stale connections (Render/cloud DBs drop idle connections) |
| `pool_recycle=3600` | — | Prevents server-side timeout on long-lived connections |
| `AsyncAttrs` | — | Enables `await` on lazy-loaded relationships |

Alembic is used for migrations with the async engine.

## Alternatives Considered

| Alternative | Why not |
| --- | --- |
| **Sync SQLAlchemy + thread pool** | Adds thread overhead; doesn't compose with other async libraries (aio-pika, httpx) |
| **Tortoise ORM** | Less mature, weaker migration tooling, smaller ecosystem |
| **SQLModel** | Built on SQLAlchemy but hides async capabilities; less flexibility for complex queries |
| **Raw asyncpg** | No ORM, no migration tooling, more boilerplate |

## Consequences

**Positive:**

- Single-threaded async model — no thread synchronization issues
- Composes naturally with other async libraries (aio-pika, redis.asyncio, httpx)
- Alembic autogenerate works with async models
- `expire_on_commit=False` eliminates the most common async SQLAlchemy pitfall

**Negative:**

- Steeper learning curve than sync SQLAlchemy
- Some SQLAlchemy features (e.g., certain lazy-load strategies) require careful handling
- Debugging async stack traces is harder
