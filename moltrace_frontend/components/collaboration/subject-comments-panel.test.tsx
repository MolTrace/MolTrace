import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api/client"
import { SubjectCommentsBody } from "@/components/collaboration/subject-comments-panel"
import {
  buildLeaveSubjectCommentBody,
  describeSubjectCommentError,
  normalizeSubjectComments,
  sortSubjectComments,
  unresolvedCommentCount,
  type SubjectCommentRecord,
} from "@/lib/collaboration/subject-comments"

const api = vi.hoisted(() => ({
  listSubjectComments: vi.fn(),
  leaveSubjectComment: vi.fn(),
  updateSubjectComment: vi.fn(),
}))

// Partial mock — keep the real builders, sorters and error classifier; stub the network.
vi.mock("@/lib/collaboration/subject-comments", async (orig) => ({
  ...(await orig<typeof import("@/lib/collaboration/subject-comments")>()),
  listSubjectComments: (...a: unknown[]) => api.listSubjectComments(...a),
  leaveSubjectComment: (...a: unknown[]) => api.leaveSubjectComment(...a),
  updateSubjectComment: (...a: unknown[]) => api.updateSubjectComment(...a),
}))

function comment(over: Partial<SubjectCommentRecord> = {}): SubjectCommentRecord {
  return {
    id: 1,
    session_id: null,
    subject_type: "regulatory_dossier",
    subject_id: 42,
    module: "regulatory_hub",
    evidence_id: null,
    artifact_id: null,
    author_email: "reviewer@example.com",
    comment: "The nitrosamine limit needs a second source.",
    comment_type: "concern",
    resolved: false,
    created_at: "2026-08-01T10:00:00Z",
    updated_at: "2026-08-01T10:00:00Z",
    metadata_json: {},
    warnings: [],
    notes: [],
    ...over,
  } as SubjectCommentRecord
}

beforeEach(() => {
  api.listSubjectComments.mockReset()
  api.leaveSubjectComment.mockReset()
  api.updateSubjectComment.mockReset()
})

describe("subject-comments lib", () => {
  it("sends the type alongside the note, trimmed", () => {
    const body = buildLeaveSubjectCommentBody({
      subjectType: "regulatory_dossier",
      subjectId: 42,
      comment: "  Needs a second source.  ",
      commentType: "concern",
    })
    expect(body).toEqual({
      subject_type: "regulatory_dossier",
      subject_id: 42,
      comment: "Needs a second source.",
      comment_type: "concern",
    })
  })

  it("defaults the type rather than omitting it — the generated model requires it", () => {
    const body = buildLeaveSubjectCommentBody({
      subjectType: "reaction_project",
      subjectId: 7,
      comment: "Looks right.",
    })
    expect(body.comment_type).toBe("note")
  })

  // Same semantics as review tasks: a filing belonging to another organization answers
  // exactly as a deleted one does, and the UI must not upgrade that into a claim.
  it("classifies an unreachable subject as not-found, never as a permissions failure", () => {
    const e = describeSubjectCommentError(new ApiError(404, {}), "regulatory_dossier")
    expect(e.kind).toBe("not_found")
    expect(e.message).not.toMatch(/permission|not allowed|forbidden|access denied/i)
    expect(e.message).toMatch(/no longer available/i)
  })

  it("points a refused spectroscopy session at its own comment surface", () => {
    const e = describeSubjectCommentError(new ApiError(403, {}), "reaction_project")
    expect(e.kind).toBe("wrong_surface")
    expect(e.message).toMatch(/piece of evidence/i)
  })

  it("puts unresolved notes above settled ones, newest first", () => {
    const rows = [
      comment({ id: 1, resolved: true, created_at: "2026-08-02T10:00:00Z" }),
      comment({ id: 2, resolved: false, created_at: "2026-07-01T10:00:00Z" }),
      comment({ id: 3, resolved: false, created_at: "2026-08-01T10:00:00Z" }),
    ]
    expect(sortSubjectComments(rows).map((c) => c.id)).toEqual([3, 2, 1])
    expect(unresolvedCommentCount(rows)).toBe(2)
  })

  it("reads a bare array and tolerates a wrapped list", () => {
    expect(normalizeSubjectComments([{ id: 1 }])).toHaveLength(1)
    expect(normalizeSubjectComments({ comments: [{ id: 1 }, { id: 2 }] })).toHaveLength(2)
    expect(normalizeSubjectComments(null)).toEqual([])
  })
})

