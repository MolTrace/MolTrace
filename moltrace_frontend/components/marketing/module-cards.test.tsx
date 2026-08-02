import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ModuleCards } from "@/components/marketing/module-cards"

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

  // The homepage published no in-body link to any marketing page: the tabs and
  // "Explore Module" are buttons (correctly — they switch and toggle rather
  // than navigate) and the overlay's launch links point at the app, which
  // robots.txt disallows. These three overview links are the crawl path to the
  // module pages, so they must render WITHOUT any interaction and for all three
  // modules at once — a link inside the active tab panel would reach neither a
  // reader on another tab nor a crawler.
  it.each([
    ["How SpectraCheck works", "/spectroscopy"],
    ["How Regentry works", "/regulatory-hub"],
    ["How Repho works", "/reaction-optimization"],
  ])("links to %s with no interaction", (label, href) => {
    render(<ModuleCards />)

    expect(screen.getByRole("link", { name: new RegExp(label, "i") })).toHaveAttribute("href", href)
  })

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
