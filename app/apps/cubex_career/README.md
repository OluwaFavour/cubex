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
- [Analysis History](#analysis-history)

---

## Domain Concepts

| Concept | Description |
| --------- | ------------- |
| **Career Subscription** | Tied to a user via `CareerSubscriptionContext` (not a workspace). Plans: Free, Plus, Pro. |
| **Career Usage Log** | Same lifecycle as API usage logs (`PENDING` → `SUCCESS` / `FAILED` / `EXPIRED`), but scoped to `user_id` + `subscription_id` instead of `workspace_id` + `api_key_id`. |
| **Quota** | Per-user credit budget from `PlanPricingRule`. Same `FeatureCostConfig` table, filtered by `product_type=CAREER`. |
| **Analysis Result** | Stores structured AI responses from successful analyses. Created automatically when a commit includes `result_data`. Linked 1:1 to a `CareerUsageLog`. |

---

## Module Structure

```text
app/apps/cubex_career/
├── dependencies.py              # Currently empty — Career uses core auth deps only
├── routers/
│   ├── subscription.py          # Plans, checkout, upgrade, cancel, activate
│   ├── internal.py              # Usage validate + commit (service-to-service)
│   └── history.py               # Analysis history (list, detail, delete)
├── schemas/
│   ├── subscription.py          # Plan, checkout, upgrade, cancel schemas
│   ├── internal.py              # Usage validate + commit schemas
│   └── history.py               # Analysis history list/detail/response schemas
├── services/
│   ├── subscription.py          # CareerSubscriptionService — Stripe + plan management
│   └── quota.py                 # CareerQuotaService — usage logging, quota enforcement
└── db/
    ├── models/
    │   ├── usage_log.py         # CareerUsageLog model
    │   └── analysis_result.py   # CareerAnalysisResult model (history records)
    └── crud/
        ├── usage_log.py         # CareerUsageLog CRUD operations
        └── analysis_result.py   # CareerAnalysisResult CRUD (list, detail, soft-delete)
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
| POST | `/usage/commit` | `X-Internal-API-Key` | Commit pending usage as SUCCESS or FAILED; optionally creates analysis history |

> Career internal endpoints require **both** the user's JWT (to identify the user) and the `X-Internal-API-Key` header (to authenticate the calling service). This differs from the API product which uses API keys instead of JWTs.

### Analysis History — `/career/history`

| Method | Path | Auth | Description |
| -------- | ------ | ------ | ------------- |
| GET | `/` | JWT | List analysis history (cursor-paginated, filterable by feature_key) |
| GET | `/{result_id}` | JWT | Get analysis result detail (ownership-checked) |
| DELETE | `/{result_id}` | JWT | Soft-delete an analysis result (idempotent, 204) |

> History endpoints are user-scoped — each user sees only their own results. Results are created automatically when a commit includes `result_data` for a successful analysis.

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
| `UsageCommitRequest` | `user_id`, `usage_id`, `success`, `metrics`, `failure`, `result_data` |
| `UsageCommitResponse` | `success`, `message` |

### History Schemas

| Schema | Key Fields |
| -------- | ------------ |
| `AnalysisHistoryItem` | `id`, `feature_key`, `title`, `result_data`, `created_at` |
| `AnalysisHistoryDetail` | Extends Item with `usage_log_id`, `updated_at` |
| `AnalysisHistoryListResponse` | `items`, `has_more`, `next_cursor` |

---

## Database Models

| Model | Table | Key Fields |
| ------- | ------- | ------------ |
| `CareerUsageLog` | `career_usage_logs` | `user_id`, `subscription_id`, `request_id`, `feature_key`, `credits_reserved`, `status` |
| `CareerAnalysisResult` | `career_analysis_results` | `usage_log_id`, `user_id`, `feature_key`, `title`, `result_data` |

The `CareerUsageLog` mirrors the structure of `UsageLog` (from cubex_api) but replaces `workspace_id` / `api_key_id` with `user_id` / `subscription_id`.

The `CareerAnalysisResult` stores the structured AI analysis response from a successful commit. It is linked 1:1 to a `CareerUsageLog` and includes denormalized `user_id` / `feature_key` for efficient querying. The `title` is auto-generated from the feature key (e.g. `career.job_match` → "Job Match Analysis").

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

---

## Analysis History

The analysis history feature stores AI analysis results for user-facing review.

### How Results Are Created

Results are created **automatically** during the commit flow. When a service calls `POST /career/internal/usage/commit` with `success=true` and a `result_data` payload, the quota service persists a `CareerAnalysisResult` row linked to the committed usage log.

```text
Service → POST /career/internal/usage/commit
           ├── success=true, result_data={...}  →  CareerAnalysisResult created
           ├── success=true, result_data=null    →  No history record
           └── success=false                     →  result_data silently discarded
```

### User-Facing Endpoints

Users access their history via the `/career/history` router:

- **List** — paginated (cursor-based), filterable by `feature_key`, includes `result_data` in each item
- **Detail** — full result with `usage_log_id` for correlation
- **Delete** — soft-delete (idempotent, 204 No Content)

### Title Auto-Generation

Each result gets a human-readable title derived from its `feature_key`:

| Feature Key | Generated Title |
| --- | --- |
| `career.job_match` | Job Match Analysis |
| `career.career_path` | Career Path Analysis |
| `career.feedback_analyzer` | Feedback Analysis |
| `career.generate_feedback` | Feedback Generation |
| `career.extract_keywords` | Keyword Extraction |
| `career.extract_cues.resume` | Resume Cue Extraction |
| `career.extract_cues.feedback` | Feedback Cue Extraction |
| `career.extract_cues.interview` | Interview Cue Extraction |
| `career.extract_cues.assessment` | Assessment Cue Extraction |
| `career.reframe_feedback` | Feedback Reframing |
