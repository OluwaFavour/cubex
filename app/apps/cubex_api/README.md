# CueBX API Product

The workspace-based developer tooling product. Provides team collaboration with role-based access, per-seat billing, API key management, and usage-tracked AI features.

## Table of Contents

- [Domain Concepts](#domain-concepts)
- [Module Structure](#module-structure)
- [Endpoints](#endpoints)
- [Services](#services)
- [Dependencies (Access Guards)](#dependencies-access-guards)
- [Schemas](#schemas)
- [Database Models](#database-models)
- [Adding a New Endpoint](#adding-a-new-endpoint)

---

## Domain Concepts

| Concept | Description |
| --------- | ------------- |
| **Workspace** | An isolated tenant. Every user starts with a personal workspace. Team workspaces can have multiple members. |
| **WorkspaceMember** | A user's membership in a workspace with a role (`OWNER`, `ADMIN`, `MEMBER`) and status (`ENABLED`, `DISABLED`). |
| **Subscription** | Tied to a workspace via `APISubscriptionContext`. Plans: Free, Basic, Professional. |
| **API Key** | Scoped to a workspace. Prefixed `cbx_live_` (production) or `cbx_test_` (test mode). Hashed with HMAC-SHA256. |
| **Usage Log** | One record per AI feature invocation. Lifecycle: `PENDING` → `SUCCESS` / `FAILED` / `EXPIRED`. |
| **Quota** | Per-workspace credit budget. Allocated from `PlanPricingRule.credits_allocation`, consumed per-feature based on `FeatureCostConfig`. |
| **Invitation** | Token-based email invite. Lifecycle: `PENDING` → `ACCEPTED` / `EXPIRED` / `REVOKED`. |

---

## Module Structure

```text
app/apps/cubex_api/
├── dependencies.py          # Workspace-scoped access guard dependencies
├── routers/
│   ├── workspace.py         # Workspace CRUD, members, invitations, API keys
│   ├── subscription.py      # Plans, checkout, seats, upgrade, cancel
│   ├── support.py           # Contact sales form
│   └── internal.py          # Usage validate + commit (service-to-service)
├── schemas/
│   ├── workspace.py         # Request/response models for workspace operations
│   ├── subscription.py      # Plan, checkout, upgrade schemas
│   └── support.py           # Sales request schemas
├── services/
│   ├── workspace.py         # WorkspaceService — workspace + member business logic
│   ├── subscription.py      # SubscriptionService — Stripe + plan management
│   ├── quota.py             # QuotaService — API key, usage logging, quota enforcement
│   └── quota_cache.py       # APIQuotaCacheService — Redis-backed key/plan caching
└── db/
    ├── models/
    │   ├── workspace.py     # Workspace, WorkspaceMember, WorkspaceInvitation, APIKey, UsageLog
    │   └── support.py       # SalesRequest
    └── crud/
        ├── workspace.py     # Workspace CRUD operations
        └── support.py       # SalesRequest CRUD operations
```

---

## Endpoints

All endpoints are mounted under `/api` in [app/main.py](../../main.py).

### Workspaces — `/api/workspaces`

| Method | Path | Auth | Permission | Description |
| -------- | ------ | ------ | ------------ | ------------- |
| GET | `/` | JWT | Member | List workspaces the user belongs to |
| POST | `/` | JWT | Any | Create a new team workspace |
| GET | `/{workspace_id}` | JWT | Member | Get workspace details with members |
| PATCH | `/{workspace_id}` | JWT | Admin+ | Update workspace name, slug, description |
| POST | `/activate` | JWT | Any | Create/retrieve personal workspace (idempotent) |
| GET | `/{workspace_id}/members` | JWT | Member | List workspace members |
| PATCH | `/{workspace_id}/members/{id}/status` | JWT | Admin+ | Enable or disable a member |
| PATCH | `/{workspace_id}/members/{id}/role` | JWT | Owner | Change a member's role |
| DELETE | `/{workspace_id}/members/{id}` | JWT | Admin+ | Remove a member |
| POST | `/{workspace_id}/leave` | JWT | Member | Leave workspace (not owner) |
| POST | `/{workspace_id}/transfer-ownership` | JWT | Owner | Transfer ownership to another member |
| GET | `/{workspace_id}/invitations` | JWT | Admin+ | List pending invitations |
| POST | `/{workspace_id}/invitations` | JWT | Admin+ | Invite user by email |
| DELETE | `/{workspace_id}/invitations/{id}` | JWT | Admin+ | Revoke a pending invitation |
| POST | `/invitations/accept` | JWT | Any | Accept invitation via token |
| POST | `/{workspace_id}/api-keys` | JWT | Admin+ | Create a live or test API key |
| GET | `/{workspace_id}/api-keys` | JWT | Member | List workspace API keys |
| DELETE | `/{workspace_id}/api-keys/{id}` | JWT | Admin+ | Revoke an API key |

### Subscriptions — `/api/subscriptions`

| Method | Path | Auth | Permission | Description |
| -------- | ------ | ------ | ------------ | ------------- |
| GET | `/plans` | None | Public | List active API plans |
| GET | `/plans/{plan_id}` | None | Public | Get plan details |
| GET | `/workspaces/{id}` | JWT | Member | Get workspace subscription |
| POST | `/workspaces/{id}/checkout` | JWT | Admin+ | Create Stripe checkout session |
| PATCH | `/workspaces/{id}/seats` | JWT | Admin+ | Update seat count |
| POST | `/workspaces/{id}/cancel` | JWT | Owner | Cancel subscription |
| POST | `/workspaces/{id}/reactivate` | JWT | Owner | Reactivate frozen workspace |
| POST | `/workspaces/{id}/preview-upgrade` | JWT | Admin+ | Preview proration for plan change |
| POST | `/workspaces/{id}/upgrade` | JWT | Admin+ | Upgrade subscription plan |

### Support — `/api/support`

| Method | Path | Auth | Description |
| -------- | ------ | ------ | ------------- |
| POST | `/contact-sales` | None | Submit a sales inquiry (rate-limited 3/hr per email) |

### Internal API — `/api/internal`

| Method | Path | Auth | Description |
| -------- | ------ | ------ | ------------- |
| POST | `/usage/validate` | `X-Internal-API-Key` | Validate API key + check quota + create pending usage log |
| POST | `/usage/commit` | `X-Internal-API-Key` | Commit pending usage as SUCCESS or FAILED |

> These endpoints are called by external AI services, not by end users directly. They authenticate via the `INTERNAL_API_SECRET` header, not JWT.

---

## Services

### `WorkspaceService` (singleton: `workspace_service`)

Handles workspace lifecycle, membership, and invitations. Key patterns:

- **Idempotent personal workspace** — `create_personal_workspace` returns existing if already created
- **Seat validation** — enabling a member or accepting an invitation checks `plan.max_seats`
- **Cascade on freeze** — when a subscription is cancelled, the workspace is frozen and members are disabled
- **Token-based invitations** — invitation tokens are hashed (SHA256) in DB, raw token sent via email

### `SubscriptionService` (singleton: `subscription_service`)

Manages Stripe integration and subscription lifecycle. Key patterns:

- **Webhook-driven** — checkout completion, subscription updates, and deletions are processed asynchronously via RabbitMQ handlers
- **Proration previews** — upgrade/downgrade costs are previewed via Stripe's proration API before committing
- **Workspace reactivation** — unfreezes workspace status and re-enables selected members

### `QuotaService` (singleton: `quota_service`)

Handles API key management and per-request usage tracking:

- **Key generation** — `cbx_live_` / `cbx_test_` prefixes, HMAC-SHA256 hashed
- **Validate pipeline** — resolve key → rate limit check → idempotency check → quota check → create PENDING log
- **Commit pipeline** — mark PENDING → SUCCESS (deduct credits) or FAILED (release reservation)
- **Idempotency** — duplicate `request_id + payload_hash + workspace_id` returns the existing log

### `APIQuotaCacheService`

Extends the core `QuotaCacheService` with Redis-based API key caching (15s TTL) to avoid a DB lookup on every request.

---

## Dependencies (Access Guards)

Defined in `dependencies.py`. These are FastAPI `Depends()` callables injected into route functions:

| Dependency | Returns | Checks |
| ------------ | --------- | -------- |
| `get_workspace_member` | `WorkspaceMember` | User is a member of the workspace |
| `get_workspace_admin` | `WorkspaceMember` | User is admin or owner |
| `get_workspace_owner` | `WorkspaceMember` | User is the owner |
| `get_active_workspace` | `Workspace` | Workspace exists and is not frozen |
| `get_active_workspace_admin` | `(WorkspaceMember, Workspace)` | Admin + workspace not frozen |
| `get_active_workspace_owner` | `(WorkspaceMember, Workspace)` | Owner + workspace not frozen |

Type aliases are provided for cleaner signatures: `WorkspaceMemberDep`, `WorkspaceAdminDep`, etc.

Usage example:

```python
@router.post("/{workspace_id}/api-keys")
async def create_api_key(
    workspace_id: UUID,
    body: APIKeyCreate,
    member_workspace: ActiveWorkspaceAdminDep,  # Tuple[WorkspaceMember, Workspace]
    session: AsyncSession = Depends(get_async_session),
):
    member, workspace = member_workspace
    # member is guaranteed to be admin+ and workspace is guaranteed active
```

---

## Schemas

Pydantic v2 request/response models in `schemas/`. Key conventions:

- **Request models** end with `Request` or `Create` / `Update`
- **Response models** end with `Response`
- **List responses** wrap items: `WorkspaceListResponse.workspaces: list[WorkspaceResponse]`
- All UUID fields use `uuid.UUID` type
- All datetime fields are timezone-aware

---

## Database Models

All models inherit from `BaseModel` which provides `id` (UUID PK), `created_at`, `updated_at`, `is_deleted`, `deleted_at`.

| Model | Table | Key Fields |
| ------- | ------- | ------------ |
| `Workspace` | `workspaces` | `display_name`, `slug` (unique), `owner_id`, `status`, `is_personal` |
| `WorkspaceMember` | `workspace_members` | `workspace_id`, `user_id`, `role`, `status`, `joined_at` |
| `WorkspaceInvitation` | `workspace_invitations` | `workspace_id`, `email`, `token_hash`, `role`, `status`, `expires_at` |
| `APIKey` | `api_keys` | `workspace_id`, `name`, `key_hash`, `key_prefix`, `is_active`, `is_test_key` |
| `UsageLog` | `usage_logs` | `api_key_id`, `workspace_id`, `request_id`, `feature_key`, `credits_reserved`, `status` |
| `SalesRequest` | `sales_requests` | `first_name`, `last_name`, `email`, `message`, `status` |

See the [Database Schema](../../README.md#database-schema) section in the root README for the full ER diagram.

---

## Adding a New Endpoint

1. **Define the schema** in `schemas/` — create request and response Pydantic models
2. **Add the route** in the appropriate router file with proper dependencies
3. **Add business logic** in the corresponding service
4. **Add CRUD** if new DB operations are needed in `db/crud/`
5. **Write tests** in `tests/apps/cubex_api/routers/` (see [tests/README.md](../../../tests/README.md) for patterns)
6. **Update `openapi.json`** — run `python manage.py generateopenapi`

Example adding a new workspace endpoint:

```python
# schemas/workspace.py
class MyNewRequest(CamelModel):
    field: str

class MyNewResponse(CamelModel):
    result: str

# routers/workspace.py
@router.post("/{workspace_id}/my-action")
async def my_action(
    workspace_id: UUID,
    body: MyNewRequest,
    member_workspace: ActiveWorkspaceAdminDep,
    session: AsyncSession = Depends(get_async_session),
):
    member, workspace = member_workspace
    result = await workspace_service.my_action(session, workspace, body)
    return MyNewResponse(result=result)
```
