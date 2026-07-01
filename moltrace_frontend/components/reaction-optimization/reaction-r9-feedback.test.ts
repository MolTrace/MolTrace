import { describe, expect, it, vi } from "vitest"

// R9 helpers live in the heavy reaction-project-detail module; mock its runtime/browser deps so
// importing the pure helpers doesn't boot the page. Use the REAL @/lib/api/client (no network here).
vi.mock("next/navigation", () => ({
  usePathname: () => "/reactions",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ reactionId: "10" }),
}))
vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (p: { children?: unknown }) => p.children }),
  AnimatePresence: (p: { children?: unknown }) => p.children,
}))

import { ApiError } from "@/lib/api/client"
import {
  canonicalConditionsKey,
  parseReactionDirectionsText,
  parseReactionMetricsText,
  parseReactionRecall,
  reactionAbEvaluateBody,
  reactionAbVerdictView,
  reactionFeedbackErrorMessage,
  reactionFeedbackReasonRequired,
  reactionFeedbackRecordView,
  reactionPreferenceRankByConditions,
  reactionPreferenceRankByRef,
  reactionPreferenceRankingView,
  reactionProposalModelVersion,
} from "@/components/reaction-optimization/reaction-project-detail"

describe("R9 feedback semantics", () => {
  it("requires a reason ONLY on reject", () => {
    expect(reactionFeedbackReasonRequired("reject")).toBe(true)
    expect(reactionFeedbackReasonRequired("accept")).toBe(false)
    expect(reactionFeedbackReasonRequired("edit")).toBe(false)
  })

  it("derives a best-effort model_version: rec field → metadata → hint → null", () => {
    expect(reactionProposalModelVersion({ model_version: "m-rec" }, "hint")).toBe("m-rec")
    expect(reactionProposalModelVersion({ metadata_json: { model_version: "m-md" } }, "hint")).toBe("m-md")
    expect(reactionProposalModelVersion({}, "gp-ucb-1")).toBe("gp-ucb-1")
    expect(reactionProposalModelVersion({}, "")).toBeNull()
    expect(reactionProposalModelVersion(null, null)).toBeNull()
  })

  it("reads the routing flags off a ReactionFeedbackRecord (the safety-signal distinction)", () => {
    const rec = {
      id: 7,
      proposal_ref: "42",
      decision: "reject",
      reason: "unsafe",
      is_safety_signal: true,
      routes_to_safety_hardening: true,
      is_preference_learnable: false,
      model_version: "gp-1",
      created_at: "2026-06-30T00:00:00Z",
      disclaimer: "Reaction feedback feeds an advisory preference re-ranker …",
    }
    const v = reactionFeedbackRecordView(rec)
    expect(v?.decision).toBe("reject")
    expect(v?.reason).toBe("unsafe")
    expect(v?.isSafetySignal).toBe(true)
    expect(v?.routesToSafetyHardening).toBe(true)
    expect(v?.isPreferenceLearnable).toBe(false)
    // an accept is preference-learnable and not a safety signal
    const acc = reactionFeedbackRecordView({
      id: 8,
      proposal_ref: "9",
      decision: "accept",
      reason: null,
      is_safety_signal: false,
      routes_to_safety_hardening: false,
      is_preference_learnable: true,
    })
    expect(acc?.isSafetySignal).toBe(false)
    expect(acc?.isPreferenceLearnable).toBe(true)
    expect(reactionFeedbackRecordView(null)).toBeNull()
  })
})

describe("R9 preference ranking (advisory re-rank)", () => {
  const ranking = {
    reaction_project_id: 4,
    bo_run_id: null,
    advisory: true,
    ranked: [
      { proposal_ref: "21", acceptance_score: 0.82, original_rank: 3, conditions_json: { t: 80 } },
      { proposal_ref: "22", acceptance_score: 0.61, original_rank: 1, conditions_json: {} },
      "junk",
    ],
    disclaimer: "advisory only",
  }

  it("parses ranked items and defaults advisory true; bo_run_id null until a BO run exists", () => {
    const v = reactionPreferenceRankingView(ranking)
    expect(v?.advisory).toBe(true)
    expect(v?.boRunId).toBeNull()
    expect(v?.ranked).toHaveLength(2) // "junk" dropped
    expect(v?.ranked[0]).toEqual({
      proposalRef: "21",
      acceptanceScore: 0.82,
      originalRank: 3,
      conditionsJson: { t: 80 },
    })
    expect(reactionPreferenceRankingView(null)).toBeNull()
  })

  it("indexes by proposal_ref with a 1-based rerank, preserving the optimiser's original_rank", () => {
    const m = reactionPreferenceRankByRef(reactionPreferenceRankingView(ranking))
    expect(m.get("21")).toEqual({ acceptanceScore: 0.82, originalRank: 3, rerank: 1 })
    expect(m.get("22")).toEqual({ acceptanceScore: 0.61, originalRank: 1, rerank: 2 })
    expect(reactionPreferenceRankByRef(null).size).toBe(0)
  })

  it("also indexes by conditions content — the id-space-agnostic join used to merge onto cards", () => {
    // proposal_ref (an acquisition-candidate id) differs from the recommendation-row id the cards
    // key on, so the merge joins by conditions_json instead.
    const m = reactionPreferenceRankByConditions(reactionPreferenceRankingView(ranking))
    // a card whose conditions match { t: 80 } picks up rank #1 regardless of its recommendation id
    expect(m.get(canonicalConditionsKey({ t: 80 }))).toEqual({
      acceptanceScore: 0.82,
      originalRank: 3,
      rerank: 1,
    })
    expect(reactionPreferenceRankByConditions(null).size).toBe(0)
  })
})

