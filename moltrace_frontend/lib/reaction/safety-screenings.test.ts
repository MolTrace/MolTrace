import { describe, expect, it } from "vitest"
import {
  GATE_BANNER,
  parseGate,
  parseScreening,
  RISK_BADGE_CLASS,
  REVIEW_BADGE_CLASS,
} from "@/lib/reaction/safety-screenings"

const RAW_SCREENING = {
  id: 1,
  reaction_project_id: 4,
  label: "Step 3 azide displacement",
  overall_risk: "critical",
  requires_expert_review: true,
  review_status: "pending",
  review_note: null,
  reviewed_by_user_id: null,
  reviewed_at: null,
  created_at: "2026-06-16T00:00:00Z",
  disclaimer: "Decision-support only; NOT a safety determination.",
  input_json: { reactant_smiles: ["CCN=[N+]=[N-]"] },
  result_json: {
    energetic_groups_found: ["azide"],
    species: [
      {
        role: "reactant",
        smiles: "CCN=[N+]=[N-]",
        parsed: true,
        overall_risk: "critical",
        flagged_groups: [
          { key: "azide", label: "Organic azide", severity: "critical", count: 1, mitigation: "Keep dilute and cold." },
        ],
      },
    ],
  },
}

describe("safety-screenings lib", () => {
  it("parses a screening incl. species + flagged groups from result_json", () => {
    const s = parseScreening(RAW_SCREENING)!
    expect(s.id).toBe(1)
    expect(s.overallRisk).toBe("critical")
    expect(s.reviewStatus).toBe("pending")
    expect(s.requiresExpertReview).toBe(true)
    expect(s.energeticGroupsFound).toEqual(["azide"])
    expect(s.species).toHaveLength(1)
    const fg = s.species[0].flaggedGroups[0]
    expect(fg).toMatchObject({ key: "azide", label: "Organic azide", severity: "critical", count: 1 })
    expect(fg.mitigation).toMatch(/dilute and cold/)
    expect(s.disclaimer).toMatch(/Decision-support only/)
  })

  it("clamps unknown enums and rejects rows without an id", () => {
    expect(parseScreening({})).toBeNull()
    const s = parseScreening({ id: 9, overall_risk: "spicy", review_status: "whatever" })!
    expect(s.overallRisk).toBe("unknown")
    expect(s.reviewStatus).toBe("not_required")
    expect(s.species).toEqual([])
  })

  it("parses the gate status with blocking ids, and defaults safely", () => {
    const g = parseGate({
      reaction_project_id: 4,
      status: "blocked",
      screenings_total: 2,
      blocking_screening_ids: [2],
      summary: "do not proceed",
    })
    expect(g.status).toBe("blocked")
    expect(g.blockingScreeningIds).toEqual([2])
    expect(g.screeningsTotal).toBe(2)

    const d = parseGate(null)
    expect(d.status).toBe("clear")
    expect(d.screeningsTotal).toBe(0)
    expect(d.blockingScreeningIds).toEqual([])
  })

  it("exposes theme-safe style maps for every risk / status / gate value", () => {
    for (const k of ["low", "medium", "high", "critical", "unknown"] as const) {
      expect(RISK_BADGE_CLASS[k]).toBeTruthy()
    }
    for (const k of ["not_required", "pending", "approved", "rejected"] as const) {
      expect(REVIEW_BADGE_CLASS[k]).toBeTruthy()
    }
    expect(GATE_BANNER.blocked.tone).toBe("blocked")
    expect(GATE_BANNER.clear.tone).toBe("clear")
    expect(GATE_BANNER.review_pending.tone).toBe("pending")
  })
})
