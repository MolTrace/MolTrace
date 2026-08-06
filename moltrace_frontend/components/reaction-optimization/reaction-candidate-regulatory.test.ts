// Repho — proposal-time regulatory verdict, invariant tests.
//
// These pin the three rules the handoff (§4) calls out, plus the two engine
// semantics that make the naive reading wrong:
//
//   * `feasible` means "no HARD violation", NOT "checked and passed".
//   * `applied_constraint_ids` counts limits the engine went on to record as
//     unmeasured, so it is not evidence that anything was checked.
//
// The behaviour under test is the *state machine*, not the markup, so a later
// redesign of the badge does not silently drop the guarantee.

import React from "react"
import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { RunRegulatoryStrip } from "@/components/reaction-optimization/reaction-candidate-regulatory"
import {
  candidateRegulatoryById,
  candidateRegulatoryForRow,
  humanizeObjectiveField,
  parseCandidateRegulatory,
  proposalRegulatoryState,
  readRunRegulatorySummary,
  violationSentence,
  type CandidateRegulatory,
} from "@/lib/reaction/regulatory-proposal"
import { itemStatus } from "@/lib/reaction/regulatory-compliance"

const HARD_VIOLATION = {
  constraint_id: 7,
  constraint_type: "impurity_limit",
  objective_field: "impurity_percent",
  comparator: "max",
  predicted_value: 0.42,
  limit_value: 0.15,
  limit_unit: "percent",
  basis: "ICH Q3B(R2) identification threshold",
  severity: "critical",
  is_hard: true,
  source_action_item_ids: [31, 32],
}

const SOFT_VIOLATION = {
  ...HARD_VIOLATION,
  constraint_id: 9,
  severity: "warning",
  is_hard: false,
  source_action_item_ids: [],
}

function reg(over: Partial<Record<string, unknown>> = {}): CandidateRegulatory {
  const parsed = parseCandidateRegulatory({
    regulatory: {
      feasible: true,
      hard_block: false,
      penalty: 0,
      violations: [],
      unmeasured: [],
      applied_constraint_ids: [],
      ...over,
    },
  })
  if (parsed == null) throw new Error("fixture failed to parse")
  return parsed
}

describe("proposalRegulatoryState", () => {
  it("never reports a genuine pass when a limit could not be checked", () => {
    // The trap: feasible:true with a non-empty unmeasured. `feasible` only means
    // no hard violation — it is not a clearance.
    const v = reg({ feasible: true, unmeasured: ["impurity_percent"] })
    expect(v.feasible).toBe(true)
    expect(proposalRegulatoryState(v)).toBe("not_checked")
    expect(proposalRegulatoryState(v)).not.toBe("within_limits")
  })

  it("does not treat applied_constraint_ids as evidence that anything was checked", () => {
    // The engine appends the id BEFORE testing whether the field is predictable,
    // so a fully unmeasured verdict still reports applied ids.
    const v = reg({
      feasible: true,
      unmeasured: ["impurity_percent", "residual_solvent_ppm"],
      applied_constraint_ids: [7, 9],
    })
    expect(v.appliedConstraintIds).toHaveLength(2)
    expect(proposalRegulatoryState(v)).toBe("not_checked")
  })

  it("reports within_limits only when every limit had a value and none was breached", () => {
    expect(proposalRegulatoryState(reg({ applied_constraint_ids: [7] }))).toBe("within_limits")
  })

  it("ranks a hard block above a soft breach, and a soft breach above unchecked", () => {
    expect(
      proposalRegulatoryState(
        reg({ hard_block: true, feasible: false, violations: [HARD_VIOLATION] }),
      ),
    ).toBe("blocked")
    expect(proposalRegulatoryState(reg({ violations: [SOFT_VIOLATION] }))).toBe("flagged")
    // A breach plus unchecked fields still reads as a breach, not as unchecked.
    expect(
      proposalRegulatoryState(reg({ violations: [SOFT_VIOLATION], unmeasured: ["yield_percent"] })),
    ).toBe("flagged")
  })
})

