/**
 * A confidence figure is meaningless without the scale it was measured on, and the platform
 * now emits two that are not comparable:
 *
 * - `verifier_quality` — the deterministic verifier's own quality scale, `tanh(significance/3)`.
 *   At the reference uncertainty for a nucleus the significance is 4, so the score there is
 *   0.870; the curve is asymptotic, so 1.0 needs a zero uncertainty and is unreachable. Drawing
 *   it as a proportion of 100% would make a good prediction look like a 87% one — and a
 *   perfect-looking bar impossible to earn.
 * - `dp4_posterior` — a probability over only the candidates supplied. It redistributes across
 *   that closed set, so it says which of *these* fits best, not whether the right structure was
 *   among them. Two caveats, not one: the set may not contain the answer, AND the number is a
 *   relative ranking rather than a calibrated probability, which is what the backend reports as
 *   `probability_is_calibrated: false`. Stating only the first leaves 0.9 reading as 90%.
 *
 * A null confidence is a third case and not an empty one: the engine ran and abstained. It is
 * reported with the warning that names the cause, never as a dash or a zeroed gauge.
 */

export type ConfidenceScale = "verifier_quality" | "dp4_posterior"

export type ScaleDescriptor = {
  scale: ConfidenceScale
  label: string
  /** Whether the figure may be drawn as a proportion of 100%. */
  allowsProportionalBar: boolean
  /** One sentence a reviewer can act on. */
  meaning: string
}

const SCALES: Record<ConfidenceScale, ScaleDescriptor> = {
  verifier_quality: {
    scale: "verifier_quality",
    label: "Verifier quality",
    // Asymptotic in the predicted uncertainty: not a percentage, and not a scale with a
    // reachable top. A bar against 100% misreads every real prediction as a poor one.
    allowsProportionalBar: false,
    meaning:
      "The deterministic verifier's own quality scale. 0.870 is the score at the reference uncertainty for the nucleus, and the scale is asymptotic — 1.0 would need a zero uncertainty, so it is unreachable.",
  },
  dp4_posterior: {
    scale: "dp4_posterior",
    label: "DP4 posterior",
    allowsProportionalBar: true,
    meaning:
      "A probability across only the candidates supplied. It says which of those fits best, not whether the correct structure was among them, and it is not calibrated \u2014 0.9 is a relative ranking, not a 90% chance of being right.",
  },
}

export function describeScale(scale: unknown): ScaleDescriptor | null {
  if (typeof scale !== "string") return null
  return SCALES[scale as ConfidenceScale] ?? null
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

/**
 * The prediction detail response names this `uncertainty`; the listing names it
 * `uncertainty_json`. Both are read so one helper serves both surfaces.
 */
function firstRecord(row: Record<string, unknown>, keys: string[]): Record<string, unknown> | null {
  for (const key of keys) {
    const value = row[key]
    if (isRecord(value)) return value
  }
  return null
}

export function readUncertainty(row: unknown): Record<string, unknown> | null {
  if (!isRecord(row)) return null
  return firstRecord(row, ["uncertainty", "uncertainty_json"])
}

export function readPredictionScale(row: unknown): ScaleDescriptor | null {
  return describeScale(readUncertainty(row)?.scale)
}

export function readStringList(row: unknown, keys: string[]): string[] {
  if (!isRecord(row)) return []
  for (const key of keys) {
    const value = row[key]
    if (Array.isArray(value)) {
      return value
        .map((v) => (typeof v === "string" ? v.trim() : ""))
        .filter((v) => v.length > 0)
    }
  }
  return []
}

export function readPredictionWarnings(row: unknown): string[] {
  return readStringList(row, ["warnings", "warnings_json"])
}

export type ConfidenceReading = {
  /** `null` when the engine reported none. */
  value: number | null
  scale: ScaleDescriptor | null
  /** True when an engine produced this result but reported no confidence. */
  declined: boolean
  /** Reader-facing text for the figure, or for its absence. Never a bare dash. */
  display: string
  /** False whenever a bar would misrepresent the number — including an unknown scale. */
  proportionalBarAllowed: boolean
}

function readNumber(row: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const v = row[key]
    if (typeof v === "number" && Number.isFinite(v)) return v
    if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Number(v)
  }
  return null
}

/** Three decimals: enough to separate 0.870 from 0.87, not enough to imply spurious precision. */
export function formatConfidence(value: number): string {
  return value.toFixed(3)
}

/**
 * An engine ran if it left a fingerprint — a scale on the uncertainty, or an engine name in
 * provenance. That separates "abstained" from "this service has no engine wired yet", which
 * also has no confidence but for an entirely different reason.
 */
function engineRan(row: Record<string, unknown>): boolean {
  if (describeScale(readUncertainty(row)?.scale) != null) return true
  return readPredictionProvenance(row)?.engine != null
}

