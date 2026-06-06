import { fireEvent, render, screen } from "@testing-library/react"
import type { ReactElement } from "react"
import { describe, expect, it, vi } from "vitest"

import { ProcessedSpectrumFullscreenView } from "@/components/spectracheck/spectracheck-processed-fullscreen-view"
import type { SpectrumPeakAnnotation } from "@/components/science/SpectrumViewer"
import { SpectraCheckEvidenceProvider } from "@/src/lib/spectracheck/useSpectraCheckEvidence"

// Plotly is heavy and irrelevant here — assert we forward the right props
// (notably the full-screen heightClassName) to the SAME SpectrumViewer.
vi.mock("@/components/science/SpectrumViewer", () => ({
  SpectrumViewer: (props: { nucleus?: "1H" | "13C"; heightClassName?: string; peaks?: unknown[] }) => (
    <div
      data-testid="spectrum-viewer"
      data-height={props.heightClassName}
      data-peak-count={props.peaks?.length ?? 0}
    >
      Nucleus context: <span>{props.nucleus}</span>
    </div>
  ),
}))

function renderWithEvidence(ui: ReactElement) {
  return render(<SpectraCheckEvidenceProvider>{ui}</SpectraCheckEvidenceProvider>)
}

function baseProps(overrides: Partial<Parameters<typeof ProcessedSpectrumFullscreenView>[0]> = {}) {
  return {
    open: true,
    onClose: vi.fn(),
    nucleus: "1H" as const,
    xy: { x: [4.2, 4.1, 4.0], y: [0, 3, 0] },
    peaks: [] as SpectrumPeakAnnotation[],
    overlays: undefined,
    displayPayload: {
      nucleus: "1H",
      filename: "trace.csv",
      peak_count: 1,
      peaks: [{ shift_ppm: 4.1, intensity: 3 }],
      warnings: [],
      notes: [],
    },
    peakCount: 1,
    score: 0.91,
    warnings: [] as string[],
    notes: null,
    loading: false,
    title: "Preview output",
    payloadMode: "preview" as const,
    sampleId: "sample-1",
    fileName: "trace.csv",
    unifiedEvidenceMeta: {
      layer: "processed_1h" as const,
      sourceTab: "Processed 1H / 13C upload",
      title: "Processed spectrum preview",
      endpoint: "/nmr/processed/preview",
      sampleId: "sample-1",
    },
    ...overrides,
  }
}

describe("ProcessedSpectrumFullscreenView", () => {
  it("renders nothing while closed", () => {
    renderWithEvidence(<ProcessedSpectrumFullscreenView {...baseProps({ open: false })} />)
    expect(screen.queryByTestId("processed-fullscreen-view")).not.toBeInTheDocument()
    expect(screen.queryByText(/Nucleus context/i)).not.toBeInTheDocument()
  })

  it("renders the spectrum and analysis tables full-screen when open", () => {
    renderWithEvidence(<ProcessedSpectrumFullscreenView {...baseProps()} />)

    // Dialog shell + title/context.
    const dialog = screen.getByTestId("processed-fullscreen-view")
    expect(dialog).toHaveAttribute("role", "dialog")
    expect(screen.getByText("Preview output")).toBeInTheDocument()
    expect(screen.getByText(/trace\.csv/)).toBeInTheDocument()

    // The SAME SpectrumViewer, told to fill the viewport via heightClassName.
    expect(screen.getByText(/Nucleus context/i)).toBeInTheDocument()
    expect(screen.getByTestId("spectrum-viewer")).toHaveAttribute("data-height", "h-[min(820px,62vh)]")

    // KPI strip + the picked-peaks results table (rendered from displayPayload).
    expect(screen.getByText("Peak count")).toBeInTheDocument()
    expect(screen.getByText("Analysis score")).toBeInTheDocument()
    expect(screen.getByText("Picked peaks")).toBeInTheDocument()
  })

  it("closes via the Exit control and the Escape key", () => {
    const onClose = vi.fn()
    renderWithEvidence(<ProcessedSpectrumFullscreenView {...baseProps({ onClose })} />)

    fireEvent.click(screen.getByLabelText("Close full screen spectrum view"))
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it("shows a loading state instead of the spectrum when no points are ready yet", () => {
    renderWithEvidence(
      <ProcessedSpectrumFullscreenView
        {...baseProps({ xy: null, displayPayload: null, loading: true, payloadMode: "analyze" })}
      />,
    )
    expect(screen.getByTestId("processed-fullscreen-view")).toBeInTheDocument()
    expect(screen.queryByTestId("spectrum-viewer")).not.toBeInTheDocument()
    expect(screen.getByText(/Running evidence match/i)).toBeInTheDocument()
  })
})
