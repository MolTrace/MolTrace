import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ImpurityAssessmentWorkspace } from "@/components/regulatory-hub/impurity-assessment-workspace"

const mockApiFetch = vi.hoisted(() => vi.fn<(path: string, init?: unknown) => Promise<unknown>>())

// Partial mock: keep ApiError + sanitizePublicApiErrorMessage real (formatApiError
// depends on them); only stub the network call.
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  apiFetch: (path: string, init?: unknown) => mockApiFetch(path, init),
}))

const RESULT = {
  daily_dose_g: 1.0,
  route: "oral",
  substance_type: "drug_substance",
  duration_months: 120,
  thresholds: {
    substance_type: "drug_substance",
    reporting_percent: 0.05,
    identification_percent: 0.1,
    qualification_percent: 0.1,
    regulatory_basis: "ICH Q3A(R2)",
    table_reference: "Attachment 1",
  },
  residual_solvents: [],
  elemental_impurities: [],
  structural_impurities: [
    {
      smiles: "CN(C)N=O",
      name: "NDMA",
      m7_class: 2,
      m7_ttc_ug_per_day: null,
      coc_flag: true,
      expert_review_required: true,
      regulatory_action_required: "Compound-specific AI required",
      cpca: {
        category: 1,
        ai_limit_ng_per_day: 26.5,
        potency_score: 1,
        coc_flag: true,
        measured_ng_per_day: 50.0,
        within_ai_limit: false,
        regulatory_basis: "FDA Nitrosamine Guidance Rev 2",
      },
      regulatory_basis: "ICH M7(R2)",
    },
  ],
  nitrosamine_cumulative_risk: { total_risk_ratio: 1.887, passes: false, n_components: 1 },
  rule_set_versions: { q3ab: "sha256:aaa", m7: "sha256:bbb", cpca: "sha256:ccc" },
  disclaimer: "Decision-support only, NOT a regulatory determination.",
  human_review_required: true,
  warnings: [],
}

describe("ImpurityAssessmentWorkspace", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it("posts the assessment and renders the report with the disclaimer + thresholds", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValue(RESULT)

    render(<ImpurityAssessmentWorkspace />)
    await user.click(screen.getByRole("button", { name: "Assess" }))

    await waitFor(() => expect(screen.getByText("Assessment report")).toBeInTheDocument())
    // POST to the assess route.
    expect(mockApiFetch).toHaveBeenCalledWith(
      "/regulatory/impurities/assess",
      expect.objectContaining({ method: "POST" }),
    )
    // Persistent disclaimer banner.
    expect(screen.getByText("Decision-support only — requires qualified sign-off")).toBeInTheDocument()
    // Thresholds tab (default) shows the reporting %.
    expect(screen.getByText("Reporting")).toBeInTheDocument()
    // Nitrosamine tab is available because cumulative risk is present.
    expect(screen.getByRole("tab", { name: "Nitrosamine risk" })).toBeInTheDocument()
  })

  it("gates report export behind the qualified-sign-off acknowledgement", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValue(RESULT)

    render(<ImpurityAssessmentWorkspace />)
    await user.click(screen.getByRole("button", { name: "Assess" }))
    await waitFor(() => expect(screen.getByText("Requires qualified sign-off")).toBeInTheDocument())

    const exportBtn = screen.getByRole("button", { name: /Export report/ })
    expect(exportBtn).toBeDisabled()

    await user.click(screen.getByRole("checkbox", { name: /Acknowledge qualified review/ }))
    expect(exportBtn).toBeEnabled()
  })

  it("blocks a non-positive dose client-side without calling the API", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    render(<ImpurityAssessmentWorkspace />)

    const dose = screen.getByLabelText("Daily dose (g/day)")
    await user.clear(dose)
    await user.type(dose, "0")
    await user.click(screen.getByRole("button", { name: "Assess" }))

    expect(await screen.findByText("Daily dose must be greater than 0 g/day.")).toBeInTheDocument()
    expect(mockApiFetch).not.toHaveBeenCalled()
  })
})
