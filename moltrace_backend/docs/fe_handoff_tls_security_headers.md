# FE Handoff — Security Prompt 9: TLS / security headers

**TL;DR: no frontend code action required.** The backend now emits standard security response
headers (HSTS on HTTPS, plus `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
`Permissions-Policy`). No route, request/response model, status code, or `schema.d.ts` contract
changed. `/openapi.json` is unchanged.

## What changed (backend / edge only)

- Every API response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: geolocation=(),
  microphone=(), camera=()`.
- `Strict-Transport-Security` (HSTS, 2-year + preload) is emitted **only over HTTPS** (it keys off
  `X-Forwarded-Proto`), so local plain-HTTP dev is unaffected.

## Two things for the FE to be aware of (not code changes)

1. **`X-Frame-Options: DENY` on API responses** — this applies to the **API backend**, which is
   never framed, so it does not affect the Next.js app. If the FE ever needs to embed a backend
   response in an iframe (it does not today), flag it.
2. **The FE's own HTML security headers (CSP, X-Frame-Options on the app pages) remain
   FE/Next.js-owned** — this prompt hardened the API backend only. A strong **Content-Security-
   Policy** for the application HTML is a separate FE task (the backend serves JSON, where CSP adds
   little). Consider adding CSP + frame-ancestors in the Next.js config / hosting headers to round
   out the securityheaders.com A+ grade for the app origin.

## Verification

- `schema.d.ts`: **do not regenerate** — `/openapi.json` unchanged.
- Backend suite green incl. `tests/test_security_headers.py`.

No required FE checklist items; item 2 above is an optional FE follow-up for the app origin's CSP.
