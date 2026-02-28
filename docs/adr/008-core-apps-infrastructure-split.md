# ADR-008: Core / Apps / Infrastructure Split

**Status:** Accepted
**Date:** 2025-02

## Context

CueBX serves two product surfaces (API platform, career portal) plus background infrastructure (messaging, scheduling). As the codebase grew, we needed a module structure that:

- Separates shared concerns from product-specific logic
- Allows a new product surface to be added without touching existing code
- Makes infrastructure components independently deployable

## Decision

Organise `app/` into **three top-level layers**:

```text
app/
├── core/           # Shared foundation
│   ├── auth/       # JWT, OAuth, tokens, guards
│   ├── models/     # SQLAlchemy models (all tables)
│   ├── services/   # Business logic (CRUD, subscriptions, quotas)
│   ├── utils/      # Helpers (email, crypto, rate limiting)
│   └── db/         # Engine, session factory, config
│
├── apps/           # Product surfaces (each is a FastAPI sub-application)
│   ├── cubex_api/  # Main API — workspaces, projects, support tickets
│   └── cubex_career/ # Career portal — public job listings, applications
│
└── infrastructure/ # Background processes
    ├── messaging/  # RabbitMQ consumer, queues, handlers
    └── scheduler/  # APScheduler jobs (cleanup, Stripe sync, reminders)
```

**Dependency rule:** arrows point inward.

- `apps/` and `infrastructure/` may import from `core/`
- `core/` MUST NOT import from `apps/` or `infrastructure/`
- `apps/cubex_api` and `apps/cubex_career` MUST NOT import from each other
- `infrastructure/messaging` and `infrastructure/scheduler` MUST NOT import from each other

**Mounting:**

```python
# app/main.py
app.mount("/api/v1", cubex_api_app)
app.mount("/career", cubex_career_app)
```

Each product surface has its own router tree, dependencies, and README.

## Alternatives Considered

| Alternative | Why not |
| --- | --- |
| **Flat structure** (all routers in one directory) | Doesn't scale past ~20 route files; hard to tell what's shared vs. product-specific |
| **Django-style apps** (each app owns its models + routes) | Leads to circular imports when apps share models (e.g., `User` is needed everywhere) |
| **Microservices** | Premature for a <10-person team; adds network hops, deployment complexity, and data consistency challenges |
| **Hexagonal / ports-and-adapters** | Correct in theory, but adds too many abstraction layers for the current team size and pace of iteration |

## Consequences

**Positive:**

- Clear ownership — `cubex_career` can be developed, tested, and documented independently of `cubex_api`
- Adding a third product surface (e.g., `cubex_admin_api`) means adding one folder under `apps/` and one `app.mount()` call
- Infrastructure processes only import `core/`, making them lightweight containers
- Dependency rule prevents circular imports

**Negative:**

- Shared models live in `core/models/` even when only one product surface uses them — requires discipline to avoid bloating `core/`
- Cross-product features (e.g., "career listing links to API workspace") require coordination through `core/services/` rather than direct imports
- The dependency rule is enforced by `import-linter` (added to `requirements-dev.txt`) and by architectural abstractions: cross-layer communication uses **hook registries** (`app/core/services/lifecycle.py`) and **protocol-based publishers** (`app/core/services/event_publisher.py`) registered at startup in `app/main.py`
