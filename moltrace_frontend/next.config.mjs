const rawBuildId =
  process.env.NEXT_PUBLIC_MOLTRACE_BUILD_ID ||
  process.env.MOLTRACE_BUILD_ID ||
  process.env.RENDER_GIT_COMMIT ||
  process.env.VERCEL_GIT_COMMIT_SHA ||
  process.env.COMMIT_SHA ||
  `local-${Date.now()}`

const moltraceBuildId = rawBuildId.replace(/[^a-zA-Z0-9._-]/g, "-").slice(0, 120)

/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  env: {
    NEXT_PUBLIC_MOLTRACE_BUILD_ID: moltraceBuildId,
  },
  generateBuildId: async () => moltraceBuildId,
  async headers() {
    const noStoreHeaders = [
      {
        key: "Cache-Control",
        value: "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
      },
      { key: "Pragma", value: "no-cache" },
      { key: "Expires", value: "0" },
    ]

    // ── Security response headers (Security Prompt 9 FE follow-up) ───────────
    // The backend API origin already emits HSTS + the X-* headers; the Next app
    // HTML origin emitted none. These apply to every app route (separate keys
    // from the Cache-Control rules above, so they never collide with the
    // MARKETING_PATHS cache logic — Next merges headers across matching rules).
    const isDev = process.env.NODE_ENV !== "production"

    // Direct (non-proxied) backend origin some flows may hit; same-origin
    // `/api/backend` calls are already covered by 'self'.
    const backendOrigin = "https://moltrace-backend.onrender.com"

    // Pragmatic Next.js-compatible CSP. Next injects inline bootstrap/hydration
    // <script>/<style>, so 'unsafe-inline' is required without a nonce pipeline;
    // dev additionally needs 'unsafe-eval' + ws: for React Refresh / HMR.
    // @vercel/analytics loads from same-origin (/_vercel/insights/*) → 'self'.
    const csp = [
      "default-src 'self'",
      `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self' data:",
      `connect-src 'self' ${backendOrigin}${isDev ? " ws: http://localhost:*" : ""}`,
      "worker-src 'self' blob:",
      "manifest-src 'self'",
      "frame-ancestors 'none'",
      "frame-src 'self'",
      "base-uri 'self'",
      "form-action 'self'",
      "object-src 'none'",
    ].join("; ")

    const securityHeaders = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      // The app is never meant to be framed; enforced now (belt for the CSP's
      // frame-ancestors, which rides Report-Only until validated).
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      // Belt-and-suspenders with the edge/CDN. Browsers honor a single HSTS
      // policy, so a duplicate from Vercel/Render (if any) is harmless.
      {
        key: "Strict-Transport-Security",
        value: "max-age=63072000; includeSubDomains; preload",
      },
      // SHIP REPORT-ONLY FIRST: browsers report violations to the console but do
      // NOT block, so this can't break Next's inline scripts/styles, Plotly,
      // charts, or embeds. Once the console is clean across authed pages, flip
      // this key to "Content-Security-Policy" to enforce.
      { key: "Content-Security-Policy-Report-Only", value: csp },
    ]

    // Public, statically-prerendered marketing pages. These carry no authed or
    // tenant-specific data — the same HTML is served to everyone — so they are
    // safe to cache at a shared CDN and (crucially) safe to keep bfcache-
    // eligible for instant back/forward navigation. `max-age=0` keeps the
    // browser always-revalidating on normal navigation (so content is never
    // stale on a fresh load), while `s-maxage`/`stale-while-revalidate` let an
    // edge cache absorb load. EVERY other route — and all of /api/backend —
    // stays `no-store` via the catch-all below.
    //
    // SECURITY: this list and the catch-all's negative-lookahead are derived
    // from the SAME array (MARKETING_PATHS) so they can never drift. Adding a
    // path here both (a) gives it the cacheable policy and (b) removes it from
    // the no-store catch-all — preventing a duplicate, conflicting
    // Cache-Control header. Do NOT add any authed/app route here.
    const MARKETING_PATHS = [
      "/",
      "/platform",
      "/spectroscopy",
      "/regulatory-hub",
      "/reaction-optimization",
      "/integrations",
      "/pharmaceutical-rd",
      "/academic-research",
      "/cro-analytical",
      "/regulatory-affairs",
      "/about",
      "/careers",
      "/blog",
      "/contact",
    ]

    const marketingCacheHeaders = [
      {
        key: "Cache-Control",
        value: "public, max-age=0, s-maxage=300, stale-while-revalidate=86400",
      },
    ]

    // Negative-lookahead fragment that removes the marketing paths from the
    // no-store catch-all. `:path` strips the leading slash, so "/" -> "" (an
    // empty path, matched by a bare `$`) and "/about" -> "about" (matched by an
    // anchored `about$`). Anchoring with `$` ensures we only exclude the exact
    // marketing page, never an app route that merely shares a prefix (e.g.
    // `/regulatory` stays no-store even though `/regulatory-affairs` is cached).
    const marketingExclusion = MARKETING_PATHS.map((p) =>
      p === "/" ? "$" : `${p.slice(1)}$`,
    ).join("|")

    return [
      // Security headers on every route. Distinct keys from the cache rules, so
      // both sets are emitted; safe on static assets (CSP/X-Frame are ignored on
      // non-document responses).
      {
        source: "/:path*",
        headers: securityHeaders,
      },
      {
        source: "/sw.js",
        headers: [
          ...noStoreHeaders,
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
      {
        source: "/manifest.webmanifest",
        headers: noStoreHeaders,
      },
      {
        source: "/manifest.json",
        headers: noStoreHeaders,
      },
      {
        source: "/icons/:path*",
        headers: noStoreHeaders,
      },
      {
        source: "/icon.svg",
        headers: noStoreHeaders,
      },
      {
        source: "/apple-icon.png",
        headers: noStoreHeaders,
      },
      {
        source: "/api/backend/:path*",
        headers: noStoreHeaders,
      },
      // Cacheable marketing pages. Must precede the no-store catch-all, and the
      // catch-all explicitly excludes these same paths (see marketingExclusion).
      ...MARKETING_PATHS.map((source) => ({
        source,
        headers: marketingCacheHeaders,
      })),
      {
        source: `/:path((?!_next/static|_next/image|icons/|favicon.ico|${marketingExclusion}|.*\\..*).*)`,
        headers: noStoreHeaders,
      },
    ]
  },
}

export default nextConfig
