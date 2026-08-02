import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api/client"
import { SubjectApprovalsBody } from "@/components/collaboration/subject-approvals-panel"
import {
  APPROVAL_DECISIONS,
  approvalDecisionLabel,
  buildRecordSubjectApprovalBody,
  currentSubjectApproval,
  describeSubjectApprovalError,
  isSubjectApprovalDecision,
  normalizeSubjectApprovals,
  sortSubjectApprovals,
  type SubjectApprovalRecord,
} from "@/lib/collaboration/subject-approvals"

const api = vi.hoisted(() => ({
  listSubjectApprovals: vi.fn(),
  recordSubjectApproval: vi.fn(),
}))

// Partial mock — keep the real builders, sorters and vocabulary guard; stub the network.
vi.mock("@/lib/collaboration/subject-approvals", async (orig) => ({
  ...(await orig<typeof import("@/lib/collaboration/subject-approvals")>()),
  listSubjectApprovals: (...a: unknown[]) => api.listSubjectApprovals(...a),
  recordSubjectApproval: (...a: unknown[]) => api.recordSubjectApproval(...a),
}))

/** The two decisions that belong to the SpectraCheck session surface. They live on the
 *  record type only because both surfaces share one table, and `POST /approvals` refuses
 *  them — so they must never reach a picker on a filing or a campaign. */
const STRUCTURE_ONLY_DECISIONS = ["approved_plausible", "approved_confirmed"] as const

function approval(over: Partial<SubjectApprovalRecord> = {}): SubjectApprovalRecord {
  return {
    id: 1,
    session_id: null,
    subject_type: "regulatory_dossier",
    subject_id: 42,
    module: "regulatory_hub",
    evidence_id: null,
    report_id: null,
    approver_email: "qa@example.com",
    decision: "approved",
    rationale: "Limits verified against the batch record.",
    created_at: "2026-08-01T10:00:00Z",
    metadata_json: {},
    warnings: [],
    notes: [],
    ...over,
  } as SubjectApprovalRecord
}

beforeEach(() => {
  api.listSubjectApprovals.mockReset()
  api.recordSubjectApproval.mockReset()
})

describe("subject-approvals lib", () => {
  // The trap: two vocabularies in one schema, only one of which this endpoint accepts.
  it("offers only the decisions a filing or a campaign can carry", () => {
    expect([...APPROVAL_DECISIONS]).toEqual(["approved", "rejected", "needs_changes", "deferred"])
    for (const d of STRUCTURE_ONLY_DECISIONS) {
      expect(APPROVAL_DECISIONS as readonly string[]).not.toContain(d)
      expect(isSubjectApprovalDecision(d)).toBe(false)
    }
  })

  it("refuses to send a structure-elucidation decision rather than letting it be refused", async () => {
    const { recordSubjectApproval: real } = await vi.importActual<
      typeof import("@/lib/collaboration/subject-approvals")
    >("@/lib/collaboration/subject-approvals")
    await expect(
      real({
        subjectType: "regulatory_dossier",
        subjectId: 42,
        // Only reachable through a widened cast — which is exactly the bug this guards.
        decision: "approved_confirmed" as never,
        rationale: "…",
      }),
    ).rejects.toThrow(/does not apply to a filing or a campaign/i)
  })

  it("omits a blank approver so the extra=forbid model does not 422", () => {
    const body = buildRecordSubjectApprovalBody({
      subjectType: "regulatory_dossier",
      subjectId: 42,
      decision: "needs_changes",
      rationale: "  Second source missing.  ",
      approverEmail: "   ",
    })
    expect(body).toEqual({
      subject_type: "regulatory_dossier",
      subject_id: 42,
      decision: "needs_changes",
      rationale: "Second source missing.",
    })
    expect("approver_email" in body).toBe(false)
  })

  it("carries an explicit approver through when one is given", () => {
    const body = buildRecordSubjectApprovalBody({
      subjectType: "reaction_project",
      subjectId: 7,
      decision: "approved",
      rationale: "Yield confirmed.",
      approverEmail: "qa@example.com",
    })
    expect(body.approver_email).toBe("qa@example.com")
  })

  // There is no PATCH: position changes by recording another decision, so "current" is a
  // read over the list, not a mutable field.
  it("reads the newest decision as the one that stands", () => {
    const rows = [
      approval({ id: 1, decision: "needs_changes", created_at: "2026-07-01T10:00:00Z" }),
      approval({ id: 2, decision: "approved", created_at: "2026-08-01T10:00:00Z" }),
    ]
    expect(sortSubjectApprovals(rows).map((a) => a.id)).toEqual([2, 1])
    expect(currentSubjectApproval(rows)?.decision).toBe("approved")
    expect(currentSubjectApproval([])).toBeNull()
  })

  it("labels a structure decision precisely if a shared table ever returns one", () => {
    expect(approvalDecisionLabel("approved")).toBe("Approved")
    expect(approvalDecisionLabel("needs_changes")).toBe("Needs changes")
    expect(approvalDecisionLabel("approved_confirmed")).toMatch(/structure/i)
    expect(approvalDecisionLabel(null)).toBe("—")
  })

  it("classifies an unreachable subject as not-found, never as a permissions failure", () => {
    const e = describeSubjectApprovalError(new ApiError(404, {}), "reaction_project")
    expect(e.kind).toBe("not_found")
    expect(e.message).not.toMatch(/permission|not allowed|forbidden|access denied/i)
    expect(e.message).toMatch(/campaign/)
  })

  it("reads a bare array and tolerates a wrapped list", () => {
    expect(normalizeSubjectApprovals([{ id: 1 }])).toHaveLength(1)
    expect(normalizeSubjectApprovals({ approvals: [{ id: 1 }, { id: 2 }] })).toHaveLength(2)
    expect(normalizeSubjectApprovals(undefined)).toEqual([])
  })
})

