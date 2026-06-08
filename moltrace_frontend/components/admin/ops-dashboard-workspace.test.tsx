import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { OpsDashboardWorkspace } from "@/components/admin/ops-dashboard-workspace"

// Hoisted so both the vi.mock factory (itself hoisted) and the test body can
// reference them without hitting the temporal dead zone.
const { MockApiError, mockApiFetch } = vi.hoisted(() => {
  class MockApiError extends Error {
    status: number
    data?: unknown
    constructor(status: number, data?: unknown, message?: string) {
      super(message ?? `status ${status}`)
      this.name = "ApiError"
      this.status = status
      this.data = data
    }
  }
  return { MockApiError, mockApiFetch: vi.fn<(path: string) => Promise<unknown>>() }
})

vi.mock("@/lib/api/client", () => ({
  ApiError: MockApiError,
  apiFetch: (path: string) => mockApiFetch(path),
}))

const GATE = {
  fails_closed: true,
  self_check_passed: true,
  self_check_failures: [],
  checks: [
    { name: "dominance", description: "Prompt 17 dominance gate" },
    { name: "audit_chain", description: "Prompt 12 audit chain verifies" },
    { name: "tests_green", description: "test suite is green" },
    { name: "data_leakage", description: "never trained on the gold set" },
  ],
  output_contract_schema_version: "1.0.0",
  monitoring_thresholds: { psi_warn: 0.1, psi_breach: 0.25 },
  data_mode: "live",
  generated_at: "2026-06-08T12:00:00Z",
}

const LINEAGE_EMPTY = {
  rows: [],
  registry_configured: false,
  note: "No model registry is configured on this deployment yet.",
  data_mode: "live",
  generated_at: "2026-06-08T12:00:00Z",
}

function routeOk(path: string): Promise<unknown> {
  if (path.includes("deployment-gate")) return Promise.resolve(GATE)
  if (path.includes("model-lineage")) return Promise.resolve(LINEAGE_EMPTY)
  return Promise.reject(new Error(`unexpected path ${path}`))
}

describe("OpsDashboardWorkspace", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it("renders the fail-closed posture, self-check, the four checks, and thresholds", async () => {
    mockApiFetch.mockImplementation(routeOk)
    render(<OpsDashboardWorkspace />)

    await waitFor(() => expect(screen.getByText("Fails closed")).toBeInTheDocument())
    expect(screen.getByText("Self-check passed")).toBeInTheDocument()
    // The four-check policy.
    expect(screen.getByText("dominance")).toBeInTheDocument()
    expect(screen.getByText("audit_chain")).toBeInTheDocument()
    expect(screen.getByText("tests_green")).toBeInTheDocument()
    expect(screen.getByText("data_leakage")).toBeInTheDocument()
    // A monitoring threshold, key humanized (psi_warn → "psi warn").
    expect(screen.getByText("psi warn")).toBeInTheDocument()
  })

  it("shows the lineage empty-state note when no registry is configured", async () => {
    mockApiFetch.mockImplementation(routeOk)
    render(<OpsDashboardWorkspace />)

    await waitFor(() => expect(screen.getByText("No model lineage yet")).toBeInTheDocument())
    expect(
      screen.getByText("No model registry is configured on this deployment yet."),
    ).toBeInTheDocument()
  })

  it("surfaces an admin-access-required state on 401/403", async () => {
    mockApiFetch.mockImplementation((path: string) => {
      if (path.includes("deployment-gate")) return Promise.reject(new MockApiError(403))
      if (path.includes("model-lineage")) return Promise.reject(new MockApiError(403))
      return Promise.reject(new Error("unexpected"))
    })
    render(<OpsDashboardWorkspace />)

    await waitFor(() => expect(screen.getByText("Admin access required")).toBeInTheDocument())
  })

  it("renders a lineage row with a drift-status chip when the registry is populated", async () => {
    const populated = {
      ...LINEAGE_EMPTY,
      registry_configured: true,
      rows: [
        {
          model_id: "lora_adapter:13C:1.0.0",
          role: "lora_adapter",
          nucleus: "13C",
          semantic_version: "1.0.0",
          artifact_sha256: "sha256:abc",
          training_snapshot_hash: "sha256:def",
          metric_vector: { top1_accuracy: 0.91 },
          promoted_utc: "2026-06-08T00:00:00Z",
          promotion_reason: "dominance gate passed",
          supersedes: null,
          drift_status: "breach",
        },
      ],
    }
    mockApiFetch.mockImplementation((path: string) => {
      if (path.includes("deployment-gate")) return Promise.resolve(GATE)
      if (path.includes("model-lineage")) return Promise.resolve(populated)
      return Promise.reject(new Error("unexpected"))
    })
    render(<OpsDashboardWorkspace />)

    await waitFor(() => expect(screen.getByText("lora_adapter:13C:1.0.0")).toBeInTheDocument())
    expect(screen.getByText("breach")).toBeInTheDocument()
  })
})
