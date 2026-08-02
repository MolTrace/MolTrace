import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api/client"
import { SubjectReviewersBody } from "@/components/collaboration/subject-reviewers-panel"
import {
  buildNominateSubjectReviewerBody,
  describeSubjectReviewerError,
  normalizeSubjectReviewers,
  pendingReviewerCount,
  sortSubjectReviewers,
  type SubjectReviewerRecord,
} from "@/lib/collaboration/subject-reviewers"

const api = vi.hoisted(() => ({
  listSubjectReviewers: vi.fn(),
  nominateSubjectReviewer: vi.fn(),
  setSubjectReviewerStatus: vi.fn(),
}))

// Partial mock — keep the real builders, sorters and error classifier; stub the network.
vi.mock("@/lib/collaboration/subject-reviewers", async (orig) => ({
  ...(await orig<typeof import("@/lib/collaboration/subject-reviewers")>()),
  listSubjectReviewers: (...a: unknown[]) => api.listSubjectReviewers(...a),
  nominateSubjectReviewer: (...a: unknown[]) => api.nominateSubjectReviewer(...a),
  setSubjectReviewerStatus: (...a: unknown[]) => api.setSubjectReviewerStatus(...a),
}))

function reviewer(over: Partial<SubjectReviewerRecord> = {}): SubjectReviewerRecord {
  return {
    id: 1,
    session_id: null,
    subject_type: "regulatory_dossier",
    subject_id: 42,
    module: "regulatory_hub",
    reviewer_email: "reviewer@example.com",
    assigned_by: "lead@example.com",
    status: "assigned",
    created_at: "2026-08-01T10:00:00Z",
    updated_at: "2026-08-01T10:00:00Z",
    metadata_json: {},
    warnings: [],
    notes: [],
    ...over,
  } as SubjectReviewerRecord
}

beforeEach(() => {
  api.listSubjectReviewers.mockReset()
  api.nominateSubjectReviewer.mockReset()
  api.setSubjectReviewerStatus.mockReset()
})

describe("subject-reviewers lib", () => {
  it("sends the status rather than omitting it — the generated model requires it", () => {
    const body = buildNominateSubjectReviewerBody({
      subjectType: "regulatory_dossier",
      subjectId: 42,
      reviewerEmail: "  reviewer@example.com  ",
    })
    expect(body).toEqual({
      subject_type: "regulatory_dossier",
      subject_id: 42,
      reviewer_email: "reviewer@example.com",
      status: "assigned",
    })
  })

  it("puts live nominations above finished ones, most recently updated first", () => {
    const rows = [
      reviewer({ id: 1, status: "completed", updated_at: "2026-08-02T10:00:00Z" }),
      reviewer({ id: 2, status: "assigned", updated_at: "2026-07-01T10:00:00Z" }),
      reviewer({ id: 3, status: "in_review", updated_at: "2026-08-01T10:00:00Z" }),
      reviewer({ id: 4, status: "removed", updated_at: "2026-08-03T10:00:00Z" }),
    ]
    expect(sortSubjectReviewers(rows).map((r) => r.id)).toEqual([3, 2, 4, 1])
    expect(pendingReviewerCount(rows)).toBe(2)
  })

  it("classifies an unreachable subject as not-found, never as a permissions failure", () => {
    const e = describeSubjectReviewerError(new ApiError(404, {}), "regulatory_dossier")
    expect(e.kind).toBe("not_found")
    expect(e.message).not.toMatch(/permission|not allowed|forbidden|access denied/i)
  })

  // The session surface is genuinely different: there, a reviewer row confers a role.
  it("points a refused spectroscopy session at its own reviewer surface", () => {
    const e = describeSubjectReviewerError(new ApiError(403, {}), "reaction_project")
    expect(e.kind).toBe("wrong_surface")
    expect(e.message).toMatch(/role for that session/i)
  })

  it("reads a bare array and tolerates a wrapped list", () => {
    expect(normalizeSubjectReviewers([{ id: 1 }])).toHaveLength(1)
    expect(normalizeSubjectReviewers({ reviewers: [{ id: 1 }, { id: 2 }] })).toHaveLength(2)
    expect(normalizeSubjectReviewers(null)).toEqual([])
  })
})

