import { fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"

import { SpectrumResultsFullscreen } from "@/components/spectracheck/spectracheck-fullscreen-results"

describe("SpectrumResultsFullscreen", () => {
  it("renders its children inline when closed — no dialog chrome", () => {
    render(
      <SpectrumResultsFullscreen open={false} onClose={vi.fn()} title="Results">
        <div data-testid="results-child">Spectrum + tables</div>
      </SpectrumResultsFullscreen>,
    )

    // In-place: the children are visible even while closed (this is the normal
    // inline page view), unlike a portal overlay that hides everything.
    expect(screen.getByTestId("results-child")).toBeInTheDocument()
    // …but none of the full-screen chrome is present.
    expect(screen.queryByTestId("spectrum-results-fullscreen")).not.toBeInTheDocument()
    expect(screen.queryByLabelText("Close full screen spectrum view")).not.toBeInTheDocument()
  })

  it("promotes the SAME children into a full-screen dialog when open", () => {
    render(
      <SpectrumResultsFullscreen
        open
        onClose={vi.fn()}
        eyebrow="Full screen · Processed 1H"
        title="Processed output"
        subtitle="trace.csv"
        tag="sample-1"
      >
        <div data-testid="results-child">Spectrum + tables</div>
      </SpectrumResultsFullscreen>,
    )

    const dialog = screen.getByTestId("spectrum-results-fullscreen")
    expect(dialog).toHaveAttribute("role", "dialog")
    expect(dialog).toHaveAttribute("aria-modal", "true")

    // Header context — eyebrow + title + file/sample tags.
    expect(screen.getByText("Full screen · Processed 1H")).toBeInTheDocument()
    expect(screen.getByText("Processed output")).toBeInTheDocument()
    expect(screen.getByText(/trace\.csv/)).toBeInTheDocument()
    expect(screen.getByText("sample-1")).toBeInTheDocument()

    // The children render exactly once — there is no second copy of the
    // results subtree (which is what would double-fetch the analysis panels).
    expect(screen.getAllByTestId("results-child")).toHaveLength(1)
  })

  it("closes via the Exit control and the Escape key", () => {
    const onClose = vi.fn()
    render(
      <SpectrumResultsFullscreen open onClose={onClose} title="Results">
        <div>child</div>
      </SpectrumResultsFullscreen>,
    )

    fireEvent.click(screen.getByLabelText("Close full screen spectrum view"))
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it("keeps the same child DOM node mounted across the open→close toggle (no remount/refetch)", () => {
    function Harness() {
      const [open, setOpen] = useState(true)
      return (
        <div>
          <button type="button" onClick={() => setOpen((v) => !v)}>
            toggle
          </button>
          <SpectrumResultsFullscreen open={open} onClose={() => setOpen(false)} title="Results">
            <input data-testid="stateful-child" />
          </SpectrumResultsFullscreen>
        </div>
      )
    }

    render(<Harness />)
    const input = screen.getByTestId("stateful-child") as HTMLInputElement
    // Imperatively mutate DOM state that only survives if the node is NOT recreated.
    input.value = "preserved"

    // Leave full screen.
    fireEvent.click(screen.getByText("toggle"))

    const afterClose = screen.getByTestId("stateful-child") as HTMLInputElement
    // Identical node reference + retained value proves React reused the subtree
    // rather than unmounting and remounting it (so live panels never re-fetch).
    expect(afterClose).toBe(input)
    expect(afterClose.value).toBe("preserved")
  })
})
