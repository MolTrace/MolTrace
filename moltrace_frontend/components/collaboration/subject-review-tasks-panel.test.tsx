import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api/client"
import { SubjectReviewTasksBody } from "@/components/collaboration/subject-review-tasks-panel"
import {
  buildRaiseReviewTaskBody,
  describeSubjectReviewTaskError,
  normalizeReviewTasks,
  openReviewTaskCount,
  sortReviewTasks,
  type ReviewTaskRecord,
} from "@/lib/collaboration/subject-review-tasks"

const api = vi.hoisted(() => ({
  listSubjectReviewTasks: vi.fn(),
  raiseSubjectReviewTask: vi.fn(),
  updateSubjectReviewTask: vi.fn(),
}))

// Partial mock — keep the real builders, sorters and error classifier; stub the network.
vi.mock("@/lib/collaboration/subject-review-tasks", async (orig) => ({
  ...(await orig<typeof import("@/lib/collaboration/subject-review-tasks")>()),
  listSubjectReviewTasks: (...a: unknown[]) => api.listSubjectReviewTasks(...a),
  raiseSubjectReviewTask: (...a: unknown[]) => api.raiseSubjectReviewTask(...a),
  updateSubjectReviewTask: (...a: unknown[]) => api.updateSubjectReviewTask(...a),
}))

function task(over: Partial<ReviewTaskRecord> = {}): ReviewTaskRecord {
  return {
    id: 1,
    session_id: null,
    subject_type: "regulatory_dossier",
    subject_id: 42,
    module: "regulatory_hub",
    title: "Confirm the nitrosamine limit",
    description: null,
    assigned_to: "reviewer@example.com",
    status: "open",
    priority: "high",
    created_at: "2026-08-01T10:00:00Z",
    updated_at: "2026-08-01T10:00:00Z",
    metadata_json: {},
    warnings: [],
    notes: [],
    ...over,
  } as ReviewTaskRecord
}

beforeEach(() => {
  api.listSubjectReviewTasks.mockReset()
  api.raiseSubjectReviewTask.mockReset()
  api.updateSubjectReviewTask.mockReset()
})

describe("subject-review-tasks lib", () => {
  it("omits blank optional fields so the extra=forbid model does not 422", () => {
    const body = buildRaiseReviewTaskBody({
      subjectType: "regulatory_dossier",
      subjectId: 42,
      title: "  Check the limit  ",
      description: "   ",
      assignedTo: "",
    })
    expect(body).toEqual({
      subject_type: "regulatory_dossier",
      subject_id: 42,
      title: "Check the limit",
      status: "open",
      priority: "medium",
    })
    expect("description" in body).toBe(false)
    expect("assigned_to" in body).toBe(false)
  })

  it("carries description, assignee and priority through when they are set", () => {
    const body = buildRaiseReviewTaskBody({
      subjectType: "reaction_project",
      subjectId: 7,
      title: "Check the solvent swap",
      description: "See cycle 3.",
      assignedTo: "chem@example.com",
      priority: "critical",
    })
    expect(body.description).toBe("See cycle 3.")
    expect(body.assigned_to).toBe("chem@example.com")
    expect(body.priority).toBe("critical")
  })

  // The endpoint answers 404 for a subject that is not yours AND for one that does not
  // exist, on purpose — raising a task must not reveal that another customer's filing
  // exists. Rendering it as a permissions error would state something the response does
  // not support.
  it("classifies an unreachable subject as not-found, never as a permissions failure", () => {
    const e = describeSubjectReviewTaskError(
      new ApiError(404, { detail: "Review subject not found." }),
      "regulatory_dossier",
    )
    expect(e.kind).toBe("not_found")
    expect(e.message).not.toMatch(/permission|not allowed|forbidden|access denied/i)
    expect(e.message).toMatch(/no longer available/i)
  })

  it("classifies a refused spectroscopy session as the wrong surface", () => {
    const e = describeSubjectReviewTaskError(new ApiError(403, {}), "reaction_project")
    expect(e.kind).toBe("wrong_surface")
    expect(e.message).toMatch(/session workspace/i)
  })

  it("names the subject in plain language, not by its wire token", () => {
    expect(describeSubjectReviewTaskError(new ApiError(404, {}), "regulatory_dossier").message).toMatch(/filing/)
    expect(describeSubjectReviewTaskError(new ApiError(404, {}), "reaction_project").message).toMatch(/campaign/)
  })

  it("puts open tasks above closed ones, newest first", () => {
    const rows = [
      task({ id: 1, status: "resolved", updated_at: "2026-08-02T10:00:00Z" }),
      task({ id: 2, status: "open", updated_at: "2026-07-01T10:00:00Z" }),
      task({ id: 3, status: "in_progress", updated_at: "2026-08-01T10:00:00Z" }),
    ]
    expect(sortReviewTasks(rows).map((t) => t.id)).toEqual([3, 2, 1])
    expect(openReviewTaskCount(rows)).toBe(2)
  })

  it("reads a bare array and tolerates a wrapped list", () => {
    expect(normalizeReviewTasks([{ id: 1 }])).toHaveLength(1)
    expect(normalizeReviewTasks({ review_tasks: [{ id: 1 }, { id: 2 }] })).toHaveLength(2)
    expect(normalizeReviewTasks(null)).toEqual([])
  })
})

