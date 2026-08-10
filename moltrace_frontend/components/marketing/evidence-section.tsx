import { BookMarked, FileSignature, Link2 } from "lucide-react"
import { AccentCard } from "./accent-card"
import { ConstellationBackdrop } from "./constellation-backdrop"

/**
 * The section a reader lands on after clicking "See how the evidence trail
 * works" in the hero (it owns #solutions, which the hero, the header nav and
 * the closing CTA all point at).
 *
 * It used to render the SAME <EvidenceCard> the hero renders, so that click
 * scrolled a reader 1,800px to see the picture they were already looking at,
 * and then described in prose — confidence scores, citations, contradictions —
 * what the picture showed in pixels. The card is now the hero's alone, and this
 * section answers the question the click actually asks: what can I check?
 *
 * Every claim here is traced to backend source rather than to other marketing
 * copy, and — the harder test — to source that a customer request actually
 * reaches. See the note above `mechanics` for a capability that passed the first
 * test and failed the second.
 *   - unkeyed SHA-256 entry chaining: `compute_entry_hash` in
 *     moltrace_backend/src/nmrcheck/audit_chain.py returns "sha256:"; HMAC
 *     appears only under that file's "anchor signing" heading
 *   - the signature/record binding is `record_content_hash`, the §11.70 tie
 *   - citations resolve through the /regulatory/sources/* routes
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

/**
 * WHY THESE THREE AND NOT THE VERIFIER.
 *
 * Two earlier cards here described the four-test structure verifier — prediction
 * bounds, assignment consistency, 2D HSQC ranges, mass-spec match, combined by
 * Bayesian log-odds. That engine is real, well built, and does not run in the
 * shipped product:
 *
 *   - `verify_structure` has exactly two callers, both inside the AI layer
 *     (spectroscopy/ai/rag.py and ai/ms_models.py). `src/nmrcheck/` — the whole
 *     HTTP layer — never imports the verification package.
 *   - The only route in is POST /spectrum/reason, gated on
 *     `_reasoning_llm_available()`, which returns False unless
 *     `find_spec("anthropic")` succeeds — checked BEFORE the API key, so no
 *     environment variable can rescue it.
 *   - `anthropic` is declared only in the optional `rag` extra, and the
 *     production Dockerfile installs `--extra fid --extra gcs` on both uv sync
 *     lines. The shipped image has never contained the package.
 *
 * So a customer request returns `reasoner_available=false` with `candidates=[]`
 * and the verifier is never called. A capability no customer can reach is not a
 * claim this page can make.
 *
 * What replaced it is the trail itself, which IS reachable and IS the product
 * claim: chained, citable, signed. If the reasoning path ships in the image, the
 * verifier card can come back — with the Dockerfile change as its evidence.
 */
const mechanics = [
  {
    icon: Link2,
    title: "A trail anyone can re-walk",
    pill: "Integrity",
    desc: "Audit entries are chained with unkeyed SHA-256, so the record can be re-verified from an export with no secret at all. Removal, reordering and alteration are named as separate findings.",
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
    icon: FileSignature,
    title: "Signatures bind their record",
    pill: "Sign-off",
    desc: "An e-signature carries a SHA-256 hash of the exact record snapshot it signed, so it cannot be moved to a different record, and the signed manifestation stays displayable.",
  },
]

/**
 * THE BAND IS DARK IN BOTH THEMES, and the `dark` class on the section is how
 * rather than a wall of hard-coded hexes. Adding it re-points every design token
 * inside this subtree — `--card`, `--muted-foreground`, `--mt-*-ink` — at the
 * values the .dark block already defines, which are the ones that clear AA on a
 * near-black background. On a page that is already dark it is a no-op.
 *
 * Hard-coding the colours instead would have meant maintaining a second palette
 * that silently stops matching the first, and would have taken the teal eyebrow
 * below AA the moment anyone retuned the token.
 */
export function EvidenceSection() {
  return (
    <section className="dark relative isolate overflow-hidden py-28 text-foreground" id="solutions">
      <ConstellationBackdrop />
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl">
          {/* Eyebrow deliberately not "Evidence-First AI" — that was a
              truncation of the hero badge two screens up. */}
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em]" style={{ color: "var(--mt-teal-ink)" }}>
            Reading the evidence
          </p>
          {/* Heading, then straight to the cards. The paragraph that sat here
              restated in prose exactly what the three cards say — chained,
              cited, signed — so a reader met the same argument twice before
              reaching the substance. */}
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            What makes the trail checkable.
          </h2>
        </div>

        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {mechanics.map((m) => (
            <AccentCard key={m.title} {...m} {...TEAL} tone="glass" />
          ))}
        </div>

        {/* THE CLOSING DISCLAIMER WAS REMOVED, and this note is the check that
            it was safe to remove rather than a decision made by eye.
            It read: "Overall confidence is a total, not a verdict. It is
            decision support for a qualified reviewer — not proof of identity,
            and not a calibrated probability that the structure is correct. A
            human signs off, every time."

            It had become orphaned HERE. It qualified a confidence score, and
            this section stopped discussing confidence when the verifier cards
            were replaced by the three above — chaining, references, signatures.
            A disclaimer standing next to no claim is clutter, and clutter is
            how a page teaches readers to skip its disclaimers.

            What it qualified, and where that qualification now lives:
              - the 87.3% figure is the hero's card, which carries its own
                caption directly beneath it: "Illustrative example of a MolTrace
                result — not a measured sample" (hero.tsx).
              - "a human decides" is HOME_FAQS on this same page — "Does
                MolTrace's AI make the analytical or regulatory decisions?" —
                answered No, AI is strictly advisory.
              - "not a calibrated probability" is the SpectraCheck module FAQ
                (lib/seo/modules.ts) and the product surface itself, where
                spectracheck-evidence-panels.tsx gates the word "probability" on
                the backend's own probability_is_calibrated flag.

            The one thing the homepage no longer states in so many words is
            "not a calibrated probability" — acceptable only because the single
            confidence figure on it is labelled illustrative. If a REAL, measured
            confidence number ever appears on this page, that line has to come
            back next to it. See also the note at the top of this file: the word
            "calibrated" must not be reintroduced as a claim without a measured
            ECE behind it. */}
      </div>
    </section>
  )
}
