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

This runs Black → Ruff → Pyright → Pytest in sequence, stopping on the first failure.

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

# 4. Test
pytest tests/ -x -q --tb=short
```

If all four pass, you're safe to commit. CI will run the same checks.

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

Services are class-based singletons that inherit from `SingletonService`. Initialize via `ClassName.init()` in lifespan:

```python
from app.core.services.base import SingletonService

class MyService(SingletonService):
    @classmethod
    def init(cls, config: str) -> None:
        cls._config = config
        cls._initialized = True

    @classmethod
    def do_something(cls) -> str:
        cls._ensure_initialized()
        return cls._config
```

`SingletonService` provides `_initialized`, `_ensure_initialized()`, and `_reset()` (for test teardown) automatically.

### CRUD pattern

Database operations go in `db/crud/` modules. Each CRUD module is a class with `@staticmethod` methods taking an `AsyncSession`:

```python
class WorkspaceCRUD:
    @staticmethod
    async def get_by_id(session: AsyncSession, workspace_id: UUID) -> Workspace | None:
        ...
```

### Router pattern

Routers follow FastAPI conventions. Each endpoint function should:

1. Extract dependencies (auth, session, access guards)
2. Delegate to a service method
3. Return a Pydantic response model

```python
@router.post("/{workspace_id}/api-keys")
async def create_api_key(
    workspace_id: UUID,
    body: APIKeyCreate,
    member_workspace: ActiveWorkspaceAdminDep,
    session: AsyncSession = Depends(get_async_session),
) -> APIKeyCreatedResponse:
    member, workspace = member_workspace
    return await quota_service.create_api_key(session, workspace, body)
```

### Import ordering

1. Standard library
2. Third-party packages
3. Local imports (`app.*`)

Ruff handles sorting automatically.

### Enum naming

All enums are in `app/core/enums.py`. Values use UPPER_SNAKE_CASE:

```python
class MemberRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
```

### Background job pattern

Offload non-critical work to RabbitMQ via the event publisher abstraction:

```python
from app.core.services.event_publisher import get_publisher

await get_publisher()("otp_emails", {"email": user.email, "otp": code})
```

The concrete publisher is registered at startup in `app/main.py`. Application code should never import directly from `app.infrastructure.messaging` — use `get_publisher()` instead.

Never call external services (Brevo, Stripe) synchronously in request handlers if it can be queued.
