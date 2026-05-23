import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import {
  SpectrumViewer,
  chemicalShiftFromPlotPointer,
  nearestSourcePointAtPpm,
  smoothRawFidAromaticBaseForDisplay,
} from "@/components/science/SpectrumViewer"

/**
 * Plotly is dynamically imported so this mock captures whatever ``data`` prop
 * is handed to the underlying Plot component. Each test then asserts on the
 * trace list (markers and per-category groups) plus layout shape guide-lines
 * without ever spinning up react-plotly in jsdom.
 */
type CapturedPlotProps = {
  data?: Array<{
    type?: string
    mode?: string
    name?: string
    x?: unknown[]
    y?: unknown[]
    line?: { color?: string }
    marker?: { color?: string }
    hovertext?: unknown[]
    showlegend?: boolean
    connectgaps?: boolean
  }>
  layout?: {
    uirevision?: unknown
    showlegend?: boolean
    shapes?: Array<{
      type?: string
      x0?: number
      x1?: number
      y0?: number
      y1?: number
      layer?: string
      line?: { color?: string; width?: number }
    }>
    annotations?: Array<{
      x?: number
      y?: number
      text?: string
      textangle?: number
      showarrow?: boolean
      font?: { color?: string; size?: number }
    }>
    yaxis?: {
      range?: number[]
      zeroline?: boolean
    }
  }
}
let capturedPlotProps: CapturedPlotProps | null = null

vi.mock("next/dynamic", () => ({
  __esModule: true,
  default: () =>
    function PlotMock(props: CapturedPlotProps) {
      capturedPlotProps = props
      return <div data-testid="plotly-mock" />
    },
}))

function freshRender(ui: React.ReactElement) {
  capturedPlotProps = null
  return render(ui)
}

