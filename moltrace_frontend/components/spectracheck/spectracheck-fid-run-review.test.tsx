import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, apiFetch } from "@/lib/api/client"
import { SpectraCheckFidRunReview } from "@/components/spectracheck/spectracheck-fid-run-review"

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client")
  return { ...actual, apiFetch: vi.fn() }
})

const apiFetchMock = vi.mocked(apiFetch)

const RUN = {
  id: 7,
  user_id: 3,
  created_at: "2026-08-09T12:00:00Z",
  sample_id: "SMP-1",
  filename: "tobramycin.zip",
  selected_preset: "standard",
  quality_label: "review",
  quality_score: 0.62,
  review_status: "pending_review",
  preview: {},
}

const DECISION = {
  id: 1,
  run_id: 7,
  reviewer_user_id: 9,
  action: "approve",
  previous_status: "pending_review",
  new_status: "approved",
  comment: "Baseline and phasing check out.",
  created_at: "2026-08-09T13:00:00Z",
}

/** Route the mock by path so a test does not depend on call ordering. */
function routeBy(handlers: Record<string, unknown | (() => unknown)>) {
  apiFetchMock.mockImplementation(async (path: string) => {
    for (const [fragment, value] of Object.entries(handlers)) {
      if (path.includes(fragment)) {
        const resolved = typeof value === "function" ? (value as () => unknown)() : value
        return resolved as never
      }
    }
    throw new Error(`unexpected path ${path}`)
  })
}

async function openRun() {
  render(<SpectraCheckFidRunReview />)
  const row = await screen.findByTestId("fid-run-row-7")
  fireEvent.click(row)
  return row
}

describe("FID run review", () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it("lists runs with their review status", async () => {
    routeBy({ "review-decisions": [], "/fid/runs": [RUN] })
    render(<SpectraCheckFidRunReview />)
    expect(await screen.findByTestId("fid-run-row-7")).toBeInTheDocument()
    expect(screen.getByTestId("fid-run-status-pending_review").textContent).toBe("Awaiting review")
  })

  it("shows the decision history once a run is selected", async () => {
    routeBy({ "review-decisions": [DECISION], "/fid/runs": [RUN] })
    await openRun()
    expect(await screen.findByTestId("fid-run-review-detail")).toBeInTheDocument()
    expect(screen.getByText("Baseline and phasing check out.")).toBeInTheDocument()
    // The stored values are `approve` / `approved`; the reader sees labels, never
    // the wire values. "Approved" is unique here — this run is still pending, so
    // it can only be the decision's resulting status. ("Approve" alone would also
    // match the action button.)
    expect(screen.getByText("Approved")).toBeInTheDocument()
    expect(screen.queryByText("approve")).not.toBeInTheDocument()
  })

  it("records a decision and refreshes the history", async () => {
    routeBy({ "review-decisions": [], "/fid/runs": [RUN] })
    await openRun()
    await screen.findByTestId("fid-run-no-decisions")

    routeBy({
      "/approve": DECISION,
      "review-decisions": [DECISION],
      "/fid/runs": [{ ...RUN, review_status: "approved" }],
    })
    fireEvent.click(screen.getByTestId("fid-review-action-approve"))

    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith(
        "/fid/runs/7/approve",
        expect.objectContaining({ method: "POST" }),
      ),
    )
    expect(await screen.findByTestId("fid-run-status-approved")).toBeInTheDocument()
  })

  it("explains a self-review refusal instead of showing a generic failure", async () => {
    routeBy({ "review-decisions": [], "/fid/runs": [RUN] })
    await openRun()
    await screen.findByTestId("fid-run-no-decisions")

    const detail = "You created this run, so it needs a review from someone else."
    routeBy({
      "/approve": () => {
        throw new ApiError(409, { detail }, detail)
      },
      "review-decisions": [],
      "/fid/runs": [RUN],
    })
    fireEvent.click(screen.getByTestId("fid-review-action-approve"))

    // Rendered verbatim, and NOT in the error slot — nothing failed and there is
    // nothing to retry; the run needs a different reviewer.
    expect((await screen.findByTestId("fid-review-self-review")).textContent).toBe(detail)
    expect(screen.queryByTestId("fid-review-action-error")).not.toBeInTheDocument()
  })

  it("keeps a genuine failure in the error slot", async () => {
    routeBy({ "review-decisions": [], "/fid/runs": [RUN] })
    await openRun()
    await screen.findByTestId("fid-run-no-decisions")

    routeBy({
      "/reject": () => {
        throw new ApiError(500, { detail: "boom" }, "boom")
      },
      "review-decisions": [],
      "/fid/runs": [RUN],
    })
    fireEvent.click(screen.getByTestId("fid-review-action-reject"))

    expect(await screen.findByTestId("fid-review-action-error")).toBeInTheDocument()
    expect(screen.queryByTestId("fid-review-self-review")).not.toBeInTheDocument()
  })

  it("says so when there are no runs rather than rendering an empty table", async () => {
    routeBy({ "/fid/runs": [] })
    render(<SpectraCheckFidRunReview />)
    expect(await screen.findByTestId("fid-run-review-empty")).toBeInTheDocument()
  })
})
