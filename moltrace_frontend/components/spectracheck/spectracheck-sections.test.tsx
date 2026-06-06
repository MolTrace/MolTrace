import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { SpectrumViewer, sampleSpectrumTraceForPlot } from "@/components/science/SpectrumViewer"
import { SpectraCheckProcessedSpectrumSection } from "@/components/spectracheck/spectracheck-processed-spectrum-section"
import { SpectraCheckRawFidSection } from "@/components/spectracheck/spectracheck-raw-fid-section"
describe("SpectraCheck processed / raw sections", () => {
  it("processed section shows title and Preview / Analyze actions", () => {
    render(
      <SpectraCheckProcessedSpectrumSection
        sampleId="t1"
        onSampleIdChange={() => {}}
        solvent="CDCl3"
        candidatesText="A | CCO"
      />
    )
    expect(screen.getByText("Configure & upload spectrum")).toBeInTheDocument()
    // Action tile buttons (Step 2) — text is concatenated from inner spans.
    expect(screen.getByRole("button", { name: /Inspect spectrum/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Run evidence match/i })).toBeInTheDocument()
  })

  it("raw FID section shows title and Preview / Process actions", () => {
    render(<SpectraCheckRawFidSection sampleId="t1" onSampleIdChange={() => {}} solvent="CDCl3" />)
    expect(screen.getByText("Configure & upload raw FID archive")).toBeInTheDocument()
    // Action tile buttons (Step 2).
    expect(screen.getByRole("button", { name: /Preview spectrum/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Process FID/i })).toBeInTheDocument()
  })

  it("processed spectrum drop-zone opens the native file picker", () => {
    render(
      <SpectraCheckProcessedSpectrumSection
        sampleId="t1"
        onSampleIdChange={() => {}}
        solvent="CDCl3"
        candidatesText="A | CCO"
      />
    )
    const input = screen.getByLabelText(/Processed spectrum file/i, { selector: "input" }) as HTMLInputElement
    const clickSpy = vi.spyOn(input, "click").mockImplementation(() => undefined)

    fireEvent.click(screen.getByRole("button", { name: /Drop processed spectrum file/i }))

    expect(clickSpy).toHaveBeenCalled()
    clickSpy.mockRestore()
  })

  it("processed spectrum picker includes parseable NMR spectrum file formats", () => {
    render(
      <SpectraCheckProcessedSpectrumSection
        sampleId="t1"
        onSampleIdChange={() => {}}
        solvent="CDCl3"
        candidatesText="A | CCO"
      />
    )
    const input = screen.getByLabelText(/Processed spectrum file/i, { selector: "input" }) as HTMLInputElement

    expect(input.accept).toContain(".jcamp")
    expect(input.accept).toContain(".xy")
    expect(input.accept).toContain(".asc")
    expect(input.accept).toContain(".dat")
    expect(input.accept).not.toContain(".fid")
  })

  it("raw FID drop-zone opens the native file picker", () => {
    render(<SpectraCheckRawFidSection sampleId="t1" onSampleIdChange={() => {}} solvent="CDCl3" />)
    const input = screen.getByLabelText(/Raw FID archive/i, { selector: "input" }) as HTMLInputElement
    const clickSpy = vi.spyOn(input, "click").mockImplementation(() => undefined)

    fireEvent.click(screen.getByRole("button", { name: /Drop raw FID archive/i }))

    expect(clickSpy).toHaveBeenCalled()
    clickSpy.mockRestore()
  })

  it("raw FID picker includes every supported raw archive format", () => {
    render(<SpectraCheckRawFidSection sampleId="t1" onSampleIdChange={() => {}} solvent="CDCl3" />)
    const input = screen.getByLabelText(/Raw FID archive/i, { selector: "input" }) as HTMLInputElement

    expect(input.accept).toContain(".zip")
    expect(input.accept).toContain(".tar.gz")
    expect(input.accept).toContain(".tgz")
    expect(input.accept).not.toContain(".fid")
  })
})

describe("SpectrumViewer", () => {
  it("renders placeholder state without crashing when arrays are empty", () => {
    render(<SpectrumViewer x={[]} y={[]} />)
    expect(screen.getByText(/No spectrum loaded/i)).toBeInTheDocument()
  })

  it("exposes a bottom-toolbar move mode for dragging the spectrum", () => {
    render(<SpectrumViewer x={[5, 4, 3, 2, 1]} y={[0, 1, 0, 2, 0]} />)

    const moveButton = screen.getByRole("button", { name: /Move spectrum/i })
    expect(moveButton).toHaveAttribute("aria-pressed", "false")

    fireEvent.click(moveButton)
    expect(screen.getByRole("button", { name: /Disable spectrum move mode/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    )

    const pane = screen.getByTestId("spectrum-move-pane")
    vi.spyOn(pane, "getBoundingClientRect").mockReturnValue({
      bottom: 260,
      height: 240,
      left: 0,
      right: 500,
      top: 20,
      width: 500,
      x: 0,
      y: 20,
      toJSON: () => ({}),
    })
    Object.assign(pane, {
      setPointerCapture: vi.fn(),
      releasePointerCapture: vi.fn(),
    })

    fireEvent.pointerDown(pane, { button: 0, clientX: 100, pointerId: 1 })
    fireEvent.pointerMove(pane, { clientX: 180, pointerId: 1 })
    fireEvent.pointerUp(pane, { pointerId: 1 })
  })

  it("downsamples dense traces without dropping narrow spikes", () => {
    const x = Array.from({ length: 100_000 }, (_, i) => i)
    const y = Array.from({ length: 100_000 }, () => 0)
    y[12_345] = 1000

    const sampled = sampleSpectrumTraceForPlot(x, y, { maxPoints: 1000 })

    expect(sampled.sampled).toBe(true)
    expect(sampled.method).toBe("viewport_min_max_lttb")
    expect(sampled.x.length).toBeLessThanOrEqual(1000)
    expect(sampled.y).toContain(1000)
    expect(sampled.meanBinSize).toBeGreaterThan(1)
  })

  it("resamples only the active viewport range", () => {
    const x = Array.from({ length: 100_000 }, (_, i) => i)
    const y = Array.from({ length: 100_000 }, () => 0)
    y[12_345] = 1000
    y[50_000] = 5000

    const sampled = sampleSpectrumTraceForPlot(x, y, {
      maxPoints: 1000,
      xRange: [12_000, 13_000],
    })

    expect(sampled.sourceLength).toBe(100_000)
    expect(sampled.visibleLength).toBe(1001)
    expect(sampled.x.every((ppm) => ppm >= 12_000 && ppm <= 13_000)).toBe(true)
    expect(sampled.y).toContain(1000)
    expect(sampled.y).not.toContain(5000)
  })

  it("keeps a NaN gap when the dominant solvent range is masked", () => {
    const x = Array.from({ length: 100 }, (_, i) => i)
    const y = Array.from({ length: 100 }, (_, i) => i)

    const sampled = sampleSpectrumTraceForPlot(x, y, {
      maxPoints: 200,
      maskRange: { startIndex: 45, endIndex: 55 },
    })

    expect(sampled.sampled).toBe(false)
    expect(sampled.meanBinSize).toBeNull()
    expect(sampled.y.some((v) => Number.isNaN(v))).toBe(true)
  })
})
