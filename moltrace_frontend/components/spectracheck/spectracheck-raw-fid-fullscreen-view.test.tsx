import { fireEvent, render, screen } from "@testing-library/react"
import type { ReactElement } from "react"
import { describe, expect, it, vi } from "vitest"

import { RawFidSpectrumFullscreenView } from "@/components/spectracheck/spectracheck-raw-fid-fullscreen-view"
import type { SpectrumPeakAnnotation } from "@/components/science/SpectrumViewer"
import { SpectraCheckEvidenceProvider } from "@/src/lib/spectracheck/useSpectraCheckEvidence"

// Plotly is heavy and irrelevant here — assert we forward the right props
// (notably the full-screen heightClassName + the raw-FID viewerPeaks) to the
// SAME SpectrumViewer the inline raw-FID card renders.
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

function baseProps(overrides: Partial<Parameters<typeof RawFidSpectrumFullscreenView>[0]> = {}) {
  return {
    open: true,
    onClose: vi.fn(),
    nucleus: "1H" as const,
    xy: { x: [4.2, 4.1, 4.0], y: [0, 3, 0] },
    viewerPeaks: [] as SpectrumPeakAnnotation[],
    displayPayload: {
      nucleus: "1H",
      filename: "sample.fid.zip",
      peak_count: 1,
      peaks: [{ shift_ppm: 4.1, intensity: 3 }],
      warnings: [],
      notes: [],
    },
    gsdResult: null,
    legacyDetectionResult: null,
    loading: false,
    payloadMode: "process" as const,
    title: "Processed FID output",
    fileName: "sample.fid.zip",
    sampleId: "sample-1",
    vendorDetected: "Bruker",
    nucleusMeta: "1H",
    sw: 10000,
    td: 65536,
    sha: "abc123",
    warnings: [] as string[],
    unifiedEvidenceMeta: {
      layer: "raw_fid_1h" as const,
      sourceTab: "Raw FID upload",
      title: "Raw FID process",
      endpoint: "/nmr/raw-fid/process",
      sampleId: "sample-1",
    },
    ...overrides,
  }
}

describe("RawFidSpectrumFullscreenView", () => {
  it("renders nothing while closed", () => {
    renderWithEvidence(<RawFidSpectrumFullscreenView {...baseProps({ open: false })} />)
    expect(screen.queryByTestId("raw-fid-fullscreen-view")).not.toBeInTheDocument()
    expect(screen.queryByText(/Nucleus context/i)).not.toBeInTheDocument()
  })

  it("renders the spectrum and analysis tables full-screen when open", () => {
    renderWithEvidence(<RawFidSpectrumFullscreenView {...baseProps()} />)

    // Dialog shell + title/context.
    const dialog = screen.getByTestId("raw-fid-fullscreen-view")
    expect(dialog).toHaveAttribute("role", "dialog")
    expect(screen.getByText("Processed FID output")).toBeInTheDocument()
    expect(screen.getByText(/sample\.fid\.zip/)).toBeInTheDocument()

    // The SAME SpectrumViewer, told to fill the viewport via heightClassName.
    expect(screen.getByText(/Nucleus context/i)).toBeInTheDocument()
    expect(screen.getByTestId("spectrum-viewer")).toHaveAttribute("data-height", "h-[min(820px,62vh)]")

    // Raw-FID KPI strip + the picked-peaks results table (process mode).
    expect(screen.getByText("Vendor")).toBeInTheDocument()
    expect(screen.getByText("Spectral width")).toBeInTheDocument()
    expect(screen.getByText("TD points")).toBeInTheDocument()
    expect(screen.getByText("Picked peaks")).toBeInTheDocument()
  })

  it("closes via the Exit control and the Escape key", () => {
    const onClose = vi.fn()
    renderWithEvidence(<RawFidSpectrumFullscreenView {...baseProps({ onClose })} />)

    fireEvent.click(screen.getByLabelText("Close full screen spectrum view"))
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it("shows a loading state instead of the spectrum when no points are ready yet", () => {
    renderWithEvidence(
      <RawFidSpectrumFullscreenView
        {...baseProps({ xy: null, displayPayload: null, loading: true, payloadMode: "process" })}
      />,
    )
    expect(screen.getByTestId("raw-fid-fullscreen-view")).toBeInTheDocument()
    expect(screen.queryByTestId("spectrum-viewer")).not.toBeInTheDocument()
    // Top status badge reflects the process operation; canvas placeholder is generic.
    expect(screen.getByText(/Processing FID/i)).toBeInTheDocument()
    expect(screen.getByText(/Preparing spectrum/i)).toBeInTheDocument()
  })
})
