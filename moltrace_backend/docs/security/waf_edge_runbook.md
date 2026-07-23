# WAF & edge abuse protection — runbook (Security Prompt 16)

## What is enforced in-app vs at the edge

P16's prompt asks for "per-tenant + per-route rate limits and quotas … and a WAF." Two layers, with
an **honest boundary**:

| Control | Where | Status |
|---|---|---|
| **Per-tenant + per-route rate limiting** | in-app (`src/nmrcheck/rate_limit.py`) | **Built + tested** — the real enforcement of "abusive traffic is throttled per tenant," but the buckets are **per Cloud Run instance**, so the effective limit is looser than configured. See the known limitation below. |
| **Global request-body-size guard** | in-app (`rate_limit.py`, multipart exempt) | **Built + tested.** |
| **WAF** (OWASP CRS, IP reputation, bot/geo rules, L7 DDoS) | **network edge** | **Runbook only — not enabled.** Google Cloud Armor is the native option on the current host; see below. |

A WAF is a **network-edge** control. The backend runs on **Google Cloud Run** (service
`moltrace-backend`, project `moltrace-prod`, region `us-central1`); Cloud Run has **no WAF of its
own**, and the native edge-WAF option — **Google Cloud Armor** — is **available but not currently
enabled**. This codebase cannot configure edge infrastructure. Shipping an in-app component named
"WAF" would be dishonest, so the WAF is delivered as the operational runbook here; the in-app rate
limiter is the testable, in-repo enforcement.

What the platform *does* already give the edge, absent a WAF: the Cloud Run service is the **only**
internet-reachable component. Cloud SQL for PostgreSQL 16 sits on a **private IP** reached over
**Direct VPC egress** with no public endpoint, secrets come from **Secret Manager** and the
field-encryption key from **Cloud KMS**, and the raw-data vault is **Cloud Storage** (not a public
bucket). Managed TLS terminates at the Google front end. So the exposed attack surface a WAF would
protect is the HTTP API alone — the datastore is not internet-addressable. Deploys are keyless
(**Workload Identity Federation**, no long-lived deploy credential to steal), which removes a
supply-chain path to the edge but is not itself a traffic control.

## In-app rate limiter (the enforceable core)

- **Algorithm:** token bucket, O(1) memory/key. `capacity = limit × burst`, refill `limit / window`.
- **Key:** `system api key | admin` → unlimited; authenticated user → `user:{id}:{route}` (the
  per-user key *is* the per-tenant key today — the product is single-tenant-per-user and the request
  carries no org id); anonymous public route → `ip:{client_ip}:{route}`.
- **Policy:** tight limits on the unauthenticated auth endpoints (`/auth/login` 10/min, sign-up /
  reset 5/min, …); a generous `RATE_LIMIT_DEFAULT_PER_MINUTE` (300) elsewhere.
- **Response:** `429` with `Retry-After` + `X-RateLimit-Limit/Remaining/Window` (CORS-exposed).
- **Abuse signal:** each throttle emits a de-duplicated `SecurityEvent(event_type="rate_limit")`.
- **Settings (default-off so tests/dev are unaffected; set on the Cloud Run service via
  `--set-env-vars`):** `RATE_LIMIT_ENABLED`, `RATE_LIMIT_DEFAULT_PER_MINUTE`,
  `RATE_LIMIT_BURST_MULTIPLIER`, `RATE_LIMIT_TRUST_FORWARDED_FOR`, `MAX_REQUEST_BODY_BYTES`.
- **Fail-open:** an internal limiter error never 500s a request; only an exceeded bucket raises 429.

### KNOWN LIMITATION — the in-process store is per-instance on Cloud Run

**This is a real correctness gap today, not a theoretical one.** The limiter's bucket store is
in-process, and Cloud Run is deployed with `--concurrency 80 --min-instances 0 --max-instances 2`
(see [`deploy/README.md`](../../deploy/README.md)). Consequences:

- **The effective rate limit can be up to 2× the configured value.** Each container instance keeps
  its own bucket map, and Cloud Run's load balancer spreads requests across them, so with two
  instances live a client can consume two independent buckets. `/auth/login` at a configured 10/min
  can admit up to ~20/min; the 300/min default up to ~600/min. (Within a single instance the limit
  is exact: the container runs **one** uvicorn worker — no `--workers` in `moltrace_backend/Dockerfile`
  — so the multiplier is bounded by instance count, not worker count.)
- **Per-instance state is lost on scale-to-zero.** With `--min-instances 0` the service idles down to
  no instances; every bucket is discarded and a returning client starts from a full bucket. A slow
  attacker pacing requests around the idle window can therefore evade the sustained limit entirely.
