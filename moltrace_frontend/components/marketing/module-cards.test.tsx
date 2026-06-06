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
})
