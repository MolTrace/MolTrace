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

  it("sends the chosen assessing authority, so an EU filing is not judged by the FDA limit", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValue(RESULT)

    render(<ImpurityAssessmentWorkspace />)

    // FDA is the default; EMA applies a Category-1 limit of 18 ng/day rather than 26.5.
    await user.click(screen.getByRole("radio", { name: "EMA" }))
    await user.click(screen.getByRole("button", { name: "Assess" }))

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalled())
    const [, init] = mockApiFetch.mock.calls[0] as [string, { body: Record<string, unknown> }]
    expect(init.body.authority).toBe("EMA")
  })

  it("names how each residual-solvent limit was derived", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    // Toluene at 50 g/day: the dose-scaled limit is 178 ppm, while the Option-1 table
    // constant is 890. Benzene keeps its fixed Class 1 limit at any dose. Showing both
    // numbers in one column without saying which rule produced them is the ambiguity
    // this label exists to close.
    mockApiFetch.mockResolvedValue({
      ...RESULT,
      daily_dose_g: 50.0,
      residual_solvents: [
        {
          identifier: "toluene",
          matched: true,
          solvent_name: "Toluene",
          class_number: 2,
          pde_mg_per_day: 8.9,
          concentration_limit_ppm: 890.0,
          measured_ppm: null,
          permitted_ppm: 178.0,
          limit_basis: "option_2_dose_scaled",
          passed: null,
          margin_ppm: null,
          regulatory_basis: "ICH Q3C(R8): Impurities: Guideline for Residual Solvents",
        },
        {
          identifier: "benzene",
          matched: true,
          solvent_name: "Benzene",
          class_number: 1,
          pde_mg_per_day: null,
          concentration_limit_ppm: 2.0,
          measured_ppm: null,
          permitted_ppm: 2.0,
          limit_basis: "class_1_fixed",
          passed: null,
          margin_ppm: null,
          regulatory_basis: "ICH Q3C(R8): Impurities: Guideline for Residual Solvents",
        },
      ],
    })

    render(<ImpurityAssessmentWorkspace />)
    await user.click(screen.getByRole("button", { name: "Assess" }))
    await waitFor(() => expect(screen.getByText("Assessment report")).toBeInTheDocument())
    await user.click(screen.getByRole("tab", { name: /Residual solvents/ }))

    expect(await screen.findByText("scaled to dose")).toBeInTheDocument()
    expect(screen.getByText("fixed Class 1 limit")).toBeInTheDocument()
    // The wire token itself must never reach the reader.
    expect(screen.queryByText("option_2_dose_scaled")).not.toBeInTheDocument()
  })

  it("shows which authority's limit was applied, next to the limit it changed", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    // The server echoes the authority it resolved. FDA and EMA differ only on the Category-1
    // acceptable intake -- 26.5 vs 18 ng/day -- so the number alone cannot tell a reviewer
    // which rule produced it.
    mockApiFetch.mockResolvedValue({
      ...RESULT,
      authority: "EMA",
      structural_impurities: [
        {
          ...RESULT.structural_impurities[0],
          cpca: { ...RESULT.structural_impurities[0].cpca, ai_limit_ng_per_day: 18.0 },
        },
      ],
    })

    render(<ImpurityAssessmentWorkspace />)
    await user.click(screen.getByRole("button", { name: "Assess" }))
    await waitFor(() => expect(screen.getByText("Assessment report")).toBeInTheDocument())

    // Specific to the report header -- "EMA" on its own also matches the selector button above.
    expect(screen.getByText(/EMA limits applied/i)).toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: /Structural/ }))
    // And beside the one number the choice actually changes.
    expect(await screen.findByText(/18 ng\/day \(EMA\)/)).toBeInTheDocument()
  })

  it("shows the evidence behind a CPCA category rather than the category alone", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValue({
      ...RESULT,
      structural_impurities: [
        {
          ...RESULT.structural_impurities[0],
          class_definition: "Class 2: known mutagen with unknown carcinogenic potential.",
          structural_alerts: ["N-nitrosamine"],
          reasoning: "N-nitroso centre flanked by unbranched alkyl chains.",
          cpca: {
            ...RESULT.structural_impurities[0].cpca,
            category_description: "Category 1: most potent, AI 26.5 ng/day.",
            alpha_h_score: 1,
            activating_features: ["two alpha hydrogens"],
            deactivating_features: ["tertiary carbon"],
          },
        },
      ],
    })

    render(<ImpurityAssessmentWorkspace />)
    await user.click(screen.getByRole("button", { name: "Assess" }))
    await waitFor(() => expect(screen.getByText("Assessment report")).toBeInTheDocument())
    await user.click(screen.getByRole("tab", { name: /Structural/ }))

    // The reasoning a regulator would ask for, not just the verdict.
    expect(await screen.findByText(/two alpha hydrogens/)).toBeInTheDocument()
    expect(screen.getByText(/tertiary carbon/)).toBeInTheDocument()
    expect(screen.getByText(/N-nitrosamine/)).toBeInTheDocument()
    expect(screen.getByText(/N-nitroso centre flanked by unbranched alkyl chains/)).toBeInTheDocument()
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
