import { AlertTriangle, BookMarked, Layers } from "lucide-react"
import { AccentCard } from "./accent-card"

/**
 * The section a reader lands on after clicking "See how the evidence trail
 * works" in the hero (it owns #solutions, which the hero, the header nav and
 * the closing CTA all point at).
 *
 * It used to render the SAME <EvidenceCard> the hero renders, so that click
 * scrolled a reader 1,800px to see the picture they were already looking at,
 * and then described in prose — confidence scores, citations, contradictions —
 * what the picture showed in pixels. The card is now the hero's alone, and this
 * section answers the question the click actually asks: where does that number
 * come from?
 *
 * Everything here is traceable to backend source rather than to other marketing
 * copy:
 *   - the four tests are `_ALL_TESTS` in
 *     moltrace_backend/src/moltrace/spectroscopy/verification/scorer.py:845
 *   - the combination is `"model": "bayesian_log_odds"` at scorer.py:868
 *   - AI-may-only-reorder-within-a-verdict is the deterministic-first contract
 *
 * NOTE ON THE CLAIM THAT WAS HERE: this section previously promised "a
 * calibrated confidence score with uncertainty bounds". Neither half survives
 * contact with the code — there is no calibration anywhere in verification/,
 * and the site's own SpectraCheck FAQ (lib/seo/modules.ts) states the result is
 * "not a calibrated DP4/DP5 probability". Calibration is not a synonym for
 * confidence; it is the specific property that makes a number a probability,
 * and it is the first thing a reviewer with statistics training will test. Do
 * not reintroduce the word without a measured ECE to back it.
 */

const TEAL = { accent: "var(--mt-teal)", ink: "var(--mt-teal-ink)", soft: "var(--mt-teal-soft)" }

const mechanics = [
  {
    icon: Layers,
    title: "Four tests, one verdict",
    pill: "Deterministic core",
    desc: "Prediction bounds, assignment consistency, 2D HSQC ranges and mass-spec match run independently, then combine by Bayesian log-odds. A model may reorder candidates inside a verdict class — never across one.",
  },
  {
    // Was "Supporting evidence links the spectral database entry, literature
    // reference or guidance section it came from." That described the regulatory
    // RAG, which is a different module; what spectroscopy actually carries is the
    // published shift table behind an assignment and a DOI on literature records.
    icon: BookMarked,
    title: "Reference data, named",
    pill: "Provenance",
    desc: "Solvent and impurity assignments name the published shift table they were matched against, and literature records keep their DOI and source link.",
  },
  {
    icon: AlertTriangle,
    title: "Disagreement is reported",
    pill: "Human review",
    desc: "Unexplained integrals, and missing or extra cross-peaks, are reported per test — beside the score instead of folded into it. A qualified reviewer signs off.",
  },
]

export function EvidenceSection() {
  return (
    <section className="border-y bg-muted/30 py-24" id="solutions">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl">
          {/* Eyebrow deliberately not "Evidence-First AI" — that was a
              truncation of the hero badge two screens up. */}
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em]" style={{ color: "var(--mt-teal-ink)" }}>
            Reading the evidence
          </p>
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Where that confidence figure comes from.
          </h2>
          <p className="mt-4 text-base leading-relaxed text-muted-foreground">
            No black box, and no single model&apos;s opinion. The score above is a total produced by
            four independent tests, and every part of it stays open to inspection.
          </p>
        </div>

        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {mechanics.map((m) => (
            <AccentCard key={m.title} {...m} {...TEAL} />
          ))}
        </div>

        {/* The limit of the claim, stated on the page that makes it rather than
            only in an FAQ answer three sections down. */}
        <p className="mt-14 max-w-3xl border-t pt-8 text-sm leading-relaxed text-muted-foreground">
          Overall confidence is a total, not a verdict. It is decision support for a qualified
          reviewer — not proof of identity, and not a calibrated probability that the structure is
          correct. A human signs off, every time.
        </p>
      </div>
    </section>
  )
}
