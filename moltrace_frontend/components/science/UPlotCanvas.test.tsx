import { afterEach, describe, expect, it, vi } from "vitest"
import { act, render, waitFor } from "@testing-library/react"
import { UPlotCanvas } from "@/components/science/UPlotCanvas"

afterEach(() => {
  vi.restoreAllMocks()
})

describe("UPlotCanvas", () => {
  it("renders a container div with the expected testid", () => {
    const { getByTestId } = render(
      <UPlotCanvas x={[1, 2, 3]} y={[0, 5, 0]} height={300} />,
    )
    const container = getByTestId("uplot-spectrum-canvas")
    expect(container).toBeInTheDocument()
  })

  it("creates a uPlot canvas inside the container once width becomes positive", async () => {
    // jsdom returns clientWidth=0 by default. Patch HTMLElement so the
    // mount-gate that waits for a positive width can proceed.
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get() {
        return 720
      },
    })
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get() {
        return 400
      },
    })

    const { getByTestId } = render(
      <UPlotCanvas x={[10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]} y={[0, 0, 1, 5, 1, 0, 0, 2, 0, 0, 0]} height={400} />,
    )
    const container = getByTestId("uplot-spectrum-canvas")
    expect(container).toBeInTheDocument()

    // uPlot loads asynchronously (dynamic import). Wait for the canvas
    // element to be appended by uPlot itself.
    await waitFor(
      () => {
        expect(container.querySelector("canvas")).not.toBeNull()
      },
      { timeout: 4000 },
    )
  })

  it("mounts the canvas even when the container width starts at 0", async () => {
    // Default jsdom — clientWidth=0. The component must mount uPlot anyway
    // with a fallback width, otherwise the chart silently never renders.
    const { getByTestId } = render(
      <UPlotCanvas x={[1, 2, 3]} y={[0, 5, 0]} height={300} />,
    )
    const container = getByTestId("uplot-spectrum-canvas")
    expect(container).toBeInTheDocument()
    // The mount should still produce a <canvas> element — that's the signal
    // that uPlot was actually constructed (not just its CSS preloaded).
    await waitFor(
      () => {
        expect(container.querySelector("canvas")).not.toBeNull()
      },
      { timeout: 4000 },
    )
  })

  it("renders a canvas even when x values arrive unsorted (peak-table CSV case)", async () => {
    // The original bug: uPlot silently fails to draw the line when x is not
    // monotonically increasing. UPlotCanvas now sorts before handing data to
    // uPlot, so this case must still produce a canvas element.
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get() {
        return 720
      },
    })
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get() {
        return 400
      },
    })

    const { getByTestId } = render(
      // Ethanol peak-table order: 3.65 ppm first, then 1.26, then 2.10 — NOT
      // monotonic. The sort fix should normalize this to [1.26, 2.10, 3.65].
      <UPlotCanvas x={[3.65, 1.26, 2.10]} y={[2, 3, 1]} height={400} />,
    )
    const container = getByTestId("uplot-spectrum-canvas")
    await waitFor(
      () => {
        expect(container.querySelector("canvas")).not.toBeNull()
      },
      { timeout: 4000 },
    )
  })
})
