import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"

import { ReactionProgramInterfaceWorkspace } from "@/components/reaction-optimization/reaction-program-interface-workspace"

// Heavy child components are stubbed — this test focuses on the tab-row
// layout, not the program-overview or reaction-studio surfaces.
vi.mock(
  "@/components/reaction-optimization/reaction-optimization-landing",
  () => ({
    ReactionOptimizationLanding: () => (
      <div data-testid="reaction-overview-stub" />
    ),
  }),
)

vi.mock(
  "@/components/reaction-studio/reaction-studio-workspace",
  () => ({
    ReactionStudioWorkspace: () => (
      <div data-testid="reaction-studio-stub" />
    ),
  }),
)

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}))

describe("ReactionProgramInterfaceWorkspace — mobile tab layout", () => {
  it("renders both tab triggers with their full labels", () => {
    render(<ReactionProgramInterfaceWorkspace />)
    expect(
      screen.getByRole("tab", { name: "Reaction Optimization" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("tab", { name: "Reaction Studio (program-level)" }),
    ).toBeInTheDocument()
  })

  it("makes the tab list horizontally scrollable so long labels never get cut off on mobile", () => {
    // Regression for the mobile-overflow report: the long
    // "Reaction Studio (program-level)" label used to push past the right
    // edge of the screen because TabsList defaults to ``inline-flex w-fit``.
    // The fix wraps the list in ``overflow-x-auto`` + a hidden scrollbar
    // and adds ``shrink-0`` to each trigger so labels keep their natural
    // width instead of being clipped.
    render(<ReactionProgramInterfaceWorkspace />)
    const tablist = screen.getByRole("tablist")
    expect(tablist.className).toContain("overflow-x-auto")
    expect(tablist.className).toContain("max-w-full")
  })

  it("prevents tab labels from being squeezed (shrink-0 on every trigger)", () => {
    render(<ReactionProgramInterfaceWorkspace />)
    const triggers = screen.getAllByRole("tab")
    expect(triggers.length).toBe(2)
    for (const trigger of triggers) {
      // Each trigger keeps its content width — never compressed below
      // its label, which is what previously caused the cutoff.
      expect(trigger.className).toContain("shrink-0")
    }
  })
})
