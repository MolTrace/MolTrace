import Link from "next/link"
import { ArrowRight, Bell, BookOpen, Clock, FileText, Mail, Rss } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"
import { BlogPostsGrid } from "@/components/marketing/blog-posts-grid"
import { POSTS } from "@/lib/blog/posts"

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
            {/* Cover-first layout: the artwork owns one half at full bleed and
                the type is sized to carry the other. The one-paragraph `claim`
                is deliberately NOT repeated here — every point it makes is made
                again in the essay body, so the card leads with the headline and
                the figure and sends the reader onward. `claim` still drives the
                non-featured cards in BlogPostsGrid. */}
            <article
              className="mt-6 overflow-hidden rounded-3xl border bg-card shadow-sm"
              style={{ borderTop: "3px solid var(--mt-teal)" }}
            >
              {/* Only the headline block sits beside the cover. The figure and
                  the byline moved to a full-width band below, which is what
                  keeps this row short enough for the cover to run near its own
                  1.9:1 — the whole frame survives, magnet AND the gloved hand.
                  With the figure still in this column the row ran ~860px tall,
                  the cover was squeezed to a 44%-wide slice, and the hand — the
                  "we" in "why we count" — was the first thing cropped out. */}
              <div className={featured.heroImage ? "grid lg:grid-cols-[1.25fr_1fr]" : ""}>
              {featured.heroImage ? (
                <div className="relative min-h-[240px] sm:min-h-[320px]">
                  <img
                    src={featured.heroImage}
                    alt={featured.heroImageAlt ?? ""}
                    className="absolute inset-0 h-full w-full object-cover"
                    // Right-of-centre: whatever the row's height costs us comes
                    // off the left, where there is only the equipment rack.
                    style={{ objectPosition: "62% 45%" }}
                    loading="lazy"
                    decoding="async"
                  />
                  <span className="absolute left-5 top-5 inline-flex items-center rounded-full bg-black/55 px-3 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-white backdrop-blur-sm">
                    {featured.topicLabel}
                  </span>
                </div>
              ) : null}

              <div className="flex flex-col justify-center gap-5 p-7 sm:p-10 lg:p-12">
                <div>
                  <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5" aria-hidden />
                      {featured.readingMinutes} min read
                    </span>
                    <span aria-hidden>•</span>
                    <span className="font-mono tabular-nums">{featured.date}</span>
                    {featured.heroImage ? null : (
                      <span className="inline-flex items-center rounded-full border bg-violet-50 px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-violet-700 dark:border-violet-900 dark:bg-violet-950/40 dark:text-violet-300">
                        {featured.topicLabel}
                      </span>
                    )}
                    {featured.status === "forthcoming" ? (
                      <span className="inline-flex items-center rounded-full border border-dashed px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                        Forthcoming
                      </span>
                    ) : null}
                  </div>

                  {/* The card's anchor: heavy, tight-leading, underlined in
                      brand teal. Sized in rem rather than a type step so it can
                      run larger than anything else on the page without
                      disturbing the scale the rest of the index uses. */}
                  <h2 className="mt-5 text-[2.1rem] font-bold leading-[1.06] tracking-tight sm:text-[2.7rem] lg:text-[3.1rem]">
                    {featured.status === "live" ? (
                      <Link
                        href={`/blog/${featured.slug}`}
                        className="underline decoration-[3px] underline-offset-[7px] transition-opacity hover:opacity-80"
                        style={{ textDecorationColor: "var(--mt-teal)" }}
                      >
                        {featured.title}
                      </Link>
                    ) : (
                      featured.title
                    )}
                  </h2>

                  <p className="mt-5 text-lg leading-relaxed text-muted-foreground">
                    {featured.dek}
                  </p>
                </div>
              </div>
              </div>

              {/* Full-width band: the figure the essay turns on, and the way in.
                  17 is measured; 2 is what the strict gate asks for — the label
                  and the wording keep those two apart rather than implying a
                  result. */}
              <div className="grid gap-6 border-t p-7 sm:p-10 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center lg:gap-10 lg:p-12">
                <div className="relative overflow-hidden rounded-2xl border bg-muted/30 p-5 sm:p-6">
                  <div aria-hidden className="scientific-grid-subtle absolute inset-0 opacity-30" />
                  <div className="relative flex flex-wrap items-baseline gap-x-6 gap-y-2">
                    <p
                      className="font-mono text-4xl font-bold tabular-nums tracking-tight sm:text-5xl"
                      style={{ color: "var(--mt-teal-ink)" }}
                    >
                      Δ=17 → Δ=2
                    </p>
                    <div className="min-w-[16rem] flex-1">
                      <p
                        className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                        style={{ color: "var(--mt-teal-ink)" }}
                      >
                        Illustrative — sample figures
                      </p>
                      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                        Median absolute peak-count delta against the NMRShiftDB2 reference, set
                        against the ≤2 the strict gate asks for.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-4 lg:flex-col lg:items-end">
                  <div className="flex items-center gap-3">
                    <span
                      aria-hidden
                      className="flex h-9 w-9 items-center justify-center rounded-full border font-mono text-xs font-bold"
                      style={{ color: "var(--mt-teal-ink)" }}
                    >
                      M
                    </span>
                    <span className="whitespace-nowrap text-sm text-muted-foreground">
                      MolTrace research team
                    </span>
                  </div>
                  {featured.status === "live" ? (
                    <Button asChild size="lg" className="gap-2 rounded-full px-6">
                      <Link href={`/blog/${featured.slug}`}>
                        Read the essay
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  ) : null}
                </div>
              </div>
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
                No tracking pixels · Unsubscribe in one click · Designed to support GDPR-aligned data handling
              </p>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  )
}