describe("R9 conditions content key + recall validation", () => {
  it("canonicalizes conditions so key order and 20 vs 20.0 collide, and rejects non-records", () => {
    expect(canonicalConditionsKey({ t: 80, ph: 7 })).toBe(canonicalConditionsKey({ ph: 7, t: 80 }))
    expect(canonicalConditionsKey({ t: 20 })).toBe(canonicalConditionsKey({ t: 20.0 }))
    expect(canonicalConditionsKey({ t: 80 })).not.toBe(canonicalConditionsKey({ t: 70 }))
    expect(canonicalConditionsKey(null)).toBe("")
    expect(canonicalConditionsKey("nope")).toBe("")
  })

  it("validates safety_flag_recall as a number in [0,1], else null (never a silent 0)", () => {
    expect(parseReactionRecall("0.95")).toBe(0.95)
    expect(parseReactionRecall(0)).toBe(0)
    expect(parseReactionRecall(1)).toBe(1)
    expect(parseReactionRecall("")).toBeNull() // blank is NOT 0
    expect(parseReactionRecall("x")).toBeNull()
    expect(parseReactionRecall(1.5)).toBeNull() // out of range
    expect(parseReactionRecall(-0.1)).toBeNull()
  })
})

describe("R9 A/B promotion verdict (advisory, deploys nothing)", () => {
  it("reads the verdict; human sign-off + rollback default true even if omitted", () => {
    const v = reactionAbVerdictView({
      champion_version: "c1",
      challenger_version: "c2",
      promotable: false,
      safety_regression: true,
      dominates: false,
      reasons: ["safety_flag_recall regressed"],
      excluded_metrics: ["weird_metric"],
    })
    expect(v?.promotable).toBe(false)
    expect(v?.safetyRegression).toBe(true)
    expect(v?.dominates).toBe(false)
    expect(v?.requiresHumanSignoff).toBe(true) // defaulted
    expect(v?.rollbackAvailable).toBe(true) // defaulted
    expect(v?.reasons).toEqual(["safety_flag_recall regressed"])
    expect(v?.excludedMetrics).toEqual(["weird_metric"])
    expect(reactionAbVerdictView(null)).toBeNull()
  })
})

describe("R9 metric / direction parsing + A/B request body", () => {
  it("parses key=value, JSON, and newline metrics; drops non-numeric", () => {
    expect(parseReactionMetricsText("r2=0.88, rmse=0.21")).toEqual({ r2: 0.88, rmse: 0.21 })
    expect(parseReactionMetricsText('{"r2": 0.9, "n": "x"}')).toEqual({ r2: 0.9 })
    expect(parseReactionMetricsText("r2: 0.7\nrmse: 0.3")).toEqual({ r2: 0.7, rmse: 0.3 })
    expect(parseReactionMetricsText("")).toEqual({})
    expect(parseReactionMetricsText("bad")).toEqual({})
  })

  it("normalizes directions to the backend's higher/lower tokens (accepting friendly synonyms)", () => {
    // friendly synonyms normalize to the backend vocabulary
    expect(parseReactionDirectionsText("r2=maximize, rmse=minimize")).toEqual({
      r2: "higher",
      rmse: "lower",
    })
    expect(parseReactionDirectionsText("r2=higher, rmse=lower")).toEqual({
      r2: "higher",
      rmse: "lower",
    })
    expect(parseReactionDirectionsText("a=max, b=min")).toEqual({ a: "higher", b: "lower" })
    expect(parseReactionDirectionsText("r2=sideways")).toEqual({}) // unknown token dropped
    expect(parseReactionDirectionsText("")).toEqual({})
  })

  it("builds the A/B request body, omitting directions when empty and defaulting tolerance", () => {
    const body = reactionAbEvaluateBody({
      championVersion: "c1",
      championMetrics: "r2=0.8",
      championRecall: "0.95",
      challengerVersion: "c2",
      challengerMetrics: "r2=0.85",
      challengerRecall: "0.97",
      directions: "",
      tolerance: "",
    })
    expect(body.champion).toEqual({ model_version: "c1", metrics: { r2: 0.8 }, safety_flag_recall: 0.95 })
    expect(body.challenger).toEqual({ model_version: "c2", metrics: { r2: 0.85 }, safety_flag_recall: 0.97 })
    expect(body.tolerance).toBe(0) // empty → default 0
    expect("directions" in body).toBe(false) // omitted when empty
    // blank versions fall back to stable labels; directions included when provided
    const body2 = reactionAbEvaluateBody({
      championVersion: "",
      championMetrics: "",
      championRecall: "x",
      challengerVersion: "",
      challengerMetrics: "",
      challengerRecall: "",
      directions: "r2=maximize",
      tolerance: "0.05",
    })
    expect(body2.champion.model_version).toBe("champion")
    expect(body2.challenger.model_version).toBe("challenger")
    expect(body2.champion.safety_flag_recall).toBe(0) // "x" → 0
    expect(body2.tolerance).toBe(0.05)
    expect(body2.directions).toEqual({ r2: "higher" }) // normalized to backend vocabulary
  })
})

describe("R9 feedback error message", () => {
  it("surfaces a 422 detail (e.g. reject without a valid reason)", () => {
    expect(
      reactionFeedbackErrorMessage(new ApiError(422, { detail: "reason is required for a reject" })),
    ).toBe("reason is required for a reject")
  })

  it("falls back to a reason-required message on a 422 without a string detail", () => {
    const out = reactionFeedbackErrorMessage(new ApiError(422, {}))
    expect(out.toLowerCase()).toContain("reason")
  })

  it("routes non-422 errors through formatApiError", () => {
    const out = reactionFeedbackErrorMessage(new ApiError(404, { detail: "Reaction project not found." }))
    expect(out).toContain("project not found")
  })
})
