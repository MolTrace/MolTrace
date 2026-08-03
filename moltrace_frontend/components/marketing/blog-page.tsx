import Link from "next/link"
import { ArrowRight, Bell, BookOpen, FileText, Mail, Rss } from "lucide-react"
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
            <article
              className="mt-6 grid gap-10 rounded-3xl border bg-card p-6 shadow-sm sm:p-10 lg:grid-cols-[1.4fr_1fr]"
              style={{ borderTop: "3px solid var(--mt-teal)" }}
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center rounded-full border bg-violet-50 px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-violet-700 dark:bg-violet-950/40 dark:text-violet-300 border-violet-200 dark:border-violet-900">
                    {featured.topicLabel}
                  </span>
                  {featured.status === "forthcoming" ? (
                    <span className="inline-flex items-center rounded-full border border-dashed px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                      Forthcoming
                    </span>
                  ) : null}
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
                {featured.status === "live" ? (
                  <div className="mt-8">
                    <Button asChild size="lg" className="gap-2">
                      <Link href={`/blog/${featured.slug}`}>
                        Read the essay
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  </div>
                ) : null}
              </div>

              {/* Visual flank — the essay's own hero artwork once it has one,
                  falling back to the scientific-grid metric plate for essays
                  that don't. The SVG is used here rather than the PNG twin:
                  it stays crisp at any width and costs a fraction as much.
                  Width/height are set so the space is reserved before the
                  image loads and the card doesn't shift under it. */}
              {featured.heroImage ? (
                // self-start, and no object-cover: the grid stretches this column
                // to the height of the essay text beside it, so a 1200x630 hero
                // forced to fill it was cropped to a near-square centre slice —
                // losing the headline and the figures the artwork exists to show.
                // Letting it keep its own aspect ratio shows the whole thing.
                <aside className="relative self-start overflow-hidden rounded-2xl border bg-muted/30">
                  <img
                    src={`${featured.heroImage}.svg`}
                    alt={featured.heroImageAlt ?? ""}
                    width={1200}
                    height={630}
                    className="h-auto w-full"
                    loading="lazy"
                    decoding="async"
                  />
                </aside>
              ) : (
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
                    Illustrative — sample figures
                  </p>
                  <p
                    className="mt-4 font-mono text-5xl font-bold tabular-nums tracking-tight sm:text-6xl"
                    style={{ color: "var(--mt-teal-ink)" }}
                  >
                    Δ=17 → Δ=2
                  </p>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                    Example of the median absolute peak-count delta the multiplet-clustering layer is
                    designed to reduce against the NMRShiftDB2 corpus.
                  </p>
                  <p className="mt-6 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    Strict gate target: ≤2
                  </p>
                </div>
              </aside>
              )}
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
