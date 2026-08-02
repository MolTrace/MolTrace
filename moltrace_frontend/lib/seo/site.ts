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

/**
 * The single string Google quotes back. Verified 2026-08-02: a live AI Overview
 * for "moltrace platform" paraphrased this description almost verbatim.
 *
 * Two constraints follow from that, and both are load-bearing:
 *  1. KEEP IT UNDER ~160 CHARACTERS. The previous 188-character version had its
 *     tail trimmed, which silently dropped regulatory intelligence — one of the
 *     three modules vanished from the summary.
 *  2. FRONT-LOAD ALL THREE CAPABILITIES, and name every audience the product
 *     actually serves. The old copy said "pharmaceutical R&D" only, and the AI
 *     Overview duly reported the product as being for pharma alone.
 */
export const SITE_DESCRIPTION =
  "MolTrace is the audit-ready evidence engine for academic, chemical and pharmaceutical R&D — NMR/MS interpretation, impurity profiling, reaction optimization."
