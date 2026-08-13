import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, apiFetch } from "@/lib/api/client"
import { SpectraCheckFidRunReview } from "@/components/spectracheck/spectracheck-fid-run-review"

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client")
  return { ...actual, apiFetch: vi.fn() }
})

const apiFetchMock = vi.mocked(apiFetch)

/** A colleague's run, open for a verdict — the population the queue exists for. */
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
  viewer_is_author: false,
  viewer_can_review: true,
}

/** The caller's own run. `viewer_can_review` is false: they may not sign their own work. */
const OWN_RUN = {
  ...RUN,
  id: 8,
  user_id: 42,
  filename: "kanamycin.zip",
  viewer_is_author: true,
  viewer_can_review: false,
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

  it("asks the server for the chosen slice instead of filtering in the browser", async () => {
    // The queue is server-side on purpose: one limit-bounded page ordered
    // newest-first would let a prolific author's own runs push it out of view.
    routeBy({ "review-decisions": [], "/fid/runs": [RUN] })
    render(<SpectraCheckFidRunReview />)
    await screen.findByTestId("fid-run-row-7")
    expect(apiFetchMock.mock.calls[0]?.[0]).toContain("scope=all")

    fireEvent.click(screen.getByTestId("fid-run-scope-review_queue"))
    await waitFor(() =>
      expect(
        apiFetchMock.mock.calls.some(([path]) => String(path).includes("scope=review_queue")),
      ).toBe(true),
    )
  })

  it("says whose run each row is, now that the list is mixed", async () => {
    routeBy({ "review-decisions": [], "/fid/runs": [RUN, OWN_RUN] })
    render(<SpectraCheckFidRunReview />)
    // Read off viewer_is_author, never by comparing user_id to the signed-in user —
    // the client is not told who it is.
    expect((await screen.findByTestId("fid-run-author-7")).textContent).toBe("Someone else")
    expect(screen.getByTestId("fid-run-author-8").textContent).toBe("You")
  })

  it("refuses self-review before the post rather than after a failed one", async () => {
    routeBy({ "review-decisions": [], "/fid/runs": [OWN_RUN] })
    render(<SpectraCheckFidRunReview />)
    fireEvent.click(await screen.findByTestId("fid-run-row-8"))
    await screen.findByTestId("fid-run-review-detail")

    expect(screen.getByTestId("fid-review-cannot-review")).toBeInTheDocument()
    // All four, not only the verdicts: the backend applies the separation rule
    // before it reads the action, so an author cannot add a comment either.
    for (const action of ["approve", "request_changes", "reject", "review"]) {
      expect(screen.getByTestId(`fid-review-action-${action}`)).toBeDisabled()
    }
    expect(screen.getByTestId("fid-review-comment")).toBeDisabled()

    fireEvent.click(screen.getByTestId("fid-review-action-approve"))
    expect(apiFetchMock.mock.calls.some(([path]) => String(path).includes("/approve"))).toBe(false)
  })

  it("explains an empty queue instead of reading as a fault", async () => {
    // Colleagues resolve through shared organization membership, and an org is
    // created deliberately — signing up does not create one. A permanently empty
    // queue is the accurate answer for somebody on no team, so it has to say why.
    routeBy({ "/fid/runs": [] })
    render(<SpectraCheckFidRunReview />)
    await screen.findByTestId("fid-run-review-empty")

    fireEvent.click(screen.getByTestId("fid-run-scope-review_queue"))
    await waitFor(() =>
      expect(screen.getByTestId("fid-run-review-empty").textContent).toContain("organization"),
    )
  })

  it("keeps the run you just signed open after it leaves the queue", async () => {
    routeBy({ "review-decisions": [], "/fid/runs": [RUN] })
    render(<SpectraCheckFidRunReview />)
    fireEvent.click(screen.getByTestId("fid-run-scope-review_queue"))
    fireEvent.click(await screen.findByTestId("fid-run-row-7"))
    await screen.findByTestId("fid-run-no-decisions")

    // Clause 2 lapses on completion, so the approved run drops out of the queue.
    // Losing the evidence at the instant of signing is backwards for a Part 11
    // signature — the panel holds the run open rather than deriving it from the list.
    routeBy({ "/approve": DECISION, "review-decisions": [DECISION], "/fid/runs": [] })
    fireEvent.click(screen.getByTestId("fid-review-action-approve"))

    expect(await screen.findByTestId("fid-run-out-of-view")).toBeInTheDocument()
    expect(screen.getByTestId("fid-run-review-detail")).toBeInTheDocument()
    expect(screen.getByText("Baseline and phasing check out.")).toBeInTheDocument()
  })

  it("opens the run just processed instead of making you find it again", async () => {
    routeBy({ "review-decisions": [], "/fid/runs": [RUN] })
    render(<SpectraCheckFidRunReview focusRunId={7} />)
    // No click: the process response named the run, so review starts on it.
    expect(await screen.findByTestId("fid-run-review-detail")).toBeInTheDocument()
    await waitFor(() =>
      expect(
        apiFetchMock.mock.calls.some(([path]) => String(path).includes("/7/review-decisions")),
      ).toBe(true),
    )
  })
})
