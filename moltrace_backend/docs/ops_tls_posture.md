# Ops — TLS / Transport Security Posture (Security Prompt 9)

What the application enforces in code, and what the deployment edge must enforce, to reach an
SSL Labs / securityheaders.com **A+** posture.

## Enforced in application code (this prompt)

The response middleware emits, on every response:

| Header | Value | Notes |
|---|---|---|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | **HTTPS only** — emitted when `X-Forwarded-Proto: https` (the TLS-terminating edge) or the request is already https. Configurable via `HSTS_*` env. 2-year max-age + `preload` meets the hstspreload.org bar. |
| `X-Content-Type-Options` | `nosniff` | always |
| `X-Frame-Options` | `DENY` | always — API responses are never framed |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | always |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` | always — deny powerful features by default |

HSTS is deliberately **not** sent over plain HTTP, so local dev and health probes are unaffected;
browsers only honour HSTS over HTTPS anyway.

### Configuration (env)

- `HSTS_ENABLED` (default `true`)
- `HSTS_MAX_AGE_SECONDS` (default `63072000` = 2 years)
- `HSTS_INCLUDE_SUBDOMAINS` (default `true`)
- `HSTS_PRELOAD` (default `true`)

Before submitting the apex domain to the browser **preload list** (hstspreload.org), confirm every
subdomain is HTTPS-capable — preload is hard to reverse.

## Enforced at the edge (deployment / infra — not application code)

TLS termination, cipher policy, and certificate lifecycle live at the platform edge (Render /
CDN), not in this FastAPI process:

1. **TLS 1.3 + modern ciphers** — the edge must negotiate TLS 1.3 (TLS 1.2 only with AEAD
   suites), disable TLS ≤1.1, and prefer forward-secret suites. Target SSL Labs **A+**.
2. **Certificate issuance / rotation** — managed automatically by the platform (ACME / Let's
   Encrypt on Render). No private keys in the app or repo. Document the renewal owner + alerting.
3. **HSTS at the edge (optional belt-and-suspenders)** — the app already emits HSTS on HTTPS; the
   edge may also add it. Avoid emitting it twice with conflicting directives.
4. **Verify** — run an SSL Labs scan (or `testssl.sh`) against the production host after any edge
   change; keep the report with the release evidence. Target grade A+.

## mTLS for service-to-service (documented seam — not live in v1)

MolTrace runs as a single FastAPI service today, so there is no internal service-to-service hop
to mutually authenticate yet. When the platform grows to multiple internal services (worker mesh,
sidecars), enforce **mTLS** between them:

- Issue short-lived client + server certs from an internal CA (e.g. a service mesh — Linkerd /
  Istio — or SPIFFE/SPIRE workload identities), rotated automatically.
- Each service presents and verifies a peer certificate; reject unauthenticated internal calls.
- The application code change at that point is to require/verify the client cert (or trust the
  mesh's mTLS) on internal endpoints — a small, contained addition behind this documented seam.

Until then, internal calls are in-process (no network hop), so mTLS is N/A; this section is the
adoption runbook for when the topology changes.
