import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { SpectrumViewer1D } from "@/components/science/SpectrumViewer1D"

// react-plotly.js is loaded via next/dynamic and never renders under jsdom; stub it so the
// surrounding chrome (toolbar vs. no toolbar) is what we assert on.
vi.mock("next/dynamic", () => ({
  default: () => function PlotStub() {
    return <div data-testid="plotly-stub" />
  },
}))

const X = [1, 2, 3, 4, 5]
const Y = [10, 40, 15, 80, 20]

/**
 * Regression guard for the Report "Selected Visual Evidence" previews.
 *
 * The preview cards embed the same viewer as the full workspace. Its toolbar buttons are
 * `w-full sm:w-auto` — and `sm:` is a VIEWPORT breakpoint, not a container query — so inside a
 * narrow preview card on a wide screen they stayed auto-width and wrapped to three or four rows.
 * That subtree was taller than the preview's `max-h-[min(200px,28vh)] overflow-hidden` box, so the
 * chart was clipped out of view entirely and the card rendered nothing but buttons.
 */
describe("SpectrumViewer1D preview mode", () => {
  it("renders the full toolbar by default (the interactive workspace)", () => {
    render(<SpectrumViewer1D x={X} y={Y} nucleus="1H" />)
    expect(screen.getByRole("button", { name: /reset zoom/i })).toBeTruthy()
    expect(screen.getByRole("button", { name: /full view/i })).toBeTruthy()
    expect(screen.getByRole("button", { name: /increase peak height/i })).toBeTruthy()
    expect(screen.getByLabelText(/intensity gain/i)).toBeTruthy()
  })

  it("renders NO toolbar or gain slider when showControls is false", () => {
    render(<SpectrumViewer1D x={X} y={Y} nucleus="1H" showControls={false} height={150} />)
    // The exact controls visible in the broken screenshots must be absent.
    for (const name of [
      /reset zoom/i,
      /full view/i,
      /pan left/i,
      /pan right/i,
      /increase peak height/i,
      /decrease peak height/i,
      /toggle labels/i,
      /export image/i,
    ]) {
      expect(screen.queryByRole("button", { name })).toBeNull()
    }
    expect(screen.queryByLabelText(/intensity gain/i)).toBeNull()
    // …and the plot surface itself is still mounted, which is the whole point.
    expect(screen.getByLabelText(/1H 1D display/i)).toBeTruthy()
  })

  it("drops the 280px floor in preview mode so the chart fits a compact card", () => {
    const { container: preview } = render(
      <SpectrumViewer1D x={X} y={Y} nucleus="1H" showControls={false} height={150} />,
    )
    expect(preview.querySelector(".min-h-\\[280px\\]")).toBeNull()

    const { container: full } = render(<SpectrumViewer1D x={X} y={Y} nucleus="1H" />)
    expect(full.querySelector(".min-h-\\[280px\\]")).not.toBeNull()
  })
})
