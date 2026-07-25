import type { MetadataRoute } from "next"

import { SITE_URL } from "@/lib/seo/site"

// Public marketing routes only. This list is intentionally the same set as
// MARKETING_PATHS in next.config.mjs (the cacheable, prerendered pages) minus
// the /platform alias, which canonicalises to "/" and so is deliberately kept
// out of the sitemap to avoid submitting a duplicate URL.
//
// priority/changeFrequency are hints, not guarantees — Google largely ignores
// them, but a well-formed sitemap still accelerates discovery of every URL.
type Entry = {
  path: string
  priority: number
  changeFrequency: MetadataRoute.Sitemap[number]["changeFrequency"]
}

const ROUTES: Entry[] = [
  { path: "/", priority: 1.0, changeFrequency: "weekly" },
  { path: "/spectroscopy", priority: 0.9, changeFrequency: "monthly" },
  { path: "/regulatory-hub", priority: 0.9, changeFrequency: "monthly" },
  { path: "/reaction-optimization", priority: 0.9, changeFrequency: "monthly" },
  { path: "/integrations", priority: 0.8, changeFrequency: "monthly" },
  { path: "/pharmaceutical-rd", priority: 0.8, changeFrequency: "monthly" },
  { path: "/academic-research", priority: 0.8, changeFrequency: "monthly" },
  { path: "/cro-analytical", priority: 0.8, changeFrequency: "monthly" },
  { path: "/regulatory-affairs", priority: 0.8, changeFrequency: "monthly" },
  { path: "/about", priority: 0.7, changeFrequency: "monthly" },
  { path: "/blog", priority: 0.7, changeFrequency: "weekly" },
  { path: "/careers", priority: 0.5, changeFrequency: "monthly" },
  { path: "/contact", priority: 0.5, changeFrequency: "yearly" },
]

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date()
  return ROUTES.map(({ path, priority, changeFrequency }) => ({
    url: `${SITE_URL}${path === "/" ? "" : path}`,
    lastModified,
    changeFrequency,
    priority,
  }))
}
