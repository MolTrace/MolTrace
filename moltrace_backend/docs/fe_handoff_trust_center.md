# FE handoff — Trust Center page (+ outstanding security-surface items)

**Security Prompt 22** (with two small follow-ons from **P17** and **P16**). This is the
FE-side work left over from the backend security series — the customer-facing pieces the
backend can't publish itself.

> **No API contract change. No `schema.d.ts` regeneration needed.** Nothing here adds or
> alters an endpoint — item 1 is content publishing, item 2 is a static file, item 3 is
> optional error-handling polish.

---

## 1. Publish the Trust Center page (primary)

**Source content:** [`docs/security/trust_center.md`](security/trust_center.md) — treat it
as the source of truth and mirror it; don't invent new copy.

**Build:** a marketing page (suggested route `/trust`, or fold into the existing
`/security` surface if one exists) rendering four sections from that file:

1. **Certifications & framework status** — the table (SOC 2 Type II · ISO/IEC 27001:2022 ·
   27017/27018 · Part 11/GAMP 5/ALCOA+ · GDPR) with their status column.
2. **Security posture at a glance** — the five grouped bullets (Access · Data protection ·
   Integrity & traceability · Detection & response · Secure delivery · Resilience).
3. **Sub-processor register** — the 5-row table (Render · Vercel · customer-configured IdP ·
   GitHub · optional hosted SIEM/paging) with Purpose / Data handled / Region-notes.
4. **Requesting trust artifacts** — the contact + disclosure path (link `SECURITY.md` and
   `/.well-known/security.txt`).

**Placement:** link it from the **footer** (legal/security cluster) — per the
"integrate, don't clutter" rule, do **not** add a new top-level nav item.

### ⚠️ Non-negotiable copy constraints

This page is the highest-risk surface for a compliance overclaim. Preserve verbatim:

- **"designed to support"** framing for SOC 2 / ISO 27001 / Part 11 / GxP / GDPR — never
  "compliant", "certified", or "achieved".
- The explicit line: **"MolTrace does not currently hold a SOC 2 report or an ISO 27001
  certificate."** SOC 2 is **not held**.
- ISO 27017/27018 are **extensions** that would accompany an ISO 27001 certification — not
  standalone certifications.
- Sub-processor rows must stay factually identical to the source table (they're contractual;
  customers are notified of material changes per their DPA).

This matches the hedging already applied across the ~12 marketing pages, the footer, and
the whitepapers — keep new copy consistent with it.

### Keeping it in sync

`docs/security/trust_center.md` is the in-repo source; the backend
[`compliance/controls.json`](../../compliance/controls.json) register (machine-validated in
CI) backs the framework-status claims. When the backend adds a control or a sub-processor
changes, the doc updates first — re-sync the page from it.

---

## 2. Serve `/.well-known/security.txt` at the apex (P17 follow-on)

The backend now serves an RFC 9116 `security.txt` **on the API origin**
(`GET /.well-known/security.txt`). For researchers to discover it, the **apex
`moltrace.co`** should serve it too — that's the FE/Vercel origin.

**Options (either is fine):**
- a static `public/.well-known/security.txt` on the FE, or
- a Vercel rewrite/proxy of `/.well-known/security.txt` → the backend route (keeps a single
  source; the backend computes a never-stale `Expires`).

Must be served as `text/plain; charset=utf-8` over HTTPS at exactly that path. See
[`docs/security/vulnerability_disclosure_policy.md`](security/vulnerability_disclosure_policy.md).

---

## 3. (Optional) Surface rate-limit responses (P16 follow-on)

The API can return **`429`** with **`Retry-After`** and `X-RateLimit-Limit` /
`-Remaining` / `-Window` (all CORS-exposed). Today the FE's generic error handling covers
this adequately — this is polish, not required:

- on a `429`, show "Too many requests — try again in ~N seconds" using `Retry-After`
  rather than a generic error;
- optionally back off/disable the submit control for that window.

Rate limiting is **default-off** outside production, so this is hard to exercise locally
unless `RATE_LIMIT_ENABLED=true`.

---

## Verification

1. `/trust` renders all four sections; the sub-processor table matches the source file.
2. Grep the built page for forbidden strings — `SOC 2 compliant`, `SOC 2 certified`,
   `ISO 27001 certified`, `is certified` — should return **nothing**; the
   "does not currently hold" line **is** present.
3. `curl -sI https://moltrace.co/.well-known/security.txt` → `200`,
   `content-type: text/plain; charset=utf-8`.
4. Footer links to `/trust`; no new top-level nav entry.
