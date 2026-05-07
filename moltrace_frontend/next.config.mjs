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
      {
        source: "/:path((?!_next/static|_next/image|icons/|favicon.ico|.*\\..*).*)",
        headers: noStoreHeaders,
      },
    ]
  },
}

export default nextConfig
