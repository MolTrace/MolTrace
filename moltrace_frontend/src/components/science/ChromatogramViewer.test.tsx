import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { ChromatogramViewer } from "@/src/components/science/ChromatogramViewer"

vi.mock("next/dynamic", () => ({
  __esModule: true,
  default: () =>
    function PlotMock(props: Record<string, unknown>) {
      const layout = props.layout as { shapes?: unknown[] } | undefined
      const data = props.data as ReadonlyArray<{ mode?: string }> | undefined
      const markerCount = data?.filter((t) => t.mode === "markers").length ?? 0
      return (
        <div
          data-testid="plotly-mock"
          data-shapes-count={String(layout?.shapes?.length ?? 0)}
          data-marker-traces={String(markerCount)}
          data-line-traces={String(data?.filter((t) => t.mode === "lines").length ?? 0)}
        />
      )
    },
}))

describe("ChromatogramViewer", () => {
  it("renders trace", () => {
    render(
      <ChromatogramViewer
        traces={[{ name: "TIC", rt: [0, 1, 2], intensity: [10, 50, 20], type: "TIC" }]}
      />
    )
    expect(screen.getByTestId("plotly-mock")).toHaveAttribute("data-line-traces", "1")
  })

  it("renders feature markers", () => {
    render(
      <ChromatogramViewer
        traces={[{ name: "XIC", rt: [0, 1, 2], intensity: [1, 5, 2], type: "XIC", mz: 255.1 }]}
        features={[
          {
            id: "f1",
            rtStart: 0.5,
            rtEnd: 1.5,
            rtApex: 1.0,
            label: "Peak A",
            purityLabel: "major",
          },
        ]}
      />
    )
    const plot = screen.getByTestId("plotly-mock")
    expect(Number(plot.getAttribute("data-shapes-count"))).toBeGreaterThan(0)
    expect(plot.getAttribute("data-marker-traces")).toBe("1")
  })

  it("handles empty state", () => {
    render(<ChromatogramViewer traces={[]} />)
    expect(screen.getByText("No chromatogram or XIC data available yet.")).toBeInTheDocument()
    expect(screen.queryByTestId("plotly-mock")).not.toBeInTheDocument()
  })

  it("does not introduce horizontal overflow on the viewer root", () => {
    const { container } = render(
      <div className="w-[200px] max-w-[200px] overflow-hidden border">
        <ChromatogramViewer
          traces={[
            {
              name: "XIC",
              rt: [0, 5, 10],
              intensity: [100, 200, 150],
              type: "XIC",
              mz: 300.12345,
            },
          ]}
          features={[
            { rtStart: 2, rtEnd: 8, rtApex: 5, label: "Long label ".repeat(20), purityLabel: "test" },
          ]}
        />
      </div>
    )
    const root = screen.getByTestId("chromatogram-viewer-root")
    expect(root.className).toMatch(/max-w-full/)
    expect(root.className).toMatch(/min-w-0/)
    expect(root.className).toMatch(/overflow-x-hidden/)
    expect(container.firstElementChild?.scrollWidth).toBeLessThanOrEqual(
      (container.firstElementChild as HTMLElement).clientWidth + 1
    )
  })
})
