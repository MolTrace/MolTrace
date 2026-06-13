import { beforeEach, describe, expect, it, vi } from "vitest"
import { fetchDashboardCoreModuleActivity } from "@/src/lib/dashboard/dashboard-core-module-activity"

const { mockApiFetch } = vi.hoisted(() => ({
  mockApiFetch: vi.fn(),
}))

vi.mock("@/lib/api/client", () => ({
  apiFetch: mockApiFetch,
}))

describe("fetchDashboardCoreModuleActivity", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it("rolls up sanitized core module open events in stable module order", async () => {
    mockApiFetch.mockResolvedValue([
      {
        event_type: "core_module_opened",
        created_at: "2026-05-20T12:00:00Z",
        metadata_json: { module: "spectracheck", surface: "programs_workspace" },
      },
      {
        event_type: "core_module_opened",
        created_at: "2026-05-20T12:05:00Z",
        metadata_json: { module: "regulatory_hub", surface: "programs_workspace" },
      },
      {
        event_type: "core_module_opened",
        created_at: "2026-05-20T12:10:00Z",
        metadata_json: { module: "reactioniq", surface: "programs_workspace" },
      },
      {
        event_type: "core_module_opened",
        created_at: "2026-05-20T12:15:00Z",
        metadata_json: { module: "reaction_optimization", surface: "legacy_program_key" },
      },
    ])

    const activity = await fetchDashboardCoreModuleActivity()

    expect(mockApiFetch).toHaveBeenCalledWith("/analytics/events?event_type=core_module_opened&limit=200", {
      method: "GET",
    })
    expect(activity).toEqual({
      available: true,
      total: 4,
      warnings: [],
      rows: [
        {
          module: "spectracheck",
          label: "SpectraCheck",
          count: 1,
          latestAt: "2026-05-20T12:00:00Z",
        },
        {
          module: "regulatory_hub",
          label: "Regentry",
          count: 1,
          latestAt: "2026-05-20T12:05:00Z",
        },
        {
          module: "reactioniq",
          label: "Repho",
          count: 2,
          latestAt: "2026-05-20T12:15:00Z",
        },
      ],
    })
  })

  it("keeps dashboard callers stable when analytics cannot be read", async () => {
    mockApiFetch.mockRejectedValue(new Error("forbidden"))

    await expect(fetchDashboardCoreModuleActivity()).resolves.toMatchObject({
      available: false,
      total: 0,
      warnings: ["Core module analytics unavailable."],
      rows: [
        { module: "spectracheck", label: "SpectraCheck", count: 0, latestAt: null },
        { module: "regulatory_hub", label: "Regentry", count: 0, latestAt: null },
        { module: "reactioniq", label: "Repho", count: 0, latestAt: null },
      ],
    })
  })
})
