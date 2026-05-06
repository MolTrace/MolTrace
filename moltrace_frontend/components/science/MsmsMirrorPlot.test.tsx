import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { MsmsMirrorPlot } from "@/components/science/MsmsMirrorPlot"

vi.mock("next/dynamic", () => ({
  __esModule: true,
  default: () =>
    function PlotMock(props: Record<string, unknown>) {
      const data = props.data as ReadonlyArray<{ y?: (number | null)[] }> | undefined
      const ys = data?.flatMap((t) => t.y?.filter((v): v is number => typeof v === "number") ?? []) ?? []
      const hasPositive = ys.some((v) => v > 0)
      const hasNegative = ys.some((v) => v < 0)
      return (
        <div
          data-testid="plotly-mock"
          data-has-positive={hasPositive ? "1" : "0"}
          data-has-negative={hasNegative ? "1" : "0"}
          data-trace-count={String(data?.length ?? 0)}
        />
      )
    },
}))

describe("MsmsMirrorPlot", () => {
  it("renders observed peaks", () => {
    render(
      <MsmsMirrorPlot
        observedPeaks={[
          { mz: 100, intensity: 1000 },
          { mz: 120, intensity: 500 },
        ]}
      />
    )
    const plot = screen.getByTestId("plotly-mock")
    expect(plot).toHaveAttribute("data-has-positive", "1")
    expect(plot).toHaveAttribute("data-trace-count", "1")
  })

  it("renders mirror reference peaks", () => {
    render(
      <MsmsMirrorPlot
        observedPeaks={[{ mz: 100, intensity: 1000 }]}
        referencePeaks={[
          { mz: 101, intensity: 800 },
          { mz: 130, intensity: 200 },
        ]}
      />
    )
    const plot = screen.getByTestId("plotly-mock")
    expect(plot).toHaveAttribute("data-has-positive", "1")
    expect(plot).toHaveAttribute("data-has-negative", "1")
    expect(plot).toHaveAttribute("data-trace-count", "2")
  })

  it("handles empty reference", () => {
    render(
      <MsmsMirrorPlot
        observedPeaks={[{ mz: 50, intensity: 200 }]}
        referencePeaks={[]}
      />
    )
    const plot = screen.getByTestId("plotly-mock")
    expect(plot).toHaveAttribute("data-trace-count", "1")
    expect(plot).toHaveAttribute("data-has-negative", "0")
  })

  it("labels do not crash when missing", () => {
    expect(() =>
      render(
        <MsmsMirrorPlot
          observedPeaks={[{ mz: 100, intensity: 1 }]}
          referencePeaks={[{ mz: 102, intensity: 2 }]}
          fragmentMatches={[{ observed_mz: 100, theoretical_mz: 100.01, score: 0.5 }]}
        />
      )
    ).not.toThrow()
    expect(screen.getByTestId("plotly-mock")).toBeInTheDocument()
  })
})
