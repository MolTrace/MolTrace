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
    dek: "Every new AI backend ships as opt-in. Promotion to default is a published-threshold decision, not a vibes call.",
    claim:
      "GSD-Prompt-3 shipped as `experimental: true` with a documented promotion gate (target: 95% solvent detection, median compound-count delta ≤2). Until both clear, the default stays legacy. We publish the corpus, the threshold, and the date a feature crosses each one.",
    topic: "methodology",
    topicLabel: "Methodology",
    date: "2026-05-27",
    readingMinutes: 6,
    status: "forthcoming",
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
    slug: "fit-chi-squared-of-10-15",
    title: "Why legacy's fit χ² of 10¹⁵ is honest",
    dek: "Per-peak QC metrics landed on legacy peaks and immediately surfaced a units mismatch. We shipped the column anyway.",
    claim:
      "GSD reports fit residuals normalized to baseline σ; legacy reports them in raw signal-domain units. The same threshold paints 31/37 peaks 'red' on legacy spectra. The right fix is detector-side normalization — but in the meantime, the column tells the truth.",
    topic: "engineering",
    topicLabel: "Engineering",
    date: "2026-05-28",
    readingMinutes: 6,
    status: "forthcoming",
  },
  {
    slug: "hmdb-style-validation",
    title: "Validation against references that count the way detectors count",
    dek: "NMRShiftDB2 said the algorithm was failing. HMDB-style references said it was clearing the strict gate. Both were right.",
    claim:
      "Same algorithm, two corpora, two verdicts. The Phase 14 framework added expert-curated multiplet-line references so we could finally separate detector quality from corpus granularity. Strict gate cleared at multiplet-line scale; NMRShiftDB2 environment-scale stays xfailed by design.",
    topic: "science",
    topicLabel: "Science",
    date: "2026-05-27",
    readingMinutes: 10,
    status: "forthcoming",
  },
  {
    slug: "additive-never-destructive",
    title: "Additive, never destructive — across 39 evidence layers",
    dek: "Every existing endpoint and regression test must stay green as new layers land. Here's how the typed-Pydantic contract makes that affordable.",
    claim:
      "Layer 22 (proton/carbon-13 scoring) and Layer 39 (LCMS feature grouping) speak the same API style. Stable JSON keys, additive fields, openapi-typescript regen on every contract change. The 'never overwrite a prior layer' rule is what lets us ship weekly without breaking last year's dossier.",
    topic: "engineering",
    topicLabel: "Engineering",
    date: "2026-05-15",
    readingMinutes: 12,
    status: "forthcoming",
  },
  {
    slug: "fda-ai-framework-2025",
    title: "Reading the FDA's January 2025 AI framework, in code",
    dek: "Stage-4 human oversight gates aren't a paragraph in a policy; they're a release queue in your audit table.",
    claim:
      "The FDA's 2025 framework formalizes risk-based credibility for AI in regulatory submissions. We mapped each stage onto concrete code: model-card registry, recipe-hash provenance, human-signoff queue, immutable raw vault. The PRs are linkable; the audit ledger is queryable.",
    topic: "regulatory",
    topicLabel: "Regulatory",
    date: "2026-05-10",
    readingMinutes: 11,
    status: "forthcoming",
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
