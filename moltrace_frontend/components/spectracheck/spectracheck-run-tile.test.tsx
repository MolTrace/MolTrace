import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { Eye } from "lucide-react"

import { SpectraCheckRunTile } from "@/components/spectracheck/spectracheck-run-tile"

/**
 * Guards the run tile against the drift this component was extracted to end.
 *
 * The Processed tab's Analyze action had grown into the product's only
 * 148px-plus full-bleed gradient card, carrying white type on --mt-teal at
 * 1.74:1 contrast — which app/globals.css already documents as failing WCAG AA
 * ("tuned for fills/icons, not type"). Meanwhile Raw FID used a different tile
 * design for the same two verbs. Hierarchy must come from fill and label, never
 * from making one control physically larger than every other primary action.
 */
function renderTile(overrides: Partial<Parameters<typeof SpectraCheckRunTile>[0]> = {}) {
  return render(
    <SpectraCheckRunTile
      eyebrow="Analyze"
      eyebrowIcon={Eye}
      headline="Run evidence match"
      description="Detect peaks and match against candidate structures."
      tone="primary"
      tooltip="Standard analysis."
      {...overrides}
    />,
  )
}

describe("SpectraCheckRunTile", () => {
  it("uses the house tile geometry, not an oversized gradient card", () => {
    renderTile()
    const tile = screen.getByRole("button", { name: /Run evidence match/i })

    expect(tile.className).toContain("rounded-xl")
    expect(tile.className).toContain("p-4")
    // The specific regressions: an outsized min-height, a heavier radius/border
    // pair, and white body type on a brand fill.
    expect(tile.className).not.toMatch(/min-h-\[148px\]/)
    expect(tile.className).not.toMatch(/rounded-2xl/)
    expect(tile.className).not.toMatch(/border-2/)
    expect(tile.className).not.toMatch(/text-white/)
    expect(tile.getAttribute("style") ?? "").not.toMatch(/linear-gradient/)
  })

  it("carries a focus ring and an explicit accessible name", () => {
    renderTile()
    const tile = screen.getByRole("button", { name: /Run evidence match/i })

    expect(tile.className).toContain("focus-visible:ring-2")
    // Without an explicit label, assistive tech reads the eyebrow, badge,
    // headline and description as one blob before reaching the verb.
    expect(tile).toHaveAttribute("aria-label", "Run evidence match")
  })

  it("states a disabled reason as visible text rather than a title", () => {
    renderTile({ disabled: true, disabledReason: "Waiting for the analysis already running." })
    const tile = screen.getByRole("button", { name: /Run evidence match/i })

    expect(tile).toBeDisabled()
    // A disabled control never fires its native tooltip, so a `title` would be
    // unreachable by mouse, keyboard and touch alike.
    expect(tile).not.toHaveAttribute("title")
    expect(screen.getByText(/Waiting for the analysis already running\./i)).toBeInTheDocument()
  })

  it("marks the experimental tone with amber tokens that have a dark counterpart", () => {
    renderTile({ tone: "experimental", badge: "Experimental" })
    const tile = screen.getByRole("button", { name: /Run evidence match/i })
    const style = tile.getAttribute("style") ?? ""

    // Tokens, not the hard-coded #D97706 / #B45309 / rgb(254 243 199) literals
    // the old GSD variant used, which had no dark-mode counterpart.
    expect(style).toContain("var(--mt-amber)")
    expect(style).not.toMatch(/#[0-9a-fA-F]{6}/)
  })
})
