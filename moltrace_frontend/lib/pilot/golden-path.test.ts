// Golden Path — the honesty invariants.
//
// Every test here guards a way the demo could look fine on screen while telling a
// pharma buyer something untrue. They are not coverage for coverage's sake.

import { describe, expect, it } from "vitest"
import {
  evaluateContracts,
  formatElapsed,
  hasPath,
  initialOutcomes,
  inputsFromScenario,
  measuredArcElapsedMs,
  missingInputs,
  pilotStepSummaryIsCanned,
  readRecordedArc,
  splitRoi,
  type ExpectedOutputContract,
  type GoldenPathStepOutcome,
  type GoldenPilotScenario,
  type RoiSnapshot,
} from "@/lib/pilot/golden-path"

function outcome(patch: Partial<GoldenPathStepOutcome> & Pick<GoldenPathStepOutcome, "key">): GoldenPathStepOutcome {
  const base = initialOutcomes().find((o) => o.key === patch.key)
  if (!base) throw new Error(`unknown step ${patch.key}`)
  return { ...base, ...patch }
}

function contract(patch: Partial<ExpectedOutputContract> = {}): ExpectedOutputContract {
  return {
    id: 1,
    scenario_id: 1,
    step_key: "spectracheck_evidence_item",
    target_module: "spectracheck",
    expected_output_type: "evidence_item",
    created_at: "2026-08-06T00:00:00Z",
    ...patch,
  }
}

function snapshot(patch: Partial<RoiSnapshot> = {}): RoiSnapshot {
  return {
    id: 1,
    scope: "global",
    period_start: "2026-07-01T00:00:00Z",
    period_end: "2026-08-01T00:00:00Z",
    tasks_automated: 12,
    total_minutes_saved: 240,
    total_hours_saved: 4,
    // Added when the backend put the estimate qualifier on the wire.
    time_saved_is_estimated: true,
    time_saved_basis: "per_task_type_constants",
    reports_generated: 3,
    workflows_completed: 2,
    analyses_completed: 7,
    review_tasks_completed: 5,
    failed_jobs: 1,
    qc_warnings: 2,
    created_at: "2026-08-01T00:00:00Z",
    data_mode: "live",
    ...patch,
  }
}

describe("ROI: measured counts vs estimated hours", () => {
  it("keeps the hours figure separate from the measured counts", () => {
    const split = splitRoi(snapshot(), 1234)
    expect(split.estimatedHoursSaved).toBe(4)
    expect(split.measuredArcElapsedMs).toBe(1234)
    // Every count exposed as measured must be a real event count — the hours
    // figure must never appear among them.
    expect(split.measuredCounts.map((c) => c.key)).toEqual([
      "tasks_automated",
      "analyses_completed",
      "reports_generated",
      "workflows_completed",
      "review_tasks_completed",
      "qc_warnings",
      "failed_jobs",
    ])
    expect(split.measuredCounts.some((c) => c.key.includes("hours"))).toBe(false)
    expect(split.measuredCounts.some((c) => c.key.includes("minutes"))).toBe(false)
  })

  it("renders a missing snapshot as no-data, never as zero", () => {
    const split = splitRoi(null, null)
    // The bug this guards: `?? 0` on a missing snapshot reads as "we measured
    // zero hours saved" rather than "we have no data".
    expect(split.estimatedHoursSaved).toBeNull()
    expect(split.estimatedHoursSaved).not.toBe(0)
    expect(split.measuredCounts).toEqual([])
    expect(split.dataMode).toBeNull()
  })

  it("keeps the arc's own clock even when no snapshot exists", () => {
    // The arc's elapsed time is measured by this page and does not depend on
    // the ROI snapshot, so a missing snapshot must not erase it.
    expect(splitRoi(null, 900).measuredArcElapsedMs).toBe(900)
  })

  it("carries snapshot warnings through so they can render above the figures", () => {
    expect(splitRoi(snapshot({ warnings: ["Partially synced."] }), null).warnings).toEqual([
      "Partially synced.",
    ])
  })
})

