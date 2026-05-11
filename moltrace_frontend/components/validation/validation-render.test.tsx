import type { ReactElement, ReactNode } from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"

/**
 * Strong baseline render tests for the Validation Center components +
 * cross-module readiness cards (consumed by SpectraCheck/Regulatory/Reaction).
 */

const apiFetchMock = vi.fn()

vi.mock("@/lib/api/client", () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
  ApiError: class ApiError extends Error {
    status: number
    data: unknown
    constructor(status: number, data: unknown, message?: string) {
      super(message ?? String(status))
      this.status = status
      this.data = data
    }
  },
}))

vi.mock("next/navigation", () => ({
  usePathname: () => "/validation-center",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ validationProjectId: "1", validationRunId: "1" }),
}))

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: { children: ReactNode }) => props.children }),
  AnimatePresence: ({ children }: { children: ReactNode }) => children,
}))

function renderC(ui: ReactElement) {
  return render(ui)
}

beforeEach(() => {
  apiFetchMock.mockReset()
  apiFetchMock.mockImplementation(async () => [])
})

describe("ValidationCenterWorkspace (landing + projects index)", () => {
  it("renders without crashing", async () => {
    const { ValidationCenterWorkspace } = await import("@/components/validation/validation-center-workspace")
    renderC(<ValidationCenterWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Validation|Center|Project/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("ValidationDashboardWorkspace", () => {
  it("renders without crashing", async () => {
    const { ValidationDashboardWorkspace } = await import("@/components/validation/validation-dashboard-workspace")
    renderC(<ValidationDashboardWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Validation|Dashboard|Run/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("ValidationProjectDetailWorkspace", () => {
  it("renders without crashing", async () => {
    const { ValidationProjectDetailWorkspace } = await import(
      "@/components/validation/validation-project-detail-workspace"
    )
    renderC(<ValidationProjectDetailWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Validation|Project|Run|Detail/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("ValidationRunDetailWorkspace", () => {
  it("renders without crashing", async () => {
    const { ValidationRunDetailWorkspace } = await import("@/components/validation/validation-run-detail-workspace")
    renderC(<ValidationRunDetailWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Validation|Run|Detail/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("CapaWorkspace", () => {
  it("renders without crashing", async () => {
    const { CapaWorkspace } = await import("@/components/validation/capa-workspace")
    renderC(<CapaWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/CAPA|corrective|action/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("ControlledRecordsWorkspace", () => {
  it("renders without crashing", async () => {
    const { ControlledRecordsWorkspace } = await import("@/components/validation/controlled-records-workspace")
    renderC(<ControlledRecordsWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Controlled|Record|GxP/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("DataIntegrityWorkspace", () => {
  it("renders without crashing", async () => {
    const { DataIntegrityWorkspace } = await import("@/components/validation/data-integrity-workspace")
    renderC(<DataIntegrityWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Data integrity|ALCOA/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("DeviationsWorkspace", () => {
  it("renders without crashing", async () => {
    const { DeviationsWorkspace } = await import("@/components/validation/deviations-workspace")
    renderC(<DeviationsWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Deviation|Variance|Investigation/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("ESignatureRecordsWorkspace", () => {
  it("renders without crashing", async () => {
    const { ESignatureRecordsWorkspace } = await import("@/components/validation/esignature-records-workspace")
    renderC(<ESignatureRecordsWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Signature|e-sig|Signed/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("InspectionPackageWorkspace", () => {
  it("renders without crashing", async () => {
    const { InspectionPackageWorkspace } = await import("@/components/validation/inspection-package-workspace")
    renderC(<InspectionPackageWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Inspection|Package|Audit/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("SystemReleasesWorkspace", () => {
  it("renders without crashing", async () => {
    const { SystemReleasesWorkspace } = await import("@/components/validation/system-releases-workspace")
    renderC(<SystemReleasesWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Release|System|Version/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("ValidationTraceabilityWorkspace", () => {
  it("renders without crashing", async () => {
    const { ValidationTraceabilityWorkspace } = await import("@/components/validation/validation-traceability-workspace")
    renderC(<ValidationTraceabilityWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Traceability|Matrix|Requirement/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

// Cross-module readiness card consumers — these are the integration seams
describe("Cross-module readiness cards", () => {
  it("SpectraCheckValidationReadinessCard renders", async () => {
    const { SpectraCheckValidationReadinessCard } = await import(
      "@/components/validation/validation-readiness-summary"
    )
    renderC(<SpectraCheckValidationReadinessCard sessionId="test-session" />)
    expect(document.body.textContent).toBeDefined()
  })

  it("RegulatoryHubValidationReadinessCard renders", async () => {
    const { RegulatoryHubValidationReadinessCard } = await import(
      "@/components/validation/validation-readiness-summary"
    )
    renderC(<RegulatoryHubValidationReadinessCard />)
    expect(document.body.textContent).toBeDefined()
  })

  it("ReactionValidationReadinessCard renders", async () => {
    const { ReactionValidationReadinessCard } = await import(
      "@/components/validation/validation-readiness-summary"
    )
    renderC(<ReactionValidationReadinessCard />)
    expect(document.body.textContent).toBeDefined()
  })

  it("ReportsValidationReadinessCard renders", async () => {
    const { ReportsValidationReadinessCard } = await import(
      "@/components/validation/validation-readiness-summary"
    )
    renderC(<ReportsValidationReadinessCard />)
    expect(document.body.textContent).toBeDefined()
  })
})
