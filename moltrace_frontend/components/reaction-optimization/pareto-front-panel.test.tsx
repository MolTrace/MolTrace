import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { ParetoFrontPanel } from "@/components/reaction-optimization/pareto-front-panel"
import type { ParetoFront } from "@/lib/reaction/pareto"

// Mock next/dynamic so the client-only Plotly chart becomes a lightweight stub
// that surfaces its trace count + axis titles as data-attributes (same approach
// as the SpectraCheck spectrum-viewer tests).
vi.mock("next/dynamic", () => ({
  __esModule: true,
  default: () =>
    function PlotMock(props: Record<string, unknown>) {
      const data = (props.data as unknown[]) ?? []
      const layout = props.layout as { xaxis?: { title?: { text?: string } }; yaxis?: { title?: { text?: string } } }
      return (
        <div
          data-testid="plotly-mock"
          data-trace-count={String(data.length)}
          data-x-title={layout?.xaxis?.title?.text ?? ""}
          data-y-title={layout?.yaxis?.title?.text ?? ""}
        />
      )
    },
}))

const FRONT: ParetoFront = {
  objectives: ["yield", "selectivity", "impurity", "conversion"],
  hypervolume: 1234567,
  hypervolumeMethod: "monte_carlo",
  referencePoint: [0, 0, 0, 0],
  paretoSize: 2,
  evaluatedExperimentCount: 5,
  kneeExperimentId: 41,
  members: [
    { experimentId: 41, experimentCode: "BO-4", objectives: { yield: 85, selectivity: 85, impurity: 3, conversion: 95 }, nonDominated: true },
    { experimentId: 42, experimentCode: "BO-5", objectives: { yield: 90, selectivity: 70, impurity: 5, conversion: 88 }, nonDominated: true },
    { experimentId: 43, experimentCode: "BO-6", objectives: { yield: 50, selectivity: 50, impurity: 9, conversion: 60 }, nonDominated: false },
  ],
  note: "Non-dominated set over the weighted dimensions. Advisory; requires human review.",
}

describe("ParetoFrontPanel", () => {
  it("renders hypervolume + pareto-size KPIs with the method caption", () => {
    render(<ParetoFrontPanel front={FRONT} trend={[]} />)
    expect(screen.getByText("1.23e+6")).toBeInTheDocument() // compact hypervolume
    expect(screen.getByText(/method: Monte Carlo/i)).toBeInTheDocument()
    expect(screen.getByText("Pareto size")).toBeInTheDocument()
    expect(screen.getByText("evaluated")).toBeInTheDocument()
  })

  it("lists only non-dominated members and rings the knee", () => {
    render(<ParetoFrontPanel front={FRONT} trend={[]} />)
    expect(screen.getByText("BO-4")).toBeInTheDocument()
    expect(screen.getByText("BO-5")).toBeInTheDocument()
    expect(screen.queryByText("BO-6")).not.toBeInTheDocument() // dominated — not in the front table
    expect(screen.getByText(/knee · balanced/i)).toBeInTheDocument()
  })

  it("plots all three traces (evaluated, front, knee) with the chosen objectives on the axes", () => {
    render(<ParetoFrontPanel front={FRONT} trend={[]} />)
    const plot = screen.getByTestId("plotly-mock")
    expect(plot).toHaveAttribute("data-trace-count", "3")
    expect(plot).toHaveAttribute("data-x-title", "yield")
    expect(plot).toHaveAttribute("data-y-title", "selectivity")
  })

  it("offers an objective-pair selector when there are more than two objectives", () => {
    render(<ParetoFrontPanel front={FRONT} trend={[]} />)
    expect(screen.getByText("X objective")).toBeInTheDocument()
    expect(screen.getByText("Y objective")).toBeInTheDocument()
  })

  it("keeps the advisory note visible", () => {
    render(<ParetoFrontPanel front={FRONT} trend={[]} />)
    expect(screen.getByText(/Advisory; requires human review/i)).toBeInTheDocument()
  })

  it("shows the hypervolume convergence trend only with ≥2 runs", () => {
    const { rerender } = render(<ParetoFrontPanel front={FRONT} trend={[]} />)
    expect(screen.queryByText(/Hypervolume convergence/i)).not.toBeInTheDocument()
    rerender(
      <ParetoFrontPanel
        front={FRONT}
        trend={[
          { boRunId: 1, hypervolume: 100, objectivesKey: "conversion|impurity|selectivity|yield" },
          { boRunId: 2, hypervolume: 200, objectivesKey: "conversion|impurity|selectivity|yield" },
        ]}
      />,
    )
    expect(screen.getByText(/Hypervolume convergence/i)).toBeInTheDocument()
    expect(screen.getAllByTestId("plotly-mock").length).toBe(2)
  })

  it("falls back to a single objective with no pair selector when only two objectives", () => {
    const twoObj: ParetoFront = { ...FRONT, objectives: ["yield", "selectivity"] }
    render(<ParetoFrontPanel front={twoObj} trend={[]} />)
    expect(screen.queryByText("X objective")).not.toBeInTheDocument()
  })
})
