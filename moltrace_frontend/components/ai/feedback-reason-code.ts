import type { components } from "@/src/lib/api/schema"

/**
 * Closed reason_code taxonomy for prediction feedback / review submission
 * (Prompt 23, v0.19.1 — backend handoff 2026-06-07).
 *
 * The schema emits this as an inline string-union per field (not a shared
 * named enum component), so the type is derived from one of the four
 * carriers and shared across both consumers (`ai-module-prediction-
 * augmentation`, `ai-active-learning-workspace`) to keep their dropdowns
 * in lockstep.
 */
export type ReasonCode = NonNullable<
  components["schemas"]["PredictionFeedbackCreate"]["reason_code"]
>

/**
 * Display order — narrow-to-broad: spectrum-derived errors first, then
 * structure/integration, then calibration, then the open-ended bucket.
 * Order matches the BE taxonomy comment so analytics rollups read in
 * the same order.
 */
export const REASON_CODES: readonly ReasonCode[] = [
  "wrong_shift",
  "wrong_multiplicity",
  "wrong_structure",
  "missed_impurity",
  "wrong_integration",
  "calibration_off",
  "other",
] as const

/** Human-readable labels for the dropdown. Snake_case is preserved as the
 *  wire value; the label is what scientists read in the UI. */
export const REASON_CODE_LABEL: Record<ReasonCode, string> = {
  wrong_shift: "Wrong chemical shift",
  wrong_multiplicity: "Wrong multiplicity",
  wrong_structure: "Wrong structure",
  missed_impurity: "Missed impurity / artifact",
  wrong_integration: "Wrong integration",
  calibration_off: "Calibration off",
  other: "Other",
}

/**
 * Negative feedback_type values that surface the reason_code dropdown.
 * Per the BE handoff (v0.19.1) the curated negative set is exactly:
 *   rejected · corrected · error_case · uncertain
 * `not_useful` is intentionally NOT in this set per the handoff — it's a
 * lighter-weight rating, not a structured-error verdict.
 */
const NEGATIVE_FEEDBACK_TYPES = new Set<string>([
  "rejected",
  "corrected",
  "error_case",
  "uncertain",
])

export function isNegativeFeedbackType(feedbackType: string): boolean {
  return NEGATIVE_FEEDBACK_TYPES.has(feedbackType)
}
