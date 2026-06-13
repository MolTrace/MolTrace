/**
 * MolTrace UI design system — visual regression baseline routes.
 *
 * One entry per static (non-dynamic) reskinned surface, grouped by module
 * accent color. Dynamic routes ([id], [tenantId], etc.) are excluded — they
 * require seeded data to reliably capture.
 *
 * To add a new route after a reskin: append to the appropriate group with a
 * descriptive `name` (used as the screenshot filename) and the path.
 *
 * To re-capture: pnpm visual:baseline
 * To diff later: re-run, then visually compare with the previous capture.
 */

export type Route = {
  /** Filename-safe key. Becomes <name>.png in the screenshots dir. */
  name: string
  /** Path under localhost:3000. */
  path: string
  /** Module accent the surface uses. Informational only. */
  accent: "teal" | "cyan" | "violet" | "slate" | "mixed"
}

export const ROUTES: Route[] = [
  // Marketing / auth (no accent — pre-shell surfaces)
  { name: "00-root", path: "/", accent: "mixed" },
  { name: "01-sign-in", path: "/sign-in", accent: "mixed" },
  { name: "02-sign-up", path: "/sign-up", accent: "mixed" },

  // Dashboard + cross-cutting (teal)
  { name: "10-dashboard", path: "/dashboard", accent: "teal" },
  { name: "11-projects", path: "/projects", accent: "teal" },
  { name: "12-actions", path: "/actions", accent: "teal" },
  { name: "13-reports", path: "/reports", accent: "teal" },
  { name: "14-review-queue", path: "/review", accent: "teal" },
  { name: "15-platform", path: "/platform", accent: "teal" },

  // SpectraCheck (teal)
  { name: "20-spectracheck", path: "/spectracheck", accent: "teal" },
  { name: "21-spectroscopy", path: "/spectroscopy", accent: "teal" },

  // Compounds + Batches (teal)
  { name: "30-compounds", path: "/compounds", accent: "teal" },
  { name: "31-batches", path: "/batches", accent: "teal" },

  // Reactions (violet)
  { name: "40-reactions", path: "/reactions", accent: "violet" },
  { name: "41-reactions-studio", path: "/reactions/studio", accent: "violet" },

  // ComplianceCore (cyan)
  { name: "50-regulatory", path: "/regulatory", accent: "cyan" },
  { name: "51-regulatory-action-queue", path: "/regulatory/action-queue", accent: "cyan" },
  { name: "52-regulatory-notifications", path: "/regulatory/notifications", accent: "cyan" },
  { name: "53-regulatory-rule-updates", path: "/regulatory/rule-updates", accent: "cyan" },
  { name: "54-regulatory-sources", path: "/regulatory/sources", accent: "cyan" },
  { name: "55-regulatory-surveillance", path: "/regulatory/surveillance", accent: "cyan" },

  // Validation (cyan)
  { name: "60-validation", path: "/validation", accent: "cyan" },
  { name: "61-validation-center", path: "/validation-center", accent: "cyan" },
  { name: "62-validation-center-projects", path: "/validation-center/projects", accent: "cyan" },
  { name: "63-validation-center-releases", path: "/validation-center/releases", accent: "cyan" },
  { name: "64-validation-center-traceability", path: "/validation-center/traceability", accent: "cyan" },
  { name: "65-validation-center-data-integrity", path: "/validation-center/data-integrity", accent: "cyan" },
  { name: "66-validation-center-deviations", path: "/validation-center/deviations", accent: "cyan" },
  { name: "67-validation-center-capa", path: "/validation-center/capa", accent: "cyan" },
  { name: "68-validation-center-esignatures", path: "/validation-center/esignatures", accent: "cyan" },
  { name: "69-validation-center-controlled-records", path: "/validation-center/controlled-records", accent: "cyan" },
  { name: "6a-validation-center-inspection-package", path: "/validation-center/inspection-package", accent: "cyan" },

  // ML Model Factory (teal)
  { name: "70-ml", path: "/ml", accent: "teal" },
  { name: "71-ml-calibration", path: "/ml/calibration", accent: "teal" },
  { name: "72-ml-deployment-candidates", path: "/ml/deployment-candidates", accent: "teal" },
  { name: "73-ml-error-analysis", path: "/ml/error-analysis", accent: "teal" },
  { name: "74-ml-evaluations", path: "/ml/evaluations", accent: "teal" },
  { name: "75-ml-models", path: "/ml/models", accent: "teal" },
  { name: "76-ml-ood", path: "/ml/ood", accent: "teal" },
  { name: "77-ml-training", path: "/ml/training", accent: "teal" },

  // AI (teal)
  { name: "80-ai", path: "/ai", accent: "teal" },
  { name: "81-ai-active-learning", path: "/ai/active-learning", accent: "teal" },
  { name: "82-ai-canary", path: "/ai/canary", accent: "teal" },
  { name: "83-ai-monitoring", path: "/ai/monitoring", accent: "teal" },
  { name: "84-ai-predictions", path: "/ai/predictions", accent: "teal" },
  { name: "85-ai-services", path: "/ai/services", accent: "teal" },
  { name: "86-ai-shadow-evaluations", path: "/ai/shadow-evaluations", accent: "teal" },

  // Knowledge Library (teal)
  { name: "90-knowledge", path: "/knowledge", accent: "teal" },
  { name: "91-knowledge-analytical", path: "/knowledge/analytical", accent: "teal" },
  { name: "92-knowledge-datasets", path: "/knowledge/datasets", accent: "teal" },
  { name: "93-knowledge-extractions", path: "/knowledge/extractions", accent: "teal" },
  { name: "94-knowledge-model-improvement", path: "/knowledge/model-improvement", accent: "teal" },
  { name: "95-knowledge-reactions", path: "/knowledge/reactions", accent: "teal" },
  { name: "96-knowledge-regulatory", path: "/knowledge/regulatory", accent: "teal" },
  { name: "97-knowledge-review", path: "/knowledge/review", accent: "teal" },
  { name: "98-knowledge-sources", path: "/knowledge/sources", accent: "teal" },

  // Automation ROI (violet)
  { name: "a0-roi", path: "/roi", accent: "violet" },

  // Settings (slate)
  { name: "b0-settings-methods", path: "/settings/methods", accent: "slate" },
  { name: "b1-settings-connectors", path: "/settings/connectors", accent: "slate" },
  { name: "b2-settings-instrument-watch", path: "/settings/instrument-watch", accent: "slate" },
  { name: "b3-settings-mapping-templates", path: "/settings/mapping-templates", accent: "slate" },
  { name: "b4-settings-team", path: "/settings/team", accent: "slate" },
  { name: "b5-settings-deployment", path: "/settings/deployment", accent: "slate" },

  // Admin (slate)
  { name: "c0-admin-system", path: "/admin/system", accent: "slate" },
  { name: "c1-admin-security", path: "/admin/security", accent: "slate" },
  { name: "c2-admin-audit", path: "/admin/audit", accent: "slate" },
  { name: "c3-admin-debug", path: "/admin/debug", accent: "slate" },
  { name: "c4-admin-feature-flags", path: "/admin/feature-flags", accent: "slate" },
  { name: "c5-admin-ingestion", path: "/admin/ingestion", accent: "slate" },
  { name: "c6-admin-tenants", path: "/admin/tenants", accent: "slate" },
  { name: "c7-admin-tenant-summary", path: "/admin/tenant-summary", accent: "slate" },
]
