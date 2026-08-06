import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ArrowRight } from "lucide-react"
import Link from "next/link"
import { HeroMoleculeLayer } from "./hero-molecule-layer"
import { EvidenceCard } from "./evidence-card"

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
                sections below, not to a paragraph nobody finishes. */}
            <p className="hero-copy-wrap mt-6 max-w-xl text-pretty text-lg text-muted-foreground sm:text-xl">
              Every result carries its confidence, its citations, and its contradictions.
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
        <div className="hero-stat-grid mt-16 grid grid-cols-2 gap-x-8 gap-y-6 border-t pt-8 sm:grid-cols-4 lg:mt-20">
          {[
            { value: "SpectraCheck", label: "Raw spectra → structure evidence", ink: "var(--mt-teal-ink)" },
            { value: "Regentry", label: "Evidence → ICH action items", ink: "var(--mt-cyan-ink)" },
            { value: "Repho", label: "Constraints → optimized reactions", ink: "var(--mt-violet-ink)" },
            { value: "Report", label: "Audit-ready dossier & sign-off", ink: "var(--mt-amber-ink)" },
          ].map((stat) => (
            <div key={stat.label} className="min-w-0">
              {/* The "ink" variants, never the vivid accents: the bright tokens
                  are tuned for fills and icons and fail AA as type on a light
                  page. */}
              <div className="text-lg font-semibold tracking-tight" style={{ color: stat.ink }}>
                {stat.value}
              </div>
              <div className="mt-1 text-xs leading-relaxed text-muted-foreground">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
