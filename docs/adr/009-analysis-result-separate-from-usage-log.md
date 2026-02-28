# ADR-009: Separate CareerAnalysisResult Table for History

**Status:** Accepted
**Date:** 2026-02

## Context

When a career feature request succeeds, the AI service returns structured result data (e.g., career path recommendations, keyword extractions, feedback analysis). We need to store this data so users can browse their analysis history without re-running requests.

`CareerUsageLog` already tracks every validate → commit lifecycle, but it is an **operational** table:

- It records both successes and failures
- It stores billing metadata (credits reserved/charged, model used, tokens, latency)
- It is queried by the quota service on every request (hot path)
- Adding a large JSON column would bloat rows and slow quota lookups

We needed to decide where to persist the AI result payload.

## Decision

Create a **separate `CareerAnalysisResult` table** linked 1:0..1 to `CareerUsageLog`:

```text
CareerUsageLog  ──1:0..1──▶  CareerAnalysisResult
```

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | Inherited from `BaseModel` |
| `usage_log_id` | FK (unique) | Points to the originating `CareerUsageLog` |
| `user_id` | FK | Denormalised for fast user-scoped queries |
| `feature_key` | Enum | Copied from the usage log for filtering |
| `title` | String(255) | Auto-generated human-readable title from feature key |
| `result_data` | JSON | The AI response payload |
| `created_at` | DateTime | Inherited from `BaseModel` |

**Indexes:**

- `(user_id, created_at DESC)` — powers the paginated history list
- `(user_id, feature_key)` — powers filtered history queries

**Write path:** `commit_usage()` in `QuotaService` creates the result row inside the same transaction that updates the usage log to `SUCCESS`, only when `success=True` and `result_data` is provided.

**Read path:** Three user-facing endpoints under `/career/history` (list, get, delete) query `CareerAnalysisResult` directly without touching `CareerUsageLog`.

## Alternatives Considered

| Alternative | Why not |
| --- | --- |
| **Add `result_data` JSON column to `CareerUsageLog`** | Mixes operational and presentational concerns; bloats every row (including failures) with a nullable JSON column; slows quota-path queries that scan this table |
| **Store results in a separate NoSQL store (Redis, S3)** | Adds infrastructure complexity; results are relational (belong to a user, linked to a usage log) and benefit from transactional writes alongside the commit |
| **Store results in a generic key-value table** | Loses type safety and queryability; can't index on `feature_key` or paginate efficiently |
| **Let the AI service store its own results** | Splits ownership of user data across services; complicates deletion (GDPR) and history queries |

## Consequences

**Positive:**

- `CareerUsageLog` stays lean — quota lookups remain fast
- History queries only touch `CareerAnalysisResult` with purpose-built indexes
- The 1:0..1 relationship enforces that each usage log produces at most one result
- `user_id` denormalisation avoids a join through `CareerUsageLog` for every history list request
- Soft-delete (`is_deleted`) lets users remove results from their history without losing the audit trail in `CareerUsageLog`
- The `title` column enables human-readable history lists without parsing `result_data`

**Negative:**

- Denormalising `user_id` and `feature_key` means two columns are duplicated between tables — acceptable given they are small and rarely change
- A separate table adds one more migration and one more CRUD module to maintain
- The write path in `commit_usage()` now does an extra INSERT on success — negligible cost given commits are not on the hot path
