import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { SpectrumViewer1D } from "@/components/science/SpectrumViewer1D"
import { sampleSpectrumTraceForPlot } from "@/components/science/SpectrumViewer"

/**
 * Capture what the viewer actually hands to Plotly. jsdom never renders the real chart, so the
 * captured `data` prop is the ground truth for what a user would see.
 */
const captured = vi.hoisted(() => ({ calls: [] as unknown[] }))

vi.mock("next/dynamic", () => ({
  default: () =>
    function PlotStub(props: Record<string, unknown>) {
      captured.calls.push(props.data)
      return <div data-testid="plotly-stub" />
    },
}))

/**
 * A realistic worst case for a decimator: a flat-zero baseline holding ONE narrow singlet —
 * three points wide, like a sharp 1H line in a 64k-point spectrum. Any sampler that drops it has
 * visually deleted the only feature in the spectrum.
 *
 * The apex index is chosen so no singlet point falls on a multiple of the old stride
 * (ceil(65536/5000) = 14): a stride sampler provably returns all zeros for this fixture.
 */
function singletFixture(length = 65536, apexIndex = 32771) {
  const x: number[] = new Array(length)
  const y: number[] = new Array(length).fill(0)
  for (let i = 0; i < length; i++) x[i] = 10 - (i / (length - 1)) * 10 // 10 → 0 ppm
  y[apexIndex - 1] = 50
  y[apexIndex] = 100
  y[apexIndex + 1] = 50
  return { x, y, apexPpm: x[apexIndex] }
}

function lastPrimaryTrace(): { x: number[]; y: number[] } {
  const data = captured.calls[captured.calls.length - 1] as Array<{ x: number[]; y: number[] }>
  expect(Array.isArray(data)).toBe(true)
  expect(data.length).toBeGreaterThan(0)
  return data[0]
}

describe("SpectrumViewer1D display downsampling", () => {
  it("never deletes the only peak in the spectrum", () => {
    const { x, y } = singletFixture()
    render(<SpectrumViewer1D x={x} y={y} nucleus="1H" />)

    const trace = lastPrimaryTrace()
    // Downsampling genuinely engaged — this is not a pass-through of 64k points…
    expect(trace.y.length).toBeLessThan(6000)
    // …and the singlet survived it. The baseline is exactly zero, so if the sampler dropped the
    // peak, the whole trace is zeros and the spectrum renders as an empty line.
    expect(Math.max(...trace.y)).toBeGreaterThan(0)
  })

  it("tells the user the trace was downsampled", () => {
    const { x, y } = singletFixture()
    render(<SpectrumViewer1D x={x} y={y} nucleus="1H" />)
    expect(screen.getByText(/downsampled/i)).toBeInTheDocument()
  })
})

describe("the shared sampler keeps a narrow peak at every zoom", () => {
  it("retains the singlet apex for full range and for progressively tighter windows", () => {
    const { x, y, apexPpm } = singletFixture()
    // From the full sweep down to a window a fraction of a ppm wide — wherever the apex is in
    // view, its full height must survive sampling.
    const windows: Array<[number, number] | undefined> = [
      undefined,
      [apexPpm - 2.5, apexPpm + 2.5],
      [apexPpm - 0.5, apexPpm + 0.5],
      [apexPpm - 0.05, apexPpm + 0.05],
    ]
    for (const xRange of windows) {
      const sampled = sampleSpectrumTraceForPlot(x, y, { maxPoints: 1600, xRange: xRange ?? null })
      expect(Math.max(...sampled.y)).toBe(100)
    }
  })
})
