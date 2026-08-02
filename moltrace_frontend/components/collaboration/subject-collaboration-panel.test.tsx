import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { SubjectCollaborationPanel } from "@/components/collaboration/subject-collaboration-panel"

const api = vi.hoisted(() => ({
  listSubjectReviewTasks: vi.fn(),
  listSubjectComments: vi.fn(),
  listSubjectApprovals: vi.fn(),
  listSubjectReviewers: vi.fn(),
}))

vi.mock("@/lib/collaboration/subject-review-tasks", async (orig) => ({
  ...(await orig<typeof import("@/lib/collaboration/subject-review-tasks")>()),
  listSubjectReviewTasks: (...a: unknown[]) => api.listSubjectReviewTasks(...a),
}))
vi.mock("@/lib/collaboration/subject-comments", async (orig) => ({
  ...(await orig<typeof import("@/lib/collaboration/subject-comments")>()),
  listSubjectComments: (...a: unknown[]) => api.listSubjectComments(...a),
}))
vi.mock("@/lib/collaboration/subject-approvals", async (orig) => ({
  ...(await orig<typeof import("@/lib/collaboration/subject-approvals")>()),
  listSubjectApprovals: (...a: unknown[]) => api.listSubjectApprovals(...a),
}))
vi.mock("@/lib/collaboration/subject-reviewers", async (orig) => ({
  ...(await orig<typeof import("@/lib/collaboration/subject-reviewers")>()),
  listSubjectReviewers: (...a: unknown[]) => api.listSubjectReviewers(...a),
}))

beforeEach(() => {
  api.listSubjectReviewTasks.mockReset().mockResolvedValue([])
  api.listSubjectComments.mockReset().mockResolvedValue([])
  api.listSubjectApprovals.mockReset().mockResolvedValue([])
  api.listSubjectReviewers.mockReset().mockResolvedValue([])
})

const task = {
  id: 1,
  title: "Confirm the nitrosamine limit",
  status: "open",
  priority: "high",
  assigned_to: null,
  description: null,
  updated_at: "2026-08-01T10:00:00Z",
}

describe("SubjectCollaborationPanel", () => {
  it("names the record in plain language, not by its wire token", async () => {
    render(<SubjectCollaborationPanel subjectType="regulatory_dossier" subjectId={42} />)
    expect(await screen.findByText(/nominations for this filing/i)).toBeInTheDocument()
    expect(screen.queryByText(/regulatory_dossier|subject_type|subject_id/)).not.toBeInTheDocument()
  })

  // A tab nobody opens costs nothing: only the default surface loads on mount.
  it("loads only the open tab, then the one the reader switches to", async () => {
    const user = userEvent.setup()
    render(<SubjectCollaborationPanel subjectType="regulatory_dossier" subjectId={42} />)

    await waitFor(() => expect(api.listSubjectReviewTasks).toHaveBeenCalledWith("regulatory_dossier", 42))
    expect(api.listSubjectComments).not.toHaveBeenCalled()
    expect(api.listSubjectApprovals).not.toHaveBeenCalled()
    expect(api.listSubjectReviewers).not.toHaveBeenCalled()

    await user.click(screen.getByRole("tab", { name: /Notes/i }))
    await waitFor(() => expect(api.listSubjectComments).toHaveBeenCalledWith("regulatory_dossier", 42))
    expect(await screen.findByLabelText(/Your note/i)).toBeInTheDocument()
  })

  it("badges a tab with what is still outstanding on it", async () => {
    api.listSubjectReviewTasks.mockResolvedValue([task, { ...task, id: 2, status: "resolved" }])
    render(<SubjectCollaborationPanel subjectType="reaction_project" subjectId={7} />)

    const tasksTab = await screen.findByRole("tab", { name: /Review tasks/i })
    await waitFor(() => expect(within(tasksTab).getByText("1")).toBeInTheDocument())
    // A tab that has not loaded carries no count — an absent badge is not a claim of zero.
    expect(within(screen.getByRole("tab", { name: /Reviewers/i })).queryByText(/\d/)).toBeNull()
  })

  it("carries all four surfaces on one record", async () => {
    render(<SubjectCollaborationPanel subjectType="reaction_project" subjectId={7} />)
    for (const name of [/Review tasks/i, /Notes/i, /Sign-off/i, /Reviewers/i]) {
      expect(await screen.findByRole("tab", { name })).toBeInTheDocument()
    }
  })

  it("holds off on every surface while the route id is still resolving", async () => {
    render(<SubjectCollaborationPanel subjectType="regulatory_dossier" subjectId={null} />)
    await screen.findByRole("tab", { name: /Review tasks/i })
    expect(api.listSubjectReviewTasks).not.toHaveBeenCalled()
    expect(api.listSubjectComments).not.toHaveBeenCalled()
  })
})
