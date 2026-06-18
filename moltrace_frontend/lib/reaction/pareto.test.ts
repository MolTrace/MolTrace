import { describe, expect, it } from "vitest"
import {
  formatHypervolume,
  hypervolumeMethodLabel,
  hypervolumeTrend,
  nonDominatedExperimentIds,
  objectivesKey,
  paretoFrontFromRun,
  readParetoFront,
} from "@/lib/reaction/pareto"

const RAW_FRONT = {
  objectives: ["yield", "selectivity", "impurity"],
  hypervolume: 1234567,
  hypervolume_method: "monte_carlo",
  reference_point: [0, 0, 0],
  pareto_size: 2,
  evaluated_experiment_count: 3,
  knee_experiment_id: 41,
  members: [
    {
      experiment_id: 41,
      experiment_code: "BO-4",
      objectives: { yield: 85, selectivity: 85, impurity: 3 },
      non_dominated: true,
    },
    {
      experiment_id: 42,
      experiment_code: "BO-5",
      objectives: { yield: 90, selectivity: 70, impurity: 5 },
      non_dominated: true,
    },
    {
      experiment_id: 43,
      experiment_code: "BO-6",
      objectives: { yield: 50, selectivity: 50, impurity: 9 },
      non_dominated: false,
    },
  ],
  note: "Non-dominated set. Advisory; requires human review.",
}

describe("pareto lib", () => {
  it("parses a well-formed pareto_front from diagnostics_json", () => {
    const front = readParetoFront({ pareto_front: RAW_FRONT })
    expect(front).not.toBeNull()
    expect(front!.objectives).toEqual(["yield", "selectivity", "impurity"])
    expect(front!.hypervolume).toBe(1234567)
    expect(front!.hypervolumeMethod).toBe("monte_carlo")
    expect(front!.paretoSize).toBe(2)
    expect(front!.kneeExperimentId).toBe(41)
    expect(front!.members).toHaveLength(3)
    expect(front!.members[0].objectives.yield).toBe(85)
  })

  it("returns null for single-objective / missing / empty fronts", () => {
    expect(readParetoFront(null)).toBeNull()
    expect(readParetoFront({})).toBeNull()
    expect(readParetoFront({ pareto_front: null })).toBeNull()
    expect(readParetoFront({ pareto_front: { objectives: [], members: [] } })).toBeNull()
    expect(readParetoFront({ pareto_front: { objectives: ["yield"], members: [] } })).toBeNull()
  })

  it("reads the front from a run via diagnostics_json or legacy diagnostics", () => {
    expect(paretoFrontFromRun({ diagnostics_json: { pareto_front: RAW_FRONT } })).not.toBeNull()
    expect(paretoFrontFromRun({ diagnostics: { pareto_front: RAW_FRONT } })).not.toBeNull()
    expect(paretoFrontFromRun({ diagnostics_json: {} })).toBeNull()
  })

  it("collects non-dominated experiment ids only", () => {
    const front = readParetoFront({ pareto_front: RAW_FRONT })
    const ids = nonDominatedExperimentIds(front)
    expect([...ids].sort()).toEqual([41, 42])
    expect(ids.has(43)).toBe(false)
    expect(nonDominatedExperimentIds(null).size).toBe(0)
  })

  it("trends hypervolume only across runs of the same objective set, oldest→newest", () => {
    const key = objectivesKey(["yield", "selectivity", "impurity"])
    const runs = [
      { bo_run_id: 2, diagnostics_json: { pareto_front: { ...RAW_FRONT, hypervolume: 200 } } },
      { bo_run_id: 1, diagnostics_json: { pareto_front: { ...RAW_FRONT, hypervolume: 100 } } },
      // different objective set — excluded
      {
        bo_run_id: 3,
        diagnostics_json: {
          pareto_front: { ...RAW_FRONT, objectives: ["yield", "conversion"], hypervolume: 999 },
        },
      },
    ]
    const pts = hypervolumeTrend(runs, key)
    expect(pts.map((p) => p.boRunId)).toEqual([1, 2])
    expect(pts.map((p) => p.hypervolume)).toEqual([100, 200])
  })

  it("formats hypervolume + method labels", () => {
    expect(formatHypervolume(1234567)).toBe("1.23e+6")
    expect(formatHypervolume(42.5)).toBe("42.5")
    expect(formatHypervolume(null)).toBe("—")
    expect(hypervolumeMethodLabel("exact_2d")).toBe("exact (2-D)")
    expect(hypervolumeMethodLabel("monte_carlo")).toBe("Monte Carlo")
  })
})
