/**
 * Single source of truth for the "Field notes" blog.
 *
 * Post data lives here (not inside the page/grid component) so the list page,
 * the per-post route (`app/blog/[slug]/page.tsx`), and the sitemap can all
 * import the same records. A post becomes a real, indexable page the moment it
 * flips from `status: "forthcoming"` to `status: "live"` AND gets a `body`.
 *
 * Editorial rule (see MolTrace claims stance): posts are grounded in real work
 * documented in the white papers + codebase. Forthcoming posts carry only a
 * one-paragraph `claim` and are honestly badged; they are NOT emitted as routes
 * or sitemap entries, so we never ship thin pages.
 */

export type BlogTopic =
  | "all"
  | "science"
  | "engineering"
  | "methodology"
  | "regulatory"
  | "company"

/** A block of article body. Kept intentionally small + serializable so a post
 *  body is plain data, rendered by the route with a tiny inline formatter
 *  (supports `code`, **bold**, *italic* inside `p`/`quote`/`list` text). */
export type PostBlock =
  | { type: "p"; text: string }
  | { type: "h2"; text: string }
  | { type: "quote"; text: string }
  | { type: "list"; items: string[] }

export type BlogPost = {
  slug: string
  title: string
  dek: string
  /** One-paragraph editorial claim — shown on the index card. */
  claim: string
  topic: Exclude<BlogTopic, "all">
  topicLabel: string
  /** ISO date (YYYY-MM-DD). */
  date: string
  readingMinutes: number
  status: "live" | "forthcoming"
  /** External link (opens in a new tab). Internal published posts do NOT set
   *  this — they are linked to `/blog/{slug}` by status instead. */
  href?: string
  /** <=155-char summary for the per-post `<meta name="description">`. Falls
   *  back to `dek` when absent. */
  metaDescription?: string
  /** Short title for the `<title>` tag only; the H1 and the cards keep `title`.
   *
   *  The rendered tag is this plus the layout's " | MolTrace", so keep it under
   *  49 characters to stay inside the ~60 Google displays. An essay headline can
   *  afford to be longer than a search result can. */
  metaTitle?: string
  /** Byline for the article + JSON-LD author. */
  author?: string
  /** Hero artwork shown on the post and the featured card. Path under
   *  `/public/blog/`, WITH its extension — an .svg diagram or a raster
   *  photograph are both fine, so the field does not assume a format. */
  heroImage?: string
  /** Raster twin for `og:image` and the Article JSON-LD image, 1200x630.
   *
   *  Needed only when `heroImage` is an SVG: no major social platform or Slack
   *  renders an SVG link preview, and Google's structured-data guidance wants a
   *  raster, so pointing og:image at a .svg yields a link with no card at all.
   *  When `heroImage` is already a raster it serves as its own twin and this
   *  can be omitted — see `socialImageFor`.
   *
   *  Regenerate an SVG's twin after any edit to the source:
   *    node -e "const s=require('sharp'),f=require('fs');
   *      s(f.readFileSync('public/blog/<name>.svg'),{density:200})
   *       .resize(1200,630,{fit:'fill'}).png({palette:true,quality:90,effort:10})
   *       .toFile('public/blog/<name>.png')"
   */
  heroSocialImage?: string
  /** Describes the artwork for screen readers. Required whenever heroImage is
   *  set — the artwork carries the post's argument, not just decoration. */
  heroImageAlt?: string
  /** Full article body. Present only for `status: "live"` posts. */
  body?: PostBlock[]
}