describe("measured arc elapsed time", () => {
  it("is null when nothing ran, rather than zero", () => {
    expect(measuredArcElapsedMs(initialOutcomes())).toBeNull()
  })

  it("sums only the steps that actually ran", () => {
    const outcomes = [
      outcome({ key: "raw_fid_process", status: "succeeded", elapsedMs: 400 }),
      outcome({ key: "candidate_evidence", status: "succeeded", elapsedMs: 600 }),
      outcome({ key: "impurity_assess" }),
    ]
    expect(measuredArcElapsedMs(outcomes)).toBe(1000)
  })

  it("formats sub-second, second and minute durations distinctly", () => {
    expect(formatElapsed(null)).toBe("—")
    expect(formatElapsed(420)).toBe("420 ms")
    expect(formatElapsed(1500)).toBe("1.5 s")
    expect(formatElapsed(65_000)).toBe("1 min 5 s")
  })
})

describe("contract evaluation runs against the real responses", () => {
  it("passes when the real payload carries every required field", () => {
    const checks = evaluateContracts(
      [contract({ required_fields_json: ["best_candidate.total_score"] })],
      [
        outcome({
          key: "candidate_evidence",
          status: "succeeded",
          payload: { best_candidate: { total_score: 8.1 } },
        }),
      ],
    )
    expect(checks[0].status).toBe("pass")
    expect(checks[0].matchedStep).toBe("candidate_evidence")
  })

  it("fails when a required field is missing from the real payload", () => {
    const checks = evaluateContracts(
      [contract({ required_fields_json: ["best_candidate.total_score"] })],
      [outcome({ key: "candidate_evidence", status: "succeeded", payload: { best_candidate: {} } })],
    )
    expect(checks[0].status).toBe("fail")
    expect(checks[0].missingRequiredFields).toEqual(["best_candidate.total_score"])
  })

  it("fails when a forbidden field is present", () => {
    const checks = evaluateContracts(
      [contract({ forbidden_fields_json: ["fabricated_citation"] })],
      [
        outcome({
          key: "candidate_evidence",
          status: "succeeded",
          payload: { fabricated_citation: "x" },
        }),
      ],
    )
    expect(checks[0].status).toBe("fail")
    expect(checks[0].forbiddenFieldsPresent).toEqual(["fabricated_citation"])
  })

  it("would fail on the recorder's canned summary, proving it checks real output", () => {
    // The recorder writes `{expected_output: "safe summary", …}` for every step.
    // A contract written against a real response must NOT pass against that —
    // otherwise the panel is validating theatre.
    const canned = {
      step_index: 1,
      module: "spectracheck",
      expected_output: "safe summary",
      review_status: "requires review",
      resource_links: [],
    }
    const checks = evaluateContracts(
      [contract({ required_fields_json: ["best_candidate.total_score"] })],
      [outcome({ key: "candidate_evidence", status: "succeeded", payload: canned })],
    )
    expect(checks[0].status).toBe("fail")
  })

  it("never reports a clean pass for a step the engine flagged for review", () => {
    const checks = evaluateContracts(
      [contract({ step_key: "reaction_constraint", target_module: "reaction_optimization" })],
      [outcome({ key: "bo_run", status: "requires_review", payload: { status: "requires_review" } })],
    )
    expect(checks[0].status).toBe("warning")
    expect(checks[0].status).not.toBe("pass")
  })

  it("reports a step that never ran as not-assessed, not as a pass", () => {
    const checks = evaluateContracts([contract({ step_key: "nothing_matches_this" })], initialOutcomes())
    // Falls back to the module match, which is still pending.
    expect(checks[0].status).toBe("not_assessed")
  })

  it("fails when the step finished in a state the contract does not accept", () => {
    const checks = evaluateContracts(
      [contract({ expected_statuses_json: ["succeeded"] })],
      [outcome({ key: "candidate_evidence", status: "requires_review", payload: {} })],
    )
    expect(checks[0].status).toBe("fail")
    expect(checks[0].statusMismatch).toBe(true)
  })
})

