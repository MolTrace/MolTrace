import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import { ModuleRouteGuard } from "@/src/lib/modules/module-route-guard"
import { routeIsOffered, type ModuleKey } from "@/src/lib/modules/module-routes"

let pathname = "/dashboard"
vi.mock("next/navigation", () => ({ usePathname: () => pathname }))
vi.mock("next/link", () => ({
  default: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}))

/** Mirrors the real provider, including its fail-open rule, so the guard is tested against it. */
let included: Set<ModuleKey> | null = new Set(["spectracheck"])
let loading = false
vi.mock("@/src/lib/modules/included-modules-provider", () => ({
  useIncludedModules: () => ({
    loading,
    displayNames: { spectracheck: "SpectraCheck", regulatory_hub: "Regentry", reaction_optimization: "Repho" },
    isRouteOffered: (href: string) => routeIsOffered(href, included),
  }),
}))

/** Stands in for a page: it "fetches" the instant it mounts. */
const mounted = vi.fn()
function Page() {
  mounted()
  return <div data-testid="page">page content</div>
}

function renderAt(path: string) {
  pathname = path
  return render(
    <ModuleRouteGuard>
      <Page />
    </ModuleRouteGuard>,
  )
}

describe("ModuleRouteGuard", () => {
  beforeEach(() => {
    mounted.mockClear()
    included = new Set(["spectracheck"])
    loading = false
  })

  it("NEVER MOUNTS the page of an absent product — filtering nav removes the link, not the route", () => {
    renderAt("/regulatory/dossiers/12")
    expect(screen.queryByTestId("page")).toBeNull()
    expect(mounted).not.toHaveBeenCalled()
    expect(screen.getByTestId("module-route-not-included-regulatory_hub")).toBeTruthy()
  })

  it("blocks the reaction tree too, at any depth", () => {
    renderAt("/reactions/7/studio")
    expect(mounted).not.toHaveBeenCalled()
    expect(screen.getByTestId("module-route-not-included-reaction_optimization")).toBeTruthy()
  })

  it("renders the product this workspace does have", () => {
    renderAt("/spectracheck/sessions/3")
    expect(screen.getByTestId("page")).toBeTruthy()
    expect(mounted).toHaveBeenCalledTimes(1)
  })

  it("never gates a shared route", () => {
    // /projects belongs here: a SpectraCheck session carries a project_id, so the project list is
    // not Repho's. /compounds is SpectraCheck-owned and this workspace has SpectraCheck.
    for (const path of ["/dashboard", "/projects", "/settings", "/compounds", "/mobile"]) {
      mounted.mockClear()
      const { unmount } = renderAt(path)
      expect(mounted).toHaveBeenCalledTimes(1)
      unmount()
    }
  })

  it("does not make a shared route wait on the readout", () => {
    // Only module-owned routes pay the loading hold; everything else renders immediately.
    loading = true
    renderAt("/dashboard")
    expect(mounted).toHaveBeenCalledTimes(1)
  })

  it("holds a module-owned route while the readout is in flight, rather than letting it fetch", () => {
    // The race this closes: mounting before capabilities land fires the page's requests against a
    // server that refuses them — the exact burst the guard exists to prevent.
    loading = true
    renderAt("/regulatory")
    expect(mounted).not.toHaveBeenCalled()
    expect(screen.queryByTestId("page")).toBeNull()
  })

  it("FAILS OPEN when capabilities cannot be read at all", () => {
    // Losing the readout must never lock a paying customer out of what they bought.
    included = null
    renderAt("/regulatory/dossiers")
    expect(mounted).toHaveBeenCalledTimes(1)
  })

  it("fails open on an empty readout too", () => {
    included = new Set()
    renderAt("/reactions")
    expect(mounted).toHaveBeenCalledTimes(1)
  })

  it("uses the product name, not the wire key, and does not read as an error", () => {
    renderAt("/regulatory")
    const el = screen.getByTestId("module-route-not-included-regulatory_hub")
    expect(el.textContent).toContain("Regentry")
    expect(el.textContent).not.toContain("regulatory_hub")
    expect(el.textContent).not.toMatch(/error|denied|forbidden|failed|403/i)
  })

  it("does not confuse a lookalike path for a gated one", () => {
    // moduleForRoute matches on segments; /regulatory-affairs is not /regulatory.
    renderAt("/regulatory-affairs")
    expect(mounted).toHaveBeenCalledTimes(1)
  })
})
