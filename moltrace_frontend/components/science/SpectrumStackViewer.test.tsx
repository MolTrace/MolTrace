import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import {
  SpectrumStackViewer,
  envelopeSampleSpectrum,
  stackTraceColor,
  stackTraceDash,
  type SpectrumStackTrace,
} from "@/components/science/SpectrumStackViewer"

/** A flat baseline with one narrow peak — the feature a careless downsampler destroys. */
function spectrumWithPeak(id: string, peakPpm: number, height = 100): SpectrumStackTrace {
  const x: number[] = []
  const y: number[] = []
  for (let i = 0; i <= 10_000; i++) {
    const ppm = (i / 10_000) * 10
    x.push(ppm)
    y.push(Math.abs(ppm - peakPpm) < 0.002 ? height : 1)
  }
  return { id, label: id, x, y }
}

describe("envelope downsampling", () => {
  it("keeps a narrow peak at full height after reducing 10,000 points", () => {
    const trace = spectrumWithPeak("a", 7.26)
    const points = envelopeSampleSpectrum(trace.x, trace.y, { min: 0, max: 10 })
    expect(points.length).toBeLessThan(700)
    expect(Math.max(...points.map((p) => p.high))).toBe(100)
  })

  it("keeps the baseline band, not just the peaks", () => {
    const points = envelopeSampleSpectrum([0, 1, 2, 3], [-5, 5, -5, 5], { min: 0, max: 3 })
    expect(Math.min(...points.map((p) => p.low))).toBe(-5)
    expect(Math.max(...points.map((p) => p.high))).toBe(5)
  })

  it("drops points outside the requested window so a zoom rescales honestly", () => {
    const trace = spectrumWithPeak("a", 7.26)
    const points = envelopeSampleSpectrum(trace.x, trace.y, { min: 0, max: 2 })
    expect(Math.max(...points.map((p) => p.high))).toBe(1)
    expect(points.every((p) => p.ppm >= 0 && p.ppm <= 2)).toBe(true)
  })

  it("ignores non-finite samples rather than emitting a broken path", () => {
    const points = envelopeSampleSpectrum([0, 1, 2], [Number.NaN, 4, Number.POSITIVE_INFINITY], {
      min: 0,
      max: 2,
    })
    expect(points).toHaveLength(1)
    expect(points[0].high).toBe(4)
  })

  it("returns nothing for an empty trace or a collapsed window", () => {
    expect(envelopeSampleSpectrum([], [], { min: 0, max: 1 })).toEqual([])
    expect(envelopeSampleSpectrum([1], [1], { min: 5, max: 5 })).toEqual([])
  })
})

describe("SpectrumStackViewer", () => {
  const traces = [spectrumWithPeak("one", 7.26), spectrumWithPeak("two", 2.5, 40)]

  it("invites the user rather than rendering an empty frame when nothing has finished", () => {
    render(<SpectrumStackViewer traces={[]} />)
    expect(screen.getByTestId("spectrum-stack-viewer-empty")).toBeInTheDocument()
  })

  it("draws one path per spectrum on a shared axis", () => {
    render(<SpectrumStackViewer traces={traces} />)
    expect(screen.getByTestId("spectrum-stack-viewer-trace-one")).toBeInTheDocument()
    expect(screen.getByTestId("spectrum-stack-viewer-trace-two")).toBeInTheDocument()
  })

  it("puts high ppm on the left, the convention every NMR reader expects", () => {
    render(<SpectrumStackViewer traces={[spectrumWithPeak("one", 9.5)]} />)
    const d = screen.getByTestId("spectrum-stack-viewer-trace-one").getAttribute("d") ?? ""
    const firstX = Number(d.slice(1).split(" ")[0])
    const commands = d.split("L")
    const lastX = Number(commands[commands.length - 1].trim().split(" ")[0])
    // The path is emitted low-ppm-first, so its LAST point must sit further left than its first.
    expect(lastX).toBeLessThan(firstX)
  })

  it("scales each spectrum to its own peak so a weak one is still readable", () => {
    render(<SpectrumStackViewer traces={traces} />)
    const strong = screen.getByTestId("spectrum-stack-viewer-trace-one").getAttribute("d") ?? ""
    const weak = screen.getByTestId("spectrum-stack-viewer-trace-two").getAttribute("d") ?? ""
    const topOf = (d: string) => Math.min(...[...d.matchAll(/[ML][\d.]+ ([\d.]+)/g)].map((m) => Number(m[1])))
    // Both reach the same fraction of their own amplitude — a 40-high trace is not left flat
    // next to a 100-high one. Baselines differ by the cascade offset, so compare the rise.
    expect(topOf(weak)).toBeLessThan(400)
    expect(topOf(strong)).toBeLessThan(400)
  })

  it("puts every spectrum on one scale when the reviewer asks for it", () => {
    render(<SpectrumStackViewer traces={traces} />)
    const before = screen.getByTestId("spectrum-stack-viewer-trace-two").getAttribute("d")
    fireEvent.click(screen.getByTestId("spectrum-stack-viewer-shared-scale"))
    const after = screen.getByTestId("spectrum-stack-viewer-trace-two").getAttribute("d")
    expect(after).not.toBe(before)
  })

  it("collapses the cascade to a true overlay at zero offset", () => {
    render(<SpectrumStackViewer traces={traces} />)
    fireEvent.change(screen.getByTestId("spectrum-stack-viewer-cascade"), { target: { value: "0" } })
    expect(screen.getByText("overlay")).toBeInTheDocument()
  })

  it("hides and restores a spectrum without recolouring the others", () => {
    render(<SpectrumStackViewer traces={traces} />)
    const colorBefore = screen.getByTestId("spectrum-stack-viewer-trace-two").getAttribute("stroke")
    fireEvent.click(screen.getByTestId("spectrum-stack-viewer-toggle-one"))
    expect(screen.queryByTestId("spectrum-stack-viewer-trace-one")).not.toBeInTheDocument()
    expect(screen.getByTestId("spectrum-stack-viewer-trace-two").getAttribute("stroke")).toBe(colorBefore)
    fireEvent.click(screen.getByTestId("spectrum-stack-viewer-toggle-one"))
    expect(screen.getByTestId("spectrum-stack-viewer-trace-one")).toBeInTheDocument()
  })

  it("reports the selected spectrum when its legend entry is used", () => {
    const onSelect = vi.fn()
    render(<SpectrumStackViewer traces={traces} onSelectTrace={onSelect} />)
    fireEvent.click(screen.getByTestId("spectrum-stack-viewer-legend-two"))
    expect(onSelect).toHaveBeenCalledWith("two")
  })

  it("emphasises the active spectrum and dims the rest", () => {
    render(<SpectrumStackViewer traces={traces} activeTraceId="two" />)
    const active = screen.getByTestId("spectrum-stack-viewer-trace-two")
    const other = screen.getByTestId("spectrum-stack-viewer-trace-one")
    expect(active).toHaveAttribute("data-active", "true")
    expect(Number(other.getAttribute("opacity"))).toBeLessThan(1)
    expect(Number(active.getAttribute("stroke-width"))).toBeGreaterThan(
      Number(other.getAttribute("stroke-width")),
    )
  })

  it("gives assistive technology the axis it is showing", () => {
    render(<SpectrumStackViewer traces={traces} nucleus="13C" />)
    expect(screen.getByRole("img", { name: /13C chemical-shift axis/i })).toBeInTheDocument()
  })

  it("rotates colours so two spectra never share one", () => {
    expect(stackTraceColor(0)).not.toBe(stackTraceColor(1))
    expect(stackTraceColor(0)).toBe(stackTraceColor(8))
  })
})

