import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { ReactionRegulatoryCompliancePanel } from "@/components/reaction-optimization/reaction-regulatory-compliance-panel"
import {
  parseComplianceReport,
  itemStatus,
  type ComplianceReport,
} from "@/lib/reaction/regulatory-compliance"

const api = vi.hoisted(() => ({ getRegulatoryCompliance: vi.fn() }))

// Partial mock — keep the real parsers + style maps; stub the network call.
vi.mock("@/lib/reaction/regulatory-compliance", async (orig) => ({
  ...(await orig<typeof import("@/lib/reaction/regulatory-compliance")>()),
  getRegulatoryCompliance: (...a: unknown[]) => api.getRegulatoryCompliance(...a),
}))

const REPORT: ComplianceReport = {
  reactionProjectId: 12,
  enforcedConstraintCount: 1,
  activeConstraintIds: [5],
  constraintBases: ["ICH Q3B(R2) identification threshold"],
  experimentsEvaluated: 2,
  nonCompliantExperimentCount: 1,
  items: [
    {
      experimentId: 41,
      experimentCode: "E-bad",
      status: "completed",
      feasible: false,
      hardBlock: true,
      penalty: 1,
      violations: [
        {
          constraintId: 5,
          constraintType: "impurity_limit",
          objectiveField: "impurity_percent",
          comparator: "max",
          predictedValue: 0.4,
          limitValue: 0.15,
          limitUnit: "percent",
          basis: "ICH Q3B(R2) identification threshold",
          severity: "high",
          isHard: true,
          sourceActionItemIds: [3],
        },
      ],
      unmeasured: [],
    },
    {
      experimentId: 40,
      experimentCode: "E-ok",
      status: "completed",
      feasible: true,
      hardBlock: false,
      penalty: 0,
      violations: [],
      unmeasured: [],
    },
  ],
  notes: [],
}

describe("regulatory-compliance lib", () => {
  it("parses a raw report defensively and derives row status", () => {
    const parsed = parseComplianceReport({
      reaction_project_id: 12,
      experiments_evaluated: 1,
      non_compliant_experiment_count: 1,
      items: [
        { experiment_id: 1, experiment_code: "E1", status: "completed", feasible: false, hard_block: true, penalty: 1, violations: [{ limit_value: 0.15, predicted_value: 0.4, is_hard: true }] },
      ],
      notes: ["x"],
    })
    expect(parsed.experimentsEvaluated).toBe(1)
    expect(parsed.items[0]!.violations[0]!.limitValue).toBe(0.15)
    expect(itemStatus(parsed.items[0]!)).toBe("non_compliant")
  })

  it("classifies soft-violation as flagged, clean as within_limits", () => {
    expect(itemStatus({ hardBlock: false, violations: [{} as never], feasible: true } as never)).toBe("flagged")
    expect(itemStatus({ hardBlock: false, violations: [], feasible: true } as never)).toBe("within_limits")
  })
})

describe("ReactionRegulatoryCompliancePanel", () => {
  it("renders the summary, a non-compliant row, and expands its violation", async () => {
    api.getRegulatoryCompliance.mockResolvedValue(REPORT)
    const user = userEvent.setup()
    render(<ReactionRegulatoryCompliancePanel reactionProjectId={12} />)

    // Summary + honest scoping copy.
    expect(await screen.findByText("Non-compliant")).toBeInTheDocument()
    expect(screen.getByText(/not applied at\s+recommendation time/i)).toBeInTheDocument()
    expect(screen.getByText("ICH Q3B(R2) identification threshold")).toBeInTheDocument()
    expect(screen.getByText("E-bad")).toBeInTheDocument()
    expect(screen.getByText("E-ok")).toBeInTheDocument()

    // Expand the violation detail.
    await user.click(screen.getByRole("button", { name: /1 violation/i }))
    await waitFor(() => expect(screen.getByText(/impurity_percent max 0.15 percent/i)).toBeInTheDocument())
    expect(screen.getByText(/regulatory action item 3/i)).toBeInTheDocument()
  })

  it("shows an empty state when there is nothing to evaluate", async () => {
    api.getRegulatoryCompliance.mockResolvedValue({
      ...REPORT,
      experimentsEvaluated: 0,
      nonCompliantExperimentCount: 0,
      items: [],
    })
    render(<ReactionRegulatoryCompliancePanel reactionProjectId={12} />)
    expect(await screen.findByText("Nothing to evaluate yet")).toBeInTheDocument()
  })
})
