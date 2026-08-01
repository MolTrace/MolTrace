import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { ModuleGate } from "@/src/lib/modules/module-not-included-tile"

const isIncluded = vi.fn()
vi.mock("@/src/lib/modules/included-modules-provider", () => ({
  useIncludedModules: () => ({
    isIncluded,
    displayNames: { regulatory_hub: "Regentry", reaction_optimization: "Repho" },
  }),
}))

/** Stands in for a cross-module card: it "fetches" the moment it mounts. */
const mounted = vi.fn()
function Child() {
  mounted()
  return <div data-testid="child">real card</div>
}

describe("ModuleGate", () => {
  it("renders the child when the product is included", () => {
    mounted.mockClear()
    isIncluded.mockReturnValue(true)
    render(
      <ModuleGate module="regulatory_hub" what="Regulatory impact">
        <Child />
      </ModuleGate>,
    )
    expect(screen.getByTestId("child")).toBeTruthy()
    expect(mounted).toHaveBeenCalledTimes(1)
  })

  it("NEVER MOUNTS the child when the product is absent — so its requests never fire", () => {
    // This is the load-bearing assertion: hiding a card while still fetching its data
    // is not gating. The child must not run at all.
    mounted.mockClear()
    isIncluded.mockReturnValue(false)
    render(
      <ModuleGate module="regulatory_hub" what="Regulatory impact">
        <Child />
      </ModuleGate>,
    )
    expect(screen.queryByTestId("child")).toBeNull()
    expect(mounted).not.toHaveBeenCalled()
  })

  it("states the situation using the product's display name, not a wire key", () => {
    isIncluded.mockReturnValue(false)
    render(
      <ModuleGate module="regulatory_hub" what="Regulatory impact of this result">
        <Child />
      </ModuleGate>,
    )
    const tile = screen.getByTestId("module-not-included-regulatory_hub")
    expect(tile.textContent).toContain("Regulatory impact of this result")
    expect(tile.textContent).toContain("Regentry")
    expect(tile.textContent).toContain("does not include")
    // never the raw key, and never an error framing
    expect(tile.textContent).not.toContain("regulatory_hub")
    expect(tile.textContent).not.toMatch(/error|denied|failed|forbidden/i)
  })

  it("can hide entirely for decorative surfaces", () => {
    mounted.mockClear()
    isIncluded.mockReturnValue(false)
    const { container } = render(
      <ModuleGate module="reaction_optimization" what="Handoff" fallback="hide">
        <Child />
      </ModuleGate>,
    )
    expect(container.textContent).toBe("")
    expect(mounted).not.toHaveBeenCalled()
  })
})
