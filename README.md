# CueBX

![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)
[![Tests](https://github.com/OluwaFavour/cubex/actions/workflows/tests.yml/badge.svg)](https://github.com/OluwaFavour/cubex/actions/workflows/tests.yml)

A multi-product SaaS platform that provides AI-powered developer tools and career services through a unified API. CueBX ships two products — **CueBX API** (workspace-based developer tooling with team collaboration, role-based access, and per-seat billing) and **CueBX Career** (an individual subscription service for AI-assisted career development).

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Architecture Overview](#architecture-overview)
- [Database Schema](#database-schema)
- [Flow Diagrams](#flow-diagrams)
  - [Authentication](#authentication-flow)
  - [Workspace Lifecycle](#workspace-lifecycle)
  - [Subscriptions and Payments](#subscriptions-and-payments-flow)
  - [Messaging Pipeline](#messaging-pipeline)
  - [Usage and Quota Enforcement](#usage-and-quota-enforcement)
  - [Scheduler Jobs](#scheduler-jobs)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Docker](#docker)
- [CLI Reference](#cli-reference)
- [API Endpoints](#api-endpoints)
- [API Error Conventions](#api-error-conventions)
- [Environment Variables](#environment-variables)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)
- [Submodule Docs](#submodule-docs)

---

## Tech Stack

| Category | Technology |
| ---------- | ----------- |
| **Framework** | FastAPI + Uvicorn |
| **Language** | Python 3.13 |
| **Database** | PostgreSQL 16 (asyncpg) |
| **ORM / Migrations** | SQLAlchemy 2.0 (async) + Alembic |
| **Cache / Rate Limiting** | Redis 7 |
| **Message Broker** | RabbitMQ 3 (aio-pika) |
| **Payments** | Stripe |
| **Background Jobs** | APScheduler |
| **Admin Panel** | SQLAdmin |
| **Email** | Brevo (HTTP API) |
| **File Storage** | Cloudinary |
| **Monitoring** | Sentry |
| **Templating** | Jinja2 |
| **CLI** | Typer + Rich |
| **Auth** | JWT (PyJWT) + bcrypt + OAuth2 (Google, GitHub) |

---

## Architecture Overview

```text
                                    ┌──────────────────────────────────────────────────┐
                                    │                  External Services                │
                                    │  Stripe · Brevo · Cloudinary · Google · GitHub   │
                                    └──────────────────────┬───────────────────────────┘
                                                           │
                                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                      FastAPI Application                                    │
│                                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  Auth        │  │  Workspaces │  │  Subscriptions│  │  Support     │  │  Admin       │   │
│  │  /auth/*     │  │  /api/*     │  │  /api/* +     │  │  /api/*     │  │  /admin      │   │
│  │             │  │             │  │  /career/*    │  │             │  │  (SQLAdmin)  │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └──────┬───────┘   │
│         │                │                │                 │                │            │
│         └────────────────┴────────────────┴─────────────────┴────────────────┘            │
│                                           │                                               │
│  ┌────────────────────────────────────────┴──────────────────────────────────────────┐    │
│  │                              Core Services Layer                                  │    │
│  │  AuthService · RedisService · QuotaCacheService · BrevoService · Renderer · ...   │    │
│  └──────────┬──────────────────────────┬─────────────────────────────┬───────────────┘    │
│             │                          │                             │                     │
│  ┌──────────▼──────────┐   ┌──────────▼──────────┐   ┌──────────────▼──────────────┐     │
│  │  PostgreSQL (asyncpg)│   │  Redis               │   │  RabbitMQ (aio-pika)        │     │
│  │  Models + CRUD       │   │  Cache + Rate Limits  │   │  Queues + Retry + DLQ       │     │
│  └─────────────────────┘   └─────────────────────┘   └─────────────────────────────┘     │
│                                                                                           │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

   Separate Processes (Docker targets):

   ┌──────────────────────┐          ┌──────────────────────┐
   │   Scheduler (worker)  │          │   Consumer (worker)   │
   │   APScheduler         │          │   RabbitMQ Consumer   │
   │   • Cleanup users     │          │   • Email handlers    │
   │   • Expire usage logs │          │   • Stripe handlers   │
   └──────────────────────┘          │   • Usage handlers    │
                                      └──────────────────────┘
```

---

## Database Schema

17 models across 20 tables. All models inherit from `BaseModel` which provides `id` (UUID PK), `created_at`, `updated_at`, `is_deleted`, `deleted_at`.

```text
┌──────────────────────┐
│        User          │
│ ──────────────────── │
│ email (unique)       │
│ email_verified       │
│ full_name            │
│ avatar_url           │
│ password_hash        │
│ is_active            │
│ stripe_customer_id   │
└──────────┬───────────┘
           │
     ┌─────┼──────────────────────────────────────────┐
     │     │                                           │
     ▼     ▼                                           ▼
┌─────────────────┐ ┌──────────────────┐  ┌──────────────────────────┐
│  OAuthAccount   │ │  RefreshToken    │  │  CareerSubscriptionCtx   │
│ ─────────────── │ │ ──────────────── │  │ ────────────────────────  │
│ provider        │ │ token_hash       │  │ subscription_id (FK)──┐  │
│ provider_acct_id│ │ expires_at       │  │ user_id (FK)          │  │
│ user_id (FK)    │ │ device_info      │  │ credits_used          │  │
└─────────────────┘ │ revoked_at       │  └───────────────────────┼──┘
                    │ user_id (FK)     │                          │
                    └──────────────────┘                          │
                                                                  ▼
┌──────────────────────┐                           ┌──────────────────────┐
│       OTPToken       │                           │     Subscription     │
│ ──────────────────── │                           │ ──────────────────── │
│ email                │                           │ plan_id (FK)─────┐   │
│ code_hash            │                           │ product_type     │   │
│ purpose              │                           │ stripe_sub_id    │   │
│ expires_at           │                           │ status           │   │
│ attempts             │                           │ seat_count       │   │
│ user_id (FK)         │                           │ current_period_* │   │
└──────────────────────┘                           │ cancel_at_end    │   │
                                                   │ amount           │   │
                              ┌─────────────────── └──────────────────┼───┘
                              │                                       │
                              ▼                                       ▼
                ┌──────────────────────────┐            ┌──────────────────────┐
                │  APISubscriptionContext   │            │        Plan          │
                │ ──────────────────────── │            │ ──────────────────── │
                │ subscription_id (FK)     │            │ name                 │
                │ workspace_id (FK)────┐   │            │ description          │
                │ credits_used         │   │            │ price / display_price│
                └──────────────────────┼───┘            │ stripe_price_id      │
                                       │                │ seat_price           │
                                       ▼                │ product_type         │
┌────────────────────────────────────────────────┐      │ type (free/paid)     │
│                   Workspace                    │      │ features (JSONB)     │
│ ────────────────────────────────────────────── │      │ max_seats, min_seats │
│ display_name, slug (unique), description       │      │ rank                 │
│ owner_id (FK → User), status, is_personal      │      └──────────┬───────────┘
└─────┬──────────────┬──────────────┬────────────┘                 │
      │              │              │                               ▼
      ▼              ▼              ▼                  ┌──────────────────────┐
┌────────────┐ ┌──────────────┐ ┌─────────┐          │   PlanPricingRule    │
│ Workspace  │ │  Workspace   │ │ APIKey  │          │ ──────────────────── │
│ Member     │ │  Invitation  │ │ ─────── │          │ plan_id (FK)         │
│ ────────── │ │ ──────────── │ │ name    │          │ multiplier           │
│ workspace  │ │ workspace    │ │ key_hash│          │ credits_allocation   │
│ _id (FK)   │ │ _id (FK)     │ │ prefix  │          │ rate_limit_per_min   │
│ user_id    │ │ email        │ │ expires │          │ rate_limit_per_day   │
│ (FK)       │ │ token_hash   │ │ _at     │          └──────────────────────┘
│ role       │ │ role         │ │ is_test │
│ status     │ │ status       │ │ _key    │     ┌──────────────────────┐
│ joined_at  │ │ expires_at   │ │ scopes  │     │  FeatureCostConfig   │
└────────────┘ │ inviter_id   │ │workspace│     │ ──────────────────── │
               │ (FK)         │ │ _id(FK) │     │ feature_key          │
               └──────────────┘ └────┬────┘     │ product_type         │
                                     │          │ internal_cost_credits│
                    ┌────────────────┘          └──────────────────────┘
                    ▼
         ┌─────────────────────┐              ┌──────────────────────┐
         │      UsageLog       │              │   CareerUsageLog     │
         │ ─────────────────── │              │ ──────────────────── │
         │ api_key_id (FK)     │              │ user_id (FK)         │
         │ workspace_id (FK)   │              │ subscription_id (FK) │
         │ request_id          │              │ request_id           │
         │ feature_key         │              │ feature_key          │
         │ credits_reserved    │              │ credits_reserved     │
         │ credits_charged     │              │ credits_charged      │
         │ status (PENDING →   │              │ status               │
         │   SUCCESS/FAILED/   │              │ model_used, tokens,  │
         │   EXPIRED)          │              │ latency_ms           │
         │ model_used, tokens, │              │ failure_type/reason  │
         │ latency_ms          │              └──────────────────────┘
         │ failure_type/reason │                       │
         └─────────────────────┘                       │ 1:0..1
                                                       ▼
                                    ┌───────────────────────────┐
                                    │   CareerAnalysisResult    │
                                    │ ───────────────────────── │
                                    │ usage_log_id (FK, unique) │
                                    │ user_id (FK)              │
                                    │ feature_key               │
                                    │ title                     │
                                    │ result_data (JSON)        │
                                    └───────────────────────────┘

                                    ┌──────────────────────┐
                                    │   StripeEventLog     │
         ┌─────────────────────┐    │ ──────────────────── │
         │    SalesRequest     │    │ event_id (unique)    │
         │ ─────────────────── │    │ event_type           │
         │ first_name          │    │ processed_at         │
         │ last_name, email    │    └──────────────────────┘
         │ message, status     │
         └─────────────────────┘    ┌──────────────────────┐
                                    │     DLQMessage       │
                                    │ ──────────────────── │
                                    │ queue_name (indexed) │
                                    │ message_body         │
                                    │ error_message        │
                                    │ headers (JSON)       │
                                    │ attempt_count        │
                                    │ status (pending →    │
                                    │   retried/discarded) │
                                    └──────────────────────┘
```

### Key Relationships

| Relationship | Type | Description |
| --- | --- | --- |
| User → OAuthAccount | 1:N | A user can have multiple OAuth providers linked |
| User → RefreshToken | 1:N | Multiple active sessions per user |
| User → CareerSubscriptionContext → Subscription | 1:1:1 | One career subscription per user (via context) |
| Workspace → APISubscriptionContext → Subscription | 1:1:1 | One API subscription per workspace (via context) |
| Workspace → WorkspaceMember | 1:N | Multiple members per workspace |
| Workspace → APIKey → UsageLog | 1:N:N | Keys scoped to workspace, logs scoped to key |
| CareerUsageLog → CareerAnalysisResult | 1:0..1 | Successful analyses with `result_data` produce a history record |
| Plan → PlanPricingRule | 1:1 | Each plan has one pricing/quota configuration |
| Subscription → Plan | N:1 | Multiple subscriptions reference the same plan |

---

## Flow Diagrams

### Authentication Flow

```text
                                ┌──────────────┐
                                │   Client     │
                                └──────┬───────┘
                                       │
                        ┌──────────────┼──────────────┐
                        │              │              │
                   Email/Pass     OAuth (Google    Password
                   Signup         or GitHub)       Reset
                        │              │              │
                        ▼              ▼              ▼
                  ┌──────────┐  ┌───────────┐  ┌──────────────┐
                  │ POST     │  │ GET       │  │ POST         │
                  │ /signup  │  │ /oauth/   │  │ /password/   │
                  └────┬─────┘  │ {provider}│  │ reset        │
                       │        └─────┬─────┘  └──────┬───────┘
                       ▼              │               │
                ┌────────────┐        ▼               ▼
                │ Create     │  ┌───────────┐  ┌──────────────┐
                │ User (DB)  │  │ Redirect  │  │ Generate OTP │
                └────┬───────┘  │ to        │  │ (HMAC-based) │
                     │          │ Provider  │  └──────┬───────┘
                     ▼          └─────┬─────┘         │
              ┌────────────┐         │               ▼
              │ Generate   │         ▼         ┌──────────────┐
              │ OTP        │  ┌───────────┐    │ Queue Email  │──▶ RabbitMQ
              │ (HMAC)     │  │ Callback  │    │ (Brevo)      │
              └────┬───────┘  │ Exchange  │    └──────────────┘
                   │          │ Code →    │
                   ▼          │ Tokens    │
            ┌────────────┐    └─────┬─────┘
            │ Queue Email│          │
            │ via        │──▶ RabbitMQ
            │ RabbitMQ   │          │
            └────┬───────┘          │
                 │                  │
                 ▼                  ▼
          ┌────────────┐     ┌───────────┐
          │ POST       │     │ Return    │
          │ /signup/   │     │ JWT +     │
          │ verify     │     │ Refresh   │
          │ (OTP)      │     │ Token     │
          └────┬───────┘     └───────────┘
               │
               ▼
        ┌────────────┐      ┌──────────────────────────────────┐
        │ JWT +      │      │         Token Lifecycle          │
        │ Refresh    │      │                                  │
        │ Tokens     │      │  Access Token ──(expires)──▶     │
        └────────────┘      │    POST /token/refresh           │
                            │       │                          │
                            │       ▼                          │
                            │  New Access Token                │
                            │                                  │
                            │  POST /signout ──▶ Revoke        │
                            │  POST /signout/all ──▶ Revoke All│
                            └──────────────────────────────────┘
```

### Workspace Lifecycle

```text
  Owner                                            Invited User
    │                                                    │
    ▼                                                    │
┌────────────┐                                           │
│ POST       │                                           │
│ /workspaces│   Creates personal workspace              │
│ /activate  │   with owner membership                   │
└────┬───────┘                                           │
     │                                                   │
     ▼                                                   │
┌────────────┐                                           │
│ Workspace  │ status: ACTIVE                            │
│ (DB)       │ type: PERSONAL                            │
└────┬───────┘                                           │
     │                                                   │
     ├──────────── Manage API Keys ──────────────┐       │
     │  POST   /workspaces/{id}/api-keys         │       │
     │  DELETE /workspaces/{id}/api-keys/{key_id} │       │
     │                                            │       │
     ├──────────── Invite Members ───────────────┐│       │
     │  POST /workspaces/{id}/invitations        ││       │
     │         │                                 ││       │
     │         ▼                                 ││       │
     │  ┌──────────────┐                         ││       │
     │  │ Queue Email  │──▶ RabbitMQ ──▶ Brevo ──┼┼──▶ Email
     │  │ Invitation   │                         ││       │
     │  └──────────────┘                         ││       │
     │                                           ││       ▼
     │                                           ││  ┌────────────┐
     │                                           ││  │ POST       │
     │                                           ││  │ /workspaces│
     │                                           ││  │ /invitations│
     │                                           ││  │ /accept    │
     │                                           ││  └────┬───────┘
     │                                           ││       │
     │                                           ││       ▼
     │                                           ││  Member added
     │                                           ││  role: MEMBER
     │                                           ││       │
     │                                           ││       │
     ├──────────── Manage Members ───────────────┘│       │
     │  PUT /members/{id}/role   (ADMIN/MEMBER)   │       │
     │  PUT /members/{id}/status (ACTIVE/SUSPENDED)│       │
     │  DELETE /members/{id}     (remove)          │       │
     │                                             │       │
     ├──────────── Transfer Ownership ─────────────┘       │
     │  POST /workspaces/{id}/transfer-ownership           │
     │         │                                           │
     │         ▼                                           │
     │  Old owner → ADMIN, Target member → OWNER           │
     │                                                     │
     └──────────── Leave Workspace ────────────────────────┘
        POST /workspaces/{id}/leave
```

### Subscriptions and Payments Flow

```text
  Client                      CueBX API                  Stripe                 RabbitMQ
    │                            │                          │                      │
    │  GET /plans                │                          │                      │
    │ ──────────────────────────▶│                          │                      │
    │  List available plans      │                          │                      │
    │ ◀──────────────────────────│                          │                      │
    │                            │                          │                      │
    │  POST /checkout            │                          │                      │
    │ ──────────────────────────▶│                          │                      │
    │                            │  Create Checkout Session │                      │
    │                            │ ────────────────────────▶│                      │
    │                            │  Return session URL      │                      │
    │                            │ ◀────────────────────────│                      │
    │  Redirect to Stripe        │                          │                      │
    │ ◀──────────────────────────│                          │                      │
    │                            │                          │                      │
    │  ═══════════ User completes payment on Stripe ═══════════                    │
    │                            │                          │                      │
    │                            │  Webhook: checkout       │                      │
    │                            │  .session.completed      │                      │
    │                            │ ◀────────────────────────│                      │
    │                            │                          │                      │
    │                            │  Verify signature        │                      │
    │                            │  Publish to queue ──────────────────────────────▶│
    │                            │                          │                      │
    │                            │                          │              ┌───────▼───────┐
    │                            │                          │              │ Worker:       │
    │                            │                          │              │ Create        │
    │                            │                          │              │ Subscription  │
    │                            │                          │              │ + Quota       │
    │                            │                          │              │ + Email       │
    │                            │                          │              └───────────────┘
    │                            │                          │                      │
    │  ═══════════ Ongoing subscription management ═════════════                   │
    │                            │                          │                      │
    │  GET /preview-upgrade      │                          │                      │
    │ ──────────────────────────▶│  Preview proration       │                      │
    │ ◀──────────────────────────│ ◀───────────────────────▶│                      │
    │                            │                          │                      │
    │  POST /upgrade             │  Update subscription     │                      │
    │ ──────────────────────────▶│ ────────────────────────▶│                      │
    │ ◀──────────────────────────│ ◀────────────────────────│                      │
    │                            │                          │                      │
    │  POST /cancel              │  Cancel at period end    │                      │
    │ ──────────────────────────▶│ ────────────────────────▶│                      │
    │ ◀──────────────────────────│ ◀────────────────────────│                      │
    │                            │                          │                      │
    │                            │  Webhook: subscription   │                      │
    │                            │  .updated / .deleted     │                      │
    │                            │ ◀────────────────────────│                      │
    │                            │  Publish to queue ──────────────────────────────▶│
    │                            │                          │              ┌───────▼───────┐
    │                            │                          │              │ Worker:       │
    │                            │                          │              │ Update/Delete │
    │                            │                          │              │ Subscription  │
    │                            │                          │              │ + Email       │
    │                            │                          │              └───────────────┘
```

### Messaging Pipeline

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          12 Queue Triplets                                       │
│                                                                                  │
│  Email Queues:          otp_emails, password_reset_confirmation_emails,          │
│                         subscription_activated_emails, subscription_canceled_*,  │
│                         payment_failed_emails, workspace_invitation_emails       │
│                                                                                  │
│  Stripe Queues:         stripe_checkout_completed, stripe_subscription_updated,  │
│                         stripe_subscription_deleted, stripe_payment_failed       │
│                                                                                  │
│  Usage Queues:          usage_commits, career_usage_commits                      │
└──────────────────────────────────────────────────────────────────────────────────┘

For each queue:

  Publisher                Main Queue               Handler
     │                        │                        │
     │   publish_event()      │                        │
     │ ──────────────────────▶│   process_message()    │
     │                        │ ──────────────────────▶│
     │                        │                        │
     │                        │          ┌─────────────┤
     │                        │          │             │
     │                        │     (success)     (failure)
     │                        │          │             │
     │                        │          ▼             ▼
     │                        │        [ACK]     Check x-retry-attempt
     │                        │                        │
     │                        │          ┌─────────────┤
     │                        │          │             │
     │                        │   (retries left)  (retries exhausted)
     │                        │          │             │
     │                        │          ▼             ▼
     │                        │   ┌────────────┐  ┌────────────────┐
     │                        │   │Retry Queue │  │Dead Letter     │
     │                        │   │ (with TTL) │  │Queue           │
     │                        │   └─────┬──────┘  └───────┬────────┘
     │                        │         │                 │
     │                        │   (TTL expires)     ┌─────▼─────┐
     │                        │         │           │ Email     │
     │                        │◀────────┘           │ Alert to  │
     │                        │ (re-delivered       │ Admin     │
     │                        │  to main queue)     └───────────┘

  Retry Config:
    Email queues:   TTL 30s, max 3 retries
    Stripe queues:  TTL 60s, max 3-5 retries
    Usage queues:   TTL 30s, max 3 retries
```

> **Deep dive:** See [app/infrastructure/messaging/README.md](app/infrastructure/messaging/README.md) for handler examples, multi-retry strategies, and troubleshooting.

### Usage and Quota Enforcement

```text
  External Service                CueBX Internal API            QuotaCacheService
       │                                │                              │
       │  POST /internal/usage/validate │                              │
       │  Headers: X-Internal-API-Key   │                              │
       │ ──────────────────────────────▶│                              │
       │                                │  Check quota + rate limit    │
       │                                │ ────────────────────────────▶│
       │                                │                              │
       │                                │    ┌─────────────────────────┤
       │                                │    │                         │
       │                                │ (within quota)         (exceeded)
       │                                │    │                         │
       │                                │    ▼                         ▼
       │  200 OK (allowed)              │  Return OK              Return 429
       │ ◀──────────────────────────────│◀─────────────────────────────│
       │                                │                              │
       │  ═══════ Service performs the AI operation ═══════            │
       │                                │                              │
       │  POST /internal/usage/commit   │                              │
       │ ──────────────────────────────▶│                              │
       │                                │  Decrement credits           │
       │                                │ ────────────────────────────▶│
       │                                │  Create UsageLog (COMMITTED) │
       │  200 OK                        │  Publish to usage queue      │
       │ ◀──────────────────────────────│ ──────▶ RabbitMQ             │
       │                                │                              │

  Quota Cache (Redis or Memory):
    ┌──────────────────────────────────────────────────────┐
    │  Per-workspace snapshot:                             │
    │    credits_remaining, credits_used, rate counters    │
    │                                                      │
    │  Loaded from:                                        │
    │    PlanPricingRule (credits, rate limits)             │
    │    FeatureCostConfig (per-feature credit costs)      │
    │    Subscription status + plan tier                   │
    │                                                      │
    │  Refreshed on:                                       │
    │    Subscription change, plan upgrade, cache miss     │
    └──────────────────────────────────────────────────────┘
```

### Scheduler Jobs

```text
  APScheduler (AsyncIOScheduler)
  Persistent job stores backed by PostgreSQL
       │
       ├──── Job Store: "cleanups" ────────────────────────────────┐
       │     Table: scheduler_cleanup_jobs                         │
       │                                                           │
       │     ┌─────────────────────────────────────────────┐       │
       │     │ cleanup_soft_deleted_users                   │       │
       │     │ Trigger: CronTrigger, daily at 03:00 UTC    │       │
       │     │ Action: Permanently delete users where       │       │
       │     │   is_deleted=True and deleted_at > 30 days   │       │
       │     └─────────────────────────────────────────────┘       │
       │                                                           │
       ├──── Job Store: "usage_logs" ──────────────────────────────┤
       │     Table: scheduler_usage_log_jobs                       │
       │                                                           │
       │     ┌─────────────────────────────────────────────┐       │
       │     │ expire_pending_usage_logs                    │       │
       │     │ Trigger: IntervalTrigger, every 5 minutes    │       │
       │     │ Action: Set status=EXPIRED for usage logs    │       │
       │     │   with status=PENDING older than 15 min      │       │
       │     └─────────────────────────────────────────────┘       │
       │                                                           │
       │     ┌─────────────────────────────────────────────┐       │
       │     │ expire_pending_career_usage_logs             │       │
       │     │ Trigger: IntervalTrigger, every 5 minutes    │       │
       │     │ Action: Same as above for career usage logs  │       │
       │     └─────────────────────────────────────────────┘       │
       │                                                           │
       └───────────────────────────────────────────────────────────┘

  Standalone mode initializes: Database, Redis, Brevo, Renderer
  before starting the scheduler event loop.
```

> **Deep dive:** See [app/infrastructure/scheduler/README.md](app/infrastructure/scheduler/README.md) for job configuration, custom triggers, and Docker usage.

---

## Project Structure

```text
cubex/
├── app/
│   ├── main.py                         # FastAPI app, lifespan, middleware, routers
│   ├── admin/                          # SQLAdmin panel (/admin)
│   │   ├── auth.py                     #   HMAC-signed admin authentication
│   │   ├── views.py                    #   Model views (Plan, User, Workspace, …)
│   │   └── setup.py                    #   Mount admin on FastAPI app
│   ├── apps/
│   │   ├── cubex_api/                  # Workspace product
│   │   │   ├── db/                     #   Models + CRUD (Workspace, WorkspaceMember, …)
│   │   │   ├── routers/                #   Workspace, Subscription, Support, Internal
│   │   │   ├── schemas/                #   Pydantic request/response models
│   │   │   ├── services/               #   Business logic (workspace, subscription, quota)
│   │   │   └── dependencies.py         #   Auth + workspace access guards
│   │   └── cubex_career/               # Career product (same layout)
│   │       ├── db/
│   │       ├── routers/
│   │       ├── schemas/
│   │       ├── services/
│   │       └── dependencies.py
│   ├── core/
│   │   ├── config.py                   # Pydantic Settings + 18 component loggers
│   │   ├── enums.py                    # All shared enums
│   │   ├── utils.py                    # Utility functions
│   │   ├── logger.py                   # Logger + Sentry setup
│   │   ├── data/                       #   plans.json (subscription plan seed data)
│   │   ├── db/                         #   SQLAlchemy engine, base model, shared CRUD
│   │   ├── dependencies/               #   Session, auth, internal API key deps
│   │   ├── exceptions/                 #   Custom exception types + 17 handlers
│   │   ├── routers/                    #   Auth router, Webhook router
│   │   ├── schemas/                    #   Shared Pydantic schemas
│   │   └── services/                   #   Auth, Redis, Brevo, Cloudinary, QuotaCache, OAuth, EventPublisher, Lifecycle…
│   ├── infrastructure/
│   │   ├── messaging/                  # RabbitMQ: connection, publisher, consumer, queues
│   │   │   └── handlers/              #   Email, Stripe event, usage commit handlers
│   │   └── scheduler/                  # APScheduler: jobs + standalone entrypoint
│   └── templates/                      # Jinja2 templates (emails, alerts)
├── migrations/                         # Alembic migration versions
├── tests/                              # Pytest test suite (1600+ tests)
├── manage.py                           # Typer CLI (runserver, migrate, precommit, syncplans, …)
├── docker-compose.yml                  # Local dev: API + Scheduler + Worker + Postgres + Redis + RabbitMQ
├── Dockerfile                          # Multi-stage: api / scheduler / worker targets
├── render.yaml                         # Render deployment blueprint
├── alembic.ini                         # Alembic configuration
├── pyproject.toml                      # Project metadata + pytest config
├── requirements.txt                    # Runtime dependencies
└── requirements-dev.txt                # Dev/test dependencies
```

---

## Getting Started

### Prerequisites

- **Python 3.13+** (see `.python-version`)
- **Docker & Docker Compose** (for PostgreSQL, Redis, RabbitMQ)
- **Git**

### 1. Clone and set up the virtual environment

```bash
git clone https://github.com/OluwaFavour/cubex.git
cd cubex
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your values (DATABASE_URL, REDIS_URL, etc.)
```

### 3. Start infrastructure services

```bash
docker compose --profile dev up -d
```

This starts **PostgreSQL 16**, **Redis 7**, and **RabbitMQ 3** with management UI.

### 4. Run database migrations and seed plans

```bash
python manage.py migrate
python manage.py syncplans
```

### 5. Start the development server

```bash
python manage.py runserver
```

The API is now available at **<http://localhost:8000>**. Visit:

- **Swagger UI:** <http://localhost:8000/docs>
- **ReDoc:** <http://localhost:8000/redoc>
- **Admin Panel:** <http://localhost:8000/admin>
- **RabbitMQ Management:** <http://localhost:15672> (guest/guest)

---

## Docker

### Build targets

The Dockerfile provides three build targets:

| Target | Description | Command |
| -------- | ------------ | --------- |
| `api` | FastAPI server on port 8000 | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| `scheduler` | APScheduler background jobs | `python -m app.infrastructure.scheduler.main` |
| `worker` | RabbitMQ message consumer | `python -m app.infrastructure.messaging.main` |

```bash
# Build individual targets
docker build --target api -t cubex-api .
docker build --target scheduler -t cubex-scheduler .
docker build --target worker -t cubex-worker .
```

### Compose profiles

| Profile | Services | Use Case |
| --------- | ---------- | ---------- |
| `dev` | api + scheduler + worker + postgres + redis + rabbitmq | Full local development |
| `api-only` | api only | When infra services run externally |
| `scheduler-only` | scheduler only | Isolated scheduler deployment |
| `worker-only` | worker only | Isolated worker deployment |

```bash
# Full local environment
docker compose --profile dev up -d

# Only the API (external Postgres, Redis, RabbitMQ)
docker compose --profile api-only up -d

# Run migrations in Docker
docker compose run --rm api alembic upgrade head

# View logs
docker compose logs -f api
docker compose logs -f worker scheduler
```

---

## CLI Reference

All commands are run via `python manage.py <command>`.

| Command | Description |
| --------- | ------------- |
| `runserver` | Start Uvicorn dev server (auto-reload in debug mode) |
| `migrate` | Run `alembic upgrade head` |
| `makemigrations [comment]` | Generate a new Alembic migration (`--autogenerate`) |
| `showmigrations` | Show Alembic migration history |
| `clearalembic` | Delete all rows from `alembic_version` table |
| `createextensions <exts>` | Ensure PostgreSQL extensions exist (e.g. `citext`) |
| `syncplans [--dry-run]` | Upsert subscription plans from `app/core/data/plans.json` |
| `precommit [--fix] [--skip-tests]` | Run pre-commit checks (Black → Ruff → Pyright → Pytest) |
| `generateopenapi` | Re-generate `openapi.json` from current app |
| `runbroker` | Start RabbitMQ via Docker |
| `startngrok` | Expose localhost:8000 via ngrok tunnel |

---

## API Endpoints

The API is organized into 10 route groups with 57 endpoints total:

| Prefix | Tag | Endpoints | Description |
| -------- | ----- | ----------- | ------------- |
| `/auth` | Authentication | 14 | Signup, signin, OTP verify, OAuth, JWT refresh, password reset, sessions, profile |
| `/webhooks` | Webhooks | 1 | Stripe webhook receiver |
| `/api` | API - Workspaces | 14 | CRUD, members, invitations, API keys, ownership transfer |
| `/api` | API - Subscriptions | 9 | Plans, checkout, seats, upgrade, cancel, reactivate |
| `/api` | API - Support | 1 | Contact sales form |
| `/api` | API - Internal API | 2 | Usage validate + commit (service-to-service) |
| `/career` | Career - Subscriptions | 8 | Plans, checkout, upgrade, cancel, activate |
| `/career` | Career - Internal API | 2 | Usage validate + commit (service-to-service) |
| `/career` | Career - History | 3 | List, get, delete analysis results |
| `/admin/api` | Admin - DLQ | 1 | DLQ metrics (total, by status, by queue) |
| `/health` | Health Check | 1 | DB + Redis + RabbitMQ (when enabled) connectivity check |

**Full reference:** Start the server and visit `/docs` (Swagger) or `/redoc`.

---

## API Error Conventions

### Standard Error Response

All errors return a JSON body with a `detail` field:

```json
{
  "detail": "Human-readable error message"
}
```

### Stripe-specific Errors

Stripe errors include additional fields:

```json
{
  "detail": "Your card was declined",
  "stripe_code": "card_declined",
  "decline_code": "insufficient_funds",
  "param": "payment_method"
}
```

### HTTP Status Codes

| Code | Exception | When |
| ------ | ----------- | ------ |
| 400 | `BadRequestException`, `OTPExpiredException`, `OTPInvalidException`, `OAuthException` | Invalid input or expired/invalid OTP |
| 401 | `AuthenticationException` | Missing/invalid JWT. Response includes `WWW-Authenticate: Bearer` header |
| 402 | `PaymentRequiredException`, `StripeCardException` | Subscription required or card declined |
| 403 | `ForbiddenException` | Insufficient permissions (wrong role, workspace frozen, etc.) |
| 404 | `NotFoundException` | Resource not found or user not a member of workspace |
| 409 | `ConflictException`, `IdempotencyException` | Duplicate resource or idempotent replay |
| 422 | (FastAPI built-in) | Request body validation failure |
| 429 | `RateLimitExceededException`, `TooManyAttemptsException` | Rate limit hit. Response includes `Retry-After` header (seconds) |
| 500 | `DatabaseException` | Internal server error |
| 501 | `NotImplementedException` | Feature not yet implemented |
| 502 | `StripeAPIException` | Stripe API unreachable or returned an error |

### Rate Limiting Headers

When a rate limit is exceeded, the response includes:

```text
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/json

{"detail": "Rate limit exceeded. Try again in 60 seconds."}
```

### Authentication

All protected endpoints require a Bearer token:

```text
Authorization: Bearer <access_token>
```

Service-to-service (internal) endpoints use a separate header:

```text
X-Internal-API-Key: <INTERNAL_API_SECRET>
```

---

## Environment Variables

### Application

| Variable | Description | Default |
| ---------- | ------------- | --------- |
| `ENVIRONMENT` | `development` or `production` | `development` |
| `API_DOMAIN` | Public API URL | `http://localhost:8000` |
| `DEBUG` | Enable debug mode | `false` |
| `ROOT_PATH` | API version prefix | `/v1` |

### Database & Cache

| Variable | Description | Default |
| ---------- | ------------- | --------- |
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) | **required** |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `RABBITMQ_URL` | RabbitMQ AMQP connection string | `amqp://guest:guest@localhost:5672//` |

### Auth Secrets

| Variable | Description | Default |
| ---------- | ------------- | --------- |
| `JWT_SECRET_KEY` | JWT signing secret | `another_supersecret_key` * |
| `SESSION_SECRET_KEY` | Session cookie signing secret | `supersecretkey` * |
| `OTP_HMAC_SECRET` | HMAC key for OTP generation | `otp_hmac_secret_key_change_in_production` * |

### OAuth

| Variable | Description | Default |
| ---------- | ------------- | --------- |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | (empty) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | (empty) |
| `GITHUB_CLIENT_ID` | GitHub OAuth client ID | (empty) |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth client secret | (empty) |
| `OAUTH_REDIRECT_BASE_URI` | OAuth callback base URL | `http://localhost:8000/auth` |

### External Services

| Variable | Description | Default |
| ---------- | ------------- | --------- |
| `STRIPE_API_KEY` | Stripe secret API key | `your_stripe_api_key` * |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret | `your_stripe_webhook_secret` * |
| `BREVO_API_KEY` | Brevo email API key | `your_brevo_api_key` |
| `BREVO_SENDER_EMAIL` | From email address | `your_brevo_sender_email` |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name | `your_cloudinary_cloud_name` |
| `CLOUDINARY_API_KEY` | Cloudinary API key | `your_cloudinary_api_key` |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret | `your_cloudinary_api_secret` |

### Admin & Monitoring

| Variable | Description | Default |
| ---------- | ------------- | --------- |
| `ADMIN_USERNAME` | SQLAdmin login username | `admin` |
| `ADMIN_PASSWORD` | SQLAdmin login password | `admin_password_change_in_production` * |
| `INTERNAL_API_SECRET` | Service-to-service API key | `internal_api_secret_change_in_production` * |
| `SENTRY_DSN` | Sentry error tracking DSN | (empty) |
| `SENTRY_ENVIRONMENT` | Sentry environment label | `development` |
| `ADMIN_ALERT_EMAIL` | Email for DLQ/system alerts | (none) |

### Infrastructure Flags

| Variable | Description | Default |
| ---------- | ------------- | --------- |
| `ENABLE_SCHEDULER` | Start APScheduler in API process | `true` |
| `ENABLE_MESSAGING` | Start RabbitMQ consumers in API process | `true` |
| `QUOTA_CACHE_BACKEND` | Quota cache backend (`memory` or `redis`) | `memory` ** |
| `RATE_LIMIT_BACKEND` | Rate limit backend (`memory` or `redis`) | `memory` ** |
| `ADMIN_TOKEN_VERSION` | Increment to revoke all admin sessions | `0` |

> \* Marked variables **must** be changed in production. The app validates this at startup when `ENVIRONMENT=production` and will refuse to start if insecure defaults are detected.
>
> \*\* Must be `redis` in production. The app refuses to start with in-memory backends when `ENVIRONMENT=production`.

See `.env.example` for a copy-paste template with all variables.

---

## Testing

The test suite uses **pytest** with real PostgreSQL (via testcontainers), automatic transaction rollback, and auto-mocked external services.

```bash
# Run full suite
pytest

# Run with short output (recommended for large suites)
pytest tests/ -x -q --tb=short

# Run specific module
pytest tests/core/routers/test_auth.py

# Run with coverage report
pytest --cov=app --cov-report=html
# Then open htmlcov/index.html

# Skip slow tests
pytest -m "not slow"
```

### Test markers

| Marker | Purpose |
| -------- | --------- |
| `slow` | Long-running tests |
| `integration` | Integration tests requiring real services |
| `unit` | Pure unit tests |

### Coverage

Coverage is configured in `pyproject.toml` and reports against the `app/` package. CI uploads results to Codecov.

> **Full guide:** See [tests/README.md](tests/README.md) for fixture reference, endpoint testing patterns, custom fixtures, and troubleshooting.

---

## Deployment

> **Note:** The Render deployment is temporary and subject to change.

### Render (current)

The project deploys to [Render](https://render.com) as three services defined in `render.yaml`:

| Service | Type | Plan | Docker Target |
| --------- | ------ | ------ | --------------- |
| cubex-api | Web Service | Free | `api` |
| cubex-worker | Background Worker | Starter | `worker` |
| cubex-scheduler | Background Worker | Starter | `scheduler` |

**Pre-deploy command:** `pip install -r requirements.txt && alembic upgrade head`

**Auto-generated secrets** (via Render): `SESSION_SECRET_KEY`, `JWT_SECRET_KEY`, `OTP_HMAC_SECRET`, `INTERNAL_API_SECRET`, `ADMIN_PASSWORD`

**Manual secrets** (set in Render dashboard): `DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`, all Stripe keys, all OAuth keys, Brevo keys, Sentry DSN, Cloudinary keys.

### CI

GitHub Actions runs on every push/PR to `main` and `dev` in two stages:

1. **Lint** — Black (formatting) → Ruff (linting) → Pyright (type checking)
2. **Test** — Alembic migrations → full pytest suite with coverage

See `.github/workflows/ci.yml`.

---

## Contributing

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the full guide — branch naming, Conventional Commits format, code style (Black / Ruff / Pyright), pre-commit checks, testing requirements, PR process, and project conventions.

Quick start:

```bash
git checkout dev && git pull origin dev
git checkout -b feature/my-feature
# ... make changes ...
python manage.py precommit
git push origin feature/my-feature
# Open a PR targeting dev
```

---

## Security

See **[SECURITY.md](SECURITY.md)** for the vulnerability reporting policy, scope, and an inventory of security controls.

---

## License

> *(To be added)*

---

## Submodule Docs

Detailed documentation for specific subsystems:

- **[CueBX API Product](app/apps/cubex_api/README.md)** — Workspace endpoints, services, access guards, schemas, adding new features
- **[CueBX Career Product](app/apps/cubex_career/README.md)** — Career subscription endpoints, services, schemas, API vs Career comparison
- **[Messaging Infrastructure](app/infrastructure/messaging/README.md)** — RabbitMQ queues, retry strategies, DLQ, handlers, consumer setup
- **[Scheduler Infrastructure](app/infrastructure/scheduler/README.md)** — APScheduler jobs, job stores, standalone mode, Docker usage
- **[Database Migrations](migrations/README.md)** — Migration workflow, naming conventions, troubleshooting
- **[Test Suite](tests/README.md)** — Fixtures, endpoint testing guide, coverage, writing tests
- **[Contributing Guide](CONTRIBUTING.md)** — Git workflow, commit conventions, code style, PR process
- **[Security Policy](SECURITY.md)** — Vulnerability reporting, scope, security controls
- **[Architecture Decision Records](docs/adr/README.md)** — 8 ADRs documenting key technical choices (services, async DB, RabbitMQ, OTP hashing, Docker, quota cache, admin auth, module structure)
