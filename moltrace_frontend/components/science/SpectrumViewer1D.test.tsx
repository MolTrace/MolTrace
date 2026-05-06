import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { SpectrumViewer1D } from "@/components/science/SpectrumViewer1D"

vi.mock("next/dynamic", () => ({
  __esModule: true,
  default: () =>
    function PlotMock(props: Record<string, unknown>) {
      const layout = props.layout as { xaxis?: { autorange?: boolean | string } } | undefined
      return (
        <div
          data-testid="plotly-mock"
          data-xaxis-autorange={layout?.xaxis?.autorange === "reversed" ? "reversed" : String(layout?.xaxis?.autorange)}
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
})
