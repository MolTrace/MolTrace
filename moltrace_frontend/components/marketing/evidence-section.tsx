import { Check } from "lucide-react"
import { EvidenceCard } from "./evidence-card"

const features = [
  {
    label: "Confidence scoring",
    desc: "Every interpretation returns a calibrated confidence score with uncertainty bounds.",
  },
  {
    label: "Citation linking",
    desc: "AI reasoning cites spectral databases, literature, and ICH guidelines automatically.",
  },
  {
    label: "Contradiction flags",
    desc: "Automatic detection when evidence conflicts — flagged for human review before sign-off.",
  },
  {
    label: "Full audit trail",
    desc: "Every decision timestamped, attributed, and exportable for regulatory inspection.",
  },
]

export function EvidenceSection() {
  return (
    <section className="border-y bg-muted/30 py-24" id="solutions">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center lg:gap-20">

          {/* Left: copy + feature list */}
          <div>
            <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-teal-500 dark:text-teal-400">
              Evidence-First AI
            </p>
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              Transparent reasoning.<br />
              Traceable decisions.
            </h2>
            <p className="mt-4 text-base leading-relaxed text-muted-foreground">
              No black boxes. Every AI interpretation comes with confidence scores,
              supporting citations, identified contradictions, and a complete audit trail
              designed for GxP environments.
            </p>

            <ul className="mt-8 space-y-5">
              {features.map((f) => (
                <li key={f.label} className="flex gap-4">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-teal-500/30 bg-teal-500/10">
                    <Check className="h-3.5 w-3.5 text-teal-500 dark:text-teal-400" strokeWidth={2.5} />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-foreground">{f.label}</div>
                    <div className="mt-0.5 text-sm leading-relaxed text-muted-foreground">{f.desc}</div>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {/* Right: the same card the hero shows — one copy, so the two can
              never drift into quoting different numbers at each other. */}
          <div className="flex items-center justify-center">
            <EvidenceCard className="w-full max-w-md overflow-hidden" />
          </div>

        </div>
      </div>
    </section>
  )
}
