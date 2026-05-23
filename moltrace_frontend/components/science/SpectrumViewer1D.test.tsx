import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { SpectrumViewer1D, normalizePlotlyXRange } from "@/components/science/SpectrumViewer1D"

vi.mock("next/dynamic", () => ({
  __esModule: true,
  default: () =>
    function PlotMock(props: Record<string, unknown>) {
      const layout = props.layout as {
        xaxis?: { autorange?: boolean | string; showgrid?: boolean; showspikes?: boolean; hoverformat?: string }
        yaxis?: { showgrid?: boolean }
      } | undefined
      const data = props.data as Array<{ hovertemplate?: string }> | undefined
      return (
        <div
          data-testid="plotly-mock"
          data-xaxis-autorange={layout?.xaxis?.autorange === "reversed" ? "reversed" : String(layout?.xaxis?.autorange)}
          data-xaxis-showgrid={String(layout?.xaxis?.showgrid)}
          data-yaxis-showgrid={String(layout?.yaxis?.showgrid)}
          data-xaxis-showspikes={String(layout?.xaxis?.showspikes)}
          data-xaxis-hoverformat={layout?.xaxis?.hoverformat}
          data-primary-hovertemplate={data?.[0]?.hovertemplate ?? ""}
        />
      )
    },
}))

describe("SpectrumViewer1D", () => {
  it("renders empty state", () => {
    render(<SpectrumViewer1D x={[]} y={[]} />)
    expect(screen.getByText("No spectrum data available yet.")).toBeInTheDocument()
  })

  it("renders mismatch warning when x/y lengths differ", () => {
    render(<SpectrumViewer1D x={[1, 2]} y={[1]} />)
    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(screen.getByText(/different lengths/i)).toBeInTheDocument()
  })

  it("renders with small x/y arrays", () => {
    render(<SpectrumViewer1D x={[10, 9, 8]} y={[0.1, 0.2, 0.05]} nucleus="1H" />)
    expect(screen.getByTestId("plotly-mock")).toBeInTheDocument()
  })

  it("does not mutate input arrays when gain changes", () => {
    const x = Object.freeze([1, 2, 3])
    const y = Object.freeze([0.1, 0.2, 0.3])
    render(<SpectrumViewer1D x={x as number[]} y={y as number[]} nucleus="1H" />)
    const slider = screen.getByLabelText("Intensity gain")
    fireEvent.keyDown(slider, { key: "ArrowRight" })
    expect(x).toEqual([1, 2, 3])
    expect(y).toEqual([0.1, 0.2, 0.3])
  })

  it("uses reversed x-axis by default for NMR", () => {
    render(<SpectrumViewer1D x={[1, 2, 3]} y={[0.1, 0.2, 0.3]} nucleus="1H" />)
    expect(screen.getByTestId("plotly-mock")).toHaveAttribute("data-xaxis-autorange", "reversed")
  })

  it("normalizes Plotly relayout ranges before storing spectrum state", () => {
    expect(normalizePlotlyXRange(10, 1)).toEqual([1, 10])
    expect(normalizePlotlyXRange(1, 10)).toEqual([1, 10])
  })

  it("configures exact ppm hover labels and selector spikes without chart gridlines", () => {
    render(<SpectrumViewer1D x={[210, 100, 49]} y={[0.1, 0.2, 0.3]} nucleus="13C" />)
    const plot = screen.getByTestId("plotly-mock")
    expect(plot).toHaveAttribute("data-xaxis-showgrid", "false")
    expect(plot).toHaveAttribute("data-yaxis-showgrid", "false")
    expect(plot).toHaveAttribute("data-xaxis-showspikes", "true")
    expect(plot).toHaveAttribute("data-xaxis-hoverformat", ".2f")
    expect(plot.getAttribute("data-primary-hovertemplate")).toContain("%{x:.2f} ppm")
  })
})
