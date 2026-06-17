import Link from "next/link"
import { ArrowRight, Bell, BookOpen, FileText, Mail, Rss } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"
import { BlogPostsGrid, type BlogPost } from "@/components/marketing/blog-posts-grid"

/**
 * Blog (editorial index) — full marketing-shell route at /blog.
 *
 * Tone-and-stance differentiators:
 *   1. Editorial framing ("Field notes") rather than generic "Blog."
 *   2. Each post card carries a one-paragraph CLAIM — the page is
 *      readable as an editorial index even before any post is live.
 *   3. Topic filter pills (client component) — real interactivity.
 *   4. Forthcoming-vs-live status badged honestly. Cards with
 *      `status: "forthcoming"` show "Subscribe for drop" instead of a
 *      bogus link.
 *   5. Featured essay above the fold with the full claim spelled out.
 *
 * Post content is grounded in real Phase 10-24 work documented in the
 * validation harness + white papers. When an essay is published, swap
 * `status: "forthcoming"` for `status: "live"` and add an `href`.
 */

// Curated editorial calendar. Each post reflects real work that's
// documented in the codebase + white papers. Update as essays ship.
const POSTS: BlogPost[] = [
  {
    slug: "chemical-environments-not-peaks",
    title: "Why we count chemical environments, not peaks",
    dek: "The expert-reference vs detector-output mismatch that nearly broke our promotion gate — and the clustering layer that fixed it.",
    claim:
      "NMRShiftDB2 references count distinct chemical environments; detectors faithfully resolve multiplet lines. Median peak-count deltas of 17 looked like an algorithm failure; they were a units mismatch. Field notes from the Phase 10 multiplet-clustering work.",
    topic: "methodology",
    topicLabel: "Methodology",
    date: "2026-05-27",
    readingMinutes: 9,
    status: "forthcoming",
  },
  {
    slug: "regression-by-fixture-id",
    title: "A regression test that fails by fixture_id",
    dek: "How a 20-fixture A/B JSON sidecar replaced our 'looks-good-to-me' detector reviews.",
    claim:
      "Every detector change runs against a curated NMRShiftDB2 corpus before merge. CI fails by name when any single fixture drifts >50% — so reviewers see 'nmrshiftdb2_60000006_13c regressed' instead of 'tests passed (with notes).' The boring infrastructure that quietly raised our ship velocity.",
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
      "GSD-Prompt-3 shipped as `experimental: true` with a documented gate (95% solvent detect, median compound-count delta ≤2). Until both clear, the default stays legacy. Most AI startups ship and patch; we publish the corpus, the threshold, and the date a feature crosses each one.",
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

// Featured (top-of-page) essay — most timely + highest-claim of the set.
const FEATURED_SLUG = "chemical-environments-not-peaks"
const featured = POSTS.find((p) => p.slug === FEATURED_SLUG) ?? POSTS[0]
const remaining = POSTS.filter((p) => p.slug !== featured.slug)

const STREAMS = [
  {
    icon: BookOpen,
    name: "Science",
    body: "Methodology essays, validation deep-dives, and notes from the analytical team.",
  },
  {
    icon: FileText,
    name: "Engineering",
    body: "Architecture decisions, contract design, perf wins, and the instrumentation under the hood.",
  },
  {
    icon: Rss,
    name: "Methodology",
    body: "How we measure ourselves. Promotion gates, regression-corpus design, and what 'experimental' really means.",
  },
]

export function BlogPage() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main>
        {/* ── Hero ────────────────────────────────────────────────────────── */}
        <section className="relative overflow-hidden border-b">
          <div
            aria-hidden
            className="absolute inset-x-0 top-0 h-px"
            style={{
              background:
                "linear-gradient(90deg, transparent 0%, var(--mt-teal) 25%, var(--mt-teal) 75%, transparent 100%)",
              opacity: 0.5,
            }}
          />
          <div aria-hidden className="scientific-grid-subtle absolute inset-0 opacity-30" />
          <div className="relative mx-auto max-w-7xl px-5 py-20 sm:px-6 lg:px-8 lg:py-24">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal-ink)" }}
            >
              Field notes
            </p>
            <h1 className="mt-3 max-w-4xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
              The work, written down{" "}
              <span style={{ color: "var(--mt-teal-ink)" }}>as we ship it</span>.
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
              Methodology essays, architecture decisions, validation deep-dives, and the regulatory
              context behind the design choices. Curated by the MolTrace team — written for analysts,
              engineers, and regulatory reviewers who want the actual reasoning.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Button asChild size="lg" className="gap-2">
                <Link href="#subscribe">
                  Subscribe
                  <Bell className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="gap-2">
                <Link href="/about">
                  About MolTrace
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          </div>
        </section>

        {/* ── Featured essay ─────────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-20">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Featured essay
            </p>
            <article
              className="mt-6 grid gap-10 rounded-3xl border bg-card p-6 shadow-sm sm:p-10 lg:grid-cols-[1.4fr_1fr]"
              style={{ borderTop: "3px solid var(--mt-teal)" }}
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center rounded-full border bg-violet-50 px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-violet-700 dark:bg-violet-950/40 dark:text-violet-300 border-violet-200 dark:border-violet-900">
                    {featured.topicLabel}
                  </span>
                  <span className="inline-flex items-center rounded-full border border-dashed px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                    Forthcoming
                  </span>
                </div>
                <h2 className="mt-5 text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
                  {featured.title}
                </h2>
                <p className="mt-4 text-lg font-medium leading-relaxed text-foreground/85 sm:text-xl">
                  {featured.dek}
                </p>
                <p className="mt-5 text-base leading-relaxed text-muted-foreground">
                  {featured.claim}
                </p>
                <div className="mt-6 flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                  <span className="font-mono tabular-nums">{featured.date}</span>
                  <span aria-hidden>·</span>
                  <span>{featured.readingMinutes} min read</span>
                  <span aria-hidden>·</span>
                  <span>MolTrace research team</span>
                </div>
              </div>

              {/* Visual flank — scientific-grid plate with the essay's key
                  metric called out, so the featured card has its own
                  visual anchor even before a hero image exists. */}
              <aside className="relative overflow-hidden rounded-2xl border bg-muted/30 p-6">
                <div
                  aria-hidden
                  className="scientific-grid-subtle absolute inset-0 opacity-30"
                />
                <div className="relative">
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                    style={{ color: "var(--mt-teal-ink)" }}
                  >
                    Key finding
                  </p>
                  <p
                    className="mt-4 font-mono text-5xl font-bold tabular-nums tracking-tight sm:text-6xl"
                    style={{ color: "var(--mt-teal-ink)" }}
                  >
                    Δ=17 → Δ=2
                  </p>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                    Median absolute peak-count delta against the NMRShiftDB2 corpus before vs. after
                    the multiplet-clustering layer landed.
                  </p>
                  <p className="mt-6 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    Strict gate target: ≤2
                  </p>
                </div>
              </aside>
            </article>
          </div>
        </section>

        {/* ── Editorial streams + posts ──────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-20">
            <div className="grid gap-10 lg:grid-cols-[1fr_2fr]">
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal-ink)" }}
                >
                  Editorial streams
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  Three streams, one editorial standard.
                </h2>
                <p className="mt-4 text-base text-muted-foreground">
                  We publish across science, engineering, and methodology — each stream has its own
                  audience but shares the same rigor.
                </p>
                <ul className="mt-8 space-y-5">
                  {STREAMS.map((s) => {
                    const Icon = s.icon
                    return (
                      <li key={s.name} className="flex gap-3.5">
                        <Icon
                          className="mt-0.5 h-5 w-5 shrink-0"
                          style={{ color: "var(--mt-teal)" }}
                          aria-hidden
                        />
                        <div>
                          <p className="font-semibold tracking-tight">{s.name}</p>
                          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                            {s.body}
                          </p>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </div>
              <div>
                <BlogPostsGrid posts={remaining} />
              </div>
            </div>
          </div>
        </section>

        {/* ── Subscribe ──────────────────────────────────────────────────── */}
        <section id="subscribe" className="relative overflow-hidden scroll-mt-20">
          <div aria-hidden className="scientific-grid-subtle absolute inset-0 opacity-30" />
          <div className="relative mx-auto max-w-7xl px-5 py-20 sm:px-6 lg:px-8 lg:py-28">
            <div className="mx-auto max-w-2xl text-center">
              <Bell className="mx-auto h-10 w-10" style={{ color: "var(--mt-teal)" }} aria-hidden />
              <h2 className="mt-6 text-3xl font-semibold tracking-tight sm:text-4xl">
                Get each essay as it drops.
              </h2>
              <p className="mt-4 text-base leading-relaxed text-muted-foreground sm:text-lg">
                We publish on a deliberate cadence — methodology essays land on shipping milestones,
                not on a content calendar. No marketing emails, no upsells. Just the writing.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
                <Button asChild size="lg" className="gap-2">
                  <Link href="/contact?reason=Subscribe%20to%20Field%20notes">
                    Subscribe by email
                    <Mail className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="outline" className="gap-2">
                  <Link
                    href="https://docs.moltrace.co/"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Browse documentation
                    <FileText className="h-4 w-4" />
                  </Link>
                </Button>
              </div>
              <p className="mt-8 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                No tracking pixels · Unsubscribe in one click · GDPR-compliant intake
              </p>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  )
}
