import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { GoldenPathRoiStrip } from "@/components/pilot/golden-path-roi-strip"
import { splitRoi, type RoiSnapshot } from "@/lib/pilot/golden-path"

function snapshot(patch: Partial<RoiSnapshot> = {}): RoiSnapshot {
  return {
    id: 1,
    scope: "global",
    period_start: "2026-07-01T00:00:00Z",
    period_end: "2026-08-01T00:00:00Z",
    tasks_automated: 12,
    total_minutes_saved: 240,
    total_hours_saved: 4,
    reports_generated: 3,
    workflows_completed: 2,
    analyses_completed: 7,
    review_tasks_completed: 5,
    failed_jobs: 1,
    qc_warnings: 2,
    created_at: "2026-08-01T00:00:00Z",
    data_mode: "live",
    ...patch,
  }
}

describe("GoldenPathRoiStrip", () => {
  it("labels the hours figure as estimated and keeps its basis reachable", () => {
    render(<GoldenPathRoiStrip split={splitRoi(snapshot(), 2500)} />)

    // The figure itself must not stand alone: a reader who sees "4 h" has to see
    // that it is an estimate without hovering anything.
    expect(screen.getByText("Time saved")).toBeInTheDocument()
    expect(screen.getAllByText(/estimated/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/4 h/)).toBeInTheDocument()

    // And the per-task assumption behind it is one click away, at a route that
    // actually renders the constants — /roi lists every automation-task
    // definition with its default_minutes_saved.
    const link = screen.getByRole("link", { name: /review the per-task assumptions/i })
    expect(link).toHaveAttribute("href", "/roi")
  })

  it("presents the arc's own elapsed time as measured", () => {
    render(<GoldenPathRoiStrip split={splitRoi(snapshot(), 2500)} />)
    expect(screen.getByText("Arc elapsed time")).toBeInTheDocument()
    expect(screen.getByText("2.5 s")).toBeInTheDocument()
    // "Measured" appears on the arc clock and the counts, never on the hours tile.
    expect(screen.getAllByText("Measured").length).toBe(2)
  })

  it("renders a missing snapshot as no-data rather than zero", () => {
    render(<GoldenPathRoiStrip split={splitRoi(null, null)} />)

    // The defect this guards: `?? 0` turns "we have no snapshot" into a
    // confident claim that nothing was saved and nothing was done.
    expect(screen.queryByText("0")).not.toBeInTheDocument()
    expect(screen.getByText(/no activity snapshot is available/i)).toBeInTheDocument()
    expect(screen.getByText(/— h/)).toBeInTheDocument()
  })

  it("renders snapshot warnings above the figures they qualify", () => {
    const { container } = render(
      <GoldenPathRoiStrip split={splitRoi(snapshot({ warnings: ["Partially synced."] }), 2500)} />,
    )
    const warning = screen.getByText("Partially synced.")
    const hours = screen.getByText(/4 h/)
    // A caveat below the number it caveats is a caveat most readers never reach.
    expect(container.compareDocumentPosition(warning) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(warning.compareDocumentPosition(hours) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it("shows the real event counts as measured", () => {
    render(<GoldenPathRoiStrip split={splitRoi(snapshot(), null)} />)
    expect(screen.getByText("Tasks automated")).toBeInTheDocument()
    expect(screen.getByText("12")).toBeInTheDocument()
    expect(screen.getByText("Analyses completed")).toBeInTheDocument()
    expect(screen.getByText("7")).toBeInTheDocument()
  })
})
