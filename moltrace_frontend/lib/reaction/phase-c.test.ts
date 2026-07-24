import { describe, expect, it, vi } from "vitest"

vi.mock("@/lib/api/client", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number
    data: unknown
    constructor(status: number, data: unknown) {
      super(`HTTP ${status}`)
      this.status = status
      this.data = data
    }
  },
}))

import {
  parseCapabilityReadout,
  parseForwardCheckRecord,
  parseRouteScoreRecord,
  parseSdlSiteStatus,
  parseSmilesList,
  parseYieldPredictionRun,
  routeNodeToJson,
  routeRiskBadgeClass,
  routeRiskLabel,
  validateRouteNode,
} from "@/lib/reaction/phase-c"

describe("Phase C capability readout", () => {
  it("parses capabilities defensively; heavy-off is a designed state, not an error", () => {
    const r = parseCapabilityReadout({
      capabilities: [
        {
          name: "yield_gnn",
          enabled: true,
          available: false,
          active: false,
          missing_modules: ["torch"],
          reason: "torch not installed",
          engine: "reaction_capabilities.v1",
        },
        "junk",
      ],
      disclaimer: "Heavy-ML reaction capabilities are optional, default-off extras …",
    })
    expect(r?.capabilities).toHaveLength(1)
    expect(r?.capabilities[0]).toMatchObject({
      name: "yield_gnn",
      enabled: true,
      available: false,
      active: false,
      missingModules: ["torch"],
    })
    expect(r?.disclaimer).toContain("default-off")
    expect(parseCapabilityReadout(null)).toBeNull()
  })

  it("parses SDL status; execution_surface_wired is hard false today", () => {
    const s = parseSdlSiteStatus({
      enabled: false,
      execution_surface_wired: false,
      detail: "No SDL execution routes are wired.",
      capability: { name: "sdl_execution", enabled: false, available: false, active: false, reason: "", engine: "e" },
      disclaimer: "SDL execution is a hardware-automation layer …",
    })
    expect(s?.executionSurfaceWired).toBe(false)
    expect(s?.capability?.name).toBe("sdl_execution")
    expect(parseSdlSiteStatus(null)).toBeNull()
  })
})

describe("Phase C yield predictions (R12)", () => {
  it("parses a run; the producing backend and std always survive (the honesty contract)", () => {
    const run = parseYieldPredictionRun({
      id: 3,
      backend: "k-NN surrogate",
      trained_n: 7,
      require_verified: true,
      predictions: [
        {
          conditions: { temperature: 80 },
          mean: 71.2,
          std: 6.4,
          backend: "k-NN surrogate",
          n_samples: 5,
          warnings: ["temperature_c=<missing>"],
        },
        7,
      ],
      created_at: "2026-07-01T00:00:00Z",
      disclaimer: "Yield predictions are advisory decision support …",
    })
    expect(run?.backend).toBe("k-NN surrogate")
    expect(run?.trainedN).toBe(7)
    expect(run?.requireVerified).toBe(true)
    expect(run?.predictions).toHaveLength(1) // non-record dropped
    expect(run?.predictions[0].mean).toBe(71.2)
    expect(run?.predictions[0].std).toBe(6.4)
    expect(run?.predictions[0].warnings).toEqual(["temperature_c=<missing>"]) // disclosed-degraded
    expect(parseYieldPredictionRun(null)).toBeNull()
  })

  it("keeps capability_provenance — the disclaimer names it, so it must resolve in-product", () => {
    const run = parseYieldPredictionRun({
      id: 1,
      backend: "knn_surrogate",
      predictions: [],
      capability_provenance: { capability: "yield_gnn", resolved: "knn_surrogate", reason: "torch absent" },
    })
    expect(run?.capabilityProvenance).toMatchObject({ resolved: "knn_surrogate" })
    expect(parseYieldPredictionRun({ id: 2, predictions: [] })?.capabilityProvenance).toBeNull()
  })
})