describe("SubjectApprovalsBody", () => {
  it("offers no decision the endpoint would refuse", async () => {
    api.listSubjectApprovals.mockResolvedValue([])
    const user = userEvent.setup()
    render(<SubjectApprovalsBody subjectType="regulatory_dossier" subjectId={42} />)

    await screen.findByText(/No decision recorded yet/i)
    await user.click(screen.getByRole("combobox"))

    for (const label of ["Approved", "Rejected", "Needs changes", "Deferred"]) {
      expect(await screen.findByRole("option", { name: label })).toBeInTheDocument()
    }
    expect(screen.queryByRole("option", { name: /structure/i })).not.toBeInTheDocument()
  })

  it("records a decision with its reason, then reloads", async () => {
    api.listSubjectApprovals.mockResolvedValue([])
    api.recordSubjectApproval.mockResolvedValue(approval())
    const user = userEvent.setup()
    render(<SubjectApprovalsBody subjectType="reaction_project" subjectId={7} />)

    await screen.findByText(/No decision recorded yet/i)
    await user.type(screen.getByLabelText(/Reason/i), "Yield confirmed across three runs.")
    await user.click(screen.getByRole("button", { name: /Record decision/i }))

    await waitFor(() =>
      expect(api.recordSubjectApproval).toHaveBeenCalledWith(
        expect.objectContaining({
          subjectType: "reaction_project",
          subjectId: 7,
          decision: "approved",
          rationale: "Yield confirmed across three runs.",
        }),
      ),
    )
    expect(api.listSubjectApprovals).toHaveBeenCalledTimes(2)
  })

  it("will not record a decision with no reason", async () => {
    api.listSubjectApprovals.mockResolvedValue([])
    const user = userEvent.setup()
    render(<SubjectApprovalsBody subjectType="regulatory_dossier" subjectId={42} />)

    await screen.findByText(/No decision recorded yet/i)
    await user.click(screen.getByRole("button", { name: /Record decision/i }))

    expect(await screen.findByText(/A reason is required/i)).toBeInTheDocument()
    expect(api.recordSubjectApproval).not.toHaveBeenCalled()
  })

  it("shows the decision that stands and keeps the superseded one on the record", async () => {
    api.listSubjectApprovals.mockResolvedValue([
      approval({ id: 1, decision: "needs_changes", rationale: "Second source missing.", created_at: "2026-07-01T10:00:00Z" }),
      approval({ id: 2, decision: "approved", rationale: "Second source attached.", created_at: "2026-08-01T10:00:00Z" }),
    ])
    render(<SubjectApprovalsBody subjectType="regulatory_dossier" subjectId={42} />)

    expect(await screen.findByText(/Position that stands/i)).toBeInTheDocument()
    expect(screen.getAllByText("Second source attached.").length).toBeGreaterThan(0)
    // Superseded, not erased.
    expect(screen.getByText("Second source missing.")).toBeInTheDocument()
  })

  // A recorded decision is a point-in-time record: there is nothing to edit, and nothing
  // here creates a §11.70 signature.
  it("offers no way to edit a decision, and never calls itself a signature", async () => {
    api.listSubjectApprovals.mockResolvedValue([approval()])
    render(<SubjectApprovalsBody subjectType="regulatory_dossier" subjectId={42} />)

    await screen.findByText(/Position that stands/i)
    expect(screen.queryByRole("button", { name: /^sign\b|edit|update|delete/i })).not.toBeInTheDocument()
    expect(screen.getByText(/not an electronic signature/i)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /e-Signatures workspace/i })).toHaveAttribute(
      "href",
      "/validation-center/esignatures",
    )
  })

  it("renders an unreachable subject as not-found, with no permissions claim", async () => {
    api.listSubjectApprovals.mockResolvedValue([])
    api.listSubjectApprovals.mockRejectedValueOnce(new ApiError(404, { detail: "not found" }))
    render(<SubjectApprovalsBody subjectType="regulatory_dossier" subjectId={999} />)

    expect(await screen.findByText(/This filing is not available/i)).toBeInTheDocument()
    expect(screen.queryByText(/permission/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Reason/i)).not.toBeInTheDocument()
  })

  it("waits instead of calling out while the route id is still resolving", () => {
    render(<SubjectApprovalsBody subjectType="reaction_project" subjectId={null} />)
    expect(api.listSubjectApprovals).not.toHaveBeenCalled()
  })
})
