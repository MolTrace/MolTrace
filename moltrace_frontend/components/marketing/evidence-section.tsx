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

const mechanics = [
  {
    step: "01",
    label: "Four tests, one verdict",
    desc: "Prediction bounds, assignment consistency, 2D HSQC ranges and mass-spec match run independently, then combine by Bayesian log-odds. The deterministic result is the arbiter — a model may reorder candidates inside a verdict, never across one.",
  },
  {
    step: "02",
    label: "Citations, not assertions",
    desc: "Supporting evidence links the spectral database entry, literature reference or guidance section it came from, so a reviewer can open the source instead of trusting the summary.",
  },
  {
    step: "03",
    label: "Contradictions surfaced, not smoothed",
    desc: "When evidence disagrees — an expected peak that never appeared — the conflict is reported beside the score rather than averaged into it, and the result is held for human review before sign-off.",
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

        <div className="mt-14 grid gap-10 sm:grid-cols-3 sm:gap-8">
          {mechanics.map((m) => (
            <div key={m.step} className="min-w-0">
              <div
                className="font-mono text-xs font-bold tracking-[0.18em]"
                style={{ color: "var(--mt-teal-ink)" }}
              >
                {m.step}
              </div>
              <div className="mt-3 text-base font-semibold text-foreground">{m.label}</div>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{m.desc}</p>
            </div>
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
