import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ArrowRight, ArrowUpRight, FileSignature, FlaskConical, ShieldCheck, Waves } from "lucide-react"
import Link from "next/link"
import { HeroMoleculeLayer } from "./hero-molecule-layer"
import { EvidenceCard } from "./evidence-card"

/**
 * The four beats of the arc, each wearing the colour it wears inside the app so
 * the name a reader meets here is the one they recognise once they are in it.
 *
 * These were four lines of plain text; they are cards now, and the reason that
 * is worth the pixels is that all four destinations already exist. The row used
 * to name four products and offer no way to reach any of them.
 *
 * `accent` is the vivid token — it fills the left rule and the icon.
 * `ink` is the AA-safe variant — it colours every piece of type.
 * `soft` is the low-alpha fill behind the pill.
 * Never swap those roles: the vivid tokens sit at 2–3:1 on a light page.
 */
const HERO_MODULES = [
  {
    name: "SpectraCheck",
    tag: "Spectroscopy",
    desc: "Raw spectra → structure evidence",
    href: "/spectroscopy",
    icon: Waves,
    accent: "var(--mt-teal)",
    ink: "var(--mt-teal-ink)",
    soft: "var(--mt-teal-soft)",
  },
  {
    name: "Regentry",
    tag: "Regulatory",
    desc: "Evidence → ICH action items",
    href: "/regulatory-hub",
    icon: ShieldCheck,
    accent: "var(--mt-cyan)",
    ink: "var(--mt-cyan-ink)",
    soft: "var(--mt-cyan-soft)",
  },
  {
    name: "Repho",
    tag: "Reaction",
    desc: "Constraints → optimized reactions",
    href: "/reaction-optimization",
    icon: FlaskConical,
    accent: "var(--mt-violet)",
    ink: "var(--mt-violet-ink)",
    soft: "var(--mt-violet-soft)",
  },
  {
    name: "Report",
    tag: "Dossier",
    desc: "Audit-ready dossier & sign-off",
    href: "/reports",
    icon: FileSignature,
    accent: "var(--mt-amber)",
    ink: "var(--mt-amber-ink)",
    soft: "var(--mt-amber-soft)",
  },
] as const

/**
 * Hero.
 *
 * It used to open with a three-line paragraph, two competing calls to action,
 * and a compliance strip that the very next section repeated verbatim — then
 * described confidence scores, citations and contradiction flags in prose four
 * screens before showing any. The card was the only unfakeable thing on the
 * page and it was fifth.
 *
 * So: one line of subhead, the card itself, one call to action. Show the
 * artifact, do not describe the capability.
 */
