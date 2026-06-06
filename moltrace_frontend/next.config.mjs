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