describe("telling many traces apart", () => {
  it("gives trace 9 a different pen from trace 1, not just the same colour again", () => {
    // 8 colours, 64 datasets allowed. Colour alone repeats, and two identical blue lines are two
    // datasets the reviewer cannot separate — so the dash pattern carries the difference.
    expect(stackTraceColor(8)).toBe(stackTraceColor(0))
    expect(stackTraceDash(8)).not.toBe(stackTraceDash(0))
    expect(stackTraceDash(0)).toBe("")
  })

  it("names no nucleus on the axis when the datasets do not agree on one", () => {
    render(
      <SpectrumStackViewer
        traces={[
          { id: "a", label: "a", x: [1, 2, 3], y: [1, 5, 1] },
          { id: "b", label: "b", x: [1, 2, 3], y: [1, 4, 1] },
        ]}
        nucleus={null}
      />,
    )
    expect(screen.getByText("Chemical shift (ppm)")).toBeInTheDocument()
    expect(screen.queryByText(/¹H chemical shift/)).not.toBeInTheDocument()
    expect(screen.queryByText(/¹³C chemical shift/)).not.toBeInTheDocument()
  })

  it("can be zoomed and reset from the keyboard alone", () => {
    render(
      <SpectrumStackViewer
        traces={[{ id: "a", label: "a", x: [0, 1, 2, 3, 4], y: [1, 2, 9, 2, 1] }]}
        nucleus="1H"
      />,
    )
    const plot = screen.getByTestId("spectrum-stack-viewer-plot")
    // Reset is present but inert before zooming, so a keyboard user can see the way back exists.
    expect(screen.getByTestId("spectrum-stack-viewer-reset-zoom")).toBeDisabled()

    fireEvent.keyDown(plot, { key: "+" })
    expect(screen.getByTestId("spectrum-stack-viewer-reset-zoom")).toBeEnabled()

    fireEvent.keyDown(plot, { key: "0" })
    expect(screen.getByTestId("spectrum-stack-viewer-reset-zoom")).toBeDisabled()
  })

  it("reports a shown trace as pressed, so the state and the name agree", () => {
    render(
      <SpectrumStackViewer
        traces={[{ id: "a", label: "expt-33", x: [1, 2, 3], y: [1, 5, 1] }]}
        nucleus="1H"
      />,
    )
    const toggle = screen.getByTestId("spectrum-stack-viewer-toggle-a")
    expect(toggle).toHaveAttribute("aria-pressed", "true")
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute("aria-pressed", "false")
    // The name does not flip with the state — "Show X … pressed" announced the opposite.
    expect(toggle).toHaveAccessibleName("expt-33 shown in the stack")
  })
})
