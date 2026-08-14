import type { MetadataRoute } from "next"

import { SITE_URL } from "@/lib/seo/site"

// App / authenticated / API surfaces that must never be indexed. These are the
// non-marketing route roots under app/. Keeping this list explicit (rather than
// a broad allow-nothing) means the public marketing pages stay fully crawlable
// while tenant data, auth flows, and the API proxy stay out of the index.
//
// NO TRAILING SLASHES, and that is the entire point of the entry format. Robots
// exclusion is prefix matching (RFC 9309): "Disallow: /reports/" matches
// /reports/anything but NOT /reports itself — and /reports is the form that
// actually serves, because Next 308-redirects the trailing-slash URL to the bare
// path. With the old trailing-slash list, every route ROOT here — including
// /sign-in and /sign-up, which the homepage links directly — was crawlable and
// carried the root layout's "index, follow" meta, the exact opposite of this
// comment's promise. "/reports" covers both /reports and /reports/*.
//
// /regulatory is the one entry that CANNOT be bare: as a prefix it would also
// swallow the marketing pages /regulatory-hub and /regulatory-affairs. It gets
// the "$"-anchored pair instead — "/regulatory$" for the exact root (honoured by
// Google and Bing; crawlers that treat "$" literally simply no-match it, which
// fails open to crawlable) and "/regulatory/" for everything beneath it.
const DISALLOW = [
  "/api",
  "/api-test",
  "/dashboard",
  "/admin",
  "/ai",
  "/ml",
  "/knowledge",
  "/compounds",
  "/batches",
  "/reactions",
  "/projects",
  "/reports",
  "/review",
  "/roi",
  "/validation",
  "/validation-center",
  "/spectracheck",
  "/regulatory$",
  "/regulatory/",
  "/settings",
  "/auth",
  "/login",
  "/sign-in",
  "/sign-up",
  "/mobile",
  "/offline",
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
