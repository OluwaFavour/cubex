# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in CueBX, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to report

Send an email to the project maintainer with:

1. **Description** of the vulnerability
2. **Steps to reproduce** (as detailed as possible)
3. **Impact assessment** — what an attacker could do
4. **Affected component** (e.g., auth, payments, messaging)

### What to expect

- **Acknowledgement** within 48 hours
- **Assessment** and severity classification within 1 week
- **Fix timeline** communicated once the issue is verified
- **Credit** in the fix commit (unless you prefer anonymity)

## Scope

The following areas are in scope for security reports:

| Area | Examples |
| ------ | ---------- |
| **Authentication** | JWT bypass, OTP brute force, OAuth state fixation |
| **Authorization** | Workspace role escalation, accessing other users' data |
| **Payments** | Stripe webhook forgery, subscription manipulation |
| **Data exposure** | PII leaks, API key exposure in logs or responses |
| **Injection** | SQL injection, template injection |
| **Infrastructure** | RabbitMQ message poisoning, Redis command injection |
| **Secrets** | Hardcoded credentials, insecure defaults in production |

## Out of Scope

- Denial of service (rate limiting is already in place)
- Issues in third-party dependencies (report upstream; mention to us if critical)
- Self-XSS or issues requiring physical device access

## Security Measures in Place

This project implements the following security controls:

- **Passwords** — bcrypt hashed with random salt
- **OTPs** — HMAC-SHA256 hashed, rate-limited (5 max attempts), short-lived (10 min)
- **JWT** — signed with HS256, 15-minute access tokens, refresh token rotation
- **API keys** — HMAC-SHA256 hashed, never stored in plaintext
- **Admin auth** — HMAC-signed stateless tokens with 24h expiry, auto-invalidated on password change
- **Stripe webhooks** — signature verification on every event
- **Internal API** — separate `X-Internal-API-Key` header for service-to-service calls
- **Rate limiting** — per-IP, per-user, per-endpoint, per-email (pluggable memory/Redis backends)
- **Production startup validation** — app refuses to start with default secrets when `ENVIRONMENT=production`
- **Docker** — non-root user (`appuser`), no cache dirs, minimal base image
- **Constant-time comparisons** — `hmac.compare_digest()` used for all secret comparisons
- **Soft delete** — user data retained for 30 days before permanent deletion (scheduled cleanup)
