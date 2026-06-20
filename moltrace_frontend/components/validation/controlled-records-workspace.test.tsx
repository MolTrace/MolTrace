import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api/client"
import { ControlledRecordsWorkspace } from "@/components/validation/controlled-records-workspace"

const apiMock = vi.hoisted(() => ({ fn: vi.fn() }))
let lastListPath = ""
let lastPostBody: Record<string, unknown> | null = null
let archiveImpl: (body: unknown) => Promise<unknown> = () => Promise.resolve({})

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  apiFetch: (...a: unknown[]) => apiMock.fn(...a),
}))
vi.mock("@/components/app/backend-status-indicator", () => ({
  BackendStatusIndicator: () => null,
}))

const ACTIVE = {
  id: 1,
  title: "Active Doc",
  record_type: "sop",
  version: "1",
  status: "approved",
  content_hash: "h1",
  updated_at: "2026-06-01T00:00:00Z",
  reason_for_change: null,
  deleted_at: null,
  deleted_by: null,
}
const ARCHIVED = {
  id: 2,
  title: "Archived Doc",
  record_type: "report",
  version: "3",
  status: "archived",
  content_hash: "h2",
  updated_at: "2026-06-10T00:00:00Z",
  reason_for_change: "superseded by v4",
  deleted_at: "2026-06-10T12:00:00Z",
  deleted_by: "qa@example.com",
}

beforeEach(() => {
  lastListPath = ""
  lastPostBody = null
  archiveImpl = () => Promise.resolve(ARCHIVED)
  apiMock.fn.mockReset().mockImplementation((path: string, opts?: { method?: string; body?: Record<string, unknown> }) => {
    const method = opts?.method ?? "GET"
    if (method === "GET" && (path === "/controlled-records" || path.startsWith("/controlled-records?"))) {
      lastListPath = path
      return Promise.resolve([ACTIVE, ARCHIVED])
    }
    if (method === "GET" && /^\/controlled-records\/[^/]+$/.test(path)) {
      return Promise.resolve(path.endsWith("/2") ? ARCHIVED : ACTIVE)
    }
    if (method === "POST" && path === "/controlled-records") {
      lastPostBody = opts?.body ?? null
      return Promise.resolve({ ...ACTIVE, id: 9 })
    }
    if (method === "POST" && path.endsWith("/archive")) {
      return archiveImpl(opts?.body)
    }
    return Promise.resolve({})
  })
})

describe("ControlledRecordsWorkspace — ALCOA+ hardening", () => {
  it("re-fetches with include_deleted=true when the toggle is on", async () => {
    const user = userEvent.setup()
    render(<ControlledRecordsWorkspace />)
    await waitFor(() => expect(screen.getByText("Archived Doc")).toBeInTheDocument())
    expect(lastListPath).toBe("/controlled-records")

    await user.click(screen.getByLabelText("Include archived/deleted records"))
    await waitFor(() => expect(lastListPath).toBe("/controlled-records?include_deleted=true"))
  })

  it("renders reason_for_change / deleted_by / deleted_at on archived rows (retained framing)", async () => {
    render(<ControlledRecordsWorkspace />)
    await waitFor(() => expect(screen.getByText("Archived Doc")).toBeInTheDocument())
    expect(screen.getByText("superseded by v4")).toBeInTheDocument()
    expect(screen.getByText(/retained ·/)).toBeInTheDocument()
    expect(screen.getByText(/qa@example\.com/)).toBeInTheDocument()
  })

  it("creates without sending server-authoritative timestamps", async () => {
    const user = userEvent.setup()
    render(<ControlledRecordsWorkspace />)
    await waitFor(() => expect(screen.getByText("Archived Doc")).toBeInTheDocument())

    await user.type(screen.getByLabelText("title"), "New SOP")
    await user.click(screen.getByRole("button", { name: /Create controlled record/i }))

    await waitFor(() => expect(lastPostBody).not.toBeNull())
    expect(lastPostBody).toMatchObject({ title: "New SOP", version: "1" })
    expect(lastPostBody).not.toHaveProperty("created_at")
    expect(lastPostBody).not.toHaveProperty("updated_at")
    expect(lastPostBody).not.toHaveProperty("deleted_at")
  })

  it("surfaces the 422 reason-required validation message on archive", async () => {
    const user = userEvent.setup()
    archiveImpl = () =>
      Promise.reject(
        new ApiError(422, { detail: [{ msg: "Reason must not be blank.", loc: ["body", "reason"] }] }, "Unprocessable Entity"),
      )
    render(<ControlledRecordsWorkspace />)
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Open" }).length).toBeGreaterThan(0))
    await user.click(screen.getAllByRole("button", { name: "Open" })[0]) // open the active record

    await user.type(await screen.findByLabelText("archive reason"), "   ")
    // client requires a non-blank reason; type real text so the request is sent, then the server 422s
    await user.clear(screen.getByLabelText("archive reason"))
    await user.type(screen.getByLabelText("archive reason"), "obsolete")
    await user.click(screen.getByRole("button", { name: /^Archive$/ }))

    expect(await screen.findByText("Reason must not be blank.")).toBeInTheDocument()
  })
})
