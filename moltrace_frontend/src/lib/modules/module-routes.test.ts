import { describe, expect, it } from "vitest"
import {
  MODULE_KEYS,
  moduleForRoute,
  routeIsOffered,
  type ModuleKey,
} from "@/src/lib/modules/module-routes"
import { parseSystemCapabilities } from "@/src/lib/modules/included-modules-provider"

const ALL = new Set<ModuleKey>(MODULE_KEYS)

describe("route → product map", () => {
  it("maps each product's own routes", () => {
    expect(moduleForRoute("/spectracheck")).toBe("spectracheck")
    expect(moduleForRoute("/regulatory")).toBe("regulatory_hub")
    expect(moduleForRoute("/reactions")).toBe("reaction_optimization")
  })

  it("claims the SpectraCheck-only surfaces that sit in generic nav groups", () => {
    // A Regentry-only buyer would otherwise get two permanently empty top-level items.
    expect(moduleForRoute("/review")).toBe("spectracheck")
    expect(moduleForRoute("/reports")).toBe("spectracheck")
  })

  it("leaves shared surfaces unowned so they show on every deployment", () => {
    for (const href of ["/dashboard", "/settings/team", "/admin/system", "/knowledge", "/ai"]) {
      expect(moduleForRoute(href)).toBeNull()
    }
  })

  it("matches on path segments, so a longer name never collides with a prefix", () => {
    expect(moduleForRoute("/reviewer-notes")).toBeNull() // not "/review"
    expect(moduleForRoute("/reportsomething")).toBeNull() // not "/reports"
    expect(moduleForRoute("/review/123")).toBe("spectracheck") // a real child does match
  })

  it("ignores query strings and trailing slashes", () => {
    expect(moduleForRoute("/regulatory/")).toBe("regulatory_hub")
    expect(moduleForRoute("/regulatory?tab=dossiers")).toBe("regulatory_hub")
    expect(moduleForRoute("/reactions#top")).toBe("reaction_optimization")
  })
})

describe("routeIsOffered", () => {
  it("hides a product's routes when the deployment does not include it", () => {
    const only = new Set<ModuleKey>(["spectracheck"])
    expect(routeIsOffered("/spectracheck", only)).toBe(true)
    expect(routeIsOffered("/review", only)).toBe(true)
    expect(routeIsOffered("/regulatory", only)).toBe(false)
    // /projects is shared, not Repho's: a SpectraCheck session carries a project_id, so hiding
    // it from a SpectraCheck-only workspace removed a page that product actually needs.
    expect(routeIsOffered("/projects", only)).toBe(true)
    expect(routeIsOffered("/projects/14", only)).toBe(true)
    expect(routeIsOffered("/reactions", only)).toBe(false)
    // shared surfaces survive
    expect(routeIsOffered("/dashboard", only)).toBe(true)
  })

  it("FAILS OPEN when coverage is unknown — never hides the whole app", () => {
    for (const unknown of [null, new Set<ModuleKey>()]) {
      for (const href of ["/spectracheck", "/regulatory", "/reactions", "/dashboard"]) {
        expect(routeIsOffered(href, unknown)).toBe(true)
      }
    }
  })

  it("offers everything when all three are included", () => {
    for (const href of ["/spectracheck", "/regulatory", "/reactions", "/dashboard"]) {
      expect(routeIsOffered(href, ALL)).toBe(true)
    }
  })
})

describe("parseSystemCapabilities", () => {
  it("reads the included set from the documented payload", () => {
    const parsed = parseSystemCapabilities({
      modules: [
        { module: "spectracheck", display_name: "SpectraCheck", included: true },
        { module: "regulatory_hub", display_name: "Regentry", included: false },
        { module: "reaction_optimization", display_name: "Reaction Optimization", included: false },
      ],
    })
    expect([...(parsed?.included ?? [])]).toEqual(["spectracheck"])
    // Server display names win, so a rebrand does not need an FE change.
    expect(parsed?.displayNames.reaction_optimization).toBe("Reaction Optimization")
  })

  it("treats anything other than an explicit true as NOT included", () => {
    const parsed = parseSystemCapabilities({
      modules: [
        { module: "spectracheck", included: "yes" },
        { module: "regulatory_hub" },
        { module: "reaction_optimization", included: 1 },
      ],
    })
    expect(parsed?.included.size).toBe(0)
  })

  it("ignores unknown product keys and malformed rows without throwing", () => {
    const parsed = parseSystemCapabilities({
      modules: [{ module: "chromatography", included: true }, null, "junk", { included: true }],
    })
    expect(parsed?.included.size).toBe(0)
  })

  it("returns null for a payload that is not a capability readout, so callers fail open", () => {
    for (const bad of [null, undefined, {}, { modules: "nope" }, 42]) {
      expect(parseSystemCapabilities(bad)).toBeNull()
    }
  })
})
