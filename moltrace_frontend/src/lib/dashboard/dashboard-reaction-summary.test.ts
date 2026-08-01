import { beforeEach, describe, expect, it, vi } from "vitest"
import { fetchDashboardReactionSummary } from "@/src/lib/dashboard/dashboard-reaction-summary"

const apiFetch = vi.fn()
vi.mock("@/lib/api/client", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }))

function project(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    name: "Suzuki route A",
    status: "active",
    updated_at: "2026-07-01T00:00:00Z",
    ...over,
  }
}

describe("fetchDashboardReactionSummary", () => {
  // Braces matter: an expression-bodied arrow returns the mock, and vitest calls a value returned
  // from beforeEach as the test's teardown — which would invoke apiFetch again after the test.
  beforeEach(() => {
    apiFetch.mockReset()
  })

  it("counts by status and excludes archived from every count", async () => {
    apiFetch.mockResolvedValue([
      project({ id: 1, status: "active" }),
      project({ id: 2, status: "active" }),
      project({ id: 3, status: "draft" }),
      project({ id: 4, status: "completed" }),
      project({ id: 5, status: "paused" }),
      project({ id: 6, status: "archived" }),
    ])
    const res = await fetchDashboardReactionSummary()
    expect(res.available).toBe(true)
    if (!res.available) return
    expect(res.activeProjects).toBe(2)
    expect(res.draftProjects).toBe(1)
    expect(res.completedProjects).toBe(1)
    // paused counts toward the total but has no tile of its own; archived counts nowhere.
    expect(res.totalProjects).toBe(5)
  })

  it("picks the most recently updated project, not the first in the list", async () => {
    apiFetch.mockResolvedValue([
      project({ id: 1, name: "Older", updated_at: "2026-01-01T00:00:00Z" }),
      project({ id: 2, name: "Newest", updated_at: "2026-07-30T00:00:00Z" }),
      project({ id: 3, name: "Middle", updated_at: "2026-04-01T00:00:00Z" }),
    ])
    const res = await fetchDashboardReactionSummary()
    if (!res.available) throw new Error("expected available")
    expect(res.latestProjectId).toBe(2)
    expect(res.latestProjectName).toBe("Newest")
  })

  it("never points at an archived project", async () => {
    apiFetch.mockResolvedValue([
      project({ id: 1, name: "Live", updated_at: "2026-01-01T00:00:00Z" }),
      project({ id: 2, name: "Archived", status: "archived", updated_at: "2026-07-30T00:00:00Z" }),
    ])
    const res = await fetchDashboardReactionSummary()
    if (!res.available) throw new Error("expected available")
    expect(res.latestProjectId).toBe(1)
  })

  it("still offers a link when no row has a parseable timestamp", async () => {
    apiFetch.mockResolvedValue([project({ id: 7, updated_at: "", created_at: "" })])
    const res = await fetchDashboardReactionSummary()
    if (!res.available) throw new Error("expected available")
    expect(res.latestProjectId).toBe(7)
  })

  it("reads a wrapped list as well as a bare array", async () => {
    apiFetch.mockResolvedValue({ items: [project({ id: 9 })] })
    const res = await fetchDashboardReactionSummary()
    if (!res.available) throw new Error("expected available")
    expect(res.totalProjects).toBe(1)
    expect(res.latestProjectId).toBe(9)
  })

  it("reports unavailable rather than zero when the request is refused", async () => {
    // A refused module must not render as "0 active projects" — that is a claim about the data.
    apiFetch.mockImplementation(async () => {
      throw new Error("403")
    })
    const res = await fetchDashboardReactionSummary()
    expect(res.available).toBe(false)
  })

  it("treats an empty list as a real zero", async () => {
    apiFetch.mockResolvedValue([])
    const res = await fetchDashboardReactionSummary()
    expect(res.available).toBe(true)
    if (!res.available) return
    expect(res.totalProjects).toBe(0)
    expect(res.latestProjectId).toBeNull()
  })
})