- **Scope of the impact.** This weakens *throttling ratios*, not authentication or authorization —
  every other gate (authz, MFA/step-up, audit) is DB-backed and unaffected. The limiter still blunts
  fast credential-stuffing bursts; it just does so at a looser effective rate than configured.

**The close-out is already designed in.** `rate_limit.py` puts the store behind a `RateLimitStore`
protocol (`consume` / `should_emit`), with `InProcessTokenBucketStore` as the current implementation.
Implementing a Redis-backed `RateLimitStore` and selecting it when `redis_url` is set is a drop-in —
no call-site changes — and makes the buckets shared and durable across instances and scale-to-zero.
That work is **blocked on Redis being deployed**: Memorystore is deliberately deferred (the RQ worker
is likewise not deployed), so there is no shared store to point at yet.

**Interim mitigations (operator choice):** set `--max-instances 1` to make the limit exact (at the
cost of headroom); and/or configure the limits at half their intended ceiling to absorb the 2×; and/or
enable Cloud Armor rate-limiting rules (below), which enforce at the edge *before* traffic is split
across instances and are the only cross-instance throttle available today.

## Edge WAF — recommended configuration (operator runbook)

**No WAF is enabled today.** Put one in front of the origins. Three viable options, in order of fit:

1. **Google Cloud Armor (primary — native to the current host).** Cloud Run's edge-WAF option.
   Cloud Armor attaches to a **global external Application Load Balancer**, so the rollout is: put an
   HTTPS LB in front of the `moltrace-backend` Cloud Run service (serverless NEG backend), attach a
   Cloud Armor **security policy**, then set the service to `--ingress internal-and-cloud-load-balancing`
   so the `run.app` URL can't be hit directly and bypass the policy. In the policy enable: the
   **preconfigured OWASP CRS rule sets** (`sqli-v33-stable`, `xss-v33-stable`, `lfi`, `rfi`,
   `rce`, `scannerdetection`, `protocolattack`, `sessionfixation`) at a tuned sensitivity, run in
   **preview mode** first and promote to *deny* after a short tuning window; **rate-limiting rules**
   (`rate_based_ban` / `throttle`, e.g. per-IP burst caps on `/auth/*`) — note these are the only
   cross-instance throttle available while the in-app limiter is per-instance (see the known
   limitation above); **Adaptive Protection** for L7 DDoS; **named IP lists / geo (`origin.region_code`)
   expressions** if the customer base is regional; and **reCAPTCHA/bot management** rules if scraping
   becomes an issue. Keep `RATE_LIMIT_TRUST_FORWARDED_FOR=true` so the in-app limiter keys on the LB's
   `X-Forwarded-For` client IP — the LB-only ingress setting is what stops that header being spoofed
   by a direct-to-origin request.
2. **Cloudflare (alternative / multi-origin).** Proxy `moltrace.co`, `www.moltrace.co`, and the API
   hostname through Cloudflare (orange-cloud). Enable: the **OWASP Core Rule Set** (managed WAF) in
   *block* mode after a short *log* tuning window; **rate limiting rules** (e.g. per-IP burst caps on
   `/auth/*`, complementing the in-app per-tenant limits); **Bot Fight Mode** / managed bot rules;
   **L7 DDoS** protection (on by default); and geo/ASN rules if the customer base is regional. Keep
   `RATE_LIMIT_TRUST_FORWARDED_FOR=true` so the in-app limiter keys on Cloudflare's `X-Forwarded-For`
   client IP (and restrict the origin — Cloud Run ingress + Cloudflare IP ranges — so the header can't
   be spoofed direct). Useful if one WAF should cover the Vercel frontend and the Cloud Run API alike.
3. **Vercel WAF** — for the Next.js frontend origin (`moltrace.co`), enable Vercel's WAF / firewall
   rules + rate limiting for the marketing + app pages. This covers the frontend only; it is
   complementary to 1 or 2, not a substitute for protecting the API origin.

Because all three platforms serve from their own edge, the WAF rules live in those consoles (or their
IaC: Cloud Armor via `gcloud compute security-policies` / Terraform `google_compute_security_policy`,
Cloudflare via Terraform `cloudflare_ruleset`, Vercel via project firewall config) — track them as
infrastructure, not in this repo.

## ASVS / OWASP API Top-10 alignment

See `owasp_api_top10_p16.md` for the item-by-item mapping (what P16 enforces, what prior prompts
already cover, what is edge/deferred). These controls **support** an ASVS-aligned posture; a formal
ASVS review, the Cloud Armor rollout, and the shared (Redis-backed) `RateLimitStore` are the open
operator follow-ups.