describe("SubjectReviewTasksBody", () => {
  it("lists the queue for a filing and reports what is still open", async () => {
    api.listSubjectReviewTasks.mockResolvedValue([
      task(),
      task({ id: 2, status: "resolved", title: "Attach the batch certificate" }),
    ])
    const onCount = vi.fn()
    render(
      <SubjectReviewTasksBody
        subjectType="regulatory_dossier"
        subjectId={42}
        onAttentionCountChange={onCount}
      />,
    )

    expect(await screen.findByText("Confirm the nitrosamine limit")).toBeInTheDocument()
    expect(screen.getByText("Attach the batch certificate")).toBeInTheDocument()
    // The count is what the tab badge is drawn from — the closed task must not be in it.
    await waitFor(() => expect(onCount).toHaveBeenCalledWith(1))
    expect(api.listSubjectReviewTasks).toHaveBeenCalledWith("regulatory_dossier", 42)
  })

  it("raises a task against the subject it is pointed at, then reloads", async () => {
    api.listSubjectReviewTasks.mockResolvedValue([])
    api.raiseSubjectReviewTask.mockResolvedValue(task())
    const user = userEvent.setup()
    render(<SubjectReviewTasksBody subjectType="reaction_project" subjectId={7} />)

    await screen.findByText(/No one has been asked to review this campaign yet/i)
    await user.type(screen.getByLabelText(/What should they look at/i), "Check the solvent swap")
    await user.type(screen.getByLabelText(/Assign to/i), "chem@example.com")
    await user.click(screen.getByRole("button", { name: /Raise review task/i }))

    await waitFor(() =>
      expect(api.raiseSubjectReviewTask).toHaveBeenCalledWith(
        expect.objectContaining({
          subjectType: "reaction_project",
          subjectId: 7,
          title: "Check the solvent swap",
          assignedTo: "chem@example.com",
        }),
      ),
    )
    expect(api.listSubjectReviewTasks).toHaveBeenCalledTimes(2)
  })

  it("will not send a task with no title", async () => {
    api.listSubjectReviewTasks.mockResolvedValue([])
    const user = userEvent.setup()
    render(<SubjectReviewTasksBody subjectType="regulatory_dossier" subjectId={42} />)

    await screen.findByText(/No one has been asked to review this filing yet/i)
    await user.click(screen.getByRole("button", { name: /Raise review task/i }))

    expect(await screen.findByText(/A short title is required/i)).toBeInTheDocument()
    expect(api.raiseSubjectReviewTask).not.toHaveBeenCalled()
  })

  it("progresses a task to a new status", async () => {
    api.listSubjectReviewTasks.mockResolvedValue([task()])
    api.updateSubjectReviewTask.mockResolvedValue(task({ status: "resolved" }))
    const user = userEvent.setup()
    render(<SubjectReviewTasksBody subjectType="regulatory_dossier" subjectId={42} />)

    await screen.findByText("Confirm the nitrosamine limit")
    await user.click(screen.getByRole("combobox", { name: /Status of/i }))
    await user.click(await screen.findByRole("option", { name: "Resolved" }))

    await waitFor(() => expect(api.updateSubjectReviewTask).toHaveBeenCalledWith(1, { status: "resolved" }))
  })

  // A filing belonging to another organization answers exactly as a deleted one does.
  it("renders an unreachable subject as not-found, with no permissions claim", async () => {
    api.listSubjectReviewTasks.mockRejectedValue(new ApiError(404, { detail: "Review subject not found." }))
    render(<SubjectReviewTasksBody subjectType="regulatory_dossier" subjectId={999} />)

    expect(await screen.findByText(/This filing is not available/i)).toBeInTheDocument()
    expect(screen.queryByText(/permission/i)).not.toBeInTheDocument()
    // The form is gone — there is nothing to raise a task against.
    expect(screen.queryByLabelText(/What should they look at/i)).not.toBeInTheDocument()
  })

  it("waits instead of calling out while the route id is still resolving", () => {
    render(<SubjectReviewTasksBody subjectType="reaction_project" subjectId={null} />)
    expect(api.listSubjectReviewTasks).not.toHaveBeenCalled()
  })
})
