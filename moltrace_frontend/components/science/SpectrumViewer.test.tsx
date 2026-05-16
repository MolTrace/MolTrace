import { describe, expect, it, vi } from "vitest"
import { render } from "@testing-library/react"

import { SpectrumViewer } from "@/components/science/SpectrumViewer"

/**
 * Plotly is dynamically imported so this mock captures whatever ``data`` prop
 * is handed to the underlying Plot component. Each test then asserts on the
 * trace list (markers, drop-lines, per-category groups) without ever spinning
 * up react-plotly in jsdom.
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
    showlegend?: boolean
  }>
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

  it("emits no peak traces when peaks=[]", () => {
    freshRender(<SpectrumViewer {...baseProps} />)
    const traces = capturedPlotProps?.data ?? []
    // Only the observed-line trace; no drop-line trace, no marker trace.
    expect(traces).toHaveLength(1)
    expect(traces[0].name).toMatch(/Observed/)
  })

  it("adds a drop-line trace and one marker trace per category when peaks are supplied", () => {
    freshRender(
      <SpectrumViewer
        {...baseProps}
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
    // 1 observed line + 1 drop-line + 3 category groups (aromatic_alkene,
    // oxygenated, aliphatic — the two aromatic peaks share a single trace).
    expect(traces.length).toBe(5)
    expect(names).toContain("Peak markers")
    expect(names).toContain("Aromatic alkene")
    expect(names).toContain("Oxygenated")
    expect(names).toContain("Aliphatic")
  })

  it("draws drop-lines from y=0 to each peak intensity", () => {
    freshRender(
      <SpectrumViewer
        {...baseProps}
        peaks={[
          { ppm: 7.26, intensity: 1.0, category: "aromatic_alkene" },
          { ppm: 1.26, intensity: 0.6, category: "aliphatic" },
        ]}
      />,
    )
    const traces = capturedPlotProps?.data ?? []
    const dropTrace = traces.find((t) => t.name === "Peak markers")
    expect(dropTrace).toBeDefined()
    expect(dropTrace?.mode).toBe("lines")
    // Drop-line trace alternates [baseline, peakY, null] per peak.
    expect(dropTrace?.y).toEqual([0, 1.0, null, 0, 0.6, null])
    expect(dropTrace?.x).toEqual([7.26, 7.26, null, 1.26, 1.26, null])
    // Drop-line is not in the legend so it doesn't clutter category toggles.
    expect(dropTrace?.showlegend).toBe(false)
  })

  it("uses the per-category palette for marker colors", () => {
    freshRender(
      <SpectrumViewer
        {...baseProps}
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
    expect(aromatic?.marker?.color).toBe("#00B884") // teal
    expect(labile?.marker?.color).toBe("#E8A030") // amber
    expect(aliphatic?.marker?.color).toBe("#22C55E") // green
  })

  it("falls back to the default color when a peak has no category", () => {
    freshRender(
      <SpectrumViewer
        {...baseProps}
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
        peaks={[
          { ppm: 1.26, intensity: 0.6, category: "aliphatic" },
          { ppm: 7.26, intensity: 1.0, category: "aromatic_alkene" },
          { ppm: 11.5, intensity: 0.1, category: "labile_OH_NH_SH" },
        ]}
      />,
    )
    const traces = capturedPlotProps?.data ?? []
    // Filter to just the marker traces (skip observed line + drop-line) and
    // check their order is alphabetical: Aliphatic < Aromatic alkene < Labile.
    const markerNames = traces
      .filter((t) => t.mode === "markers+text")
      .map((t) => t.name)
    expect(markerNames).toEqual(["Aliphatic", "Aromatic alkene", "Labile OH / NH / SH"])
  })
})
