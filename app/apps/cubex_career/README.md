# CueBX Career Product

An individual subscription service for AI-assisted career development. Unlike the API product (workspace-based), Career subscriptions are tied directly to a user account.

## Table of Contents

- [Domain Concepts](#domain-concepts)
- [Module Structure](#module-structure)
- [Endpoints](#endpoints)
- [Services](#services)
- [Schemas](#schemas)
- [Database Models](#database-models)
- [Key Differences from CueBX API](#key-differences-from-cuebx-api)
- [Adding a New Endpoint](#adding-a-new-endpoint)

---

## Domain Concepts

| Concept | Description |
| --------- | ------------- |
| **Career Subscription** | Tied to a user via `CareerSubscriptionContext` (not a workspace). Plans: Free, Plus, Pro. |
| **Career Usage Log** | Same lifecycle as API usage logs (`PENDING` → `SUCCESS` / `FAILED` / `EXPIRED`), but scoped to `user_id` + `subscription_id` instead of `workspace_id` + `api_key_id`. |
| **Quota** | Per-user credit budget from `PlanPricingRule`. Same `FeatureCostConfig` table, filtered by `product_type=CAREER`. |

---

## Module Structure

```text
app/apps/cubex_career/
├── dependencies.py              # Currently empty — Career uses core auth deps only
├── routers/
│   ├── subscription.py          # Plans, checkout, upgrade, cancel, activate
│   └── internal.py              # Usage validate + commit (service-to-service)
├── schemas/
│   ├── subscription.py          # Plan, checkout, upgrade, cancel schemas
│   └── internal.py              # Usage validate + commit schemas
├── services/
│   ├── subscription.py          # CareerSubscriptionService — Stripe + plan management
│   └── quota.py                 # CareerQuotaService — usage logging, quota enforcement
└── db/
    ├── models/
    │   └── usage_log.py         # CareerUsageLog model
    └── crud/
        └── usage_log.py         # CareerUsageLog CRUD operations
```

---

## Endpoints

All endpoints are mounted under `/career` in [app/main.py](../../main.py).

### Subscriptions — `/career/subscriptions`

| Method | Path | Auth | Description |
| -------- | ------ | ------ | ------------- |
| GET | `/plans` | None | List active Career plans (public) |
| GET | `/plans/{plan_id}` | None | Get Career plan details (public) |
| GET | `/` | JWT | Get current user's Career subscription |
| POST | `/checkout` | JWT | Create Stripe checkout session for a Career plan |
| POST | `/preview-upgrade` | JWT | Preview proration for plan upgrade |
| POST | `/upgrade` | JWT | Upgrade Career subscription plan |
| POST | `/cancel` | JWT | Cancel Career subscription |
| POST | `/activate` | JWT | Create free Career subscription (idempotent) |

### Internal API — `/career/internal`

| Method | Path | Auth | Description |
| -------- | ------ | ------ | ------------- |
| POST | `/usage/validate` | JWT + `X-Internal-API-Key` | Validate user quota + rate limits, create pending log |
| POST | `/usage/commit` | `X-Internal-API-Key` | Commit pending usage as SUCCESS or FAILED |

> Career internal endpoints require **both** the user's JWT (to identify the user) and the `X-Internal-API-Key` header (to authenticate the calling service). This differs from the API product which uses API keys instead of JWTs.

---

## Services

### `CareerSubscriptionService` (singleton: `career_subscription_service`)

Manages Career subscription lifecycle. Key patterns:

- **Idempotent free subscription** — `create_free_subscription` returns existing if already active
- **User-scoped** — all operations take a `user_id`, not a `workspace_id`
- **Webhook-driven** — checkout completion, updates, and deletions handled via RabbitMQ
- **Same Stripe patterns** as API product (proration previews, cancel-at-period-end)

### `CareerQuotaService` (singleton: `career_quota_service`)

Handles per-user usage tracking:

- **Validate pipeline** — resolve user subscription → rate limit → idempotency → quota check → create PENDING log
- **Commit pipeline** — mark PENDING → SUCCESS (deduct credits) or FAILED (release reservation)
- **Idempotency** — duplicate `request_id + payload_hash + user_id` returns existing log

---

## Schemas

### Subscription Schemas

| Schema | Key Fields |
| -------- | ------------ |
| `CareerSubscriptionResponse` | `id`, `user_id`, `plan_id`, `status`, `current_period_start/end`, `cancel_at_period_end`, `plan` |
| `CareerCheckoutRequest` | `plan_id`, `success_url`, `cancel_url` |
| `CareerCheckoutResponse` | `checkout_url`, `session_id` |
| `CareerUpgradePreviewRequest` | `new_plan_id` |
| `CareerUpgradePreviewResponse` | `current_plan`, `new_plan`, `proration_amount`, `total_due`, `currency` |
| `CareerUpgradeRequest` | `new_plan_id` |
| `CareerCancelRequest` | `cancel_at_period_end` (default `true`) |

### Internal Schemas

| Schema | Key Fields |
| -------- | ------------ |
| `UsageValidateRequest` | `request_id`, `feature_key`, `endpoint`, `method`, `payload_hash` |
| `UsageValidateResponse` | `access`, `user_id`, `usage_id`, `message`, `credits_reserved` |
| `UsageCommitRequest` | `user_id`, `usage_id`, `success`, `metrics`, `failure` |
| `UsageCommitResponse` | `success`, `message` |

---

## Database Models

| Model | Table | Key Fields |
| ------- | ------- | ------------ |
| `CareerUsageLog` | `career_usage_logs` | `user_id`, `subscription_id`, `request_id`, `feature_key`, `credits_reserved`, `status` |

The `CareerUsageLog` mirrors the structure of `UsageLog` (from cubex_api) but replaces `workspace_id` / `api_key_id` with `user_id` / `subscription_id`.

See the [Database Schema](../../README.md#database-schema) section in the root README for the full ER diagram.

---

## Key Differences from CueBX API

| Aspect | CueBX API | CueBX Career |
| -------- | ----------- | -------------- |
| **Subscription scope** | Workspace (team) | User (individual) |
| **Context model** | `APISubscriptionContext` (workspace ↔ subscription) | `CareerSubscriptionContext` (user ↔ subscription) |
| **Auth for internal API** | API key (`X-Internal-API-Key` only) | JWT + `X-Internal-API-Key` |
| **OAuth / members** | Workspace members, invitations, roles | None — user-only |
| **API keys** | Yes (live + test) | None — user JWT is the identity |
| **Usage log FK** | `api_key_id + workspace_id` | `user_id + subscription_id` |
| **Plans** | Free / Basic / Professional | Free / Plus / Pro |
| **Access guards** | `WorkspaceMemberDep`, `WorkspaceAdminDep`, etc. | Core `CurrentActiveUser` only |

---

## Adding a New Endpoint

1. **Define the schema** in `schemas/` — request and response Pydantic models
2. **Add the route** in the appropriate router with `CurrentActiveUser` dependency
3. **Add business logic** in the corresponding service
4. **Write tests** in `tests/apps/cubex_career/routers/`
5. **Update `openapi.json`** — run `python manage.py generateopenapi`

Career endpoints are simpler than API endpoints because there are no workspace-level access guards — every authenticated user can manage their own subscription.
