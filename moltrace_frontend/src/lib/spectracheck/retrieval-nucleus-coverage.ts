/**
 * Per-nucleus coverage for spectrum-retrieval hits.
 *
 * The reference index is built per nucleus because most public reference spectra record only ¹H
 * or only ¹³C. A hit's distance is the mean over the nuclei the query and that reference SHARE,
 * plus a penalty for query nuclei the reference lacks — so part of a small distance can be the
 * penalty rather than measured agreement. These helpers let the table say which nuclei actually
 * contributed, instead of rendering "identical on ¹³C alone" and "identical on both" the same way.
 */

/** Wire values are lower-case nucleus keys; anything else is passed through untouched. */
const NUCLEUS_LABELS: Record<string, string> = {
  "1h": "¹H",
  "13c": "¹³C",
}

function labelForNucleus(key: string): string {
  return NUCLEUS_LABELS[key.trim().toLowerCase()] ?? key
}

function cleanList(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && x.trim() !== "") : []
}

export type RetrievalCoverage = {
  /** Nuclei that actually contributed distance, in plain language ("¹H + ¹³C"). */
  matchedOnLabel: string
  /** True when the index reports no coverage at all — UNKNOWN, not "matched on nothing". */
  unknown: boolean
  /** Nuclei the QUERY had that this reference lacks. Empty for a single-nucleus query. */
  absent: string[]
  /** True only when this reference is genuinely missing data the query carried. */
  partial: boolean
  /** Plain-language explanation for the marker, or null when there is nothing to explain. */
  partialExplanation: string | null
}

/**
 * Read the coverage fields off one hit.
 *
 * Two traps this deliberately avoids:
 *  - Empty `nuclei_compared` means the deployment runs a single combined index and does not
 *    report coverage. That is UNKNOWN — render a dash and fall back to the old presentation,
 *    never "matched on nothing".
 *  - `nuclei_absent` is relative to THE QUERY, not to a complete spectrum. A ¹³C-only query
 *    returns `[]` on every hit; nothing is missing, the user simply did not run that experiment.
 *    So the marker keys off `nuclei_absent`, never off "compared is shorter than two".
 */
export function readRetrievalCoverage(hit: unknown): RetrievalCoverage {
  const rec = typeof hit === "object" && hit !== null ? (hit as Record<string, unknown>) : {}
  const compared = cleanList(rec.nuclei_compared)
  const absent = cleanList(rec.nuclei_absent)

  return {
    matchedOnLabel: compared.length > 0 ? compared.map(labelForNucleus).join(" + ") : "—",
    unknown: compared.length === 0,
    absent,
    partial: absent.length > 0,
    partialExplanation: absent.length > 0 ? explainPartialCoverage(absent) : null,
  }
}

/**
 * Wording for the partial-coverage marker.
 *
 * A reference missing ¹³C is penalised far more heavily than one missing ¹H, because ¹³C carries
 * more structural information — so the two directions must NOT read as equivalent. Plain language
 * only: no field names, no "penalty term".
 */
export function explainPartialCoverage(absent: string[]): string {
  const missing = absent.map(labelForNucleus)
  const missingLabel = missing.join(" and ")
  const comparedNote =
    absent.length === 1
      ? `so only its ${absent[0]!.trim().toLowerCase() === "1h" ? "¹³C" : "¹H"} was compared`
      : "so very little of it could be compared"
  const weight = absent.some((n) => n.trim().toLowerCase() === "13c")
    ? " Carbon data is weighted far more heavily than proton data here, so a reference without it is much weaker evidence."
    : ""
  return `This reference has no ${missingLabel} data, ${comparedNote} — part of the distance reflects the missing data rather than disagreement.${weight}`
}
