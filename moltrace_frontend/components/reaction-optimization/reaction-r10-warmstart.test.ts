import { describe, expect, it, vi } from "vitest"

// R10 helpers live in the heavy reaction-project-detail module; mock its runtime/browser deps so
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
  reactionWarmStartBuildBody,
  reactionWarmStartErrorMessage,
  reactionWarmStartPriorView,
  reactionWarmStartRankByConditions,
  reactionWarmStartRankingView,
} from "@/components/reaction-optimization/reaction-project-detail"

describe("R10 warm-start prior view (lineage)", () => {
  it("surfaces the lineage fields; owned + verified only, never the gold set", () => {
    const p = reactionWarmStartPriorView({
      id: 5,
      reaction_project_id: 4,
      snapshot_hash: "abc123def456ghi",
      objective_target: 95,
      global_mean: 0.62,
      trained_n: 18,
      excluded_gold_count: 2,
      excluded_unverified_count: 7,
      source_project_ids: [4, 9, "bad"],
      lineage: { campaigns: [{ id: 4, verified: 18 }] },
      feature_offsets: { temperature: 0.1 },
      augmentation_count: 3,
      created_at: "2026-06-30T00:00:00Z",
      disclaimer: "Warm-start priors are advisory …",
    })
    expect(p?.trainedN).toBe(18)
    expect(p?.excludedGoldCount).toBe(2)
    expect(p?.excludedUnverifiedCount).toBe(7)
    expect(p?.snapshotHash).toBe("abc123def456ghi")
    expect(p?.objectiveTarget).toBe(95)
    expect(p?.sourceProjectIds).toEqual([4, 9]) // "bad" filtered
    expect(p?.augmentationCount).toBe(3)
    expect(reactionWarmStartPriorView(null)).toBeNull()
  })

  it("flags a PREVIEW fit (lineage.verified_only:false) so the UI never presents it as verified-only", () => {
    const preview = reactionWarmStartPriorView({
      id: 6,
      snapshot_hash: "sha256:aa",
      lineage: { verified_only: false },
    })
    expect(preview?.verifiedOnly).toBe(false)
    // explicit true and absent both read as verified-only (the engine default)
    expect(reactionWarmStartPriorView({ id: 7, lineage: { verified_only: true } })?.verifiedOnly).toBe(true)
    expect(reactionWarmStartPriorView({ id: 8, lineage: {} })?.verifiedOnly).toBe(true)
    expect(reactionWarmStartPriorView({ id: 9 })?.verifiedOnly).toBe(true)
  })
})

describe("R10 warm-start ranking (advisory)", () => {
  const ranking = {
    reaction_project_id: 4,
    prior_id: 5,
    bo_run_id: null,
    global_mean: 0.62,
    advisory: true,
    ranked: [
      { proposal_ref: "31", prior_mean: 0.71, original_rank: 4, conditions_json: { t: 80 } },
      { proposal_ref: "32", prior_mean: 0.55, original_rank: 1, conditions_json: { t: 60 } },
      42,
    ],
    disclaimer: "advisory",
  }

  it("parses ranked items and defaults advisory true; bo_run_id null until a BO run exists", () => {
    const v = reactionWarmStartRankingView(ranking)
    expect(v?.advisory).toBe(true)
    expect(v?.priorId).toBe(5)
    expect(v?.boRunId).toBeNull()
    expect(v?.ranked).toHaveLength(2) // the number 42 dropped
    expect(v?.ranked[0]).toEqual({
      proposalRef: "31",
      priorMean: 0.71,
      originalRank: 4,
      conditionsJson: { t: 80 },
    })
    expect(reactionWarmStartRankingView(null)).toBeNull()
  })

  it("joins to cards by conditions content (id-space-agnostic), first-wins, preserving original_rank", () => {
    const m = reactionWarmStartRankByConditions(reactionWarmStartRankingView(ranking))
    expect(m.get(canonicalConditionsKey({ t: 80 }))).toEqual({
      priorMean: 0.71,
      originalRank: 4,
      rerank: 1,
    })
    expect(m.get(canonicalConditionsKey({ t: 60 }))).toEqual({
      priorMean: 0.55,
      originalRank: 1,
      rerank: 2,
    })
    expect(reactionWarmStartRankByConditions(null).size).toBe(0)
  })
})

describe("R10 warm-start build body", () => {
  it("omits an empty source list (backend defaults to this campaign) and dedups", () => {
    expect(reactionWarmStartBuildBody({ sourceProjectIds: [], requireVerified: true })).toEqual({
      require_verified: true,
    })
    expect(
      reactionWarmStartBuildBody({ sourceProjectIds: [4, 9, 4], requireVerified: true }).source_project_ids,
    ).toEqual([4, 9])
  })

  it("includes objective_target only when numeric; passes require_verified through", () => {
    const b = reactionWarmStartBuildBody({
      sourceProjectIds: [4],
      objectiveTarget: "95",
      requireVerified: false,
    })
    expect(b).toEqual({ source_project_ids: [4], objective_target: 95, require_verified: false })
    // blank / non-numeric target is omitted
    expect("objective_target" in reactionWarmStartBuildBody({ sourceProjectIds: [4], objectiveTarget: "", requireVerified: true })).toBe(false)
    expect("objective_target" in reactionWarmStartBuildBody({ sourceProjectIds: [4], objectiveTarget: "x", requireVerified: true })).toBe(false)
    // objective_target 0 is a real value (not blank)
    expect(reactionWarmStartBuildBody({ sourceProjectIds: [4], objectiveTarget: 0, requireVerified: true }).objective_target).toBe(0)
  })

  it("passes through non-empty gold_set_observation_ids, dropping blanks", () => {
    expect(
      reactionWarmStartBuildBody({
        sourceProjectIds: [4],
        requireVerified: true,
        goldSetObservationIds: ["4:12", "", "9:3"],
      }).gold_set_observation_ids,
    ).toEqual(["4:12", "9:3"])
  })
})

describe("R10 warm-start error message", () => {
  it("surfaces a 400 admissible-data reason from detail", () => {
    expect(
      reactionWarmStartErrorMessage(new ApiError(400, { detail: "No verified experiments to learn from." })),
    ).toBe("No verified experiments to learn from.")
  })

  it("gives a non-leaking ownership hint on a 404 (never echoing which id)", () => {
    const out = reactionWarmStartErrorMessage(new ApiError(404, { detail: "Not Found" }))
    expect(out.toLowerCase()).toContain("own every source campaign")
  })

  it("routes other errors through formatApiError", () => {
    const out = reactionWarmStartErrorMessage(new ApiError(500, { detail: "boom" }))
    expect(typeof out).toBe("string")
    expect(out).not.toBe("")
  })
})
