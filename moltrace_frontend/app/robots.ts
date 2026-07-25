import type { MetadataRoute } from "next"

import { SITE_URL } from "@/lib/seo/site"

// App / authenticated / API surfaces that must never be indexed. These are the
// non-marketing route roots under app/. Keeping this list explicit (rather than
// a broad allow-nothing) means the public marketing pages stay fully crawlable
// while tenant data, auth flows, and the API proxy stay out of the index.
const DISALLOW = [
  "/api/",
  "/api-test/",
  "/dashboard/",
  "/admin/",
  "/ai/",
  "/ml/",
  "/knowledge/",
  "/compounds/",
  "/batches/",
  "/reactions/",
  "/projects/",
  "/reports/",
  "/review/",
  "/roi/",
  "/validation/",
  "/validation-center/",
  "/spectracheck/",
  "/regulatory/",
  "/settings/",
  "/auth/",
  "/login/",
  "/sign-in/",
  "/sign-up/",
  "/mobile/",
  "/offline/",
]

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: DISALLOW,
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  }
}