describe("SubjectCommentsBody", () => {
  it("lists the thread and reports what is still unresolved", async () => {
    api.listSubjectComments.mockResolvedValue([
      comment(),
      comment({ id: 2, resolved: true, comment: "Confirmed against the batch record." }),
    ])
    const onCount = vi.fn()
    render(
      <SubjectCommentsBody
        subjectType="regulatory_dossier"
        subjectId={42}
        onAttentionCountChange={onCount}
      />,
    )

    expect(await screen.findByText("The nitrosamine limit needs a second source.")).toBeInTheDocument()
    expect(screen.getByText("Confirmed against the batch record.")).toBeInTheDocument()
    await waitFor(() => expect(onCount).toHaveBeenCalledWith(1))
    expect(api.listSubjectComments).toHaveBeenCalledWith("regulatory_dossier", 42)
  })

  it("posts a note against the subject it is pointed at, then reloads", async () => {
    api.listSubjectComments.mockResolvedValue([])
    api.leaveSubjectComment.mockResolvedValue(comment())
    const user = userEvent.setup()
    render(<SubjectCommentsBody subjectType="reaction_project" subjectId={7} />)

    await screen.findByText(/No one has left a note on this campaign yet/i)
    await user.type(screen.getByLabelText(/Your note/i), "Check the solvent swap.")
    await user.click(screen.getByRole("button", { name: /Post note/i }))

    await waitFor(() =>
      expect(api.leaveSubjectComment).toHaveBeenCalledWith(
        expect.objectContaining({
          subjectType: "reaction_project",
          subjectId: 7,
          comment: "Check the solvent swap.",
        }),
      ),
    )
    expect(api.listSubjectComments).toHaveBeenCalledTimes(2)
  })

  it("will not send an empty note", async () => {
    api.listSubjectComments.mockResolvedValue([])
    const user = userEvent.setup()
    render(<SubjectCommentsBody subjectType="regulatory_dossier" subjectId={42} />)

    await screen.findByText(/No one has left a note on this filing yet/i)
    await user.click(screen.getByRole("button", { name: /Post note/i }))

    expect(await screen.findByText(/Write something before posting/i)).toBeInTheDocument()
    expect(api.leaveSubjectComment).not.toHaveBeenCalled()
  })

  // Resolving settles a note. It must not read as, or become, a delete.
  it("marks a note settled without removing what was said", async () => {
    api.listSubjectComments.mockResolvedValue([comment()])
    api.updateSubjectComment.mockResolvedValue(comment({ resolved: true }))
    const user = userEvent.setup()
    render(<SubjectCommentsBody subjectType="regulatory_dossier" subjectId={42} />)

    await screen.findByText("The nitrosamine limit needs a second source.")
    expect(screen.queryByRole("button", { name: /delete|remove/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /Mark resolved/i }))

    await waitFor(() => expect(api.updateSubjectComment).toHaveBeenCalledWith(1, { resolved: true }))
  })

  it("reopens a settled note", async () => {
    api.listSubjectComments.mockResolvedValue([comment({ resolved: true })])
    api.updateSubjectComment.mockResolvedValue(comment())
    const user = userEvent.setup()
    render(<SubjectCommentsBody subjectType="regulatory_dossier" subjectId={42} />)

    await screen.findByText("The nitrosamine limit needs a second source.")
    await user.click(screen.getByRole("button", { name: /Reopen/i }))

    await waitFor(() => expect(api.updateSubjectComment).toHaveBeenCalledWith(1, { resolved: false }))
  })

  it("renders an unreachable subject as not-found, with no permissions claim", async () => {
    api.listSubjectComments.mockResolvedValue([])
    api.listSubjectComments.mockRejectedValueOnce(new ApiError(404, { detail: "not found" }))
    render(<SubjectCommentsBody subjectType="regulatory_dossier" subjectId={999} />)

    expect(await screen.findByText(/This filing is not available/i)).toBeInTheDocument()
    expect(screen.queryByText(/permission/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Your note/i)).not.toBeInTheDocument()
  })

  it("waits instead of calling out while the route id is still resolving", () => {
    render(<SubjectCommentsBody subjectType="reaction_project" subjectId={null} />)
    expect(api.listSubjectComments).not.toHaveBeenCalled()
  })
})
