import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { Nmr2DViewer } from "@/src/components/science/Nmr2DViewer"

vi.mock("next/dynamic", () => ({
  __esModule: true,
  default: () =>
    function PlotMock(props: Record<string, unknown>) {
      const layout = props.layout as {
        xaxis?: { autorange?: unknown }
        yaxis?: { autorange?: unknown }
      }
      const data = props.data as ReadonlyArray<{ mode?: string; type?: string; text?: unknown }> | undefined
      const trace = data?.[0]
      const hasLabels =
        trace?.mode === "markers+text" ||
        (trace?.text != null &&
          Array.isArray(trace.text) &&
          trace.text.some((t) => String(t ?? "").length > 0))
      return (
        <div
          data-testid="plotly-mock"
          data-trace-type={trace?.type ?? ""}
          data-x-autorange={String(layout?.xaxis?.autorange ?? "")}
          data-y-autorange={String(layout?.yaxis?.autorange ?? "")}
          data-has-labels={hasLabels ? "1" : "0"}
        />
      )
    },
}))

describe("Nmr2DViewer", () => {
  it("renders HSQC peaks", () => {
    render(
      <Nmr2DViewer
        experiment="HSQC"
        peaks={[
          { f2_ppm: 7.2, f1_ppm: 128.5, intensity: 1e6, assignment: "H-2", label: "c2" },
          { f2_ppm: 4.5, f1_ppm: 60.2, intensity: 8e5 },
        ]}
      />
    )
    expect(screen.getByTestId("plotly-mock")).toHaveAttribute("data-trace-type", "scattergl")
    expect(screen.getByText(/HSQC/)).toBeInTheDocument()
    expect(screen.getByTestId("plotly-mock")).toHaveAttribute("data-x-autorange", "reversed")
    expect(screen.getByTestId("plotly-mock")).toHaveAttribute("data-y-autorange", "reversed")
  })

  it("renders COSY peaks", () => {
    render(
      <Nmr2DViewer
        experiment="COSY"
        peaks={[
          { f2_ppm: 1.0, f1_ppm: 2.5, intensity: 100 },
          { f2_ppm: 2.5, f1_ppm: 1.0, intensity: 90 },
        ]}
      />
    )
    expect(screen.getByTestId("plotly-mock")).toHaveAttribute("data-trace-type", "scattergl")
    expect(screen.getByText(/COSY/)).toBeInTheDocument()
  })

  it("handles empty state", () => {
    render(<Nmr2DViewer peaks={[]} />)
    expect(screen.getByText("No 2D NMR peak data available yet.")).toBeInTheDocument()
    expect(screen.queryByTestId("plotly-mock")).not.toBeInTheDocument()
  })

  it("label toggle works", async () => {
    const user = userEvent.setup()
    render(
      <Nmr2DViewer
        peaks={[{ f2_ppm: 3.3, f1_ppm: 3.3, assignment: "OH", label: "a" }]}
      />
    )
    const plot = screen.getByTestId("plotly-mock")
    expect(plot).toHaveAttribute("data-has-labels", "1")

    await user.click(screen.getByRole("button", { name: /toggle labels/i }))
    expect(plot).toHaveAttribute("data-has-labels", "0")

    await user.click(screen.getByRole("button", { name: /toggle labels/i }))
    expect(plot).toHaveAttribute("data-has-labels", "1")
  })
})