describe("Phase C route scores (R13)", () => {
  it("serializes + validates the route tree (every node needs a SMILES; empty solvent dropped)", () => {
    const node = {
      smiles: "CC(=O)Oc1ccccc1C(=O)O",
      reagents: ["CC(=O)OC(C)=O", " "],
      solvent: "",
      children: [{ smiles: "", reagents: [], children: [] }],
    }
    const json = routeNodeToJson(node)
    expect(json.solvent).toBeUndefined()
    expect(json.reagents).toEqual(["CC(=O)OC(C)=O"])
    expect(validateRouteNode(node)).toEqual(["root.1: SMILES is required"])
  })

  it("parses a score record; missing risk defaults to unknown (the WORST tier)", () => {
    const v = parseRouteScoreRecord({
      id: 2,
      label: "route A",
      route: { smiles: "X", children: [], reagents: [] },
      mermaid: "graph TD; a-->b",
      human_review_required: true,
      score: {
        route_score: 0.61,
        // The engine emits weighted components as {value, weight} — never bare numbers.
        score_components: { safety: { value: 80, weight: 0.4 }, brevity: { value: 100, weight: 0.1 } },
        safety: {
          worst_risk: "high",
          requires_expert_review: true,
          screens: [
            { smiles: "X", role: "reagent", overall_risk: "high", requires_expert_review: true },
            { smiles: "Y", role: "molecule" }, // no risk field → must fail CLOSED to unknown
            { smiles: "Z", role: "molecule", overall_risk: "" }, // blank → also unknown
          ],
        },
        steps: [{ product: "X" }],
        step_count: 2,
        max_depth: 1,
        starting_materials: ["Y"],
        warnings: ["w1"],
      },
      disclaimer: "Retrosynthesis routes are machine proposals …",
    })
    expect(v?.routeScore).toBe(0.61)
    expect(v?.worstRisk).toBe("high")
    expect(v?.screens[0].role).toBe("reagent")
    expect(v?.screens[0].requiresExpertReview).toBe(true)
    // A screen with no/blank risk must fail CLOSED to unknown so a badge always renders —
    // an omitted badge would read as "no concern" next to red-badged siblings.
    expect(v?.screens[1].risk).toBe("unknown")
    expect(v?.screens[2].risk).toBe("unknown")
    // Components unpack to {value, weight} — never stringified objects.
    expect(v?.scoreComponents).toEqual([
      { name: "safety", value: 80, weight: 0.4 },
      { name: "brevity", value: 100, weight: 0.1 },
    ])
    expect(v?.mermaid).toContain("graph TD")
    expect(v?.route).toMatchObject({ smiles: "X" })
    // absent safety block → unknown, never neutral
    const noSafety = parseRouteScoreRecord({ id: 3, route: {}, score: {} })
    expect(noSafety?.worstRisk).toBe("unknown")
    expect(noSafety?.requiresExpertReview).toBe(true)
  })

  it("renders unknown risk as WORSE than critical (unreviewable), never neutral/muted", () => {
    expect(routeRiskLabel("unknown")).toBe("unknown — unreviewable")
    expect(routeRiskLabel("weird")).toBe("weird — unreviewable")
    expect(routeRiskLabel("critical")).toBe("critical")
    const unknownClass = routeRiskBadgeClass("unknown")
    expect(unknownClass).toContain("red") // red family, like critical
    expect(unknownClass).toContain("ring") // visually distinct from plain critical
    expect(unknownClass).not.toContain("muted")
  })
})

describe("Phase C forward checks (R14)", () => {
  it("parses SMILES lists from comma/newline text", () => {
    expect(parseSmilesList("A, B\nC,\n")).toEqual(["A", "B", "C"])
    expect(parseSmilesList("")).toEqual([])
  })

  it("parses a check record; confidence and safety verdict stay separate fields", () => {
    const v = parseForwardCheckRecord({
      id: 4,
      label: "check",
      reactants_smiles: ["A"],
      reagents_smiles: [],
      human_review_required: true,
      result: {
        products_smiles: ["B"],
        confidence: 0.87,
        safety: { overall_risk: "medium", requires_expert_review: true, energetic_groups_found: ["nitro"] },
        solvent_greenness: 6,
        warnings: [],
      },
      disclaimer: "Forward predictions and condition suggestions are machine proposals …",
    })
    expect(v?.confidence).toBe(0.87)
    expect(v?.overallRisk).toBe("medium")
    expect(v?.energeticGroupsFound).toEqual(["nitro"])
    expect(v?.humanReviewRequired).toBe(true)
    // missing safety → unknown (worst), never clean
    expect(parseForwardCheckRecord({ id: 5, result: {} })?.overallRisk).toBe("unknown")
    expect(parseForwardCheckRecord(null)).toBeNull()
  })
})