describe("SubjectReviewersBody", () => {
  // The whole point of this surface's copy: a nomination records an expectation, it does
  // not widen access. Sharing language would promise something the endpoint does not do.
  it("asks for a review and never offers to share, invite or grant access", async () => {
    api.listSubjectReviewers.mockResolvedValue([])
    const { container } = render(
      <SubjectReviewersBody subjectType="regulatory_dossier" subjectId={42} />,
    )

    await screen.findByText(/No one has been asked to review this filing yet/i)
    const text = container.textContent ?? ""
    expect(text).not.toMatch(/\bshare\b|\bshared\b|\binvite\b|\bgrant\b|\bgives them access\b/i)
    expect(text).toMatch(/does not give them access/i)
    expect(screen.getByLabelText(/Request review from/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Nominate reviewer/i })).toBeInTheDocument()
  })

  it("nominates against the subject it is pointed at, then reloads", async () => {
    api.listSubjectReviewers.mockResolvedValue([])
    api.nominateSubjectReviewer.mockResolvedValue(reviewer())
    const user = userEvent.setup()
    render(<SubjectReviewersBody subjectType="reaction_project" subjectId={7} />)

    await screen.findByText(/No one has been asked to review this campaign yet/i)
    await user.type(screen.getByLabelText(/Request review from/i), "chem@example.com")
    await user.click(screen.getByRole("button", { name: /Nominate reviewer/i }))

    await waitFor(() =>
      expect(api.nominateSubjectReviewer).toHaveBeenCalledWith({
        subjectType: "reaction_project",
        subjectId: 7,
        reviewerEmail: "chem@example.com",
      }),
    )
    expect(api.listSubjectReviewers).toHaveBeenCalledTimes(2)
  })

  it("will not nominate nobody", async () => {
    api.listSubjectReviewers.mockResolvedValue([])
    const user = userEvent.setup()
    render(<SubjectReviewersBody subjectType="regulatory_dossier" subjectId={42} />)

    await screen.findByText(/No one has been asked to review this filing yet/i)
    await user.click(screen.getByRole("button", { name: /Nominate reviewer/i }))

    expect(await screen.findByText(/Enter the email address/i)).toBeInTheDocument()
    expect(api.nominateSubjectReviewer).not.toHaveBeenCalled()
  })

  it("lists nominations and reports how many are still awaiting a look", async () => {
    api.listSubjectReviewers.mockResolvedValue([
      reviewer(),
      reviewer({ id: 2, reviewer_email: "qa@example.com", status: "completed" }),
    ])
    const onCount = vi.fn()
    render(
      <SubjectReviewersBody
        subjectType="regulatory_dossier"
        subjectId={42}
        onAttentionCountChange={onCount}
      />,
    )

    expect(await screen.findByText("reviewer@example.com")).toBeInTheDocument()
    expect(screen.getByText("qa@example.com")).toBeInTheDocument()
    await waitFor(() => expect(onCount).toHaveBeenCalledWith(1))
  })

  // There is no PATCH — a status change is another nomination for the same person, which
  // the server folds into the existing row.
  it("changes a status by re-nominating the same person", async () => {
    api.listSubjectReviewers.mockResolvedValue([reviewer()])
    api.setSubjectReviewerStatus.mockResolvedValue(reviewer({ status: "completed" }))
    const user = userEvent.setup()
    render(<SubjectReviewersBody subjectType="regulatory_dossier" subjectId={42} />)

    await screen.findByText("reviewer@example.com")
    await user.click(screen.getByRole("combobox", { name: /Status of reviewer@example.com/i }))
    await user.click(await screen.findByRole("option", { name: "Completed" }))

    await waitFor(() =>
      expect(api.setSubjectReviewerStatus).toHaveBeenCalledWith(
        "regulatory_dossier",
        42,
        "reviewer@example.com",
        "completed",
      ),
    )
  })

  it("renders an unreachable subject as not-found, with no permissions claim", async () => {
    api.listSubjectReviewers.mockResolvedValue([])
    api.listSubjectReviewers.mockRejectedValueOnce(new ApiError(404, { detail: "not found" }))
    render(<SubjectReviewersBody subjectType="regulatory_dossier" subjectId={999} />)

    expect(await screen.findByText(/This filing is not available/i)).toBeInTheDocument()
    expect(screen.queryByText(/permission/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Request review from/i)).not.toBeInTheDocument()
  })

  it("waits instead of calling out while the route id is still resolving", () => {
    render(<SubjectReviewersBody subjectType="reaction_project" subjectId={null} />)
    expect(api.listSubjectReviewers).not.toHaveBeenCalled()
  })
})
