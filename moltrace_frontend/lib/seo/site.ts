/**
 * Single source of truth for the public site origin used across SEO surfaces
 * (metadataBase, canonicals, sitemap, robots, JSON-LD). Overridable per
 * environment via NEXT_PUBLIC_SITE_URL; defaults to the production apex.
 *
 * Must be an absolute origin with no trailing slash.
 */
export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://moltrace.co"
).replace(/\/+$/, "")

export const SITE_NAME = "MolTrace"

export const SITE_TAGLINE = "AI-Native Scientific Intelligence Platform"

export const SITE_DESCRIPTION =
  "MolTrace is the audit-ready evidence engine for pharmaceutical R&D — AI-powered spectroscopy interpretation, reaction optimization, and regulatory intelligence for chemistry and R&D teams."