describe("SpectrumViewer — picked-peak rendering", () => {
  const baseProps = {
    x: [3.7, 1.3, 7.3],
    y: [0.1, 0.2, 0.05],
    nucleus: "1H" as const,
  }
  const visiblePeakOverlayDefaults = {
    defaultShowPeaks: true,
    defaultShowPeakGuides: true,
  }

  it("emits no peak traces when peaks=[]", () => {
    freshRender(<SpectrumViewer {...baseProps} />)
    const traces = capturedPlotProps?.data ?? []
    // Only the observed-line trace; no marker trace.
    expect(traces).toHaveLength(1)
    expect(traces[0].name).toMatch(/Observed/)
    expect(capturedPlotProps?.layout?.shapes).toHaveLength(0)
    // No peaks → no Mnova-style apex tick annotations either.
    expect(capturedPlotProps?.layout?.annotations ?? []).toHaveLength(0)
  })

  it("keeps lower y-axis headroom so the baseline is not clipped at zero", () => {
    freshRender(<SpectrumViewer x={[3, 2, 1]} y={[0, 1, 0]} />)

    const yRange = capturedPlotProps?.layout?.yaxis?.range
    expect(yRange?.[0]).toBeLessThan(0)
    expect(yRange?.[1]).toBeGreaterThan(1)
    expect(capturedPlotProps?.layout?.yaxis?.zeroline).toBe(true)
  })

  it("sets a stable Plotly uirevision so redraws preserve the current viewport", () => {
    freshRender(<SpectrumViewer x={[3, 2, 1]} y={[0, 1, 0]} />)

    expect(capturedPlotProps?.layout?.uirevision).toBe("spectrum")
  })

  it("uses Plotly WebGL for raw FID render mode without connecting gaps", () => {
    freshRender(<SpectrumViewer x={[3, 2, 1]} y={[0, Number.NaN, 0.2]} renderMode="webgl" />)

    const traces = capturedPlotProps?.data ?? []
    expect(traces[0].type).toBe("scattergl")
    expect(traces[0].connectgaps).toBe(false)
  })

  it("lets raw FID opt into a denser display budget for resolved multiplets", () => {
    const x = Array.from({ length: 5000 }, (_unused, index) => 10 - index * 0.001)
    const y = Array.from({ length: 5000 }, (_unused, index) =>
      index % 127 === 0 ? 10 : Math.sin(index * 0.2) * 0.01,
    )

    freshRender(<SpectrumViewer x={x} y={y} />)
    expect(capturedPlotProps?.data?.[0]?.name).toMatch(/\[R\]/)

    freshRender(
      <SpectrumViewer
        x={x}
        y={y}
        renderMode="webgl"
        maxObservedPoints={12_000}
        observedPointsPerPixel={24}
      />,
    )

    const trace = capturedPlotProps?.data?.[0]
    expect(trace?.type).toBe("scattergl")
    expect(trace?.name).toBe("Observed")
    expect(trace?.x).toHaveLength(5000)
  })

  it("keeps negative baseline excursions inside the initial y-axis range", () => {
    freshRender(<SpectrumViewer x={[4, 3, 2, 1]} y={[-0.2, 0.1, 1, -0.1]} />)

    const yRange = capturedPlotProps?.layout?.yaxis?.range
    expect(yRange?.[0]).toBeLessThan(-0.2)
    expect(yRange?.[1]).toBeGreaterThan(1)
  })

  it("clips pathological negative dispersion lobes below the visible frame (Mnova-style)", () => {
    // Synthetic baseline noise on [-0.05, +0.05] plus a single deep
    // dispersion lobe at index 4 — the kind of artefact that haunts the
    // solvent/aromatic windows when a Bruker FID is processed without
    // careful phase correction. Mestrenova clips such lobes below the
    // frame (manual §8.2.2: "Peaks Type: Only Positive") so the displayed
    // baseline stays flat instead of being punched through.
    const xs = Array.from({ length: 200 }, (_, i) => 10 - i * 0.05)
    const ys = Array.from({ length: 200 }, (_, i) =>
      i === 4 ? -8 : ((i * 9301 + 49297) % 233 - 116) / 2000,
    )
    freshRender(<SpectrumViewer x={xs} y={ys} />)
    const yRange = capturedPlotProps?.layout?.yaxis?.range ?? [0, 0]
    // The frame's bottom must be far above the -8 artefact — otherwise
    // the dispersion lobe would extend down into the visible chart and
    // protrude through the baseline.
    expect(yRange[0]).toBeGreaterThan(-1)
    // …but the honest baseline noise (~±0.05) must still be inside the
    // visible frame, not clipped at zero like Magnitude mode would do.
    expect(yRange[0]).toBeLessThan(0)
  })

  it("adds shape guide-lines and one marker trace per category when peaks are supplied", () => {
    freshRender(
      <SpectrumViewer
        {...baseProps}
        {...visiblePeakOverlayDefaults}
        peaks={[
          { ppm: 7.26, intensity: 1.0, label: "Ar-H", category: "aromatic_alkene" },
          { ppm: 3.65, intensity: 0.8, label: "CH2-O", category: "oxygenated" },
          { ppm: 1.26, intensity: 0.6, label: "CH3", category: "aliphatic" },
          { ppm: 7.55, intensity: 0.9, label: "Ar-H2", category: "aromatic_alkene" },
        ]}
      />,
    )
    const traces = capturedPlotProps?.data ?? []
    const names = traces.map((t) => t.name)
    // 1 observed line + 3 category groups (aromatic_alkene,
    // oxygenated, aliphatic — the two aromatic peaks share a single trace).
    expect(traces.length).toBe(4)
    expect(names).not.toContain("Peak markers")
    expect(names).toContain("Aromatic alkene")
    expect(names).toContain("Oxygenated")
    expect(names).toContain("Aliphatic")
    // Layout shapes per peak = drop-line (below the apex) + apex tick
    // (above the apex, up to the common label row). 4 peaks → 8 shapes.
    expect(capturedPlotProps?.layout?.shapes).toHaveLength(8)
    // One rotated ppm annotation per peak (Mestrenova-style stick label).
    expect(capturedPlotProps?.layout?.annotations).toHaveLength(4)
  })

  it("draws drop-line guides from y=0 to each peak apex (Mnova-style under-the-trace cue)", () => {
    freshRender(
      <SpectrumViewer
        {...baseProps}
        {...visiblePeakOverlayDefaults}
        peaks={[
          { ppm: 7.26, intensity: 1.0, category: "aromatic_alkene" },
          { ppm: 1.26, intensity: 0.6, category: "aliphatic" },
        ]}
      />,
    )
    const shapes = capturedPlotProps?.layout?.shapes ?? []
    // 2 drop-lines + 2 apex ticks = 4 total shapes.
    expect(shapes).toHaveLength(4)
    // The first two shapes are the drop-lines from baseline up to each apex.
    expect(shapes[0]).toMatchObject({
      type: "line",
      x0: 7.26,
      x1: 7.26,
      y0: 0,
      y1: 1.0,
      layer: "below",
    })
    expect(shapes[1]).toMatchObject({
      type: "line",
      x0: 1.26,
      x1: 1.26,
      y0: 0,
      y1: 0.6,
      layer: "below",
    })
  })

  it("defaults peak markers/legend and vertical peak guide lines off, then exposes both in the right-click menu", async () => {
    const { getByTestId, queryByRole } = freshRender(
      <SpectrumViewer
        {...baseProps}
        peaks={[
          { ppm: 7.26, intensity: 1.0, category: "aromatic_alkene" },
          { ppm: 1.26, intensity: 0.6, category: "aliphatic" },
        ]}
      />,
    )

    expect(capturedPlotProps?.layout?.shapes).toHaveLength(0)
    expect(capturedPlotProps?.layout?.annotations).toHaveLength(0)
    expect(capturedPlotProps?.layout?.showlegend).toBe(false)
    expect(capturedPlotProps?.data?.map((trace) => trace.name)).toEqual(["Observed"])
    expect(queryByRole("switch", { name: /vertical peak guide lines/i })).toBeNull()

    fireEvent.contextMenu(getByTestId("plotly-mock"))
    const guidesItem = await screen.findByRole("menuitemcheckbox", { name: /vertical peak guides/i })
    expect(guidesItem).toHaveAttribute("aria-checked", "false")
    fireEvent.click(guidesItem)

    await waitFor(() => {
      expect(capturedPlotProps?.layout?.shapes).toHaveLength(4)
      expect(capturedPlotProps?.layout?.annotations).toHaveLength(2)
    })
    expect(screen.getByRole("menu", { name: /spectrum/i })).toBeInTheDocument()
    expect(screen.getByRole("menuitemcheckbox", { name: /vertical peak guides/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: /peak markers and legend/i }))

    const traces = capturedPlotProps?.data ?? []
    expect(capturedPlotProps?.layout?.showlegend).toBe(true)
    expect(traces.map((trace) => trace.name)).toEqual([
      "Observed",
      "Aliphatic",
      "Aromatic alkene",
    ])
  })

  it("keeps the right-click spectrum menu inside the viewport", async () => {
    const originalWidth = window.innerWidth
    const originalHeight = window.innerHeight
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 260 })
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 220 })

    const { getByTestId } = freshRender(
      <SpectrumViewer
        {...baseProps}
        peaks={[
          { ppm: 7.26, intensity: 1.0, category: "aromatic_alkene" },
          { ppm: 1.26, intensity: 0.6, category: "aliphatic" },
        ]}
      />,
    )

    fireEvent.contextMenu(getByTestId("plotly-mock"), { clientX: 259, clientY: 219 })

    const menu = await screen.findByRole("menu", { name: /spectrum/i })
    expect(menu).toHaveStyle({ left: "12px", top: "8px", maxHeight: "204px" })

    Object.defineProperty(window, "innerWidth", { configurable: true, value: originalWidth })
    Object.defineProperty(window, "innerHeight", { configurable: true, value: originalHeight })
  })

  it("renders Mnova-style apex ticks + rotated ppm labels for each picked peak", () => {
    // Spectrum y range must encompass both peak apices so the apex ticks
    // have meaningful length up to the common label row — mimics a real
    // 1H spectrum where peaks sit comfortably below the chart's top edge.
    const xs = [10, 7.26, 5, 1.26, 0]
    const ys = [0.0, 1.0, 0.05, 0.6, 0.0]
    freshRender(
      <SpectrumViewer
        x={xs}
        y={ys}
        nucleus="1H"
        {...visiblePeakOverlayDefaults}
        peaks={[
          { ppm: 7.26, intensity: 1.0, category: "aromatic_alkene" },
          { ppm: 1.26, intensity: 0.6, category: "aliphatic" },
        ]}
      />,
    )
    const shapes = capturedPlotProps?.layout?.shapes ?? []
    // Apex ticks sit at indices [2, 3] (after the two drop-lines).
    const tickA = shapes[2]
    const tickB = shapes[3]
    // Both ticks share the same upper y (the common label row).
    expect(tickA?.x0).toBe(7.26)
    expect(tickB?.x0).toBe(1.26)
    expect(tickA?.y1).toBe(tickB?.y1)
    // Each tick starts at its peak apex and rises up to the label row.
    expect(tickA?.y0).toBe(1.0)
    expect(tickB?.y0).toBe(0.6)
    expect(tickA?.y1).toBeGreaterThan(1.0)
    // Annotations carry the rotated ppm labels, two-decimal format.
    const annotations = capturedPlotProps?.layout?.annotations ?? []
    expect(annotations).toHaveLength(2)
    const annA = annotations.find((a) => a.x === 7.26)
    const annB = annotations.find((a) => a.x === 1.26)
    expect(annA?.text).toBe("7.26")
    expect(annB?.text).toBe("1.26")
    // Mnova writes the stick label rotated 90° (vertical).
    expect(annA?.textangle).toBe(-90)
    expect(annB?.textangle).toBe(-90)
    expect(annA?.showarrow).toBe(false)
  })

  it("uses the per-category palette for marker colors", () => {
    freshRender(
      <SpectrumViewer
        {...baseProps}
        {...visiblePeakOverlayDefaults}
        peaks={[
          { ppm: 7.26, intensity: 1.0, category: "aromatic_alkene" },
          { ppm: 11.5, intensity: 0.1, category: "labile_OH_NH_SH" },
          { ppm: 1.26, intensity: 0.6, category: "aliphatic" },
        ]}
      />,
    )
    const traces = capturedPlotProps?.data ?? []
    const aromatic = traces.find((t) => t.name === "Aromatic alkene")
    const labile = traces.find((t) => t.name === "Labile OH / NH / SH")
    const aliphatic = traces.find((t) => t.name === "Aliphatic")
    expect(aromatic?.marker?.color).toBe("#00A6A6")
    expect(labile?.marker?.color).toBe("#A16207")
    expect(aliphatic?.marker?.color).toBe("#65A30D")
  })

  it("falls back to the default color when a peak has no category", () => {
    freshRender(
      <SpectrumViewer
        {...baseProps}
        {...visiblePeakOverlayDefaults}
        peaks={[{ ppm: 3.65, intensity: 1.0 }]}
      />,
    )
    const traces = capturedPlotProps?.data ?? []
    // No category → bucket key is "unknown" → fallback orange.
    const unknownTrace = traces.find((t) => t.name === "Unknown")
    expect(unknownTrace).toBeDefined()
    expect(unknownTrace?.marker?.color).toBe("#EA580C")
  })

  it("keeps the trace list ordered alphabetically by category so the legend is stable", () => {
    freshRender(
      <SpectrumViewer
        {...baseProps}
        {...visiblePeakOverlayDefaults}
        peaks={[
          { ppm: 1.26, intensity: 0.6, category: "aliphatic" },
          { ppm: 7.26, intensity: 1.0, category: "aromatic_alkene" },
          { ppm: 11.5, intensity: 0.1, category: "labile_OH_NH_SH" },
        ]}
      />,
    )
    const traces = capturedPlotProps?.data ?? []
    // Filter to just the marker traces (skip the observed line) and
    // check their order is alphabetical: Aliphatic < Aromatic alkene < Labile.
    // The per-peak labels now live in layout annotations (Mnova-style
    // rotated stick labels), so the marker traces themselves are pure
    // ``markers`` rather than ``markers+text``.
    const markerNames = traces
      .filter((t) => t.mode === "markers")
      .map((t) => t.name)
    expect(markerNames).toEqual(["Aliphatic", "Aromatic alkene", "Labile OH / NH / SH"])
  })
})

