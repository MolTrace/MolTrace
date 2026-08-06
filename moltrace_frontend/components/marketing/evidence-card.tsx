import { Card, CardContent } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { AlertTriangle } from "lucide-react"

/**
 * The structure-candidate card — the one thing on this site that nothing else in
 * the category shows, and the reason it now sits in the hero rather than four
 * scrolls down. It is not a feature list about confidence and citations; it is
 * those things doing their job, including disagreeing with themselves.
 *
 * Extracted so the hero and the evidence section render the SAME card. Two
 * hand-maintained copies of a number like 87.3% is how a marketing page ends up
 * contradicting itself.
 *
 * Every figure here is illustrative. It is a worked example of the output shape,
 * not a result MolTrace produced — the caption says so, and must keep saying so.
 */

const evidenceRows = [
  { label: "NMR Match", value: 92 },
  { label: "MS/MS Fit", value: 89 },
  { label: "LC-MS Family", value: 78 },
  { label: "Literature", value: 94 },
]

const citations = ["SDBS Database Entry #12847", "J. Org. Chem. 2023, 88, 4521–4539"]

export function EvidenceCard({ className }: { className?: string }) {
  return (
    <Card className={className}>
      <div className="flex flex-wrap items-start justify-between gap-2 border-b px-5 py-4">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
            Structure Candidate #1
          </p>
          <p className="mt-1 font-mono text-sm font-bold text-foreground">
            C<sub>12</sub>H<sub>16</sub>N<sub>2</sub>O<sub>3</sub>&nbsp;&nbsp;MW 236.27
          </p>
        </div>
        <span
          className="rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest"
          style={{ borderColor: "var(--mt-amber)", color: "var(--mt-amber-ink)" }}
        >
          Requires Review
        </span>
      </div>

      <CardContent className="space-y-5 px-5 py-5">
        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
              Overall Confidence
            </span>
            <span className="font-mono text-2xl font-bold" style={{ color: "var(--mt-teal-ink)" }}>
              87.3%
            </span>
          </div>
          <Progress value={87.3} className="h-1.5" />
        </div>

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
                    className="h-full rounded-full"
                    style={{ width: `${row.value}%`, backgroundColor: "var(--mt-teal)" }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* The contradiction is the point of the whole card: a system that only
            ever agrees with itself is not evidence, it is assertion. */}
        <div
          className="flex gap-3 rounded-lg border p-3"
          style={{ borderColor: "var(--mt-amber)", backgroundColor: "var(--mt-amber-soft)" }}
        >
          <AlertTriangle
            className="mt-0.5 h-4 w-4 shrink-0"
            style={{ color: "var(--mt-amber)" }}
            aria-hidden
          />
          <p className="text-xs leading-relaxed" style={{ color: "var(--mt-amber-ink)" }}>
            Expected <sup>13</sup>C peak at 142 ppm not observed in spectrum
          </p>
        </div>

        <div>
          <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
            Citations
          </p>
          <div className="space-y-1.5">
            {citations.map((cite) => (
              <p
                key={cite}
                className="font-mono text-[11px] underline decoration-dotted underline-offset-2"
                style={{ color: "var(--mt-cyan-ink)" }}
              >
                {cite}
              </p>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
