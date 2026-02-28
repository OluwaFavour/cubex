# CueBX Messaging Infrastructure

A robust, async RabbitMQ-based messaging system for background job processing with built-in retry logic and dead-letter queue support.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Publishing Events](#publishing-events)
- [Creating Handlers](#creating-handlers)
- [Queue Configuration](#queue-configuration)
- [Retry Strategies](#retry-strategies)
- [Running Consumers](#running-consumers)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## Overview

The messaging module provides an event-driven architecture for processing background jobs asynchronously. It's built on top of [aio-pika](https://aio-pika.readthedocs.io/) and offers:

- ✅ **Persistent messaging** - Messages survive broker restarts
- ✅ **Automatic retries** - Configurable single or multiple retry queues with exponential backoff
- ✅ **Dead-letter queues** - Failed messages are preserved for debugging
- ✅ **Graceful shutdown** - Clean resource cleanup on termination
- ✅ **Standalone or integrated** - Run as a separate worker or within FastAPI lifespan

---

## Architecture

### Basic Flow

```text
┌─────────────┐     publish_event()     ┌──────────────┐
│  Publisher  │ ──────────────────────▶ │  Main Queue  │
└─────────────┘                         └──────┬───────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │   Consumer   │
                                        │   (Handler)  │
                                        └──────┬───────┘
                                               │
                                    ┌──────────┴──────────┐
                                    │                     │
                               (success)             (failure)
                                    │                     │
                                    ▼                     ▼
                                 [ACK]              [REJECTED]
                                                   (no requeue)
```

### With Single Retry Queue (Optional)

```text
                                        ┌──────────────┐
                                        │  Main Queue  │ ◄─────────────────────┐
                                        └──────┬───────┘                       │
                                               │                               │
                                               ▼                               │
                                        ┌──────────────┐                       │
                                        │   Handler    │                       │
                                        └──────┬───────┘                       │
                                               │                               │
                              ┌────────────────┼────────────────┐              │
                              │                │                │              │
                         (success)    (failure, retries < max)  │    (TTL expires)
                              │                │                │              │
                              ▼                ▼                │              │
                           [ACK]        ┌─────────────┐         │              │
                                        │ Retry Queue │─────────┘              │
                                        │  (with TTL) │ dead-letter-routing-key
                                        └─────────────┘
                                               │
                                      (failure, retries >= max)
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │ Dead Letter     │ (optional)
                                      │ Queue           │
                                      └─────────────────┘
```

### With Multiple Retry Queues (Optional - Exponential Backoff)

```text
                                        ┌──────────────┐
                                        │  Main Queue  │ ◄────────────────────────────────────────┐
                                        └──────┬───────┘                                          │
                                               │                                                  │
                                               ▼                                                  │
                                        ┌──────────────┐                                          │
                                        │   Handler    │                                          │
                                        └──────┬───────┘                                          │
                                               │                                                  │
              ┌────────────────────────────────┼────────────────────────────────┐                 │
              │                                │                                │                 │
         (success)                   (failure, attempt=0)              (failure, attempt=1)      │
              │                                │                                │                 │
              ▼                                ▼                                ▼                 │
           [ACK]                     ┌─────────────────┐              ┌─────────────────┐        │
                                     │ Retry Queue #1  │              │ Retry Queue #2  │        │
                                     │   TTL: 30s      │──────┐       │   TTL: 5min     │────┐   │
                                     └─────────────────┘      │       └─────────────────┘    │   │
                                                              │                              │   │
                                                              └──────────────────────────────┴───┘
                                                                     (TTL expires → back to main)

                                               │
                                    (failure, attempt >= len(retry_queues))
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │ Dead Letter     │ (optional)
                                      │ Queue           │
                                      └─────────────────┘
```

### Configuration Options Summary

| Configuration                              | Retry Behavior                 | Use Case                         |
| ------------------------------------------ | ------------------------------ | -------------------------------- |
| No retry config                            | Fails immediately, rejected    | Simple fire-and-forget           |
| `retry_queue` + `retry_ttl` + `max_retries`| Fixed delay, limited attempts  | Consistent retry needs           |
| `retry_queues[]`                           | Progressive delays (backoff)   | External APIs, transient failures|
| `dead_letter_queue`                        | Preserves failed messages      | Debugging, manual intervention   |

---

## Quick Start

### 1. Define a Message Handler

```python
# app/infrastructure/messaging/handlers/email_handler.py

from typing import Any

async def handle_welcome_email(event: dict[str, Any]) -> None:
    """Process welcome email events."""
    user_email = event["email"]
    user_name = event["name"]
    
    # Your email sending logic here
    await send_welcome_email(user_email, user_name)
```

### 2. Configure the Queue

```python
# app/infrastructure/messaging/queues.py

from app.infrastructure.messaging.handlers.email_handler import handle_welcome_email

QUEUE_CONFIG = [
    {
        "name": "welcome_emails",
        "handler": handle_welcome_email,
        "retry_queue": "welcome_emails_retry",
        "retry_ttl": 60_000,  # 1 minute
        "max_retries": 3,
        "dead_letter_queue": "welcome_emails_dead",
    },
]
```

### 3. Publish an Event

**From application code** (routers, services in `core/` or `apps/`), use the event publisher abstraction:

```python
from app.core.services.event_publisher import get_publisher

await get_publisher()(
    queue_name="welcome_emails",
    event={"email": "user@example.com", "name": "John Doe"},
)
```

> **Note:** The direct import `from app.infrastructure.messaging import publish_event` is reserved for infrastructure-internal code and the `register_publisher()` call in `app/main.py`. Application code should always use `get_publisher()` to maintain the layer boundary (see [ADR-008](../../docs/adr/008-core-apps-infrastructure-split.md)).

### 4. Start the Consumer

```bash
# Standalone
python -m app.infrastructure.messaging.main

# Or with Docker
docker compose --profile worker-only up -d
```

---

## Configuration

### Environment Variables

Ensure the following are set in your environment:

| Variable       | Description                | Example                              |
| -------------- | -------------------------- | ------------------------------------ |
| `RABBITMQ_URL` | RabbitMQ connection string | `amqp://guest:guest@localhost:5672/` |

### Connection Management

The module uses a singleton connection pattern for efficiency:

```python
from app.infrastructure.messaging.connection import get_connection

# Get or create a robust connection (auto-reconnects on failure)
connection = await get_connection()
```

---

## Publishing Events

### Basic Usage

**Application code** (routers, services) should use the abstract publisher:

```python
from app.core.services.event_publisher import get_publisher

# Simple event
await get_publisher()(
    queue_name="notifications",
    event={"user_id": 123, "message": "Hello!"},
)
```

**Infrastructure-internal code** (handlers, consumers) can use the direct import:

```python
from app.infrastructure.messaging import publish_event

await publish_event(
    queue_name="analytics",
    event={"action": "page_view", "page": "/home"},
    headers={"x-source": "web", "x-priority": "low"},
)
```

### Message Properties

All published messages are:

- **Persistent** - `delivery_mode=PERSISTENT` ensures messages survive broker restarts
- **JSON encoded** - Events are serialized with `json.dumps()`
- **Content-typed** - `content_type="application/json"`

### Publishing Patterns

```python
# Pattern 1: Fire and forget
await publish_event("email_queue", {"to": "user@example.com"})

# Pattern 2: With correlation ID for tracking
import uuid

correlation_id = str(uuid.uuid4())
await publish_event(
    "order_processing",
    {"order_id": 456, "action": "confirm"},
    headers={"x-correlation-id": correlation_id},
)
```

---

## Creating Handlers

Handlers are async functions that process messages from queues.

### Handler Signature

```python
from typing import Any

async def my_handler(event: dict[str, Any]) -> None:
    """
    Process an event from the queue.
    
    Args:
        event: The deserialized JSON payload from the message.
        
    Raises:
        Exception: Raising any exception triggers retry logic.
    """
    pass
```

### Handler Best Practices

```python
# ✅ Good: Idempotent handler
async def handle_payment_confirmation(event: dict[str, Any]) -> None:
    payment_id = event["payment_id"]
    
    # Check if already processed (idempotency)
    if await is_payment_processed(payment_id):
        return  # Already done, skip
    
    await process_payment(payment_id)
    await mark_payment_processed(payment_id)


# ✅ Good: Proper error handling
async def handle_webhook(event: dict[str, Any]) -> None:
    try:
        # Validate payload
        if "required_field" not in event:
            raise ValueError("Missing required_field")
        
        await process_webhook(event)
        
    except ValidationError as e:
        # Don't retry validation errors - send to DLQ
        logger.error(f"Invalid payload: {e}")
        raise
    except ExternalServiceError as e:
        # Retry on external service failures
        logger.warning(f"External service failed: {e}")
        raise


# ❌ Bad: Non-idempotent handler
async def handle_send_email(event: dict[str, Any]) -> None:
    # This will send duplicate emails on retries!
    await send_email(event["to"], event["subject"], event["body"])
```

### Organizing Handlers

```text
app/infrastructure/messaging/
├── handlers/
│   ├── __init__.py
│   ├── email_handler.py
│   ├── payment_handler.py
│   └── notification_handler.py
├── connection.py
├── consumer.py
├── main.py
├── publisher.py
└── queues.py
```

---

## Queue Configuration

### QueueConfig Schema

```python
from pydantic import BaseModel

class QueueConfig(BaseModel):
    name: str                              # Required: Main queue name
    handler: Callable                      # Required: Message handler function
    retry_queue: str | None = None         # Single retry queue name
    retry_queues: list[RetryQueue] | None  # Multiple retry queues (mutually exclusive with retry_queue)
    retry_ttl: int | None = None           # TTL for single retry queue (ms)
    max_retries: int | None = None         # Max retries for single retry queue
    dead_letter_queue: str | None = None   # Dead letter queue name
```

### Configuration Examples

#### Minimal Configuration (No Retries)

```python
QUEUE_CONFIG = [
    {
        "name": "simple_queue",
        "handler": handle_simple_event,
    },
]
```

#### Single Retry Queue

```python
QUEUE_CONFIG = [
    {
        "name": "email_notifications",
        "handler": handle_email,
        "retry_queue": "email_notifications_retry",
        "retry_ttl": 30_000,       # 30 seconds
        "max_retries": 5,
        "dead_letter_queue": "email_notifications_dead",
    },
]
```

#### Multiple Retry Queues (Exponential Backoff)

```python
QUEUE_CONFIG = [
    {
        "name": "payment_webhooks",
        "handler": handle_payment_webhook,
        "retry_queues": [
            {"name": "payment_webhooks_retry_30s", "ttl": 30_000},      # 30 seconds
            {"name": "payment_webhooks_retry_5m", "ttl": 300_000},      # 5 minutes
            {"name": "payment_webhooks_retry_30m", "ttl": 1_800_000},   # 30 minutes
            {"name": "payment_webhooks_retry_1h", "ttl": 3_600_000},    # 1 hour
        ],
        "dead_letter_queue": "payment_webhooks_dead",
    },
]
```

---

## Retry Strategies

### How Retries Work

1. **Handler fails** → Exception is caught
2. **Retry attempt tracked** → `x-retry-attempt` header incremented
3. **Message published to retry queue** → With configured TTL
4. **TTL expires** → RabbitMQ dead-letters message back to main queue
5. **Process repeats** → Until max retries or success

### Single Retry Queue Strategy

Best for: Simple retry needs with consistent delay.

```python
{
    "name": "notifications",
    "handler": handle_notification,
    "retry_queue": "notifications_retry",
    "retry_ttl": 60_000,     # Always wait 1 minute before retry
    "max_retries": 3,        # Give up after 3 attempts
    "dead_letter_queue": "notifications_dead",
}
```

Timeline:

```text
Attempt 1 (fail) → wait 1m → Attempt 2 (fail) → wait 1m → Attempt 3 (fail) → wait 1m → Attempt 4 (fail) → DLQ
```

### Multiple Retry Queues Strategy (Exponential Backoff)

Best for: External service calls where longer waits increase success probability.

```python
{
    "name": "api_calls",
    "handler": handle_api_call,
    "retry_queues": [
        {"name": "api_calls_retry_10s", "ttl": 10_000},
        {"name": "api_calls_retry_1m", "ttl": 60_000},
        {"name": "api_calls_retry_10m", "ttl": 600_000},
        {"name": "api_calls_retry_1h", "ttl": 3_600_000},
    ],
    "dead_letter_queue": "api_calls_dead",
}
```

Timeline:

```text
Attempt 1 (fail) → wait 10s → Attempt 2 (fail) → wait 1m → Attempt 3 (fail) → wait 10m → Attempt 4 (fail) → wait 1h → Attempt 5 (fail) → DLQ
```

---

## Running Consumers

### Standalone Mode

Run as a separate process for dedicated message processing:

```bash
# Direct execution
python -m app.infrastructure.messaging.main

# With Docker Compose
docker compose --profile worker-only up -d
```

The standalone worker:

- Initializes database connections
- Connects to Redis
- Sets up email services (Brevo)
- Initializes template renderer
- Handles graceful shutdown (SIGINT/SIGTERM)

### Integrated Mode (FastAPI Lifespan)

Start consumers alongside your FastAPI application:

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.infrastructure.messaging import start_consumers

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    conn = await start_consumers(keep_alive=False)
    
    yield
    
    # Shutdown
    if conn:
        await conn.close()

app = FastAPI(lifespan=lifespan)
```

### Parameters

| Parameter    | Type   | Description                                                                    |
| ------------ | ------ | ------------------------------------------------------------------------------ |
| `keep_alive` | `bool` | If `True`, runs forever. If `False`, returns connection for manual management. |

---

## Best Practices

### 1. Make Handlers Idempotent

Messages may be delivered more than once. Design handlers to handle duplicates gracefully.

```python
async def handle_order(event: dict[str, Any]) -> None:
    order_id = event["order_id"]
    
    # Use a unique constraint or check before processing
    if await order_already_processed(order_id):
        return
    
    await process_order(order_id)
```

### 2. Use Meaningful Queue Names

```python
# ✅ Good
"user_welcome_emails"
"payment_webhook_processing"
"order_confirmation_notifications"

# ❌ Bad
"queue1"
"processing"
"events"
```

### 3. Set Appropriate TTLs

Consider the nature of your task:

```python
# Transient notifications - short TTL
"retry_ttl": 30_000  # 30 seconds

# External API calls - longer TTL (services may have downtime)
"retry_ttl": 300_000  # 5 minutes

# Critical financial operations - very long TTL
"retry_ttl": 3_600_000  # 1 hour
```

### 4. Monitor Dead Letter Queues

Regularly inspect DLQs for failed messages:

```bash
# Using RabbitMQ Management UI
http://localhost:15672/#/queues

# Or via CLI
rabbitmqctl list_queues name messages
```

### 5. Log Correlation IDs

Track messages across services:

```python
import uuid

correlation_id = str(uuid.uuid4())

# Publisher
await publish_event(
    "orders",
    {"order_id": 123},
    headers={"x-correlation-id": correlation_id},
)

# Handler
async def handle_order(event: dict[str, Any]) -> None:
    correlation_id = message.headers.get("x-correlation-id")
    logger.info(f"Processing order", extra={"correlation_id": correlation_id})
```

### 6. Handle Poison Messages

Some messages will never succeed. Let them fail to DLQ:

```python
async def handle_event(event: dict[str, Any]) -> None:
    # Validate early
    if not is_valid_event(event):
        logger.error(f"Invalid event schema: {event}")
        raise ValueError("Invalid event")  # Will eventually hit DLQ
    
    # Process valid events
    await process(event)
```

---

## Troubleshooting

### Common Issues

#### Messages Not Being Consumed

1. **Check queue configuration**

   ```python
   # Ensure handler is properly imported
   from app.infrastructure.messaging.handlers import my_handler
   
   QUEUE_CONFIG = [
       {"name": "my_queue", "handler": my_handler},  # ✅ Function reference, not string
   ]
   ```

2. **Verify RabbitMQ connection**

   ```bash
   # Check if RabbitMQ is running
   docker ps | grep rabbitmq
   
   # Check connection string
   echo $RABBITMQ_URL
   ```

#### Messages Stuck in Retry Queue

1. **Check TTL configuration**
   - Ensure `x-dead-letter-exchange` and `x-dead-letter-routing-key` are set
   - Verify TTL is in milliseconds (not seconds)

2. **Inspect queue in RabbitMQ Management**

   ```text
   http://localhost:15672/#/queues/%2F/your_retry_queue
   ```

#### Handler Exceptions Not Triggering Retries

Ensure exceptions are raised, not silently caught:

```python
# ❌ Bad - exceptions swallowed
async def handle_event(event):
    try:
        await process(event)
    except Exception as e:
        logger.error(e)  # Swallowed! No retry

# ✅ Good - exceptions re-raised
async def handle_event(event):
    try:
        await process(event)
    except Exception as e:
        logger.error(e)
        raise  # Triggers retry logic
```

### Debugging Tips

1. **Enable debug logging**

   ```python
   import logging
   logging.getLogger("aio_pika").setLevel(logging.DEBUG)
   ```

2. **Use RabbitMQ Management Plugin**

   ```bash
   docker exec rabbitmq rabbitmq-plugins enable rabbitmq_management
   # Access at http://localhost:15672
   ```

3. **Inspect message headers**

   ```python
   async def handle_event(event: dict[str, Any]) -> None:
       # Note: To access headers, you'd need to modify process_message
       # to pass headers to the handler
       pass
   ```

---

## API Reference

### `publish_event`

```python
async def publish_event(
    queue_name: str,
    event: dict[str, Any],
    headers: dict[str, Any] = {}
) -> None:
    """
    Publishes an event message to the specified queue.
    
    Args:
        queue_name: Target queue name
        event: Event data (will be JSON serialized)
        headers: Optional message headers
    """
```

### `start_consumers`

```python
async def start_consumers(
    keep_alive: bool
) -> aio_pika.RobustConnection | None:
    """
    Starts message consumers for all configured queues.
    
    Args:
        keep_alive: If True, runs forever. If False, returns connection.
        
    Returns:
        Connection object if keep_alive=False, else None.
    """
```

### `get_connection`

```python
async def get_connection() -> aio_pika.RobustConnection:
    """
    Gets or creates a robust RabbitMQ connection.
    
    Returns:
        Active RabbitMQ connection (auto-reconnects on failure).
    """
```

---

## Examples

### Email Notification System

```python
# handlers/email_handler.py
from app.shared.services import BrevoService

async def handle_email_notification(event: dict[str, Any]) -> None:
    await BrevoService.send_transactional_email(
        to_email=event["email"],
        template_id=event["template_id"],
        params=event.get("params", {}),
    )

# queues.py
QUEUE_CONFIG = [
    {
        "name": "email_notifications",
        "handler": handle_email_notification,
        "retry_queues": [
            {"name": "email_retry_1m", "ttl": 60_000},
            {"name": "email_retry_5m", "ttl": 300_000},
            {"name": "email_retry_15m", "ttl": 900_000},
        ],
        "dead_letter_queue": "email_dead",
    },
]

# Usage
await publish_event("email_notifications", {
    "email": "user@example.com",
    "template_id": 123,
    "params": {"name": "John", "order_id": "ORD-456"},
})
```

### Payment Webhook Processing

```python
# handlers/payment_handler.py
async def handle_payment_webhook(event: dict[str, Any]) -> None:
    event_type = event["type"]
    
    if event_type == "charge.success":
        await handle_successful_charge(event["data"])
    elif event_type == "charge.failed":
        await handle_failed_charge(event["data"])
    elif event_type == "refund.created":
        await handle_refund(event["data"])

# queues.py
QUEUE_CONFIG = [
    {
        "name": "payment_webhooks",
        "handler": handle_payment_webhook,
        "retry_queues": [
            {"name": "payment_retry_30s", "ttl": 30_000},
            {"name": "payment_retry_2m", "ttl": 120_000},
            {"name": "payment_retry_10m", "ttl": 600_000},
            {"name": "payment_retry_1h", "ttl": 3_600_000},
        ],
        "dead_letter_queue": "payment_webhooks_dead",
    },
]
```

---

## Contributing

When adding new queues or handlers:

1. Create handler in `handlers/` directory
2. Add queue configuration to `QUEUE_CONFIG` in `queues.py`
3. Export handler from `handlers/__init__.py` if needed
4. Test locally before deploying
5. Monitor DLQ after deployment

---

Happy messaging! 🐰
