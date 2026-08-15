import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { SpectrumViewer } from "@/components/science/SpectrumViewer"

/**
 * The single-spectrum half of the canvas gesture contract. The stack viewer's half lives in
 * SpectrumStackViewer.test.tsx; the shared maths in lib/science/canvas-interaction.test.ts.
 * Plotly never renders under jsdom, so the captured `layout` prop is the observable truth for
 * what the user's view would be.
 */
const captured = vi.hoisted(() => ({ layouts: [] as Array<Record<string, unknown>> }))

vi.mock("next/dynamic", () => ({
  default: () =>
    function PlotStub(props: Record<string, unknown>) {
      captured.layouts.push(props.layout as Record<string, unknown>)
      return <div data-testid="plotly-stub" />
    },
}))

function trace(length = 2000) {
  const x: number[] = new Array(length)
  const y: number[] = new Array(length)
  for (let i = 0; i < length; i++) {
    x[i] = 10 - (i / (length - 1)) * 10
    y[i] = i % 97 === 0 ? 50 : 1
  }
  return { x, y }
}

function xAxisRange(): [number, number] | undefined {
  const layout = captured.layouts[captured.layouts.length - 1]
  const xaxis = layout?.xaxis as { range?: [number, number] } | undefined
  return xaxis?.range
}

function mockPaneRect(pane: HTMLElement) {
  vi.spyOn(pane, "getBoundingClientRect").mockReturnValue({
    bottom: 380,
    height: 360,
    left: 0,
    right: 800,
    top: 20,
    width: 800,
    x: 0,
    y: 20,
    toJSON: () => ({}),
  } as DOMRect)
  Object.assign(pane, { setPointerCapture: vi.fn(), releasePointerCapture: vi.fn() })
  return pane
}

describe("canvas gesture contract — single-spectrum viewer", () => {
  it("pans on a plain mouse drag with no mode enabled", () => {
    const { x, y } = trace()
    render(<SpectrumViewer x={x} y={y} nucleus="1H" />)
    const pane = mockPaneRect(screen.getByTestId("spectrum-move-pane"))

    const before = xAxisRange()
    fireEvent.pointerDown(pane, { button: 0, pointerType: "mouse", clientX: 400, pointerId: 1 })
    fireEvent.pointerMove(pane, { clientX: 320, pointerId: 1 })
    fireEvent.pointerUp(pane, { pointerId: 1 })

    // The pan commits through a requestAnimationFrame; the pointer-up flush makes it sync.
    expect(xAxisRange()).not.toEqual(before)
  })

  it("still leaves touch drags to the page unless Move mode is on", () => {
    const { x, y } = trace()
    render(<SpectrumViewer x={x} y={y} nucleus="1H" />)
    const pane = mockPaneRect(screen.getByTestId("spectrum-move-pane"))

    const before = xAxisRange()
    fireEvent.pointerDown(pane, { button: 0, pointerType: "touch", clientX: 400, pointerId: 1 })
    fireEvent.pointerMove(pane, { clientX: 250, pointerId: 1 })
    fireEvent.pointerUp(pane, { pointerId: 1 })

    expect(xAxisRange()).toEqual(before)
  })

  it("zooms to the shift-dragged window, and 0 restores the full range", () => {
    const { x, y } = trace()
    render(<SpectrumViewer x={x} y={y} nucleus="1H" />)
    const pane = mockPaneRect(screen.getByTestId("spectrum-move-pane"))

    const before = xAxisRange()
    fireEvent.pointerDown(pane, {
      button: 0,
      pointerType: "mouse",
      shiftKey: true,
      clientX: 200,
      pointerId: 1,
    })
    fireEvent.pointerMove(pane, { clientX: 600, pointerId: 1 })
    // The selection band renders while the chord is held — proof the gesture is visible.
    expect(screen.getByTestId("spectrum-zoom-band")).toBeInTheDocument()
    fireEvent.pointerUp(pane, { clientX: 600, pointerId: 1 })

    const zoomed = xAxisRange()
    expect(zoomed).not.toEqual(before)
    // A window a quarter-pane wide is far narrower than the full sweep.
    expect(Math.abs((zoomed![1] as number) - (zoomed![0] as number))).toBeLessThan(9)

    fireEvent.keyDown(pane, { key: "0" })
    expect(xAxisRange()).toEqual(before)
  })

  it("pans and zooms from the keyboard through the shared keymap", () => {
    const { x, y } = trace()
    render(<SpectrumViewer x={x} y={y} nucleus="1H" />)
    const pane = mockPaneRect(screen.getByTestId("spectrum-move-pane"))

    const before = xAxisRange()
    fireEvent.keyDown(pane, { key: "+" })
    const zoomed = xAxisRange()
    expect(zoomed).not.toEqual(before)

    fireEvent.keyDown(pane, { key: "ArrowLeft" })
    expect(xAxisRange()).not.toEqual(zoomed)

    fireEvent.keyDown(pane, { key: "0" })
    expect(xAxisRange()).toEqual(before)
  })

  it("Escape cancels a drag and never resets the zoom", () => {
    const { x, y } = trace()
    render(<SpectrumViewer x={x} y={y} nucleus="1H" />)
    const pane = mockPaneRect(screen.getByTestId("spectrum-move-pane"))

    fireEvent.keyDown(pane, { key: "+" })
    const zoomed = xAxisRange()

    // Esc mid-shift-drag abandons the selection band…
    fireEvent.pointerDown(pane, {
      button: 0,
      pointerType: "mouse",
      shiftKey: true,
      clientX: 200,
      pointerId: 2,
    })
    fireEvent.pointerMove(pane, { clientX: 500, pointerId: 2 })
    fireEvent.keyDown(pane, { key: "Escape" })
    expect(screen.queryByTestId("spectrum-zoom-band")).not.toBeInTheDocument()

    // …and the zoom the reviewer was inside is untouched.
    expect(xAxisRange()).toEqual(zoomed)
  })

  it("adjusts intensity with the wheel only while the canvas has focus", () => {
    const { x, y } = trace()
    const { container } = render(<SpectrumViewer x={x} y={y} nucleus="1H" />)
    const pane = mockPaneRect(screen.getByTestId("spectrum-move-pane"))

    // The scale chip shows gain × yZoom, so it moves iff the wheel landed.
    const scaleChip = () =>
      (container.querySelector('[title^="Total scale"]') as HTMLElement | null)?.title ?? ""

    const before = scaleChip()
    fireEvent.wheel(pane, { deltaY: -300 })
    // Unfocused: the wheel is the page's, not the canvas's.
    expect(scaleChip()).toBe(before)

    pane.focus()
    fireEvent.wheel(pane, { deltaY: -300 })
    expect(scaleChip()).not.toBe(before)
  })
})