export function Hero() {
  return (
    <section className="hero-compat-surface relative overflow-hidden bg-background text-foreground">
      <HeroMoleculeLayer />
      <div className="hero-compat-overlay pointer-events-none absolute inset-0 z-[5]" aria-hidden />
      <div className="relative z-10 mx-auto max-w-7xl px-4 py-20 sm:px-6 sm:py-24 lg:px-8 lg:py-28">
        {/* min-w-0 on both tracks: a grid item defaults to min-width:auto, so the
            card's own content (the formula + status badge row) pushed the track
            wider than the viewport. It was invisible only because the body clips
            overflow — on a phone the right edge of the card, confidence figures
            included, was simply cut off. */}
        <div className="grid gap-12 lg:grid-cols-[1.05fr_minmax(0,26rem)] lg:items-center lg:gap-16">
          <div className="min-w-0">
            {/* Badge is whitespace-nowrap by design (it is built for one-word
                status chips). This one is a sentence, so it has to be allowed to
                wrap or it runs straight off a phone screen. */}
            <Badge
              variant="outline"
              className="mb-6 max-w-full whitespace-normal px-4 py-1.5 text-left text-sm font-medium leading-snug"
            >
              Evidence-first AI for regulated pharma &amp; chemical R&amp;D
            </Badge>
            <h1 className="hero-copy-wrap text-balance text-4xl font-semibold tracking-tight sm:text-5xl lg:text-6xl">
              Analytical evidence you can trace under audit.
            </h1>
            {/* One line. The detail belongs to the card beside it and to the
                sections below, not to a paragraph nobody finishes.

                THIS LINE USED TO READ: "Every result carries its confidence, its
                citations, and its contradictions." It was replaced because it
                promised the opposite of what the product does. `TraceableFigure`
                renders "Not traced — no citation recorded" precisely because
                plenty of results have no citation, and the spec calls that
                absence-is-a-state rule "the whole product claim". A hero that
                promises completeness undersells a product that sells honesty
                about incompleteness — and two of that sentence's three nouns
                (confidence, contradictions) rest on the verifier, which does not
                run in the shipped image. Do not restore it. */}
            <p className="hero-copy-wrap mt-6 max-w-xl text-pretty text-lg text-muted-foreground sm:text-xl">
              Every number shows its trail — or shows that it hasn&apos;t got one.
            </p>
            <div className="mt-10 flex flex-col items-start gap-4 sm:flex-row sm:items-center">
              <Button size="lg" className="min-w-[180px] gap-2" asChild>
                <Link href="/contact?reason=Request%20a%20demo">
                  Request Demo
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Link
                href="#solutions"
                className="text-sm font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
              >
                See how the evidence trail works
              </Link>
            </div>

          </div>

          {/* The artifact, above the fold. */}
          <div className="min-w-0 lg:justify-self-end">
            <EvidenceCard className="w-full max-w-full overflow-hidden shadow-xl" />
            <p className="mt-3 text-center text-[11px] text-muted-foreground lg:text-right">
              Illustrative example of a MolTrace result — not a measured sample.
            </p>
          </div>
        </div>

        {/* The four beats, each in the colour it wears inside the app, so the name
            a reader meets here is the one they recognise once they are in it.
            This replaced a separate 4-step strip that told the same story again —
            and called two of the products by names they no longer use.

            It sits in its own full-width row rather than inside the copy column
            on purpose: nested in the column it stacked ABOVE the card on a phone,
            which put the one artifact worth showing about two and a half screens
            down and undid the reason for the rewrite. */}
        <div className="hero-stat-grid mt-16 grid grid-cols-1 gap-5 border-t pt-10 sm:grid-cols-2 lg:mt-20 lg:grid-cols-4">
          {HERO_MODULES.map((m) => (
            <Link
              key={m.name}
              href={m.href}
              className="group relative block h-full min-w-0 rounded-xl border bg-card p-6 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none motion-reduce:hover:translate-y-0"
              /* The 3px left rule is the whole signature of this card: it is what
                 carries the module's colour without tinting any text. The `border`
                 class sets 1px on all four sides and this overrides the left. */
              style={{ borderLeftWidth: "3px", borderLeftColor: m.accent }}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  {/* Icons keep the vivid accent — they are shapes, not type, so
                      the AA rule that pushes text to the ink tokens does not
                      apply to them. */}
                  <m.icon className="h-6 w-6 shrink-0" style={{ color: m.accent }} aria-hidden />
                  <h3 className="truncate text-base font-semibold" style={{ color: m.ink }}>
                    {m.name}
                  </h3>
                </div>
                <ArrowUpRight
                  className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 motion-reduce:transition-none"
                  aria-hidden
                />
              </div>

              {/* The reference prints this pill in the raw accent. On a light page
                  that is 2–3:1 and fails AA at 11px, so the fill uses the -soft
                  token and the text the -ink token. Same look, readable. */}
              <span
                className="mt-2.5 inline-block rounded-full px-2 py-0.5 text-[11px] font-medium"
                style={{ backgroundColor: m.soft, color: m.ink }}
              >
                {m.tag}
              </span>

              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{m.desc}</p>
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}
