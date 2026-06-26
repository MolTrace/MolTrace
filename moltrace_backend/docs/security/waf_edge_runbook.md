# WAF & edge abuse protection — runbook (Security Prompt 16)

## What is enforced in-app vs at the edge

P16's prompt asks for "per-tenant + per-route rate limits and quotas … and a WAF." Two layers, with
an **honest boundary**:

| Control | Where | Status |
|---|---|---|
| **Per-tenant + per-route rate limiting** | in-app (`src/nmrcheck/rate_limit.py`) | **Built + tested.** This is the real enforcement of "abusive traffic is throttled per tenant." |
| **Global request-body-size guard** | in-app (`rate_limit.py`, multipart exempt) | **Built + tested.** |
| **WAF** (OWASP CRS, IP reputation, bot/geo rules, L7 DDoS) | **network edge** | **Runbook only** — see below. |

A WAF is a **network-edge** control. Render (the backend host, `moltrace-backend.onrender.com`) has
**no built-in WAF**, and this codebase cannot configure edge infrastructure. Shipping an in-app
component named "WAF" would be dishonest, so the WAF is delivered as the operational runbook here; the
in-app rate limiter is the testable, in-repo enforcement.

## In-app rate limiter (the enforceable core)

- **Algorithm:** token bucket, O(1) memory/key. `capacity = limit × burst`, refill `limit / window`.
- **Key:** `system api key | admin` → unlimited; authenticated user → `user:{id}:{route}` (the
  per-user key *is* the per-tenant key today — the product is single-tenant-per-user and the request
  carries no org id); anonymous public route → `ip:{client_ip}:{route}`.
- **Policy:** tight limits on the unauthenticated auth endpoints (`/auth/login` 10/min, sign-up /
  reset 5/min, …); a generous `RATE_LIMIT_DEFAULT_PER_MINUTE` (300) elsewhere.
- **Response:** `429` with `Retry-After` + `X-RateLimit-Limit/Remaining/Window` (CORS-exposed).
- **Abuse signal:** each throttle emits a de-duplicated `SecurityEvent(event_type="rate_limit")`.
- **Settings (default-off so tests/dev are unaffected; on in `render.yaml`):** `RATE_LIMIT_ENABLED`,
  `RATE_LIMIT_DEFAULT_PER_MINUTE`, `RATE_LIMIT_BURST_MULTIPLIER`, `RATE_LIMIT_TRUST_FORWARDED_FOR`,
  `MAX_REQUEST_BODY_BYTES`.
- **Fail-open:** an internal limiter error never 500s a request; only an exceeded bucket raises 429.

### Single-worker caveat → shared store seam

Render runs **one uvicorn worker** (no `--workers` in `render.yaml`), so the in-process bucket store
is consistent for all traffic. The store sits behind a `RateLimitStore` protocol; **if the deploy
ever scales to multiple workers/instances, the in-process store becomes per-worker** (so the
effective limit multiplies by the worker count). The fix is to implement a Redis-backed
`RateLimitStore` (the project already has a `redis_url` setting for the RQ worker) and select it when
`redis_url` is set — a drop-in, no call-site changes. Until then, keep the backend single-worker, or
treat the edge WAF as the cross-instance limiter.

## Edge WAF — recommended configuration (operator runbook)

Put a WAF/CDN in front of the origins. Two viable options:

1. **Cloudflare (recommended)** — proxy `moltrace.co`, `www.moltrace.co`, and the API hostname
   through Cloudflare (orange-cloud). Enable: the **OWASP Core Rule Set** (managed WAF) in *block*
   mode after a short *log* tuning window; **rate limiting rules** (e.g. per-IP burst caps on
   `/auth/*`, complementing the in-app per-tenant limits); **Bot Fight Mode** / managed bot rules;
   **L7 DDoS** protection (on by default); and geo/ASN rules if the customer base is regional. Keep
   `RATE_LIMIT_TRUST_FORWARDED_FOR=true` so the in-app limiter keys on Cloudflare's `X-Forwarded-For`
   client IP (and restrict the origin to Cloudflare IP ranges so the header can't be spoofed direct).
2. **Vercel WAF** — for the Next.js frontend origin, enable Vercel's WAF / firewall rules + rate
   limiting for the marketing + app pages.

Because both platforms rebuild/serve from their own edge, the WAF rules live in those dashboards (or
their IaC: Cloudflare via Terraform `cloudflare_ruleset`, Vercel via project firewall config) — track
them as infrastructure, not in this repo.

## ASVS / OWASP API Top-10 alignment

See `owasp_api_top10_p16.md` for the item-by-item mapping (what P16 enforces, what prior prompts
already cover, what is edge/deferred). These controls **support** an ASVS-aligned posture; a formal
ASVS review + the edge WAF rollout are operator follow-ups.