// Curated editorial calendar. Each post reflects real work documented in the
// codebase + white papers. Flip `status` to "live" and add `body` as essays ship.
export const POSTS: BlogPost[] = [
  {
    slug: "chemical-environments-not-peaks",
    title: "Why we count chemical environments, not peaks",
    dek: "The expert-reference vs detector-output mismatch that kept our promotion gate red — and the multiplet-clustering layer that reconciled it.",
    claim:
      "NMRShiftDB2 references count distinct chemical environments; detectors faithfully resolve multiplet lines. Median peak-count deltas of 17 looked like an algorithm failure; they were a units mismatch. Field notes from the Phase 10 multiplet-clustering work.",
    topic: "methodology",
    topicLabel: "Methodology",
    date: "2026-05-27",
    readingMinutes: 9,
    status: "live",
    metaDescription:
      "Why MolTrace counts chemical environments, not peaks: reconciling expert NMR references with detector multiplet-line output for the GSD gate.",
    author: "MolTrace research team",
    // A raster hero is its own social image, so no heroSocialImage twin is
    // needed here. JPEG, not PNG: the same photograph encodes to 71 KB as JPEG
    // and 1,379 KB as PNG, and this page is one we want crawled quickly.
    heroImage: "/blog/chemical-environments-not-peaks-lab.jpg",
    heroImageAlt:
      "A darkened NMR facility. A superconducting magnet vents cryogenic vapour inside a yellow-and-black floor marking, beside a rack of spectrometer electronics. A proton NMR spectrum is projected into the air above the bench in glowing teal, its peak clusters gathered by brackets into single points, with a magnifier hovering over one cluster. At the right, a gloved hand holds a sample tube.",
    body: [
      {
        "type": "h2",
        "text": "A delta that looked like a failure"
      },
      {
        "type": "p",
        "text": "When we first scored MolTrace's GSD (Global Spectral Deconvolution) sidecar against the NMRShiftDB2 reference corpus, the raw number was alarming. On the 19-fixture curated corpus at detection level 2, the median absolute difference between the detector's total peak count and the expert reference count was **17 peaks** — a measured value in the committed internal validation report, not an estimate. A gap that size reads, at first glance, like a detector that cannot count."
      },
      {
        "type": "p",
        "text": "It wasn't. The detector was doing exactly what a detector should. The mismatch was a units problem, and mistaking a units problem for an algorithm problem is one of the easier ways to spend a week fixing the wrong thing."
      },
      {
        "type": "p",
        "text": "The GSD backend itself is conventional and deliberately so: single-pass detection with `scipy.signal.find_peaks`, per-peak Lorentzian/pseudo-Voigt fitting via `lmfit`, level-aware overlap resolution across levels one through five, then an expert-system pass that labels each peak `compound | solvent | impurity | artifact | 13C_satellite`. Nothing about that pipeline is trying to be clever about *counting*. It resolves lines. That is the point of a deconvolution engine."
      },
      {
        "type": "h2",
        "text": "Two different things called a \"peak\""
      },
      {
        "type": "p",
        "text": "The diagnosis came from lining up what each side of the comparison actually counts. NMRShiftDB2-style expert reference tables count **distinct chemical environments** — curated, assigned shift positions, one entry per chemically distinct nucleus. A spectral detector's natural output is at **multiplet-line granularity**: every resolved line of every doublet, triplet, and AB system is a peak. One environment can present as several lines. So the reference and the detector were both correct and were counting in different units. This is documented directly in the validation harness, which notes that NMRShiftDB2 counts environments, not lines — it is a stated finding, not a post-hoc inference."
      },
      {
        "type": "p",
        "text": "The measured contrast made the granularity effect concrete. On the NMRShiftDB2 corpus, raw compound peak-count landed within ±5% of the expert reference on only **37%** of fixtures — but compound *environment*-count landed within manifest tolerance on **63%**. Environment granularity matched the reference far better than peak granularity did, which is exactly what you'd expect if the two sides were counting different things."
      },
      {
        "type": "quote",
        "text": "The 17-peak gap was never evidence the algorithm was broken. It was evidence we were comparing a line count against an environment count — the right measurement on the wrong scale."
      },
      {
        "type": "h2",
        "text": "The clustering layer"
      },
      {
        "type": "p",
        "text": "The fix was to make the comparison happen on the reference's scale. In v0.5.0 the sidecar gained a post-detection multiplet-clustering layer, `cluster_into_environments`, that groups adjacent same-category peaks within a nucleus-aware J-coupling window into a single chemical-environment entry. Crucially it preserves provenance: each `Environment` record carries `centre_ppm`, `peak_count`, `total_intensity`, `total_area`, `category`, `multiplicity`, and `constituent_peak_indices` — so every environment remembers which detector lines were merged into it. Nothing is thrown away; the detector output is re-expressed at a coarser granularity that a reviewer can unfold."
      },
      {
        "type": "p",
        "text": "The J-coupling window defaults to **30 Hz for ¹H and 5 Hz for ¹³C**, tuned against the NMRShiftDB2 20-fixture corpus to absorb strong-coupling AB systems and constrained-ring geminal H–H couplings up to 25–30 Hz. These are nucleus-aware defaults fitted to the fixture corpus, not universal physical constants. Classification helps keep the count honest from the other direction, too: ¹³C-satellite peaks are detected at ±½·J_CH (125 Hz for sp³, 160 Hz for sp²) so those non-analyte lines don't inflate the compound count."
      },
      {
        "type": "p",
        "text": "Watching the metric move as granularity is reconciled is the clearest way to see the whole story. On the same corpus, the median absolute delta goes **17 (all peaks) → 3 (compound peaks only) → 2 (clustered compound environments)**. Each step removes a source of unit mismatch: filtering to compound-category peaks, then collapsing multiplets to environments."
      },
      {
        "type": "h2",
        "text": "Clearing the strict gate"
      },
      {
        "type": "p",
        "text": "The strict production promotion gate has two published thresholds: solvent peak auto-detected on **≥95%** of fixtures that have a known residual-solvent reference, **and** median compound-environment-count delta **≤2** versus the expert reference. Two facts about how it was cleared matter for honesty."
      },
      {
        "type": "p",
        "text": "First, the ≤2 is a *target*, and the corpus median lands exactly on it — **2.0**, meeting the gate, not beating it. It should be read as \"cleared,\" never \"exceeded with margin.\" The final push came from widening the ¹H clustering window from 20 Hz to 30 Hz, which dropped the median environment-count delta from 3 to 2. The solvent arm cleared at 100% (17/17 fixtures with a known residual reference) on the 19-fixture corpus — a small curated set, not a universal accuracy claim."
      },
      {
        "type": "p",
        "text": "Second, the \"19\" is honest curation. One fixture, `60000023_1h`, was dropped as a documented data-quality outlier: its chemical-shift referencing is off by ~1.7 ppm, placing the CHCl₃ residual at 8.96 instead of 7.26 ppm, outside the CDCl₃ solvent window regardless of detector quality. The exclusion and rationale are recorded in the manifest. In the technical write-up, the window tuning that closed the median-delta half and the outlier removal that closed the solvent half are what let the strict-gate test drop its long-standing `xfail` marker and pass unconditionally in v0.6.0. A regression-floor companion test locks the baseline so any change that materially degrades the sidecar fails CI loudly — the gate is enforced, not aspirational."
      },
      {
        "type": "p",
        "text": "The reconciliation was reproduced across three independent corpora: NMRShiftDB2 (19 fixtures, 100% solvent, median environment delta 2), an HMDB-style synthetic 20-fixture multiplet-line corpus (19/20 within tolerance on environments, 20/20 on multiplet lines), and a real-instrument HMDB 100-fixture corpus (95% parseable, 93% solvent auto-detect). The synthetic corpus is the load-bearing check: the *same* clustering algorithm clears the median-≤2 gate when scored against multiplet-line references, which is only possible if the original 17-peak gap was a corpus-granularity effect rather than an algorithm failure. It's also why we don't gate on absolute peak-count against HMDB at all — HMDB's `distinct-peaks` is curator-dependent, ranging from 1 to 190 across the 100-fixture subset, so a single absolute-delta gate there would be meaningless."
      },
      {
        "type": "h2",
        "text": "Takeaway"
      },
      {
        "type": "p",
        "text": "Pick the measurement scale before you judge the number. Our 17-peak median wasn't a bug to fix in detection code; it was a signal that the detector and the reference counted in different units, and the honest move was to add a clustering layer that compares environments to environments while keeping every constituent line addressable."
      },
      {
        "type": "p",
        "text": "Two boundaries stay fixed. The GSD backend is opt-in and `experimental: true` — the default `/spectrum/analyze` flow and the legacy pipeline remain authoritative, so this work never destabilized the shipping path. And the gate is a detector-vs-reference reconciliation metric on curated fixtures: it measures solvent auto-detection and environment-count agreement, nothing more. It is not a claim of structure-identification accuracy, and MolTrace's controls are designed to *support* standards like 21 CFR Part 11 and GAMP 5 — full computerized-system validation remains the customer's responsibility."
      }
    ],
  },
  {
    slug: "regression-by-fixture-id",
    title: "A regression test that fails by fixture_id",
    dek: "How a 20-fixture A/B JSON sidecar replaced our 'looks-good-to-me' detector reviews.",
    claim:
      "Every detector change runs against a curated NMRShiftDB2 corpus before merge. CI fails by name when any single fixture drifts >50% — so reviewers see 'nmrshiftdb2_60000006_13c regressed' instead of 'tests passed (with notes).' The boring infrastructure meant to keep ship velocity high.",
    topic: "engineering",
    topicLabel: "Engineering",
    date: "2026-05-27",
    readingMinutes: 7,
    status: "forthcoming",
  },
  {
    slug: "experimental-default-promotion-gate",
    title: "What 'experimental' actually means in our promotion gate",
    dek: "A new analysis backend ships opt-in behind two published numbers. Promotion happens when the numbers move, and the commit that removes the failure marker is the record.",
    claim:
      "Our GSD sidecar shipped as experimental: true with a written promotion gate — 95% solvent auto-detection and a median compound-environment-count delta of 2 or better. The gate was declared before it was met, the test that enforced it was marked expected-to-fail, and clearing it is a diff you can read.",
    topic: "methodology",
    topicLabel: "Methodology",
    date: "2026-05-28",
    readingMinutes: 7,
    status: "live",
    metaTitle: "What 'experimental' means in our promotion gate",
    metaDescription:
      "How MolTrace promotes an experimental NMR backend to default: two published thresholds, an expected-to-fail test, and a diff recording when it cleared.",
    author: "MolTrace research team",
    heroImage: "/blog/experimental-default-promotion-gate.jpg",
    heroImageAlt:
      "A darkened facility corridor at night. A heavy interlocked door stands half-open, cold teal light spilling through it, and a tall column of horizontal bar meters glows in the opening — most filled teal, one amber and short, sitting below the others. An analytical instrument waits on a wheeled trolley at the threshold, not yet through the door.",
    body: [
      {
        "type": "h2",
        "text": "\"Experimental\" is a promise about the default path"
      },
      {
        "type": "p",
        "text": "Most software uses \"experimental\" to mean *we are not confident yet*. That is a feeling, and feelings do not survive contact with a regulated workflow. For an analysis backend whose output ends up in someone's evidence trail, the label has to mean something a reader can check."
      },
      {
        "type": "p",
        "text": "Ours means two specific things. The backend is opt-in — the default `/spectrum/analyze` flow and the legacy pipeline stay authoritative, so a customer who changes nothing is unaffected by anything happening here. And the conditions under which it stops being experimental were written down *before* they were met."
      },
      {
        "type": "p",
        "text": "That second half is the part that is easy to skip, and skipping it is how a promotion decision quietly becomes a matter of who is in the room."
      },
      {
        "type": "h2",
        "text": "The gate is two numbers on a named corpus"
      },
      {
        "type": "p",
        "text": "The strict production promotion gate for the GSD sidecar is **95% solvent auto-detection** and a **median compound-environment-count delta of 2 or better**, measured on the curated NMRShiftDB2 corpus."
      },
      {
        "type": "p",
        "text": "Two numbers, one named corpus, both chosen before the run that would judge them. Neither is a threshold anyone can slide after seeing the result, because both were committed to the repository first — and a threshold you can adjust after seeing your score is not a gate, it is a rationalisation with a number attached."
      },
      {
        "type": "p",
        "text": "The corpus matters as much as the thresholds. \"95% solvent detection\" is meaningless without stating on what; the same detector will produce very different rates on curated reference spectra and on whatever arrives from a customer's instrument. Naming the corpus is what makes the number auditable rather than promotional."
      },
      {
        "type": "h2",
        "text": "A test that is expected to fail"
      },
      {
        "type": "p",
        "text": "The gate was enforced by `test_prompt3_gsd_meets_promotion_gate`, and for as long as the sidecar fell short, that test carried a `@pytest.mark.xfail` decorator — it ran on every commit, measured the real thing, and was expected to fail."
      },
      {
        "type": "p",
        "text": "This is worth more than deleting the test until the feature is ready. An expected-to-fail test keeps the measurement running continuously, so the distance to the gate is visible on every commit rather than rediscovered at the end. It also fails *loudly* if it ever unexpectedly passes, which is the case that matters: an xfail that starts passing means either you cleared the bar or you broke the measurement, and both deserve a human looking at them."
      },
      {
        "type": "quote",
        "text": "The moment a feature stops being experimental should be a diff, not a decision someone remembers making."
      },
      {
        "type": "p",
        "text": "So the promotion event is a removed decorator. The `xfail` came off, and the test now passes unconditionally. There is no separate approval artefact to trust, because the artefact is the commit."
      },
      {
        "type": "h2",
        "text": "What actually moved the number"
      },
      {
        "type": "p",
        "text": "The change that cleared the gate was one default: the ¹H clustering window in `_DEFAULT_CLUSTER_J_HZ_BY_NUCLEUS` went from **20 Hz to 30 Hz**. That dropped the NMRShiftDB2 median compound-environment-count delta from **3 to 2**, which is the strict target."
      },
      {
        "type": "p",
        "text": "The justification is chemical rather than numerical, and it has to be. A 20 Hz window splits couplings that belong together: strong-coupling AB systems and constrained-ring geminal H–H couplings run up to about 25–30 Hz, so lines from a single environment were being counted as separate environments. Widening the window to 30 Hz stops that. The number improved because the algorithm became more correct about coupling, not because a parameter was swept until the metric moved — and if the only defence of a parameter is that it improves the score, it is a fitted constant, not a decision."
      },
      {
        "type": "h2",
        "text": "The fixture we removed, and why that is allowed"
      },
      {
        "type": "p",
        "text": "One fixture, `60000023_1h`, was dropped from the corpus. Removing data from the corpus you are being judged against deserves the most scepticism of anything here, so the standard is that the reason must be checkable by someone who assumes you are cheating."
      },
      {
        "type": "p",
        "text": "Its chemical-shift referencing is off by roughly **1.7 ppm** — the CHCl₃ residual peak lands at **8.96 ppm** instead of **7.26 ppm**. No detector can find a solvent residual outside the curated window it is looking in, so the fixture measures the archive's referencing error rather than detector quality."
      },
      {
        "type": "p",
        "text": "Three things make that defensible rather than convenient. The exclusion and its rationale are recorded in the manifest's `removed_fixtures` array, not in a commit message someone has to go digging for. The raw archive is still committed, so the spectrum can be re-included the moment an evidence layer handles out-of-band TMS/DSS referencing correction. And the resulting corpus is stated plainly: 19 fixtures, with 100% solvent auto-detection across the 17 that carry a known residual reference."
      },
      {
        "type": "h2",
        "text": "What the label still means after promotion"
      },
      {
        "type": "p",
        "text": "Clearing the gate did not make the backend the default. It made it a *measured* backend with a published result — the opt-in boundary stays where it was, and the legacy pipeline remains authoritative on the default path."
      },
      {
        "type": "p",
        "text": "The gate is also narrower than it sounds. It is a detector-versus-reference reconciliation metric on curated fixtures, covering solvent auto-detection and environment-count agreement. It is not a claim of structure-identification accuracy. And as everywhere else here, MolTrace's controls are designed to *support* standards such as 21 CFR Part 11 and GAMP 5; full computerized-system validation remains the customer's responsibility."
      },
      {
        "type": "p",
        "text": "None of this is elaborate. Write the thresholds down before you measure, name the corpus, keep the failing test running, and let the diff be the record. The value is not in any one of those steps — it is that together they leave nobody, including us, able to quietly decide that a number was good enough."
      }
    ],
  },
  {
    slug: "auditable-confidence",
    title: "No confidence number without an audit trail",
    dek: "Why we'd rather show 'pending' than a polished score with no provenance.",
    claim:
      "Every numerical claim in the UI links to its source — the spectrum file, the picked peaks, the SMILES candidate, the literature citation, the human reviewer who signed off. The implementation cost is real. The regulatory cost of doing it otherwise is higher.",
    topic: "regulatory",
    topicLabel: "Regulatory",
    date: "2026-05-21",
    readingMinutes: 8,
    status: "forthcoming",
  },
  {
    slug: "bruker-sfo1-to-gsd",
    title: "From Bruker SFO1 to GSD: plumbing instrument metadata through the contract",
    dek: "A 500-MHz field hardcoded in the FE became a real number from the vendor metadata. Three lines of code, one cascade, no contract change.",
    claim:
      "Phase 8 traced field_mhz through the preview → process → analyze chain so the GSD endpoint receives the spectrometer frequency the instrument actually used (600.13 MHz, in our verification fixture) instead of a hardcoded 500. The same plumbing pattern works for vendor / solvent / nucleus.",
    topic: "engineering",
    topicLabel: "Engineering",
    date: "2026-05-27",
    readingMinutes: 5,
    status: "forthcoming",
  },
  {
    slug: "hmdb-style-validation",
    title: "Validation against references that count the way detectors count",
    dek: "If a reference table and a detector count in different units, no threshold you pick will mean anything. So we built a corpus that counts both ways.",
    claim:
      "A published peak list and a deconvolution engine disagree by construction. The HMDB-style harness forward-models a spectrum from a reference list and then gates on environment-count and multiplet-line-count deltas separately, so detector quality can be separated from corpus granularity. It is also why one of our three corpora is deliberately not gated on peak count at all.",
    topic: "science",
    topicLabel: "Science",
    date: "2026-05-28",
    readingMinutes: 9,
    status: "live",
    metaTitle: "Counting environments vs multiplet lines",
    metaDescription:
      "How MolTrace validates NMR peak detection against references that count environments and multiplet lines separately — and why one corpus is not gated.",
    author: "MolTrace research team",
    heroImage: "/blog/hmdb-style-validation.jpg",
    heroImageAlt:
      "Two holographic panels face each other across a darkened laboratory bench. The left panel holds a neat grid of evenly spaced reference cells; the right shows real recorded traces, dense and irregular. Fine teal threads run between them, most pairing one cell to one trace, several fanning out from a single cell to many.",
    body: [
      {
        "type": "h2",
        "text": "You cannot validate against a number you do not understand"
      },
      {
        "type": "p",
        "text": "A previous note worked through why our detector's peak count sat a median of **17 peaks** away from the NMRShiftDB2 reference: the reference counts distinct chemical environments, the detector resolves multiplet lines, and one environment can present as several lines. The conclusion was that the gap was a units mismatch rather than an algorithm defect."
      },
      {
        "type": "p",
        "text": "That conclusion is comfortable, and comfortable conclusions about your own software deserve suspicion. \"The reference is measuring something else\" is exactly what you would say if your detector were simply bad. The claim only becomes evidence if you can find a reference that counts the *other* way and show that the same algorithm, unchanged, agrees with that one."
      },
      {
        "type": "p",
        "text": "That is what the HMDB-style validation harness is for."
      },
      {
        "type": "h2",
        "text": "Forward-modelling a spectrum from a published list"
      },
      {
        "type": "p",
        "text": "`gsd_hmdb_style_validation.py` runs backwards relative to the normal pipeline. It starts from a published peak list at HMDB / Pretsch granularity — every resolved line of every multiplet, as a human tabulated them — and forward-models a noisy Lorentzian spectrum from it. That synthetic spectrum then goes through the full GSD pipeline as though it had come off an instrument, and the output is scored against the list it was built from."
      },
      {
        "type": "p",
        "text": "The point of generating the spectrum rather than measuring one is that the ground truth is known exactly. There is no curator judgement between the reference and the signal, because the signal was constructed from the reference. If the detector disagrees, the disagreement is the detector's."
      },
      {
        "type": "p",
        "text": "Two details keep the synthesis from being too kind. The noise is correlated rather than white — a Gaussian σ=2 filter, which mimics the band-limited baselines you actually get from Fourier-transformed NMR — because a detector tuned against white noise will flatter itself on real data. And sparse spectra carry synthesis-floor-aware per-fixture tolerances, recorded in each entry's `notes` field, so a fixture with three signals is not scored as though a one-peak error were the same fraction of the answer as it would be on a fixture with thirty."
      },
      {
        "type": "p",
        "text": "The corpus itself is 20 fixtures, hand-curated from Fulmer and Pretsch reference data, committed at `tests/fixtures/hmdb_style_minicorpus/hmdb_style_minicorpus_v1.json`. Small, and deliberately so: every entry was checked by hand, and a corpus nobody has read is not a reference."
      },
      {
        "type": "h2",
        "text": "Gating both counts, separately"
      },
      {
        "type": "p",
        "text": "The harness reports two deltas per fixture rather than one. The environment-count delta compares against distinct chemical environments; the multiplet-line-count delta compares against resolved lines. Keeping them apart is the whole design — a single blended score would hide precisely the effect we were trying to isolate."
      },
      {
        "type": "p",
        "text": "The committed report at detection level 2 (`gsd_hmdb_style_validation_report_v1`) reads:"
      },
      {
        "type": "list",
        "items": [
          "20 fixtures processed, 20 completed, 0 errors.",
          "Environment count within tolerance on **19 of 20** fixtures — a median absolute delta of **1**.",
          "Multiplet-line count within tolerance on **20 of 20** fixtures — a median absolute delta of **2**."
        ]
      },
      {
        "type": "p",
        "text": "The same clustering algorithm that looked 17 peaks adrift against an environment-counting reference lands within tolerance on every fixture of a line-counting one. That is the shape of result a units mismatch produces. It is not the shape a broken detector produces, because a broken detector has no reason to agree with either."
      },
      {
        "type": "quote",
        "text": "A validation number is only as meaningful as your understanding of what the reference was counting. Two references, two scales, one unchanged algorithm — that is the check that actually distinguishes a units problem from a defect."
      },
      {
        "type": "h2",
        "text": "The corpus we deliberately do not gate"
      },
      {
        "type": "p",
        "text": "There is a third corpus: 100 real-instrument HMDB acquisitions, with no synthesis anywhere in the path. It measures the things a forward-modelled corpus structurally cannot — whether we can read what an instrument actually wrote."
      },
      {
        "type": "p",
        "text": "**95 of 100 fixtures are parseable.** The five that are not were each traced to the archive rather than the reader: four are Bruker layouts carrying stray `acqu2` / `acqu2s` two-dimensional parameter remnants that the HMDB curator left inside 1D archives, and one is missing its `fid` binary entirely. Solvent auto-detection runs at **53 of 57** on the subset with a known solvent reference."
      },
      {
        "type": "p",
        "text": "What this corpus is *not* gated on is per-fixture peak count — and that omission is deliberate, documented, and worth explaining, because an ungated metric usually means someone is hiding from it."
      },
      {
        "type": "p",
        "text": "HMDB's `distinct-peaks` field is curator-dependent. Across the curated 100-fixture subset it ranges from **1 to 190 peaks per fixture**. That is not a scale; it is several different people's conventions stacked into one column. A single absolute-delta threshold across that range would be satisfied or violated mostly according to which curator happened to enter a given record, and a gate that moves with the curator rather than the detector tells you nothing about the detector. The semantically meaningful signals from this corpus are parseability and solvent auto-detection, so those are the ones with thresholds on them."
      },
      {
        "type": "p",
        "text": "Declining to gate a metric is a defensible engineering decision. Declining to *publish* that you declined is not, which is why the reasoning sits in the changelog next to the numbers."
      },
      {
        "type": "h2",
        "text": "What the result does and does not claim"
      },
      {
        "type": "p",
        "text": "Three corpora, three jobs. NMRShiftDB2 checks agreement with expert environment assignments on real spectra. The HMDB-style synthetic corpus checks the detector against a known ground truth at line granularity. The real-instrument HMDB corpus checks that we can read what instruments produce. No one of them would be sufficient, and the reason for running all three is that each is blind to what the others catch."
      },
      {
        "type": "p",
        "text": "The boundaries are narrow and worth stating plainly. These are peak-count reconciliation and solvent-detection metrics on curated fixtures. They say nothing about structure-identification accuracy, which is a different claim requiring different evidence. The GSD backend remains opt-in and `experimental: true`, with the legacy pipeline authoritative on the default path. And MolTrace's controls are designed to *support* standards such as 21 CFR Part 11 and GAMP 5 — full computerized-system validation remains the customer's responsibility."
      },
      {
        "type": "p",
        "text": "The generalisable part is smaller than the numbers and more useful than them: before you threshold a validation metric, find out what the reference was counting. If you cannot answer that, the threshold is decoration."
      }
    ],
  },
]

/** Posts that are published as real, indexable routes. */
export function getLivePosts(): BlogPost[] {
  return POSTS.filter((p) => p.status === "live" && p.body && p.body.length > 0)
}

export function getPostBySlug(slug: string): BlogPost | undefined {
  return POSTS.find((p) => p.slug === slug)
}

const RASTER_IMAGE = /\.(png|jpe?g|webp)$/i

/** The image to hand social scrapers and Article JSON-LD, or undefined.
 *
 *  A raster hero is its own social image; an SVG hero needs the explicit
 *  `heroSocialImage` twin, because no major platform renders an SVG preview.
 *  Returning undefined lets the caller fall back to the site-wide card rather
 *  than advertising an image that would fail to render.
 */
export function socialImageFor(post: BlogPost): string | undefined {
  if (post.heroSocialImage) return post.heroSocialImage
  if (post.heroImage && RASTER_IMAGE.test(post.heroImage)) return post.heroImage
  return undefined
}
