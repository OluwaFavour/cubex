# ADR-003: RabbitMQ over Celery

**Status:** Accepted
**Date:** 2026-02

## Context

CueBX needs background job processing for: sending emails (OTP, welcome, password reset, subscription notifications, workspace invitations), processing Stripe webhook events, and committing usage logs. Requirements:

1. Persistent messages that survive broker restarts
2. Per-queue retry strategies with different TTLs
3. Dead-letter queues for failed messages
4. Graceful shutdown without message loss
5. Ability to run as a standalone worker process

## Decision

Use **RabbitMQ with aio-pika** (direct AMQP client) instead of Celery.

12 queue triplets are configured declaratively using Pydantic `QueueConfig` models. Each triplet consists of:

- **Main queue** — handler processes messages
- **Retry queue** — failed messages wait here with a TTL before re-delivery
- **Dead-letter queue** — messages that exceed max retries are preserved for debugging

Retry strategies vary by criticality:

- Email queues: 30s retry, 3 max retries
- Stripe queues: 60s retry, 3-5 max retries (higher tolerance for eventual consistency)
- Usage queues: 30s retry, 3 max retries

## Alternatives Considered

| Alternative | Why not |
| --- | --- |
| **Celery** | Heavyweight dependency; less control over per-queue retry semantics; implicit task routing adds complexity; worker processes are opinionated about concurrency model |
| **Redis Streams** | No native dead-letter exchange support; retry TTL requires custom implementation; less battle-tested for message reliability |
| **AWS SQS / Google Pub/Sub** | Cloud vendor lock-in; adds external dependency for local development |
| **In-process `asyncio.Queue`** | Messages lost on crash; no persistence; doesn't scale to multiple workers |

## Consequences

**Positive:**

- Full control over retry semantics per queue
- Native dead-letter exchange support — no custom DLQ implementation
- Pydantic validation catches queue misconfiguration at startup
- aio-pika is a thin async wrapper — minimal abstraction overhead
- Same consumer code runs standalone (Docker worker) or embedded (API process)

**Negative:**

- More operational overhead than Celery (no built-in monitoring dashboard like Flower)
- Custom consumer code vs. Celery's decorator-based task registration
- RabbitMQ is heavier to run locally than Redis (mitigated by Docker Compose)
