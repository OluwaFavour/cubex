# Contributing to CueBX

Thank you for contributing to CueBX! This guide covers everything you need to know to submit clean, consistent contributions.

## Table of Contents

- [Getting Started](#getting-started)
- [Branch Naming](#branch-naming)
- [Commit Messages](#commit-messages)
- [Development Workflow](#development-workflow)
- [Code Style](#code-style)
- [Pre-commit Checks](#pre-commit-checks)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Project Conventions](#project-conventions)
  - [Service pattern](#service-pattern)
  - [CRUD pattern](#crud-pattern)
  - [Router pattern](#router-pattern)
  - [Import rules](#import-rules)
  - [Enum naming](#enum-naming)
  - [Logging](#logging)
  - [Orchestration vs. responsibility](#orchestration-vs-responsibility)
  - [OpenAPI endpoint documentation](#openapi-endpoint-documentation)
  - [Background job pattern](#background-job-pattern)

---

## Getting Started

1. Clone and set up the development environment:

   ```bash
   git clone https://github.com/OluwaFavour/cubex.git
   cd cubex
   python -m venv .venv
   source .venv/bin/activate   # Linux/macOS
   .\.venv\Scripts\Activate.ps1  # Windows

   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

2. Start infrastructure services:

   ```bash
   docker compose --profile dev up -d
   ```

3. Run migrations and seed data:

   ```bash
   python manage.py migrate
   python manage.py syncplans
   ```

4. Verify everything works:

   ```bash
   pytest tests/ -x -q --tb=short
   ```

---

## Branch Naming

Always branch from `dev`. Never branch from `main` directly.

| Prefix | Purpose | Example |
| -------- | --------- | --------- |
| `feature/` | New features | `feature/dlq-dashboard` |
| `fix/` | Bug fixes | `fix/scheduler-auth-failure` |
| `refactor/` | Code restructuring | `refactor/quota-cache-pattern` |
| `docs/` | Documentation only | `docs/add-er-diagram` |
| `test/` | Test additions / fixes | `test/webhook-edge-cases` |
| `chore/` | Tooling, CI, deps | `chore/upgrade-sqlalchemy` |

---

## Commit Messages

Use the **Conventional Commits** format:

```text
<type>(<scope>): <short description>

[optional body]

[optional footer(s)]
```

### Types

| Type | When to use |
| ------ | ------------- |
| `feat` | A new feature |
| `fix` | A bug fix |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or updating tests |
| `docs` | Documentation only changes |
| `chore` | Build process, CI, dependencies |
| `perf` | Performance improvement |
| `style` | Formatting, missing semicolons (no code change) |

### Scopes

Use the module name as scope:

| Scope | Covers |
| ------- | -------- |
| `auth` | Authentication, OAuth, JWT, OTP |
| `workspace` | Workspace CRUD, members, invitations, API keys |
| `subscription` | Plans, checkout, upgrade, Stripe integration |
| `career` | Career product endpoints and services |
| `messaging` | RabbitMQ queues, consumers, handlers |
| `scheduler` | APScheduler jobs |
| `admin` | SQLAdmin panel |
| `db` | Models, migrations, CRUD |
| `config` | Settings, environment variables |
| `ci` | GitHub Actions, Docker, Render |

### Examples

```text
feat(workspace): add API key rotation endpoint

fix(messaging): prevent duplicate DLQ alerts for same event

refactor(auth): extract token generation into utility

test(subscription): add webhook edge case coverage

docs(readme): add database schema diagram

chore(ci): upgrade Python to 3.13 in workflow
```

### Rules

- Use **imperative mood** in the description: "add feature" not "added feature"
- Keep the first line under **72 characters**
- Reference GitHub issues in the footer: `Closes #6`
- Breaking changes: add `BREAKING CHANGE:` in the footer or `!` after the type: `feat(auth)!: change token format`

---

## Development Workflow

1. **Sync with `dev`:**

   ```bash
   git checkout dev
   git pull origin dev
   ```

2. **Create your branch:**

   ```bash
   git checkout -b feature/my-feature
   ```

3. **Make changes** — write code, write tests.

4. **Run checks before committing:**

   ```bash
   # Format
   black app/ tests/

   # Lint
   ruff check app/ tests/

   # Type check
   pyright app/

   # Test
   pytest tests/ -x -q --tb=short
   ```

5. **Commit with a descriptive message:**

   ```bash
   git add .
   git commit -m "feat(workspace): add API key rotation endpoint"
   ```

6. **Sync with `dev` before pushing:**

   ```bash
   git fetch origin dev
   git rebase origin/dev
   ```

7. **Push and open a PR:**

   ```bash
   git push origin feature/my-feature
   ```

---

## Code Style

### Formatting — Black

[Black](https://black.readthedocs.io/) is the project formatter. Default settings (line length 88).

```bash
# Format all code
black app/ tests/

# Check without modifying
black --check app/ tests/
```

### Linting — Ruff

[Ruff](https://docs.astral.sh/ruff/) handles import sorting and linting.

```bash
# Lint
ruff check app/ tests/

# Auto-fix
ruff check --fix app/ tests/
```

### Type Checking — Pyright

[Pyright](https://microsoft.github.io/pyright/) is used for static type analysis.

```bash
pyright app/
```

All new code should include type hints. Use `from __future__ import annotations` for forward references.

---

## Pre-commit Checks

Run the management command before every commit:

```bash
python manage.py precommit
```

This runs Black → Ruff → Pyright → Import Linter → Pytest in sequence, stopping on the first failure.

Useful flags:

```bash
# Auto-fix formatting and safe lint issues
python manage.py precommit --fix

# Skip tests (e.g. for a docs-only change)
python manage.py precommit --skip-tests
```

Or run each step manually:

```bash
# 1. Format
black app/ tests/

# 2. Lint (auto-fix safe issues)
ruff check --fix app/ tests/

# 3. Type check
pyright app/

# 4. Import contracts
lint-imports

# 5. Test
pytest tests/ -x -q --tb=short
```

If all five pass, you're safe to commit. CI will run the same checks.

---

## Testing Requirements

- **All new features must have tests.** No exceptions.
- **All new endpoints need integration tests** against a real database (see [tests/README.md](tests/README.md) for patterns).
- **Bug fixes should include a regression test** that fails without the fix and passes with it.
- **Don't break existing tests.** Run the full suite before pushing.
- **Coverage:** CI reports coverage via Codecov. Aim for >80% on new files.

### Test file naming

| Source file | Test file |
| ------------- | ----------- |
| `app/core/routers/auth.py` | `tests/core/routers/test_auth.py` |
| `app/apps/cubex_api/services/workspace.py` | `tests/apps/cubex_api/test_workspace_service.py` |
| `app/infrastructure/messaging/consumer.py` | `tests/infrastructure/messaging/test_consumer.py` |

### Test class naming

Group tests by endpoint or function:

```python
class TestCreateWorkspace:
    """Tests for POST /api/workspaces"""

class TestWorkspaceServiceCreatePersonal:
    """Tests for WorkspaceService.create_personal_workspace"""
```

### Test method naming

Use `test_<what>_<condition>_<expected>`:

```python
def test_create_workspace_with_valid_data_returns_201(self):
def test_create_workspace_without_auth_returns_401(self):
def test_create_workspace_with_duplicate_slug_returns_409(self):
```

---

## Pull Request Process

### Before opening

- [ ] All checks pass locally (format, lint, type check, tests)
- [ ] Branch is rebased on latest `dev`
- [ ] Commit messages follow Conventional Commits format

### PR title

Use the same format as commit messages:

```text
feat(workspace): add API key rotation endpoint
```

### PR description

Include:

- **What** changed (1-2 sentences)
- **Why** the change is needed
- **How** it was implemented (brief technical summary)
- Link to related GitHub issue(s): `Closes #6`
- Any migration or deployment notes

### PR requirements

- Target branch: `dev` (never `main` directly)
- CI must pass (tests + coverage)
- Descriptive title and description
- At least one reviewer approval (when available)

### Merging

- Use **squash merge** for feature branches to keep `dev` history clean
- Delete the branch after merge

---

## Project Conventions

### Service pattern

Services that are initialised once at startup (e.g. `AuthService`, `QuotaCacheService`) inherit from `SingletonService` and expose a `classmethod` `init()` called in the lifespan:

```python
from app.core.services.base import SingletonService

class MyService(SingletonService):
    @classmethod
    def init(cls, config: str) -> None:
        cls._config = config
        cls._initialized = True

    @classmethod
    def do_something(cls) -> str:
        if not cls._initialized:
            raise RuntimeError("MyService not initialised")
        return cls._config
```

`SingletonService` provides `_initialized`, `is_initialized()`, and `_reset()` (for test teardown) automatically.

Not every service inherits `SingletonService` — stateless helpers like `CloudinaryService`, `BrevoService`, and `RedisService` are plain classes with class-level state and do not need the lifecycle guard.

### CRUD pattern

Database operations go in `db/crud/` modules. Each CRUD class inherits from `BaseDB[T]`, a generic base that provides `get_by_id`, `get_all`, `create`, `update`, `delete`, and other common operations. Subclasses add domain-specific queries as **instance methods**:

```python
from app.core.db.crud.base import BaseDB

class WorkspaceDB(BaseDB[Workspace]):
    def __init__(self) -> None:
        super().__init__(model=Workspace)

    async def get_by_slug(
        self, session: AsyncSession, slug: str
    ) -> Workspace | None:
        ...

# Module-level singleton used throughout the app
workspace_db = WorkspaceDB()
```

Consumers import the pre-created instance (e.g. `from app.apps.cubex_api.db.crud import workspace_db`).

### Router pattern

Routers follow FastAPI conventions. Each endpoint function should:

1. Extract dependencies (auth, session, access guards)
2. Delegate to a **service** for writes/business logic, or call a **CRUD instance** directly for simple reads
3. Return a Pydantic response model

All database mutations use the **`async with session.begin()`** pattern — the block auto-commits on success and auto-rolls back on exception. Service and CRUD calls inside the block pass `commit_self=False` to defer the commit to the transaction manager:

```python
# Write — delegate to a service inside a transaction block
@router.post("/{workspace_id}/api-keys")
async def create_api_key(
    workspace_id: UUID,
    body: APIKeyCreate,
    member_workspace: ActiveWorkspaceAdminDep,
    session: AsyncSession = Depends(get_async_session),
) -> APIKeyCreatedResponse:
    member, workspace = member_workspace
    async with session.begin():
        return await quota_service.create_api_key(
            session, workspace, body, commit_self=False
        )

# Read — CRUD directly is fine (no transaction block needed)
@router.get("/{workspace_id}/members")
async def list_members(
    workspace_id: UUID,
    session: AsyncSession = Depends(get_async_session),
) -> list[WorkspaceMemberResponse]:
    members = await workspace_member_db.get_workspace_members(session, workspace_id)
    return [_build_member_response(m) for m in members]
```

Infrastructure code (scheduler jobs, message handlers) that doesn't receive a session via dependency injection creates its own transactional session:

```python
async with AsyncSessionLocal.begin() as session:
    await user_db.permanently_delete_soft_deleted(
        session, cutoff_date, commit_self=False
    )
```

### Import rules

**Ordering** — three groups, separated by a blank line:

1. Standard library
2. Third-party packages
3. Local imports (`app.*`)

Ruff handles sorting automatically.

**All imports must be at module level.** Inline (deferred) imports inside functions, methods, or conditional blocks are **not allowed**.

The only acceptable exception is a **genuine circular import** that cannot be resolved by restructuring the modules. In that case, add a comment explaining why:

```python
# ✅ Correct — module-level imports
from app.core.config import stripe_logger
from app.core.db import AsyncSessionLocal
from app.infrastructure.messaging.publisher import publish_event


async def action_retry(self, request: Request) -> RedirectResponse:
    await publish_event(queue, payload)


# ❌ Wrong — inline import with no circular-dependency justification
async def action_retry(self, request: Request) -> RedirectResponse:
    from app.infrastructure.messaging.publisher import publish_event  # bad
    await publish_event(queue, payload)


# ⚠️ Exception — documented circular import (rare)
def some_edge_case():
    # Circular: module X imports module Y which imports module X at class level.
    from app.core.some_module import SomeClass  # noqa: circular
    ...
```

The import-linter contracts in `pyproject.toml` enforce architectural boundaries. The dependency graph is:

```text
admin          → core, apps
infrastructure → core, apps
apps           → core only
core           → nothing above it
```

Each app product (`cubex_api`, `cubex_career`) must also be **independent** — no cross-imports between products. Shared schemas live in `app.core.schemas`.

| Contract | Rule |
| -------- | ---- |
| Core → Apps | Forbidden |
| Core → Infrastructure | Forbidden |
| Core → Admin | Forbidden |
| Apps → Infrastructure | Forbidden |
| Apps → Admin | Forbidden |
| Infrastructure → Admin | Forbidden |
| Admin → Infrastructure | Forbidden |
| cubex_api ↔ cubex_career | Independent (no cross-imports) |

Ruff enforces sorting and unused-import removal.

### Enum naming

All enums are in `app/core/enums.py`. Values use UPPER_SNAKE_CASE:

```python
class MemberRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
```

### Logging

The project uses a **centralised logging system** — never create ad-hoc loggers.

#### Setup

`app/core/logger.py` defines `setup_logger()`, which creates a `logging.Logger` with:

- **`RotatingFileHandler`** — writes to `logs/<component>.log` (5 MB, 3 backups)
- **`StreamHandler`** — mirrors to console
- **Sentry tag** — optional component label for filtering in Sentry
- **Format:** `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

`app/core/config.py` instantiates **18 component-specific loggers** and exports them via `__all__`:

| Logger | File | Sentry tag | Use for |
| ------ | ---- | ---------- | ------- |
| `app_logger` | `logs/app.log` | `app` | Application lifecycle, startup/shutdown |
| `database_logger` | `logs/database.log` | `database` | DB connections, migrations |
| `request_logger` | `logs/requests.log` | `request` | HTTP request handling in routers |
| `auth_logger` | `logs/auth.log` | `auth` | Authentication, OAuth, OTP |
| `stripe_logger` | `logs/stripe.log` | `stripe` | Stripe API calls, webhook processing |
| `rabbitmq_logger` | `logs/rabbitmq.log` | `messaging` | RabbitMQ connections, consumers |
| `scheduler_logger` | `logs/scheduler.log` | `scheduler` | APScheduler jobs |
| `workspace_logger` | `logs/workspace.log` | `workspace` | Workspace CRUD, members |
| `usage_logger` | `logs/usage.log` | `usage` | Usage tracking, quota |
| `career_logger` | `logs/career.log` | `career` | Career product |
| `webhook_logger` | `logs/webhook.log` | `webhook` | Webhook dispatch |
| `redis_logger` | `logs/redis.log` | `redis` | Redis connections, caching |
| `rate_limit_logger` | `logs/rate_limit.log` | `rate_limit` | Rate limiting |
| `plan_logger` | `logs/plan.log` | `plan` | Plan management |
| `brevo_logger` | `logs/brevo.log` | `email` | Brevo email API |
| `email_manager_logger` | `logs/email_manager.log` | `email_manager` | Email orchestration |
| `cloudinary_logger` | `logs/cloudinary.log` | `cloudinary` | Cloudinary uploads |
| `utils_logger` | `logs/utils.log` | `utils` | General utilities |

#### Logging rules

1. **Always import an existing domain-specific logger** from `app.core.config`. Never use `logging.getLogger(__name__)` or create a new logger.
2. **Use f-string interpolation** with structured `key=value` pairs for context.
3. **Pick the correct severity:**
   - `debug` — verbose diagnostics (disabled in production)
   - `info` — happy-path milestones (request received, task completed)
   - `warning` — recoverable issues (retry succeeded, optional feature unavailable)
   - `error` — failures that need attention (always include the exception)
4. **Log at boundaries** — on entry, on success, and on error. Don't litter intermediate lines unless debugging.
5. If none of the 18 loggers fit your new module, **add a new one** in `app/core/config.py` following the same `setup_logger()` pattern and export it in `__all__`.

#### Logging example

```python
# ✅ Correct — domain-specific logger, structured key=value, correct severity
from app.core.config import auth_logger

async def send_otp(email: str, purpose: OTPPurpose) -> None:
    auth_logger.info(f"Processing OTP email: email={email}, purpose={purpose.value}")
    try:
        sent = await brevo_service.send_otp_email(email, code)
        if sent:
            auth_logger.info(f"OTP email sent successfully: email={email}")
        else:
            auth_logger.warning(f"OTP email service returned False: email={email}")
    except Exception as e:
        auth_logger.error(f"Failed to send OTP email: email={email}, error={e}")
        raise


# ❌ Wrong — ad-hoc logger, no context, wrong severity
import logging
logger = logging.getLogger(__name__)

async def send_otp(email: str, purpose: OTPPurpose) -> None:
    logger.debug("sending otp")  # too low severity, no context
    await brevo_service.send_otp_email(email, code)
    logger.debug("done")  # useless
```

### Orchestration vs. responsibility

Every function or method should be either an **orchestrator** or an **actor** — never both.

| Role | Responsibility | Examples |
| ---- | -------------- | -------- |
| **Orchestrator** | Coordinates multiple steps by delegating to actors. Contains no low-level logic of its own. | Router endpoints, service methods like `create_personal_workspace` |
| **Actor** | Performs a single, focused piece of work. Does not coordinate other actors. | CRUD methods (`get_by_id`, `bulk_discard`), private helpers (`_check_email_not_member`), publisher calls |

**If a function is doing its own low-level work _and_ coordinating other calls, split it** — extract the low-level work into a private helper (actor) and keep the parent as a pure orchestrator.

This keeps each unit small, testable, and easy to reason about.

#### Orchestration example

```python
# ✅ Correct — orchestrator delegates, actors do focused work

# Orchestrator (service method)
async def create_personal_workspace(
    self, session: AsyncSession, user: User
) -> Workspace:
    """Orchestrates personal workspace creation."""
    existing = await workspace_db.get_personal(session, user.id)
    if existing:
        return existing

    slug, display_name = self._generate_workspace_identity(user)
    workspace = await workspace_db.create(session, slug=slug, ...)
    await workspace_member_db.create(session, workspace_id=workspace.id, ...)
    await subscription_db.create(session, workspace_id=workspace.id, ...)
    return workspace

# Actor (private helper) — does ONE thing
def _generate_workspace_identity(self, user: User) -> tuple[str, str]:
    """Derive slug and display name from user profile."""
    base = user.full_name or user.email.split("@")[0]
    slug = slugify(base)
    return slug, f"{base}'s Workspace"


# ❌ Wrong — mixed orchestration and low-level work in one function
async def create_personal_workspace(
    self, session: AsyncSession, user: User
) -> Workspace:
    existing = await workspace_db.get_personal(session, user.id)
    if existing:
        return existing

    # Low-level slug generation mixed into orchestrator
    base = user.full_name or user.email.split("@")[0]
    slug = slugify(base)
    display_name = f"{base}'s Workspace"

    workspace = await workspace_db.create(session, slug=slug, ...)
    await workspace_member_db.create(session, workspace_id=workspace.id, ...)
    await subscription_db.create(session, workspace_id=workspace.id, ...)
    return workspace
```

### OpenAPI endpoint documentation

Every endpoint must have comprehensive, developer-friendly OpenAPI documentation. This is a **non-negotiable** standard.

#### Required fields

| Decorator param | Purpose | Guidelines |
| --------------- | ------- | ---------- |
| `summary` | Short label in docs UI | Imperative phrase, ≤ 10 words (e.g. `"List workspace members"`) |
| `description` | Full Markdown documentation | See structure below |
| `responses` | Custom non-200 examples | Add when the default error model isn't descriptive enough |

#### Description structure

Every `description` should follow this template (adapt sections as needed):

```markdown
## Endpoint Title

One-sentence summary of what the endpoint does.

### Authorization

Who can call this and what credentials are required.

### Request

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| ...   | ...  | ...      | ...         |

### Response

| Field | Type | Description |
|-------|------|-------------|
| ...   | ...  | ...         |

### Errors

| Status | Condition |
|--------|-----------|
| 401    | Missing or invalid token |
| 404    | Resource not found |
| ...    | ...       |

### Notes

- Any caveats, rate limiting, pagination details, etc.
```

#### Reference examples

The following endpoints are the gold standard — match their level of detail:

- `POST /auth/signup` — `app/core/routers/auth.py`
- `GET /career/history` — `app/apps/cubex_career/routers/history.py`
- `POST /api/internal/usage/validate` — `app/apps/cubex_api/routers/internal.py`
- `POST /support/contact-sales` — `app/apps/cubex_api/routers/support.py`

### Background job pattern

Offload non-critical work to RabbitMQ via the event publisher abstraction:

```python
from app.core.services.event_publisher import get_publisher

await get_publisher()("otp_emails", {"email": user.email, "otp": code})
```

The concrete publisher is registered at startup in `app/main.py`. Application code should never import directly from `app.infrastructure.messaging` — use `get_publisher()` instead.

Prefer queuing external service calls (email, notifications) via RabbitMQ when the response is not needed by the caller. Synchronous calls are acceptable when the endpoint must return data from the external service (e.g. Stripe checkout URLs, OAuth token exchange).
