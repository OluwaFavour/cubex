# ADR-005: Multi-Target Dockerfile

**Status:** Accepted
**Date:** 2026-02

## Context

CueBX runs three distinct processes:

1. **API** — FastAPI web server (Uvicorn)
2. **Scheduler** — APScheduler background jobs (cleanup, expiry)
3. **Worker** — RabbitMQ message consumer (emails, Stripe events, usage)

All three share the same codebase and dependencies. We needed to decide how to package them for deployment.

## Decision

Use a **single multi-stage Dockerfile** with a shared `base` stage and three build targets:

```dockerfile
FROM python:3.13-slim AS base
# ... install deps, copy code, create non-root user

FROM base AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS scheduler
CMD ["python", "-m", "app.infrastructure.scheduler.main"]

FROM base AS worker
CMD ["python", "-m", "app.infrastructure.messaging.main"]
```

Build any target with `docker build --target <name>`.

This pairs with feature flags in `app/main.py`:

- `ENABLE_SCHEDULER=false` — API container skips scheduler startup
- `ENABLE_MESSAGING=false` — API container skips consumer startup

The scheduler and worker containers import only what they need.

## Alternatives Considered

| Alternative | Why not |
| --- | --- |
| **Separate Dockerfiles** | Dependency drift between services; triple the maintenance |
| **Single container running all three** | Can't scale independently (e.g., 3 API replicas + 1 scheduler + 2 workers) |
| **Single process with threads** | Worker/scheduler crashes take down the API; can't tune resource limits independently |

## Consequences

**Positive:**

- All three services run identical Python packages — no version drift
- Single `docker build` caches the base layer; targets are thin additions
- Independent scaling per service
- Feature flags allow running everything in one process for local dev (`docker compose --profile dev`)

**Negative:**

- Docker image includes code for all three services even though each target uses a subset
- Feature flag approach means the API process still imports scheduler/messaging modules (mitigated by lazy initialization)
