# CueBX Scheduler Infrastructure

A robust, async APScheduler-based task scheduler for running background jobs with persistent storage, graceful shutdown, and flexible execution modes.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Adding Jobs](#adding-jobs)
- [Job Stores](#job-stores)
- [Running the Scheduler](#running-the-scheduler)
- [Best Practices](#best-practices)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

---

## Overview

The scheduler module provides a time-based job execution system for processing recurring background tasks. It's built on top of [APScheduler](https://apscheduler.readthedocs.io/) and offers:

- ✅ **AsyncIO-based** - Uses `AsyncIOScheduler` for non-blocking execution
- ✅ **UTC timezone** - All jobs run in UTC for consistency
- ✅ **Persistent job storage** - SQLAlchemy job stores survive restarts
- ✅ **Graceful shutdown** - Handles SIGINT/SIGTERM signals cleanly
- ✅ **Service initialization** - Database, Redis, Brevo, and templates auto-initialized
- ✅ **Standalone or integrated** - Run as a separate worker or within FastAPI lifespan
- ✅ **Docker support** - Dedicated container target for isolated execution
- ✅ **Configurable** - Enable/disable via environment variable

---

## Architecture

### Basic Flow

```text
┌───────────────────┐
│   Job Definition  │
│  (Interval/Cron)  │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐     add_job()      ┌───────────────────┐
│  Scheduler Setup  │ ─────────────────▶ │  SQLAlchemy       │
│  (with JobStore)  │                    │  JobStore         │
└─────────┬─────────┘                    │  (PostgreSQL)     │
          │                              └─────────┬─────────┘
          │                                        │
          │                                        │
          ▼                                        ▼
┌───────────────────┐                    ┌───────────────────┐
│  AsyncIOScheduler │ ◄──────────────────│  Persisted Jobs   │
│  scheduler.start()│   (loads on start) │  (survive restart)│
└─────────┬─────────┘                    └───────────────────┘
          │
          │ (trigger fires)
          ▼
┌───────────────────┐
│   Job Executor    │
│   (async func)    │
└─────────┬─────────┘
          │
    ┌─────┴─────┐
    │           │
(success)   (failure)
    │           │
    ▼           ▼
 [Done]    [Logged]
           (misfire_grace_time)
```

### Service Initialization Flow (Standalone Mode)

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Standalone Scheduler                         │
│                                                                  │
│  ┌──────────────┐                                               │
│  │ Signal Setup │  SIGINT / SIGTERM handlers                    │
│  └──────┬───────┘                                               │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                Service Initialization                     │   │
│  │                                                           │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐          │   │
│  │  │  Database  │  │   Redis    │  │   Brevo    │          │   │
│  │  │  init_db() │  │  Service   │  │  Service   │          │   │
│  │  └────────────┘  └────────────┘  └────────────┘          │   │
│  │                                                           │   │
│  │  ┌────────────┐                                          │   │
│  │  │  Template  │                                          │   │
│  │  │  Renderer  │                                          │   │
│  │  └────────────┘                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │  Scheduler   │  scheduler.start()                            │
│  │   Started    │  Wait for shutdown_event                      │
│  └──────┬───────┘                                               │
│         │                                                        │
│         │ (signal received)                                      │
│         ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Cleanup                                │   │
│  │  scheduler.shutdown() → Redis.aclose() → dispose_db()    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Execution Modes

| Mode | Command | Use Case |
| ---- | ------- | -------- |
| **Integrated** | FastAPI lifespan (auto) | Development, small deployments |
| **Standalone** | `python -m app.infrastructure.scheduler.main` | Local testing |
| **Docker** | `docker compose --profile scheduler-only up -d` | Production, isolated workers |

---

## Quick Start

### 1. Import the Scheduler

```python
from app.infrastructure.scheduler import scheduler
```

### 2. Define a Job Function

```python
# app/infrastructure/scheduler/jobs.py

from app.core.db import AsyncSessionLocal

async def process_pending_refunds() -> None:
    """Process all pending refunds in the system."""
    async with AsyncSessionLocal.begin() as session:
        # Your refund processing logic here
        pending_refunds = await get_pending_refunds(session)
        for refund in pending_refunds:
            await process_refund(session, refund)
```

### 3. Schedule the Job

```python
from datetime import datetime
from apscheduler.triggers.interval import IntervalTrigger

from app.infrastructure.scheduler import scheduler
from app.core.config import scheduler_logger

def schedule_pending_refunds_job(minutes: int):
    """Schedule a job to process pending refunds at regular intervals."""
    scheduler_logger.info(
        f"Scheduling 'process_pending_refunds' job to run every {minutes} minutes."
    )
    scheduler.add_job(
        process_pending_refunds,
        trigger=IntervalTrigger(minutes=minutes, start_date=datetime.now()),
        replace_existing=True,
        id="process_pending_refunds_job",
        jobstore="refunds",
        misfire_grace_time=60 * 2,  # 2 minutes grace time
    )
    scheduler_logger.info("'process_pending_refunds' job scheduled successfully.")
```

---

## Configuration

### Environment Variables

| Variable | Description | Required | Default |
| -------- | ----------- | -------- | ------- |
| `DATABASE_URL` | PostgreSQL connection string | ✅ | - |
| `REDIS_URL` | Redis connection string | ✅ | `redis://redis:6379/0` |
| `BREVO_API_KEY` | Brevo email service API key | ✅ | - |
| `BREVO_SENDER_EMAIL` | Email sender address | ✅ | - |
| `BREVO_SENDER_NAME` | Email sender display name | ❌ | `CueBX` |
| `ENABLE_SCHEDULER` | Toggle scheduler on/off in FastAPI | ❌ | `True` |

### Dedicated Logger

The scheduler has its own logger configured in `app/core/config.py`:

```python
scheduler_logger = setup_logger(
    name="scheduler_logger",
    log_file="logs/scheduler.log",
    level=logging.INFO,
    sentry_tag="scheduler",
)
```

Use it for all scheduler-related logging:

```python
from app.core.config import scheduler_logger

scheduler_logger.info("Job started")
scheduler_logger.error("Job failed", exc_info=True)
```

---

## Adding Jobs

### Interval Trigger

Run a job at fixed intervals:

```python
from datetime import datetime
from apscheduler.triggers.interval import IntervalTrigger

scheduler.add_job(
    my_job_function,
    trigger=IntervalTrigger(
        minutes=30,              # Run every 30 minutes
        start_date=datetime.now()
    ),
    replace_existing=True,
    id="my_job_id",
    jobstore="my_jobstore",
    misfire_grace_time=60 * 5,  # 5 minutes grace time
)
```

### Cron Trigger

Run a job on a cron-like schedule:

```python
from apscheduler.triggers.cron import CronTrigger

scheduler.add_job(
    daily_cleanup,
    trigger=CronTrigger(
        hour=2,      # Run at 2 AM
        minute=0,
        timezone="UTC"
    ),
    replace_existing=True,
    id="daily_cleanup_job",
    jobstore="maintenance",
)
```

### Date Trigger

Run a job once at a specific time:

```python
from datetime import datetime, timedelta
from apscheduler.triggers.date import DateTrigger

scheduler.add_job(
    send_reminder,
    trigger=DateTrigger(run_date=datetime.now() + timedelta(hours=24)),
    id=f"reminder_{user_id}",
    jobstore="reminders",
    kwargs={"user_id": user_id},
)
```

### Passing Arguments to Jobs

Use `args` or `kwargs` to pass data to your job function:

```python
from datetime import timedelta

def schedule_send_payment_reminder_emails_job(hours: int):
    """Schedule a job to send payment reminder emails at regular intervals."""
    scheduler_logger.info(
        f"Scheduling 'send_payment_reminder_emails' job to run every {hours} hours."
    )
    scheduler.add_job(
        send_payment_reminder_emails,
        trigger=IntervalTrigger(hours=hours, start_date=datetime.now()),
        replace_existing=True,
        id="send_payment_reminder_emails_job",
        jobstore="payment_reminders",
        misfire_grace_time=60 * 10,  # 10 minutes grace time
        kwargs={"tolerance": timedelta(hours=hours)},
    )
    scheduler_logger.info("'send_payment_reminder_emails' job scheduled successfully.")
```

---

## Job Stores

Job stores persist scheduled jobs to survive application restarts. **Job stores are required when scheduling jobs.**

### Configuring Job Stores

Add SQLAlchemy job stores to the scheduler configuration in `main.py`:

```python
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

scheduler = AsyncIOScheduler(
    jobstores={
        "refunds": SQLAlchemyJobStore(
            url=settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql"),
            tablename="scheduler_refunds_jobs",
        ),
        "payment_reminders": SQLAlchemyJobStore(
            url=settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql"),
            tablename="scheduler_payment_reminders_jobs",
        ),
        "maintenance": SQLAlchemyJobStore(
            url=settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql"),
            tablename="scheduler_maintenance_jobs",
        ),
    },
    timezone=timezone.utc,
)
```

### Why Replace the URL?

APScheduler's SQLAlchemy job store uses synchronous database operations. The URL must be converted from `postgresql+asyncpg://` to `postgresql://` for compatibility:

```python
# ❌ Won't work - async driver
url = "postgresql+asyncpg://user:pass@host/db"

# ✅ Works - sync driver
url = "postgresql+asyncpg://...".replace("postgresql+asyncpg", "postgresql")
```

### Job Store Best Practices

```python
# ✅ Good: One job store per job category
jobstores = {
    "refunds": SQLAlchemyJobStore(..., tablename="scheduler_refunds_jobs"),
    "reminders": SQLAlchemyJobStore(..., tablename="scheduler_reminders_jobs"),
    "reports": SQLAlchemyJobStore(..., tablename="scheduler_reports_jobs"),
}

# ❌ Bad: Single job store for everything (harder to manage)
jobstores = {
    "default": SQLAlchemyJobStore(..., tablename="all_jobs"),
}
```

---

## Running the Scheduler

### Mode 1: Integrated with FastAPI

The scheduler starts automatically with FastAPI when `ENABLE_SCHEDULER=True`:

```python
# app/main.py (automatic)
if settings.ENABLE_SCHEDULER:
    scheduler.start()

# On shutdown
if settings.ENABLE_SCHEDULER:
    scheduler.shutdown()
```

### Mode 2: Standalone Execution

Run the scheduler as an independent process:

```bash
python -m app.infrastructure.scheduler.main
```

This mode:

- Initializes all required services (database, Redis, Brevo, templates)
- Handles graceful shutdown on SIGINT/SIGTERM
- Runs until interrupted

### Mode 3: Docker Container

Run as an isolated Docker service:

```bash
# Start scheduler only
docker compose --profile scheduler-only up -d

# Start with full development stack
docker compose --profile dev up -d

# View logs
docker logs -f cubex-scheduler
```

The Docker service is defined in `docker-compose.yml`:

```yaml
scheduler:
  build:
    context: .
    target: scheduler
  container_name: cubex-scheduler
  profiles:
    - dev
    - scheduler-only
  environment:
    - DATABASE_URL=${DATABASE_URL}
    - REDIS_URL=${REDIS_URL}
    - BREVO_API_KEY=${BREVO_API_KEY}
    # ... other env vars
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
```

---

## Best Practices

### 1. Use Unique Job IDs

Always provide a unique `id` to prevent duplicate jobs:

```python
# ✅ Good: Unique, descriptive ID
scheduler.add_job(
    process_refunds,
    id="process_pending_refunds_job",
    replace_existing=True,
)

# ❌ Bad: No ID (APScheduler generates random UUID)
scheduler.add_job(process_refunds)
```

### 2. Set Appropriate Misfire Grace Time

Configure how long a job can be late and still run:

```python
# ✅ Good: Grace time based on job importance
scheduler.add_job(
    critical_job,
    misfire_grace_time=60 * 2,  # 2 minutes for critical jobs
)

scheduler.add_job(
    daily_report,
    misfire_grace_time=60 * 60,  # 1 hour for daily jobs
)

# ❌ Bad: Default grace time (1 second) - too strict
scheduler.add_job(critical_job)  # Will miss jobs easily
```

### 3. Use `replace_existing=True`

Prevent duplicate jobs on application restart:

```python
# ✅ Good: Replace existing job with same ID
scheduler.add_job(
    my_job,
    id="my_job_id",
    replace_existing=True,
)

# ❌ Bad: No replace flag (creates duplicates on restart)
scheduler.add_job(my_job, id="my_job_id")
```

### 4. Handle Exceptions in Job Functions

Jobs should handle their own exceptions:

```python
# ✅ Good: Exception handling with logging
async def process_refunds():
    try:
        # Process refunds
        await do_refund_processing()
    except Exception as e:
        scheduler_logger.exception(f"Refund processing failed: {e}")
        # Optionally: send alert, update status, etc.

# ❌ Bad: Unhandled exceptions
async def process_refunds():
    await do_refund_processing()  # Crashes silently on error
```

### 5. Use UTC Timezone

The scheduler is configured with UTC. Always use UTC for consistency:

```python
from datetime import datetime, timezone

# ✅ Good: UTC-aware datetime
scheduler.add_job(
    my_job,
    trigger=IntervalTrigger(
        minutes=30,
        start_date=datetime.now(timezone.utc)
    ),
)

# ❌ Bad: Naive datetime (ambiguous)
scheduler.add_job(
    my_job,
    trigger=IntervalTrigger(start_date=datetime.now()),  # Local time?
)
```

---

## Testing

### Running Tests

```bash
# Run scheduler tests
pytest tests/infrastructure/scheduler/test_main.py -v

# Run with coverage
pytest tests/infrastructure/scheduler/test_main.py \
    --cov=app.infrastructure.scheduler.main \
    --cov-report=term-missing -v
```

### Test Structure

```text
tests/
└── infrastructure/
    └── scheduler/
        └── test_main.py    # Scheduler tests (4 tests)
```

### Example Tests

```python
"""
Test suite for scheduler initialization.
"""

from unittest.mock import patch
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.infrastructure.scheduler.main import scheduler


class TestScheduler:
    """Test suite for scheduler instance."""

    def test_scheduler_is_async_io_scheduler(self):
        """Test that scheduler is an AsyncIOScheduler instance."""
        assert isinstance(scheduler, AsyncIOScheduler)

    def test_scheduler_has_utc_timezone(self):
        """Test that scheduler is configured with UTC timezone."""
        assert scheduler.timezone is not None
        assert str(scheduler.timezone) == "UTC"


class TestMain:
    """Test suite for scheduler operations."""

    def test_scheduler_can_start(self):
        """Test that scheduler can be started."""
        with patch.object(scheduler, "start") as mock_start:
            scheduler.start()
            mock_start.assert_called_once()

    def test_scheduler_can_shutdown(self):
        """Test that scheduler can be shutdown."""
        with patch.object(scheduler, "shutdown") as mock_shutdown:
            scheduler.shutdown()
            mock_shutdown.assert_called_once()
```

### Testing Job Functions

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_process_pending_refunds():
    """Test the process_pending_refunds job function."""
    with patch("app.scheduler.jobs.get_pending_refunds", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        
        await process_pending_refunds()
        
        mock_get.assert_called_once()
```

### Testing Job Scheduling

```python
from unittest.mock import patch, MagicMock

def test_schedule_pending_refunds_job():
    """Test that job is scheduled correctly."""
    with patch.object(scheduler, "add_job") as mock_add_job:
        schedule_pending_refunds_job(minutes=30)
        
        mock_add_job.assert_called_once()
        call_kwargs = mock_add_job.call_args.kwargs
        
        assert call_kwargs["id"] == "process_pending_refunds_job"
        assert call_kwargs["jobstore"] == "refunds"
        assert call_kwargs["replace_existing"] is True
```

---

## Troubleshooting

### Scheduler Not Starting

**Symptom:** No jobs are running, no logs appear.

**Solutions:**

1. Check `ENABLE_SCHEDULER` environment variable:

   ```bash
   echo $ENABLE_SCHEDULER  # Should be True or not set
   ```

2. Verify the scheduler is imported and started:

   ```python
   from app.infrastructure.scheduler import scheduler
   print(scheduler.running)  # Should be True after start()
   ```

### Jobs Missing / Not Running

**Symptom:** Jobs were scheduled but don't execute.

**Solutions:**

1. Check misfire grace time:

   ```python
   # Increase grace time for less time-sensitive jobs
   scheduler.add_job(my_job, misfire_grace_time=60 * 30)
   ```

2. Verify job store is configured:

   ```python
   # Jobs need a job store to persist
   scheduler.add_job(my_job, jobstore="my_store")  # Store must exist!
   ```

3. Check job store tables exist in database:

   ```sql
   SELECT * FROM scheduler_refunds_jobs;
   ```

### Signal Handling Issues (Standalone Mode)

**Symptom:** Scheduler doesn't stop on Ctrl+C.

**Solutions:**

1. Ensure you're running in the main thread
2. Check signal handlers are registered:

   ```python
   signal.signal(signal.SIGINT, handle_shutdown)
   signal.signal(signal.SIGTERM, handle_shutdown)
   ```

### Database Connection Errors

**Symptom:** `SQLAlchemyJobStore` fails to connect.

**Solutions:**

1. Verify URL conversion:

   ```python
   # ✅ Correct: Use sync driver for job store
   url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
   ```

2. Check database is accessible:

   ```bash
   psql $DATABASE_URL -c "SELECT 1"
   ```

### Duplicate Jobs on Restart

**Symptom:** Same job runs multiple times.

**Solutions:**

1. Use `replace_existing=True`:

   ```python
   scheduler.add_job(my_job, id="unique_id", replace_existing=True)
   ```

2. Use unique job IDs:

   ```python
   # For user-specific jobs
   scheduler.add_job(
       send_reminder,
       id=f"reminder_user_{user_id}",
       replace_existing=True,
   )
   ```

### View Scheduled Jobs

```python
# List all scheduled jobs
for job in scheduler.get_jobs():
    print(f"Job: {job.id}, Next run: {job.next_run_time}")

# Get specific job
job = scheduler.get_job("process_pending_refunds_job")
print(job.next_run_time)

# Remove a job
scheduler.remove_job("job_id")
```

---

## API Reference

### Scheduler Instance

```python
from app.infrastructure.scheduler import scheduler

# Type: AsyncIOScheduler
# Timezone: UTC
```

### Key Methods

| Method | Description |
| ------ | ----------- |
| `scheduler.start()` | Start the scheduler |
| `scheduler.shutdown(wait=True)` | Stop the scheduler (wait for jobs to complete) |
| `scheduler.add_job(func, ...)` | Schedule a new job |
| `scheduler.remove_job(job_id)` | Remove a scheduled job |
| `scheduler.get_jobs()` | List all scheduled jobs |
| `scheduler.get_job(job_id)` | Get a specific job |
| `scheduler.pause_job(job_id)` | Pause a job |
| `scheduler.resume_job(job_id)` | Resume a paused job |

### Trigger Types

| Trigger | Import | Use Case |
| ------- | ------ | -------- |
| `IntervalTrigger` | `apscheduler.triggers.interval` | Run every N minutes/hours |
| `CronTrigger` | `apscheduler.triggers.cron` | Cron-like scheduling |
| `DateTrigger` | `apscheduler.triggers.date` | One-time execution |

---

Happy scheduling! ⏰🚀
