import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import {
  NitrosamineCumulativeRiskCard,
  type NitrosamineCumulativeRisk,
} from "@/components/regulatory-hub/nitrosamine-cumulative-risk-card"

function base(overrides: Partial<NitrosamineCumulativeRisk>): NitrosamineCumulativeRisk {
  return {
    dossier_id: 12,
    total_risk_ratio: 0,
    passes: true,
    n_components: 0,
    components: [],
    excluded: [],
    n_excluded: 0,
    regulatory_basis: "FDA Nitrosamine Guidance Rev 2",
    disclaimer: "Decision-support only, not a regulatory determination.",
    notes: [],
    human_review_required: true,
    ...overrides,
  }
}

describe("NitrosamineCumulativeRiskCard", () => {
  it("renders a green within-limit verdict when included components pass", () => {
    render(
      <NitrosamineCumulativeRiskCard
        data={base({
          total_risk_ratio: 0.7547,
          passes: true,
          n_components: 2,
          components: [
            {
              assessment_id: 34,
              structure_text: "CN(C)N=O",
              category: 1,
              ai_limit_ng_per_day: 26.5,
              measured_ng_per_day: 10,
              risk_ratio: 0.3774,
            },
          ],
        })}
      />,
    )
    expect(screen.getByText("within cumulative limit")).toBeInTheDocument()
    expect(screen.getByText("0.755")).toBeInTheDocument() // num(0.7547, 3)
    expect(screen.getByText("CN(C)N=O")).toBeInTheDocument()
    expect(screen.getByText("2 included · 0 excluded")).toBeInTheDocument()
  })

  it("renders a red exceeds-limit verdict when the ratio is ≥ 1", () => {
    render(
      <NitrosamineCumulativeRiskCard
        data={base({ total_risk_ratio: 1.51, passes: false, n_components: 1, components: [
          { assessment_id: 1, structure_text: "CN(C)N=O", category: 1, ai_limit_ng_per_day: 26.5, measured_ng_per_day: 40, risk_ratio: 1.51 },
        ] })}
      />,
    )
    expect(screen.getByText("exceeds cumulative limit")).toBeInTheDocument()
    // 1.51 appears in both the headline and the single component's risk_ratio cell.
    expect(screen.getAllByText("1.51").length).toBeGreaterThan(0)
  })

  it("renders a MUTED not-yet-assessed state for an empty/zero-component dossier (not a green pass)", () => {
    render(<NitrosamineCumulativeRiskCard data={base({ n_components: 0, passes: true, total_risk_ratio: 0 })} />)
    expect(screen.getByText("not yet assessed")).toBeInTheDocument()
    // Must NOT present the empty case as a cleared gate.
    expect(screen.queryByText("within cumulative limit")).not.toBeInTheDocument()
  })

  it("surfaces excluded watches with their reasons (never silently dropped)", () => {
    render(
      <NitrosamineCumulativeRiskCard
        data={base({
          n_excluded: 2,
          excluded: [
            { assessment_id: 40, reason: "no measured ng/day recorded on this nitrosamine watch." },
            { assessment_id: 41, reason: "structure is not a parseable nitrosamine; no CPCA AI limit to score against." },
          ],
        })}
      />,
    )
    expect(screen.getByRole("button", { name: /Excluded · 2/ })).toBeInTheDocument()
    // collapsed by default; reasons appear after expand
    expect(screen.queryByText(/no measured ng\/day recorded/)).not.toBeInTheDocument()
  })

  it("renders an unavailable note when data is null", () => {
    render(<NitrosamineCumulativeRiskCard data={null} />)
    expect(screen.getByText("Cumulative-risk rollup unavailable.")).toBeInTheDocument()
  })

  it("always surfaces the decision-support disclaimer + qualified-review requirement", () => {
    render(<NitrosamineCumulativeRiskCard data={base({ human_review_required: true })} />)
    expect(screen.getByText(/Decision-support only/)).toBeInTheDocument()
    expect(screen.getByText(/Requires qualified review/)).toBeInTheDocument()
  })
})
