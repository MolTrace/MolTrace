"use client"

// Golden Path — the ROI strip.
//
// One rule, and it is the whole reason this component is separate:
//
//   The COUNTS are measured. The HOURS are not.
//
// `total_hours_saved` is Σ(events × a hardcoded per-task constant). The ORM
// column is named `estimated_minutes_saved`; the API model drops the qualifier
// on the way out, so the qualifier has to be put back here. A pharma buyer who
// discovers the "measured" hours were an assumption table will discount every
// other number on the page — including the ones that are real.
//
// The arc's own wall-clock is shown alongside because it IS measured, and it is
// the honest version of the claim the hours figure is reaching for.

import Link from "next/link"
import { Clock, Timer } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import {
  AUTOMATION_TASK_SETTINGS_HREF,
  ESTIMATED_HOURS_BASIS,
  ESTIMATED_HOURS_QUALIFIER,
  formatElapsed,
  type RoiSplit,
} from "@/lib/pilot/golden-path"

function fmtCount(n: number | null | undefined): string {
  // A missing snapshot is "no data", never 0.
  if (n == null || !Number.isFinite(n)) return "—"
  return n.toLocaleString()
}

function fmtHours(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return "—"
  return n.toLocaleString(undefined, { maximumFractionDigits: 1 })
}

export function GoldenPathRoiStrip({ split, loading = false }: { split: RoiSplit; loading?: boolean }) {
  const hasSnapshot = split.dataMode != null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Value recorded for this workspace</CardTitle>
        <CardDescription>
          Event counts are measured. The time-saved figure is an estimate built from your own task
          assumptions, and is labelled as one.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Warnings sit ABOVE the figures they qualify. */}
        {split.warnings.length > 0 ? (
          <ul className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs">
            {split.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2">
          {/* Measured: the arc's own clock. */}
          <div className="rounded-lg border p-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Timer className="h-3.5 w-3.5 shrink-0" aria-hidden />
              <span>Arc elapsed time</span>
              <Badge variant="outline" className="ml-auto text-[10px] uppercase">
                Measured
              </Badge>
            </div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">
              {loading ? "…" : formatElapsed(split.measuredArcElapsedMs)}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Wall-clock across the steps that ran, timed by this page.
            </p>
          </div>

          {/* Estimated: the hours figure, never presented as measured. */}
          <div className="rounded-lg border p-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Clock className="h-3.5 w-3.5 shrink-0" aria-hidden />
              <span>Time saved</span>
              <InfoTooltip content={ESTIMATED_HOURS_BASIS} label="How time saved is calculated" />
              <Badge variant="outline" className="ml-auto text-[10px] uppercase">
                {ESTIMATED_HOURS_QUALIFIER}
              </Badge>
            </div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">
              {loading ? "…" : `${fmtHours(split.estimatedHoursSaved)} h`}
              <span className="ml-2 align-middle text-xs font-normal text-muted-foreground">
                ({ESTIMATED_HOURS_QUALIFIER.toLowerCase()})
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Each completed task contributes a fixed constant.{" "}
              <Link
                href={AUTOMATION_TASK_SETTINGS_HREF}
                className="underline underline-offset-4 hover:text-foreground"
              >
                Review the per-task assumptions
              </Link>
              .
            </p>
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
            <span>Recorded activity</span>
            <Badge variant="outline" className="text-[10px] uppercase">
              Measured
            </Badge>
          </div>
          {hasSnapshot ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
              {split.measuredCounts.map((c) => (
                <div key={c.key} className="rounded-md border bg-muted/20 p-2">
                  <dt className="text-[11px] text-muted-foreground">{c.label}</dt>
                  <dd className="text-lg font-semibold tabular-nums">{loading ? "…" : fmtCount(c.value)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
              {loading
                ? "Loading recorded activity…"
                : "No activity snapshot is available for this workspace yet."}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