describe("hasPath mirrors the backend's _has_path", () => {
  it("walks dotted paths through plain objects only", () => {
    expect(hasPath({ a: { b: 1 } }, "a.b")).toBe(true)
    expect(hasPath({ a: { b: 1 } }, "a.c")).toBe(false)
    expect(hasPath({ a: [{ b: 1 }] }, "a.b")).toBe(false)
    expect(hasPath(null, "a")).toBe(false)
  })

  it("counts an explicit null value as present", () => {
    // The backend tests key membership, not truthiness — a contracted field that
    // is present and null has been supplied.
    expect(hasPath({ a: null }, "a")).toBe(true)
  })
})

describe("the recorder's canned steps are identifiable and never counted", () => {
  it("recognises the recorder's literal", () => {
    expect(pilotStepSummaryIsCanned({ output_summary_json: { expected_output: "safe summary" } })).toBe(true)
    expect(pilotStepSummaryIsCanned({ output_summary_json: { candidate_count: 4 } })).toBe(false)
  })

  it("reads the executed arc from metadata, not from the canned steps", () => {
    const arc = readRecordedArc({
      metadata_json: {
        golden_path_executed_client_side: true,
        measured_total_elapsed_ms: 1500,
        steps: [
          { step: "raw_fid_process", status: "succeeded", elapsed_ms: 500 },
          { step: "bo_run", status: "requires_review", elapsed_ms: 1000 },
        ],
      },
    })
    expect(arc?.totalElapsedMs).toBe(1500)
    expect(arc?.steps.map((s) => s.status)).toEqual(["succeeded", "requires_review"])
  })

  it("returns null for a run with no executed record, rather than implying success", () => {
    // A run created by the recorder alone has five steps, all written
    // `succeeded`. Reading those would report a green arc that never ran.
    expect(readRecordedArc({ metadata_json: {} })).toBeNull()
    expect(readRecordedArc(null)).toBeNull()
    expect(readRecordedArc({ metadata_json: { steps: [{ step: "raw_fid_process", status: "succeeded" }] } })).toBeNull()
  })
})

describe("frozen inputs come from the scenario", () => {
  const scenario = (required: Record<string, unknown>): GoldenPilotScenario => ({
    id: 3,
    scenario_key: "golden",
    title: "Golden arc",
    description: "",
    scenario_type: "full_product_workflow",
    status: "approved",
    created_at: "2026-08-06T00:00:00Z",
    updated_at: "2026-08-06T00:00:00Z",
    required_inputs_json: required,
  })

  it("reads the pinned inputs so the arc replays identically", () => {
    const inputs = inputsFromScenario(
      scenario({
        archive_id: "brk-001",
        smiles: "CCO",
        solvent: "CDCl3",
        candidates_text: "CCO\nCCC",
        daily_dose_g: 0.5,
        route: "parenteral",
        reaction_project_id: 9,
      }),
    )
    expect(inputs.archiveId).toBe("brk-001")
    expect(inputs.route).toBe("parenteral")
    expect(inputs.dailyDoseG).toBe(0.5)
    expect(inputs.reactionProjectId).toBe(9)
    expect(missingInputs(inputs)).toEqual([])
  })

  it("names what the scenario failed to pin instead of guessing it", () => {
    const inputs = inputsFromScenario(scenario({}))
    expect(missingInputs(inputs)).toEqual([
      "Raw FID archive",
      "Structure (SMILES)",
      "Candidate structures",
      "Reaction project",
    ])
  })

  it("rejects an out-of-vocabulary route rather than passing it through", () => {
    // A bad enum would 422 mid-arc; falling back to the default keeps the
    // failure at the input stage where it can be named.
    expect(inputsFromScenario(scenario({ route: "intravenous" })).route).toBe("oral")
  })
})
