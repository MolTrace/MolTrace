/**
 * Detect — and relabel for — the "these integrals are relative" disclosure.
 *
 * When no structure grounds a proton budget the backend anchors the integral
 * scale to the smallest resolved signal instead: the ratios between peaks are
 * correct, but the absolute values are not proton counts and can run far above
 * the molecule's real proton total. Measured on a real 500 MHz spectrum
 * (validation fixture 33, MeOD) the same five leading peaks read
 * ``0.008 0.098 0.094 1.0 0.5`` against a 6 H structural budget and
 * ``1.0 14.0 13.5 123.5 84.5`` with no budget at all.
 *
 * The backend says so in ``warnings[]`` on every ungrounded response
 * (``nmrcheck.integration_scale.RELATIVE_INTEGRAL_DISCLOSURE``), but it does not
 * relabel the numbers themselves — ``inferred_nmr_text`` still prints ``123.5H``
 * — and that is settled, not pending. The string is not display-only: it is fed
 * back in as ``AnalysisInputs.nmr_text`` and re-parsed, and the parser requires
 * an ``NH`` integral, so ``123.5 rel.`` raises ``PeakParseError``. Relabelling at
 * source would stop the FID path producing analysable text at all — a functional
 * regression traded for a cosmetic gain.
 *
 * So this module is the permanent home of that relabelling, not a stopgap
 * awaiting a backend fix: the frontend is the only layer that can say the ``H``
 * on screen is a ratio without also breaking the round trip. Do not delete it in
 * anticipation of a producer-side fix. Teaching the parser a relative notation
 * would be a core-contract change affecting every reader of NMR text.
 *
 * One hazard this does *not* have to defend against: ungrounded numbers pasted
 * into a structured analysis are refused by name ("the parsed text accounts for
 * 152H, but the structure expects 6 total H"). The backend already stops them
 * being *used* as counts; the job here is to stop them *looking* like counts.
 */

import { isRecord } from "@/components/spectracheck/spectracheck-nmr-result-parse"

/**
 * Phrases that identify the disclosure without pinning its exact wording.
 *
 * Matching the full sentence would break silently the first time the backend
 * rewords it — and a disclosure that stops being detected fails open, back to
 * rendering ``123.5H`` as though it were a count. Both anchors are distinctive
 * enough that no other warning in the corpus contains them.
 */
const DISCLOSURE_ANCHORS = ["integrals are relative", "smallest resolved signal"]

/** True when a single warning string is the relative-integral disclosure. */
export function isRelativeIntegralDisclosure(warning: string): boolean {
  const text = warning.toLowerCase()
  return DISCLOSURE_ANCHORS.some((anchor) => text.includes(anchor))
}

/** Every warning list a loose analyze/preview payload can carry. */
function warningsAtEveryLevel(payload: unknown): string[] {
  if (!isRecord(payload)) return []
  const collected: string[] = []
  // The panels are handed either a preview block, an analysis block, or the
  // wrapper holding both side-by-side — the same three shapes
  // ``readInferredNmrText`` accommodates.
  for (const level of [payload, payload.preview, payload.analysis]) {
    if (!isRecord(level)) continue
    const raw = level.warnings
    if (Array.isArray(raw)) {
      collected.push(...raw.map((w) => String(w)))
    } else if (typeof raw === "string" && raw.trim()) {
      collected.push(raw)
    }
  }
  return collected
}

/**
 * The disclosure text carried by this payload, or null when the integrals were
 * grounded by a structure.
 *
 * Returns the backend's own sentence rather than a boolean so the notice can
 * render the wording the backend chose — including the remedy it names — instead
 * of a paraphrase that could drift out of step with it.
 */
export function findRelativeIntegralDisclosure(payload: unknown): string | null {
  return warningsAtEveryLevel(payload).find(isRelativeIntegralDisclosure) ?? null
}

/**
 * Rewrite the ``H`` suffixes in a backend-generated NMR string as ``rel.``.
 *
 * ``_peaks_to_nmr_text`` (spectrum.py) emits exactly
 * ``"5.23 (d, J = 3.6 Hz, 12.5H), 3.95 (ddd, J = 10.3 Hz, 9.5H)"`` — the
 * integral is always a number immediately followed by ``H)``. Anchoring on the
 * closing parenthesis keeps the rewrite off ``Hz`` and off any ``1H``/``13C``
 * nucleus label, which are the only other places an ``H`` follows a digit.
 *
 * Call this only when {@link findRelativeIntegralDisclosure} returned a
 * disclosure. With a proton budget the ``H`` is a genuine count and must stand.
 */
export function relabelRelativeIntegrals(text: string): string {
  return text.replace(/(\d)H\)/g, "$1 rel.)")
}

/** What the relabelled unit means, for the notice that accompanies it. */
export const RELATIVE_INTEGRAL_UNIT_HINT =
  'Integrals below read as "rel." — a multiple of the smallest resolved signal, not a proton count.'