describe("SpectrumViewer — hover chemical shift mapping", () => {
  it("maps pointer position to the exact reversed x-axis ppm scale", () => {
    const left = chemicalShiftFromPlotPointer({
      pointerX: 52,
      paneWidth: 1000,
      effectiveXMin: 0,
      effectiveXMax: 10,
      reversedXAxis: true,
    })
    const middle = chemicalShiftFromPlotPointer({
      pointerX: (52 + 984) / 2,
      paneWidth: 1000,
      effectiveXMin: 0,
      effectiveXMax: 10,
      reversedXAxis: true,
    })
    const right = chemicalShiftFromPlotPointer({
      pointerX: 984,
      paneWidth: 1000,
      effectiveXMin: 0,
      effectiveXMax: 10,
      reversedXAxis: true,
    })

    expect(left?.ppm).toBeCloseTo(10)
    expect(middle?.ppm).toBeCloseTo(5)
    expect(right?.ppm).toBeCloseTo(0)
  })

  it("maps pointer position to the exact normal x-axis ppm scale", () => {
    const left = chemicalShiftFromPlotPointer({
      pointerX: 52,
      paneWidth: 1000,
      effectiveXMin: 0,
      effectiveXMax: 10,
      reversedXAxis: false,
    })
    const right = chemicalShiftFromPlotPointer({
      pointerX: 984,
      paneWidth: 1000,
      effectiveXMin: 0,
      effectiveXMax: 10,
      reversedXAxis: false,
    })

    expect(left?.ppm).toBeCloseTo(0)
    expect(right?.ppm).toBeCloseTo(10)
  })

  it("uses Plotly's rendered x-axis converter when available", () => {
    const plotlyXAxis = {
      _offset: 80,
      _length: 800,
      p2l: (px: number) => 10 - px / 80,
    }
    const middle = chemicalShiftFromPlotPointer({
      pointerX: 480,
      paneWidth: 1000,
      effectiveXMin: 0,
      effectiveXMax: 10,
      reversedXAxis: true,
      plotlyXAxis,
    })

    expect(middle?.crosshairLeft).toBe(480)
    expect(middle?.ppm).toBeCloseTo(5)
  })

  it("uses source data, not downsampled display points, for nearby intensity lookup", () => {
    const point = nearestSourcePointAtPpm([10, 9, 8, 7], [0, 3, 12, 1], 8.2)

    expect(point).toMatchObject({ index: 2, ppm: 8, intensity: 12 })
  })

  it("keeps masked solvent-region intensity hidden while leaving ppm exact", () => {
    const point = nearestSourcePointAtPpm(
      [60, 50, 49, 48, 40],
      [1, 10, 100, 10, 1],
      49.2,
      { startIndex: 1, endIndex: 3 },
    )

    expect(point?.ppm).toBe(49)
    expect(Number.isNaN(point?.intensity)).toBe(true)
  })
})

