# ADR-007: Stateless Admin Auth via HMAC Tokens

**Status:** Accepted
**Date:** 2025-02

## Context

The admin panel (`/admin`) needs authentication separate from the main user JWT flow. Requirements:

- Superuser-only access
- No additional database table for sessions
- Token should auto-invalidate when the admin changes their password
- Works with cookie-based session storage (Starlette `SessionMiddleware`)

## Decision

Use **HMAC-signed tokens** stored in the session cookie. The token format:

```text
<credentials_hash>:<version>:<timestamp>:<signature>
```

Where:

- `credentials_hash` = first 8 chars of SHA-256(email + hashed_password)
- `version` = current `ADMIN_TOKEN_VERSION` from settings (increment to revoke all admin sessions)
- `timestamp` = Unix epoch when the token was created
- `signature` = HMAC-SHA256(credentials_hash:version:timestamp, secret=SECRET_KEY)

**Verification flow:**

1. Extract token from session
2. Split into 4 parts, verify HMAC signature
3. Check `version` matches current `ADMIN_TOKEN_VERSION` setting
4. Check `timestamp` is within 24 h
5. Recompute `credentials_hash` from the current DB record
6. Compare — if the admin changed their password, `credentials_hash` diverges → token rejected

This gives us stateless verification (no session table) with automatic credential-change invalidation.

## Alternatives Considered

| Alternative | Why not |
| --- | --- |
| **Database-backed sessions** | Requires a sessions table, cleanup job, and DB hit on every admin page load |
| **JWT** | JWTs can't be invalidated before expiry without a blocklist (which re-introduces server state) |
| **Reuse user auth** | User auth uses short-lived access + refresh tokens; admin sessions need longer-lived cookie flow for form-based UI |
| **OAuth / third-party** | Over-engineered for a single-user admin panel |

## Consequences

**Positive:**

- Zero additional DB tables; verification is pure computation
- Automatic invalidation on password change (credential hash changes)
- 24 h expiry limits window of a stolen session cookie
- Simple implementation — ~50 lines of utility code

**Negative:**

- Can't revoke an *individual* token before expiry, but all admin sessions can be revoked by incrementing `ADMIN_TOKEN_VERSION` (lighter-weight than rotating `SECRET_KEY`)
- Session cookie size increases slightly (~120 bytes for the token)
- Relies on `SECRET_KEY` staying secret; if leaked, tokens can be forged
