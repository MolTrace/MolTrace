import { describe, expect, it } from "vitest"
import {
  describeScale,
  formatConfidence,
  readConfidence,
  readPredictionProvenance,
  readPredictionScale,
  readPredictionWarnings,
  readUncertainty,
  uncertaintyFacts,
} from "@/src/lib/ai/prediction-confidence"

const VERIFIER_UNCERTAINTY = {
  n_atoms: 24,
  per_nucleus: {
    "13C": { n: 18, median_sigma_ppm: 2.1044, p90_sigma_ppm: 4.8, reference_sigma_ppm: 2.306 },
  },
  fallback_fraction: 0.125,
  layer_counts: { nmrnet: 21, hose_sphere_4: 3 },
  scale: "verifier_quality",
}

const DP4_UNCERTAINTY = {
  matched_peaks: 17,
  mae_ppm: 1.884,
  rms_ppm: 2.51,
  n_candidates: 4,
  scale: "dp4_posterior",
}

describe("confidence scales", () => {
  it("refuses a proportional bar for the verifier quality scale", () => {
    const scale = describeScale("verifier_quality")
    expect(scale?.label).toBe("Verifier quality")
    // 0.870 sits at the reference uncertainty and 1.0 is unreachable, so a bar against
    // 100% would render every real prediction as a poor one.
    expect(scale?.allowsProportionalBar).toBe(false)
    expect(scale?.meaning).toContain("0.870")
    expect(scale?.meaning).toContain("unreachable")
  })

  it("allows a bar for a closed-world posterior, and says it is closed-world", () => {
    const scale = describeScale("dp4_posterior")
    expect(scale?.allowsProportionalBar).toBe(true)
    expect(scale?.meaning).toContain("only the candidates supplied")
  })

  it("returns null for an unknown or absent scale", () => {
    expect(describeScale("percentage")).toBeNull()
    expect(describeScale(undefined)).toBeNull()
    expect(describeScale(0.9)).toBeNull()
  })
})

describe("reading a prediction's confidence", () => {
  it("reads the scale from either wire name for the uncertainty block", () => {
    // The detail response names it `uncertainty`; the listing names it `uncertainty_json`.
    expect(readPredictionScale({ uncertainty: DP4_UNCERTAINTY })?.scale).toBe("dp4_posterior")
    expect(readPredictionScale({ uncertainty_json: VERIFIER_UNCERTAINTY })?.scale).toBe(
      "verifier_quality",
    )
    expect(readUncertainty({ uncertainty: DP4_UNCERTAINTY })).toEqual(DP4_UNCERTAINTY)
    expect(readUncertainty({ nothing: 1 })).toBeNull()
  })

  it("never allows a bar when the figure carries no scale", () => {
    const reading = readConfidence({ confidence_score: 0.91 })
    expect(reading.value).toBe(0.91)
    expect(reading.scale).toBeNull()
    // Nothing says what full width would mean, so nothing may be drawn.
    expect(reading.proportionalBarAllowed).toBe(false)
  })

  it("treats a null confidence from a run engine as a reported result", () => {
    const reading = readConfidence({
      confidence_score: null,
      status: "requires_review",
      uncertainty: DP4_UNCERTAINTY,
    })
    expect(reading.value).toBeNull()
    expect(reading.declined).toBe(true)
    // Not a dash and not an empty gauge.
    expect(reading.display).toBe("Reported none")
    expect(reading.proportionalBarAllowed).toBe(false)
  })

  it("recognises an engine from provenance alone when the scale is missing", () => {
    const reading = readConfidence({
      confidence_score: null,
      metadata_json: { provenance: { engine: "moltrace.spectroscopy.ai.ms_models.x" } },
    })
    expect(reading.declined).toBe(true)
  })

  it("separates an abstention from a service with no engine wired", () => {
    // No scale and no provenance: there was nothing to abstain.
    const reading = readConfidence({ confidence_score: null })
    expect(reading.declined).toBe(false)
    expect(reading.display).toBe("Not assessed")
  })

  it("formats to three decimals so the reference score reads as 0.870", () => {
    expect(formatConfidence(0.869951)).toBe("0.870")
    expect(readConfidence({ confidence_score: 0.869951, uncertainty: VERIFIER_UNCERTAINTY }).display).toBe(
      "0.870",
    )
  })

  it("reads warnings under either wire name", () => {
    expect(readPredictionWarnings({ warnings: ["a", "  ", "b"] })).toEqual(["a", "b"])
    expect(readPredictionWarnings({ warnings_json: ["c"] })).toEqual(["c"])
    expect(readPredictionWarnings({})).toEqual([])
  })
})

describe("prediction provenance", () => {
  it("reads the engine and its component versions, sorted", () => {
    const provenance = readPredictionProvenance({
      metadata_json: {
        provenance: {
          engine: "moltrace.spectroscopy.ai.ms_models.dp4_candidate_posterior",
          model_versions: { nmrnet: "sha256:abc", dp4_scoring: "smith_goodman_2010" },
        },
      },
    })
    expect(provenance?.engine).toBe("moltrace.spectroscopy.ai.ms_models.dp4_candidate_posterior")
    expect(provenance?.components).toEqual([
      { name: "dp4_scoring", version: "smith_goodman_2010" },
      { name: "nmrnet", version: "sha256:abc" },
    ])
  })

  it("returns null when nothing recorded it", () => {
    expect(readPredictionProvenance({ metadata_json: {} })).toBeNull()
    expect(readPredictionProvenance({})).toBeNull()
    expect(readPredictionProvenance(null)).toBeNull()
    // An empty version map with no engine is nothing to show.
    expect(readPredictionProvenance({ metadata_json: { provenance: { model_versions: {} } } })).toBeNull()
  })
})

describe("uncertainty facts", () => {
  it("keeps ppm units on the DP4 error figures", () => {
    const facts = uncertaintyFacts(DP4_UNCERTAINTY)
    expect(facts).toEqual([
      { label: "Matched peaks", value: "17" },
      { label: "Mean absolute error", value: "1.884 ppm" },
      { label: "Root-mean-square error", value: "2.510 ppm" },
      { label: "Candidates compared", value: "4" },
    ])
  })

  it("expands the verifier payload's nested per-nucleus and layer detail", () => {
    const facts = uncertaintyFacts(VERIFIER_UNCERTAINTY)
    const byLabel = new Map(facts.map((f) => [f.label, f.value]))
    expect(byLabel.get("Atoms scored")).toBe("24")
    expect(byLabel.get("13C predicted uncertainty")).toBe(
      "median 2.10 ppm, 90th percentile 4.80 ppm, reference 2.31 ppm",
    )
    expect(byLabel.get("Resolved by HOSE fallback")).toBe("12.5% of atoms")
    expect(byLabel.get("Atoms by prediction layer")).toBe("nmrnet: 21, hose_sphere_4: 3")
    // The discriminator itself is not a fact about the measurement.
    expect(byLabel.has("scale")).toBe(false)
  })

  it("surfaces an unrecognised key rather than dropping it", () => {
    const facts = uncertaintyFacts({ scale: "dp4_posterior", future_metric: 3 })
    expect(facts).toEqual([{ label: "future_metric", value: "3" }])
  })

  it("returns nothing for a non-record", () => {
    expect(uncertaintyFacts(null)).toEqual([])
    expect(uncertaintyFacts(0.5)).toEqual([])
  })
})