describe("parseCandidateRegulatory", () => {
  it("returns null when the project has no active enforceable constraints", () => {
    // Key absent entirely — distinct from "checked and clean".
    expect(parseCandidateRegulatory({ human_review_required: true })).toBeNull()
    expect(parseCandidateRegulatory(null)).toBeNull()
  })

  it("keeps the provenance needed to walk back to the source action item", () => {
    const v = reg({ hard_block: true, feasible: false, violations: [HARD_VIOLATION] })
    expect(v.violations[0].sourceActionItemIds).toEqual([31, 32])
    expect(v.violations[0].basis).toBe("ICH Q3B(R2) identification threshold")
  })
})

describe("readRunRegulatorySummary", () => {
  it("treats a missing feasible_candidate_count as unknown, never as zero-blocked", () => {
    const s = readRunRegulatorySummary({ status: "succeeded", diagnostics_json: {} })
    expect(s.feasibilityKnown).toBe(false)
    expect(s.feasibleCount).toBeNull()
    expect(s.readyToSchedule).toBe(false)
  })

  it("does not read succeeded as ready to schedule when nothing survived the filters", () => {
    const s = readRunRegulatorySummary({
      status: "succeeded",
      diagnostics_json: { feasible_candidate_count: 0, regulatory_blocked_candidate_count: 6 },
    })
    expect(s.readyToSchedule).toBe(false)
    expect(s.blockedCount).toBe(6)
  })

  it("reports ready to schedule only when the run succeeded with surviving candidates", () => {
    expect(
      readRunRegulatorySummary({
        status: "succeeded",
        diagnostics_json: { feasible_candidate_count: 4 },
      }).readyToSchedule,
    ).toBe(true)
    expect(
      readRunRegulatorySummary({
        status: "requires_review",
        diagnostics_json: { feasible_candidate_count: 4 },
      }).readyToSchedule,
    ).toBe(false)
  })

  it("separates the unchecked-limits caveat so it can be rendered above the figures", () => {
    const warning =
      "2 active regulatory limit field(s) (impurity_percent, residual_solvent_ppm) could not be " +
      "checked against these proposals and were not applied to ranking: the surrogate predicts a " +
      "scalarized objective, not per-field outcomes."
    const s = readRunRegulatorySummary({
      status: "requires_review",
      warnings: ["Fewer than 5 completed experiments are available.", warning],
    })
    expect(s.uncheckedWarning).toBe(warning)
    expect(s.otherWarnings).toEqual(["Fewer than 5 completed experiments are available."])
  })

  it("falls back to diagnostics when the run carries no diagnostics_json", () => {
    const s = readRunRegulatorySummary({
      status: "succeeded",
      diagnostics: { feasible_candidate_count: 2 },
    })
    expect(s.feasibleCount).toBe(2)
  })
})

describe("candidate ↔ recommendation-row join", () => {
  // The verdict lives on the acquisition candidate; the batch table renders
  // recommendation rows, a different id space.
  const run = {
    recommendations_json: [
      {
        id: 501,
        acquisition_candidate_id: 501,
        recommendation_id: 900,
        metadata_json: {
          recommendation_id: 900,
          regulatory: { feasible: true, hard_block: false, unmeasured: ["impurity_percent"] },
        },
      },
    ],
  }

  it("finds the verdict from the recommendation row id", () => {
    const index = candidateRegulatoryById(run)
    const hit = candidateRegulatoryForRow({ id: 900 }, index)
    expect(hit).not.toBeNull()
    expect(proposalRegulatoryState(hit!)).toBe("not_checked")
  })

  it("finds the verdict from the acquisition candidate id", () => {
    const index = candidateRegulatoryById(run)
    expect(candidateRegulatoryForRow({ id: 501 }, index)).not.toBeNull()
  })

  it("returns null for a row the run does not cover", () => {
    expect(candidateRegulatoryForRow({ id: 4242 }, candidateRegulatoryById(run))).toBeNull()
  })

  it("skips candidates that carry no regulatory block", () => {
    const index = candidateRegulatoryById({
      recommendations_json: [{ id: 1, metadata_json: { human_review_required: true } }],
    })
    expect(index.size).toBe(0)
  })
})

