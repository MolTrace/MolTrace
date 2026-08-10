import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ModuleCards, staggerDelay } from "@/components/marketing/module-cards"

// The three "Explore Module" overlays were split into a lazily-loaded chunk
// (module-explore-interfaces.tsx, pulled in via next/dynamic) so they stay out
// of the homepage's initial JS. These tests guard that (a) the always-shipped
// default view renders without the overlay code, and (b) the dynamic overlay
// still resolves and mounts correctly when a user opens it.
describe("ModuleCards", () => {
  it("renders the section heading, three module tabs, and the default capabilities view", () => {
    render(<ModuleCards />)

    expect(screen.getByText("Three modules. One unified platform.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "MODULE 01" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "MODULE 02" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "MODULE 03" })).toBeInTheDocument()

    // Default (always-shipped) panel — present without loading the overlay chunk.
    expect(screen.getByText("Capabilities")).toBeInTheDocument()
    expect(screen.getByText("1D & 2D NMR interpretation (COSY, HSQC, HMBC)")).toBeInTheDocument()
  })

  it("does not render the overlay content until the user opens it", () => {
    render(<ModuleCards />)
    // The overlay lives in a separate dynamic chunk — its content must not be
    // in the initial render.
    expect(screen.queryByText("Uncover the Ground Truth in Your Data.")).not.toBeInTheDocument()
  })

  it("lazy-loads and mounts the Spectroscopy overlay when 'Explore Module' is clicked", async () => {
    render(<ModuleCards />)

    // Two Explore buttons exist (desktop + mobile); either opens the overlay.
    fireEvent.click(screen.getAllByRole("button", { name: /Explore Module/i })[0])

    // The dynamically-imported overlay resolves and renders its content...
    expect(
      await screen.findByText("Uncover the Ground Truth in Your Data.", undefined, { timeout: 4000 }),
    ).toBeInTheDocument()
    // ...and the default capabilities panel is swapped out for it.
    expect(screen.queryByText("Capabilities")).not.toBeInTheDocument()

    // Closing the overlay restores the default view.
    fireEvent.click(screen.getByLabelText("Close explore preview"))
    await waitFor(() => expect(screen.getByText("Capabilities")).toBeInTheDocument())
  })

  // The launch link lives INSIDE the explore overlay, not on the card: the card
  // carries one CTA ("Explore Module") rather than two competing ones.
  it("keeps the card down to a single CTA, with no launch link beside it", () => {
    render(<ModuleCards />)
    expect(screen.getAllByRole("button", { name: /Explore Module/i }).length).toBeGreaterThan(0)
    expect(screen.queryByRole("link", { name: /Open SpectraCheck/i })).not.toBeInTheDocument()
  })

  // The three "How X works" overview links that used to live here were removed
  // as clutter. They were the crawl path to the module pages, so the guarantee
  // did not go away — it moved UP to app/page.test.tsx, which asserts the
  // homepage links all three with no interaction. That is the invariant worth
  // holding: it stays true whichever component supplies the links (today the
  // footer and the header dropdown), where a test here could only ever hold
  // this component's implementation of it.

  it.each([
    ["MODULE 01", "Open SpectraCheck", "/spectracheck"],
    ["MODULE 02", "Open Regentry", "/regulatory"],
    ["MODULE 03", "Open Repho", "/reactions"],
  ])("reveals %s's '%s' link once the overlay is open", async (tab, label, href) => {
    render(<ModuleCards />)
    fireEvent.click(screen.getByRole("button", { name: tab }))

    // Not on the card...
    expect(screen.queryByRole("link", { name: new RegExp(label, "i") })).not.toBeInTheDocument()

    // ...and present once the reader opens the preview.
    fireEvent.click(screen.getAllByRole("button", { name: /Explore Module/i })[0])
    const link = await screen.findByRole("link", { name: new RegExp(label, "i") }, { timeout: 4000 })
    expect(link).toHaveAttribute("href", href)
  })
})

/**
 * The tab indicator slides, so the tabs read as animated. The panel they control
 * did not — switching modules only changes the strings inside the existing
 * nodes, so React reuses every element and the content swaps with no transition
 * at all. The fix is a `key`, and a `key` is exactly the kind of thing a later
 * cleanup removes as redundant, because nothing about the rendered output looks
 * wrong without it. These tests are the tripwire.
 */
describe("ModuleCards — panel transition", () => {
  const panel = (container: HTMLElement) => container.querySelector(".mt-panel-in")

  it("REMOUNTS the panel on a module switch rather than mutating it in place", () => {
    const { container } = render(<ModuleCards />)
    const before = panel(container)
    expect(before).not.toBeNull()

    fireEvent.click(screen.getByRole("button", { name: "MODULE 02" }))
    const after = panel(container)

    // A different DOM node — which is what lets the entrance animation run
    // again. Same node with new text is the bug this guards.
    expect(after).not.toBe(before)
    expect(after?.textContent).toContain("Regulatory")
  })

  it("remounts when the explore overlay is toggled too, not only on tab change", () => {
    const { container } = render(<ModuleCards />)
    const before = panel(container)
    fireEvent.click(screen.getAllByRole("button", { name: /Explore Module/i })[0])
    expect(panel(container)).not.toBe(before)
  })

  it("staggers the capability rows in order", () => {
    const { container } = render(<ModuleCards />)
    const delays = Array.from(container.querySelectorAll<HTMLElement>(".mt-stagger-in")).map((li) =>
      Number.parseInt(li.style.animationDelay, 10),
    )
    expect(delays.length).toBeGreaterThan(3)
    expect([...delays].sort((a, b) => a - b)).toEqual(delays)
    expect(delays).toEqual(delays.map((_, i) => staggerDelay(i)))
  })

  it("caps the stagger so a longer list would not crawl", () => {
    // Tested through the function, not the rendered rows: every module carries
    // exactly six capabilities today, so `index` never reaches the clamp and
    // asserting on the DOM passes whether or not the clamp exists — which is
    // how the first version of this test missed a mutation that removed it.
    expect(staggerDelay(0)).toBeLessThan(staggerDelay(5))
    expect(staggerDelay(7)).toBe(staggerDelay(6))
    expect(staggerDelay(40)).toBe(staggerDelay(6))
    expect(staggerDelay(40)).toBeLessThanOrEqual(330)
  })

  it("keeps the panel's animation class, which the reduced-motion rule switches off", () => {
    // globals.css disables .mt-panel-in and .mt-stagger-in under
    // prefers-reduced-motion. That only works if the classes are actually here.
    const { container } = render(<ModuleCards />)
    expect(panel(container)?.className).toContain("mt-panel-in")
    expect(container.querySelector(".mt-stagger-in")).not.toBeNull()
  })
})
