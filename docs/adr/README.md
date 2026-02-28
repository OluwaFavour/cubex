# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) that document key technical decisions made in CueBX. Each ADR captures the context, decision, and trade-offs for a significant architectural choice.

## Index

| # | Title | Status | Date |
| --- | ------- | -------- | ------ |
| [001](001-class-based-singleton-services.md) | Class-Based Singleton Services | Accepted | 2026-02 |
| [002](002-async-first-sqlalchemy.md) | Async-First SQLAlchemy 2.0 | Accepted | 2026-02 |
| [003](003-rabbitmq-over-celery.md) | RabbitMQ over Celery | Accepted | 2026-02 |
| [004](004-hmac-otp-hashing.md) | HMAC-Based OTP Hashing | Accepted | 2026-02 |
| [005](005-multi-target-dockerfile.md) | Multi-Target Dockerfile | Accepted | 2026-02 |
| [006](006-pluggable-quota-cache.md) | Pluggable Quota Cache with Event-Driven Invalidation | Accepted | 2026-02 |
| [007](007-stateless-admin-auth.md) | Stateless HMAC Admin Authentication | Accepted | 2026-02 |
| [008](008-core-apps-infrastructure-split.md) | Core / Apps / Infrastructure Module Split | Accepted | 2026-02 |
| [009](009-analysis-result-separate-from-usage-log.md) | Separate CareerAnalysisResult Table for History | Accepted | 2026-02 |

## Format

Each ADR follows this template:

```markdown
# ADR-NNN: Title

**Status:** Accepted | Superseded | Deprecated
**Date:** YYYY-MM

## Context
What problem are we solving? What forces are at play?

## Decision
What did we decide and why?

## Alternatives Considered
What other options were evaluated?

## Consequences
What are the positive and negative outcomes?
```

## Adding a New ADR

1. Create a new file: `docs/adr/NNN-short-kebab-title.md`
2. Use the template above
3. Add an entry to the index in this README
4. Reference the ADR in your PR description