describe("SpectrumViewer — raw FID aromatic base display smoothing", () => {
  it("smooths only aromatic base samples while preserving peak apices and outside regions", () => {
    const x = [
      9.0, 8.55, 8.45, 8.35, 8.25, 8.15, 8.05, 7.95, 7.85, 7.75,
      7.65, 7.55, 7.45, 7.35, 7.25, 7.15, 7.05, 6.95, 6.0,
    ]
    const y = [
      99, 0.1, -2.2, 0.2, 0.0, 0.1, 30, -3.0, 0.2, 0.1,
      5.0, 0.0, -1.6, 0.1, 0.0, 0.2, 0.1, 0.0, -9,
    ]

    const smoothed = smoothRawFidAromaticBaseForDisplay(x, y)

    expect(smoothed[0]).toBe(y[0])
    expect(smoothed[18]).toBe(y[18])
    expect(smoothed[6]).toBe(y[6])
    expect(smoothed[10]).toBe(y[10])
    expect(smoothed[2]).toBeGreaterThan(y[2])
    expect(smoothed[7]).toBeGreaterThan(y[7])
    expect(smoothed[12]).toBeGreaterThan(y[12])
  })

  it("applies the aromatic base cleanup only when explicitly enabled", () => {
    const x = [
      8.55, 8.45, 8.35, 8.25, 8.15, 8.05, 7.95, 7.85, 7.75, 7.65,
      7.55, 7.45, 7.35, 7.25, 7.15, 7.05,
    ]
    const y = [0, -2.4, 0.1, 0, 24, -3.1, 0.2, 0, 4.5, 0, -1.7, 0, 0.1, 0, 0.2, 0]

    freshRender(<SpectrumViewer x={x} y={y} renderMode="webgl" />)
    const rawTraceY = capturedPlotProps?.data?.[0]?.y as number[] | undefined
    expect(rawTraceY).toContain(-3.1)

    freshRender(<SpectrumViewer x={x} y={y} renderMode="webgl" rawFidAromaticBaseSmoothing />)
    const smoothedTraceY = capturedPlotProps?.data?.[0]?.y as number[] | undefined
    expect(smoothedTraceY?.some((value) => Number.isFinite(value) && value < -2)).toBe(false)
    expect(smoothedTraceY).toContain(24)
  })
})
