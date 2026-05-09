import { Card, CardContent } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Check, AlertTriangle } from "lucide-react"

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

const evidenceRows = [
  { label: "NMR Match",    value: 92 },
  { label: "MS/MS Fit",    value: 89 },
  { label: "LC-MS Family", value: 78 },
  { label: "Literature",   value: 94 },
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

          {/* Right: evidence card mockup */}
          <div className="flex items-center justify-center">
            <Card className="w-full max-w-md overflow-hidden">

              {/* Card header */}
              <div className="flex items-start justify-between border-b px-5 py-4">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                    Structure Candidate #1
                  </p>
                  <p className="mt-1 font-mono text-sm font-bold text-foreground">
                    C<sub>12</sub>H<sub>16</sub>N<sub>2</sub>O<sub>3</sub>
                    &nbsp;&nbsp;MW 236.27
                  </p>
                </div>
                <span className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-amber-600 dark:text-amber-400">
                  Requires Review
                </span>
              </div>

              <CardContent className="space-y-5 px-5 py-5">

                {/* Overall confidence */}
                <div>
                  <div className="mb-2 flex items-baseline justify-between">
                    <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                      Overall Confidence
                    </span>
                    <span className="font-mono text-2xl font-bold text-teal-500 dark:text-teal-400">
                      87.3%
                    </span>
                  </div>
                  <Progress value={87.3} className="h-1.5" />
                </div>

                {/* Evidence breakdown — stacked rows */}
                <div>
                  <p className="mb-3 text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                    Evidence Breakdown
                  </p>
                  <div className="space-y-2.5">
                    {evidenceRows.map((row) => (
                      <div key={row.label}>
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="text-muted-foreground">{row.label}</span>
                          <span className="font-mono font-semibold text-foreground">{row.value}%</span>
                        </div>
                        <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-teal-500/70 dark:bg-teal-400/70"
                            style={{ width: `${row.value}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Contradiction */}
                <div className="flex gap-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500 dark:text-amber-400" />
                  <p className="text-xs leading-relaxed text-amber-700 dark:text-amber-300">
                    Expected <sup>13</sup>C peak at 142 ppm not observed in spectrum
                  </p>
                </div>

                {/* Citations */}
                <div>
                  <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                    Citations
                  </p>
                  <div className="space-y-1.5">
                    {[
                      "SDBS Database Entry #12847",
                      "J. Org. Chem. 2023, 88, 4521–4539",
                    ].map((cite) => (
                      <p
                        key={cite}
                        className="cursor-pointer font-mono text-[11px] text-cyan-600 underline decoration-dotted underline-offset-2 dark:text-cyan-400"
                      >
                        {cite}
                      </p>
                    ))}
                  </div>
                </div>

              </CardContent>
            </Card>
          </div>

        </div>
      </div>
    </section>
  )
}