export function readConfidence(row: unknown): ConfidenceReading {
  const record = isRecord(row) ? row : {}
  const scale = describeScale(readUncertainty(record)?.scale)
  const value = readNumber(record, ["confidence_score", "confidence"])

  if (value == null) {
    const declined = engineRan(record)
    return {
      value: null,
      scale,
      declined,
      display: declined ? "Reported none" : "Not assessed",
      proportionalBarAllowed: false,
    }
  }

  return {
    value,
    scale,
    declined: false,
    display: formatConfidence(value),
    // An unlabelled figure gets no bar either: without a scale there is nothing to say the
    // bar's full width means.
    proportionalBarAllowed: scale?.allowsProportionalBar === true,
  }
}

export type ProvenanceComponent = { name: string; version: string }

export type PredictionProvenance = {
  /** The engine that produced the number. */
  engine: string | null
  /** Everything that touched the number, and at which version. */
  components: ProvenanceComponent[]
}

/**
 * `metadata_json.provenance` is the audit answer to "which model produced this". Note the
 * values are the component versions the engine resolved — a checkpoint digest for a weighted
 * model, a method tag for a published algorithm — so they are labelled as versions rather than
 * asserted to be digests.
 */
export function readPredictionProvenance(row: unknown): PredictionProvenance | null {
  if (!isRecord(row)) return null
  const metadata = firstRecord(row, ["metadata_json", "metadata"])
  const provenance = metadata ? firstRecord(metadata, ["provenance"]) : null
  if (!provenance) return null

  const engineRaw = provenance.engine
  const engine = typeof engineRaw === "string" && engineRaw.trim() ? engineRaw.trim() : null

  const components: ProvenanceComponent[] = []
  const versions = provenance.model_versions
  if (isRecord(versions)) {
    for (const [name, version] of Object.entries(versions)) {
      if (typeof version === "string" && version.trim()) {
        components.push({ name, version: version.trim() })
      } else if (typeof version === "number" && Number.isFinite(version)) {
        components.push({ name, version: String(version) })
      }
    }
    components.sort((a, b) => a.name.localeCompare(b.name))
  }

  if (engine == null && components.length === 0) return null
  return { engine, components }
}

export type UncertaintyFact = { label: string; value: string }

/** Explicit labels, because the units are part of the meaning and a humanizer would drop them. */
const FACT_LABELS: Record<string, string> = {
  n_atoms: "Atoms scored",
  matched_peaks: "Matched peaks",
  n_candidates: "Candidates compared",
  mae_ppm: "Mean absolute error",
  rms_ppm: "Root-mean-square error",
}

const PPM_KEYS = new Set(["mae_ppm", "rms_ppm"])

function formatFactValue(key: string, value: unknown): string | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    const rendered = Number.isInteger(value) ? String(value) : value.toFixed(3)
    return PPM_KEYS.has(key) ? `${rendered} ppm` : rendered
  }
  if (typeof value === "string" && value.trim()) return value.trim()
  return null
}

/**
 * Flatten the scale-specific uncertainty payload into displayable rows. Unknown keys are kept
 * under their own name rather than dropped, so a field added on the science side still surfaces
 * instead of silently disappearing.
 */
export function uncertaintyFacts(uncertainty: unknown): UncertaintyFact[] {
  if (!isRecord(uncertainty)) return []
  const facts: UncertaintyFact[] = []

  for (const [key, value] of Object.entries(uncertainty)) {
    if (key === "scale") continue

    if (key === "fallback_fraction" && typeof value === "number" && Number.isFinite(value)) {
      facts.push({
        label: "Resolved by HOSE fallback",
        value: `${(value * 100).toFixed(1)}% of atoms`,
      })
      continue
    }

    if (key === "per_nucleus" && isRecord(value)) {
      for (const [nucleus, summary] of Object.entries(value)) {
        if (!isRecord(summary)) continue
        const median = summary.median_sigma_ppm
        const p90 = summary.p90_sigma_ppm
        const reference = summary.reference_sigma_ppm
        const parts: string[] = []
        if (typeof median === "number") parts.push(`median ${median.toFixed(2)} ppm`)
        if (typeof p90 === "number") parts.push(`90th percentile ${p90.toFixed(2)} ppm`)
        if (typeof reference === "number") parts.push(`reference ${reference.toFixed(2)} ppm`)
        if (parts.length > 0) {
          facts.push({ label: `${nucleus} predicted uncertainty`, value: parts.join(", ") })
        }
      }
      continue
    }

    if (key === "layer_counts" && isRecord(value)) {
      const parts = Object.entries(value)
        .filter(([, count]) => typeof count === "number")
        .map(([layer, count]) => `${layer || "unnamed"}: ${count}`)
      if (parts.length > 0) facts.push({ label: "Atoms by prediction layer", value: parts.join(", ") })
      continue
    }

    const rendered = formatFactValue(key, value)
    if (rendered != null) facts.push({ label: FACT_LABELS[key] ?? key, value: rendered })
  }

  return facts
}
