"use client"

// Command centre — latest golden-path arc.
//
// Reads the run's `metadata_json` record of what the arc ACTUALLY did, not the
// run's `steps[]`. The only route that creates a pilot run writes every step as
// `succeeded` regardless of what happened, so counting those would show five
// green steps for an arc that never executed. A run with no client-executed
// record therefore reports "not recorded" — unknown is a state, and it is not
// the same state as passed.

import { useEffect, useState } from "react"
import Link from "next/link"
import { AlertTriangle, ArrowRight, CheckCircle2, CircleDashed, ExternalLink, Route, XCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { statusLabel } from "@/lib/ui/status"
import {
  GOLDEN_PATH_STEPS,
  actionItemResourceHref,
  formatElapsed,
  listActionItems,
  listEvidenceBundles,
  listPilotRuns,
  readRecordedArc,
  type CrossModuleActionItem,
  type PilotEvidenceBundle,
  type PilotRunDetail,
  type RecordedArc,
  type StepStatus,
} from "@/lib/pilot/golden-path"

export const GOLDEN_PATH_HREF = "/pilot/golden-path"

const STEP_ICON: Record<StepStatus, { className: string; Icon: typeof CheckCircle2 }> = {
  pending: { className: "text-muted-foreground", Icon: CircleDashed },
  running: { className: "text-sky-600 dark:text-sky-400", Icon: CircleDashed },
  succeeded: { className: "text-emerald-600 dark:text-emerald-400", Icon: CheckCircle2 },
  requires_review: { className: "text-amber-600 dark:text-amber-400", Icon: AlertTriangle },
  failed: { className: "text-red-600 dark:text-red-400", Icon: XCircle },
}

function stepTitle(key: string): string {
  return GOLDEN_PATH_STEPS.find((s) => s.key === key)?.title ?? key
}

function StepRail({ arc }: { arc: RecordedArc }) {
  return (
    <ol className="space-y-1.5">
      {arc.steps.map((step, i) => {
        const presentation = STEP_ICON[step.status]
        const Icon = presentation.Icon
        return (
          <li key={`${step.step}-${i}`} className="flex items-center gap-2 text-sm">
            <Icon className={cn("h-3.5 w-3.5 shrink-0", presentation.className)} aria-hidden />
            <span className="min-w-0 flex-1 truncate">{stepTitle(step.step)}</span>
            <span className={cn("shrink-0 text-xs", presentation.className)}>
              {statusLabel(step.status)}
            </span>
            <span className="w-16 shrink-0 text-right text-xs text-muted-foreground tabular-nums">
              {formatElapsed(step.elapsedMs)}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

export function GoldenPathCard() {
  const [run, setRun] = useState<PilotRunDetail | null>(null)
  const [arc, setArc] = useState<RecordedArc | null>(null)
  const [bundle, setBundle] = useState<PilotEvidenceBundle | null>(null)
  const [items, setItems] = useState<CrossModuleActionItem[]>([])
  const [loading, setLoading] = useState(true)
  const [unavailable, setUnavailable] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const runs = await listPilotRuns(5)
        if (cancelled) return
        // Prefer the most recent run that carries a real executed record.
        const withArc = runs.map((r) => ({ run: r, arc: readRecordedArc(r) }))
        const chosen = withArc.find((r) => r.arc != null) ?? withArc[0] ?? null
        setRun(chosen?.run ?? null)
        setArc(chosen?.arc ?? null)
        if (chosen?.run) {
          try {
            const bundles = await listEvidenceBundles(chosen.run.id)
            if (!cancelled) setBundle(bundles[0] ?? null)
          } catch {
            if (!cancelled) setBundle(null)
          }
        }
        try {
          const actionItems = await listActionItems(5)
          if (!cancelled) setItems(actionItems)
        } catch {
          if (!cancelled) setItems([])
        }
      } catch {
        if (!cancelled) setUnavailable(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3">
          <Route className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <div className="min-w-0 flex-1">
            <CardTitle className="text-base">Golden path</CardTitle>
            <CardDescription>
              The most recent end-to-end arc: raw FID through to a dossier with its provenance.
            </CardDescription>
          </div>
          <Link
            href={GOLDEN_PATH_HREF}
            className="shrink-0 text-xs underline underline-offset-4 hover:text-foreground"
          >
            Open
          </Link>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : unavailable || run == null ? (
          <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
            No arc has been run in this workspace yet.{" "}
            <Link href={GOLDEN_PATH_HREF} className="underline underline-offset-4">
              Run the golden path
            </Link>{" "}
            to record one.
          </p>
        ) : arc == null ? (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
            The latest run record does not carry an executed arc, so its step outcomes are not known.
            Run the arc from the golden-path page to record one.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="outline">{run.run_label}</Badge>
              {arc.totalElapsedMs != null ? (
                <span className="text-muted-foreground tabular-nums">
                  {formatElapsed(arc.totalElapsedMs)} measured
                </span>
              ) : null}
            </div>
            <StepRail arc={arc} />
          </>
        )}

        {items.length > 0 ? (
          <div className="border-t pt-3">
            <div className="mb-2 text-xs text-muted-foreground">Cross-module handoffs</div>
            <ul className="space-y-1.5">
              {items.slice(0, 3).map((item) => {
                const href =
                  actionItemResourceHref(item.target_resource_type, item.target_resource_id) ??
                  actionItemResourceHref(item.source_resource_type, item.source_resource_id)
                return (
                  <li key={item.id} className="flex items-center gap-2 text-xs">
                    <Badge variant="secondary" className="shrink-0 text-[10px]">
                      {statusLabel(item.source_program)}
                    </Badge>
                    <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden />
                    <Badge variant="secondary" className="shrink-0 text-[10px]">
                      {statusLabel(item.target_program)}
                    </Badge>
                    {href ? (
                      <Link href={href} className="min-w-0 flex-1 truncate underline underline-offset-4">
                        {item.title}
                      </Link>
                    ) : (
                      <span className="min-w-0 flex-1 truncate">{item.title}</span>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        ) : null}

        {bundle ? (
          <div className="border-t pt-3 text-xs">
            <span className="text-muted-foreground">Evidence bundle: </span>
            <Link
              href={GOLDEN_PATH_HREF}
              className="inline-flex items-center gap-1 underline underline-offset-4"
            >
              {bundle.title}
              <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
            </Link>
            <Badge variant="outline" className="ml-2 text-[10px]">
              {statusLabel(bundle.status)}
            </Badge>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
