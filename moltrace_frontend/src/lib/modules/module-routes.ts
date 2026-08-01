/**
 * ONE route→product map for the whole app.
 *
 * Navigation is defined in four places (the sidebar, MobileBottomNav, the command palette in
 * app-topbar, and a second shell in components/app-shell) and they WILL drift if each gates
 * itself. Every surface should ask this module which product a route belongs to, so adding a
 * route means editing one table.
 *
 * `null` means "not product-specific" — shared surfaces (dashboard, settings, admin) stay visible
 * on every deployment.
 */

/** Product keys as the server reports them in `GET /system/capabilities`. */
export const MODULE_KEYS = ["spectracheck", "regulatory_hub", "reaction_optimization"] as const
export type ModuleKey = (typeof MODULE_KEYS)[number]

export function isModuleKey(v: unknown): v is ModuleKey {
  return typeof v === "string" && (MODULE_KEYS as readonly string[]).includes(v)
}

/**
 * Route prefix → owning product. Longest prefix wins, so a more specific entry can override a
 * broader one.
 *
 * `/review` and `/reports` sit in generic nav groups but are SpectraCheck-only surfaces — a
 * Regentry-only buyer would otherwise get two permanently empty top-level items.
 */
const ROUTE_MODULE_PREFIXES: ReadonlyArray<readonly [string, ModuleKey]> = [
  ["/spectracheck", "spectracheck"],
  ["/review", "spectracheck"],
  ["/reports", "spectracheck"],
  ["/compounds", "spectracheck"],
  ["/regulatory", "regulatory_hub"],
  ["/actions", "regulatory_hub"],
  ["/reactions", "reaction_optimization"],
  // NOT /projects. It is a Workspace item, it reads the plain /projects list, and a SpectraCheck
  // session carries a project_id — so SpectraCheck needs it. Repho's own projects are
  // /reaction-projects, which live under /reactions. Mapping it here hid a page the customer
  // depends on, and once the route guard exists it would have turned that into a hard wall.
]

/**
 * Which product owns this route, or null when it is shared.
 *
 * Matches on path segments, so `/reviewer-notes` never matches `/review`.
 */
export function moduleForRoute(href: string): ModuleKey | null {
  const path = (href || "").split(/[?#]/)[0]!.replace(/\/+$/, "") || "/"
  let best: readonly [string, ModuleKey] | null = null
  for (const entry of ROUTE_MODULE_PREFIXES) {
    const [prefix] = entry
    if (path === prefix || path.startsWith(`${prefix}/`)) {
      if (best == null || prefix.length > best[0].length) best = entry
    }
  }
  return best ? best[1] : null
}

/** Human product name, for "available with <product>" copy. */
export const MODULE_DISPLAY_NAMES: Record<ModuleKey, string> = {
  spectracheck: "SpectraCheck",
  regulatory_hub: "Regentry",
  reaction_optimization: "Repho",
}

/**
 * Should a route be offered, given the included set?
 *
 * Fails OPEN while coverage is unknown (empty set), so a deployment that cannot answer
 * `/system/capabilities` keeps working exactly as it does today rather than hiding its entire nav.
 */
export function routeIsOffered(href: string, included: ReadonlySet<ModuleKey> | null): boolean {
  if (included == null || included.size === 0) return true
  const key = moduleForRoute(href)
  return key == null || included.has(key)
}