describe("user-facing wording", () => {
  it("never shows a raw wire key", () => {
    expect(humanizeObjectiveField("impurity_percent")).toBe("Impurity")
    expect(humanizeObjectiveField("nitrosamine_ng_per_day")).toBe("Nitrosamine exposure")
    // Unknown field: still humanized, never printed as snake_case.
    expect(humanizeObjectiveField("custom_side_product_percent")).toBe("Custom side product")
    expect(humanizeObjectiveField(null)).toBe("Value")
  })

  it("states the breach, the limit and the basis in one sentence", () => {
    const v = reg({ violations: [HARD_VIOLATION] }).violations[0]
    const sentence = violationSentence(v)
    expect(sentence).toBe(
      "Impurity 0.42% exceeds the 0.15% limit (ICH Q3B(R2) identification threshold).",
    )
    expect(sentence).not.toContain("impurity_percent")
  })

  it("uses the right relation for a minimum limit", () => {
    const v = reg({
      violations: [
        { ...HARD_VIOLATION, comparator: "min", objective_field: "nmr_purity_percent" },
      ],
    }).violations[0]
    expect(violationSentence(v)).toContain("qNMR purity 0.42% falls below the 0.15% limit")
  })
})

describe("RunRegulatoryStrip attribution", () => {
  it("stays hidden for a project with no enforceable limits", () => {
    // feasible_candidate_count is written on every run, so its presence alone must
    // not conjure a regulatory panel onto a project that has no limits at all.
    const summary = readRunRegulatorySummary({
      status: "succeeded",
      diagnostics_json: { feasible_candidate_count: 8, regulatory_blocked_candidate_count: 0 },
    })
    const { container } = render(
      React.createElement(RunRegulatoryStrip, { summary, hasActiveLimits: false }),
    )
    expect(container).toBeEmptyDOMElement()
  })

  it("renders once limits are in play, caveat before the figures", () => {
    const warning = "1 active regulatory limit field(s) ... were not applied to ranking: ..."
    const summary = readRunRegulatorySummary({
      status: "requires_review",
      warnings: [warning],
      diagnostics_json: { feasible_candidate_count: 3, regulatory_blocked_candidate_count: 0 },
    })
    const { container } = render(
      React.createElement(RunRegulatoryStrip, { summary, hasActiveLimits: true }),
    )
    const text = container.textContent ?? ""
    expect(text).toContain(warning)
    // The caveat must precede the number it qualifies.
    expect(text.indexOf(warning)).toBeLessThan(text.indexOf("Candidates that passed every filter"))
  })

  it("does not blame a regulatory limit for a zero that no limit caused", () => {
    const summary = readRunRegulatorySummary({
      status: "requires_review",
      diagnostics_json: { feasible_candidate_count: 0, regulatory_blocked_candidate_count: 0 },
    })
    const { container } = render(
      React.createElement(RunRegulatoryStrip, { summary, hasActiveLimits: true }),
    )
    const text = container.textContent ?? ""
    expect(text).toContain("No candidate survived this run's filters.")
    expect(text).not.toContain("hard regulatory limit filtered")
  })

  it("names the hard limit when one did the blocking", () => {
    const summary = readRunRegulatorySummary({
      status: "requires_review",
      diagnostics_json: { feasible_candidate_count: 0, regulatory_blocked_candidate_count: 5 },
    })
    const { container } = render(
      React.createElement(RunRegulatoryStrip, { summary, hasActiveLimits: true }),
    )
    expect(container.textContent ?? "").toContain("hard regulatory limit filtered")
  })
})

describe("measured-outcome side stays symmetric", () => {
  // The same false-clear used to exist on the R4 compliance panel: no violations
  // plus an unmeasured field rendered a green "Within limits".
  it("does not clear an experiment whose limit had nothing to compare against", () => {
    expect(
      itemStatus({
        experimentId: 1,
        experimentCode: "EXP-1",
        status: "completed",
        feasible: true,
        hardBlock: false,
        penalty: 0,
        violations: [],
        unmeasured: ["impurity_percent"],
      }),
    ).toBe("not_checked")
  })

  it("still clears an experiment where every limit was measured and met", () => {
    expect(
      itemStatus({
        experimentId: 1,
        experimentCode: "EXP-1",
        status: "completed",
        feasible: true,
        hardBlock: false,
        penalty: 0,
        violations: [],
        unmeasured: [],
      }),
    ).toBe("within_limits")
  })
})
