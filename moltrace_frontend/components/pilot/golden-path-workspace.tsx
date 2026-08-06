"use client"

// Golden Path — the guided route.
//
// One seeded arc, five real endpoints, each panel showing that endpoint's own
// response and its measured elapsed time. The pilot subsystem is used for what
// it genuinely provides — the frozen inputs, the expected-output contracts, the
// run record and the evidence bundle — and for nothing else. In particular the
// recorder's step summaries are never rendered: see `golden-path.ts`, rule 1.

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  ExternalLink,
  Loader2,
  Play,
  RotateCcw,
  XCircle,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { cn } from "@/lib/utils"
import { statusLabel } from "@/lib/ui/status"
import { GoldenPathContractPanel } from "@/components/pilot/golden-path-contract-panel"
import { GoldenPathRoiStrip } from "@/components/pilot/golden-path-roi-strip"
import { GoldenPathStepResult } from "@/components/pilot/golden-path-step-results"
import {
  actionItemResourceHref,
  fetchRoiSnapshot,
  formatElapsed,
  inputsFromScenario,
  listScenarios,
  missingInputs,
  splitRoi,
  type CrossModuleActionItem,
  type GoldenPathStepOutcome,
  type GoldenPilotScenario,
  type RoiSnapshot,
  type StepStatus,
} from "@/lib/pilot/golden-path"
import { useGoldenPathRun } from "@/lib/pilot/use-golden-path-run"

const STEP_STATUS_PRESENTATION: Record<
  StepStatus,
  { className: string; Icon: typeof CheckCircle2; spin?: boolean }
> = {
  pending: { className: "text-muted-foreground", Icon: CircleDashed },
  running: { className: "text-sky-600 dark:text-sky-400", Icon: Loader2, spin: true },
  succeeded: { className: "text-emerald-600 dark:text-emerald-400", Icon: CheckCircle2 },
  requires_review: { className: "text-amber-600 dark:text-amber-400", Icon: AlertTriangle },
  failed: { className: "text-red-600 dark:text-red-400", Icon: XCircle },
}

function StepCard({
  index,
  title,
  narration,
  outcome,
}: {
  index: number
  title: string
  narration: string
  outcome: GoldenPathStepOutcome
}) {
  const presentation = STEP_STATUS_PRESENTATION[outcome.status]
  const Icon = presentation.Icon
  return (
    <Card className={cn(outcome.status === "running" && "ring-1 ring-sky-500/40")}>
      <CardHeader>
        <div className="flex items-start gap-3">
          <Icon
            className={cn("mt-0.5 h-4 w-4 shrink-0", presentation.className, presentation.spin && "animate-spin")}
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <CardTitle className="text-base">
              <span className="mr-2 text-muted-foreground tabular-nums">{index}.</span>
              {title}
            </CardTitle>
            <CardDescription>{narration}</CardDescription>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <Badge variant="outline" className={cn("text-[10px]", presentation.className)}>
              {statusLabel(outcome.status)}
            </Badge>
            {outcome.elapsedMs != null ? (
              <span className="text-[11px] text-muted-foreground tabular-nums">
                {formatElapsed(outcome.elapsedMs)}
              </span>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {outcome.error ? (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm">{outcome.error}</p>
        ) : outcome.status === "pending" ? (
          <p className="text-sm text-muted-foreground">Not started.</p>
        ) : outcome.status === "running" ? (
          <p className="text-sm text-muted-foreground">Running…</p>
        ) : (
          <GoldenPathStepResult stepKey={outcome.key} payload={outcome.payload} />
        )}
      </CardContent>
    </Card>
  )
}

function HandoffChain({ items }: { items: CrossModuleActionItem[] }) {
  if (items.length === 0) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Cross-module handoffs</CardTitle>
        <CardDescription>
          What carried the work from one module to the next. Each item names the record it points at.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {items.map((item) => {
            const sourceHref = actionItemResourceHref(item.source_resource_type, item.source_resource_id)
            const targetHref = actionItemResourceHref(item.target_resource_type, item.target_resource_id)
            return (
              <li key={item.id} className="rounded-md border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{statusLabel(item.source_program)}</Badge>
                  <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  <Badge variant="secondary">{statusLabel(item.target_program)}</Badge>
                  <span className="font-medium">{item.title}</span>
                  <Badge variant="outline" className="ml-auto text-[10px]">
                    {statusLabel(item.status)}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{item.description}</p>
                {sourceHref || targetHref ? (
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
                    {sourceHref ? (
                      <Link href={sourceHref} className="inline-flex items-center gap-1 underline underline-offset-4">
                        Source record
                        <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
                      </Link>
                    ) : null}
                    {targetHref ? (
                      <Link href={targetHref} className="inline-flex items-center gap-1 underline underline-offset-4">
                        Target record
                        <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
                      </Link>
                    ) : null}
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}

export function GoldenPathWorkspace() {
  const [scenarios, setScenarios] = useState<GoldenPilotScenario[]>([])
  const [scenarioId, setScenarioId] = useState<number | null>(null)
  const [scenarioError, setScenarioError] = useState<string | null>(null)
  const [loadingScenarios, setLoadingScenarios] = useState(true)
  const [roi, setRoi] = useState<RoiSnapshot | null>(null)
  const [roiLoading, setRoiLoading] = useState(true)

  const arc = useGoldenPathRun(scenarioId)

  useEffect(() => {
    let cancelled = false
    listScenarios()
      .then((rows) => {
        if (cancelled) return
        setScenarios(rows)
        setScenarioId((current) => current ?? rows[0]?.id ?? null)
      })
      .catch(() => {
        if (!cancelled) setScenarioError("No seeded scenarios could be loaded for this workspace.")
      })
      .finally(() => {
        if (!cancelled) setLoadingScenarios(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const refreshRoi = useCallback(() => {
    setRoiLoading(true)
    fetchRoiSnapshot()
      .then(setRoi)
      .finally(() => setRoiLoading(false))
  }, [])

  useEffect(() => {
    refreshRoi()
  }, [refreshRoi])

  const scenario = useMemo(
    () => scenarios.find((s) => s.id === scenarioId) ?? null,
    [scenarios, scenarioId],
  )
  const inputs = useMemo(() => inputsFromScenario(scenario), [scenario])
  const missing = useMemo(() => missingInputs(inputs), [inputs])
  const roiSplit = useMemo(() => splitRoi(roi, arc.totalElapsedMs), [roi, arc.totalElapsedMs])
  const hasRun = arc.outcomes.some((o) => o.status !== "pending")

  const onRun = useCallback(async () => {
    await arc.run(inputs)
    refreshRoi()
  }, [arc, inputs, refreshRoi])

  return (
    <div className="space-y-4 p-4">
      <Card>
        <CardHeader>
          <CardTitle>Golden path</CardTitle>
          <CardDescription>
            One seeded arc, run end to end: raw FID through structure evidence, impurity assessment
            and compliant design, into a dossier with its provenance. Every panel below shows the
            result its own step returned.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-56 flex-1">
              <Label htmlFor="golden-path-scenario">Seeded scenario</Label>
              <Select
                value={scenarioId != null ? String(scenarioId) : undefined}
                onValueChange={(v) => setScenarioId(Number(v))}
                disabled={arc.running || scenarios.length === 0}
              >
                <SelectTrigger id="golden-path-scenario" className="mt-1 w-full">
                  <SelectValue placeholder={loadingScenarios ? "Loading…" : "No scenario available"} />
                </SelectTrigger>
                <SelectContent>
                  {scenarios.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button onClick={onRun} disabled={arc.running || scenario == null || missing.length > 0}>
              {arc.running ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Play className="h-4 w-4" aria-hidden />
              )}
              Run the arc
            </Button>
            {hasRun && !arc.running ? (
              <Button variant="outline" onClick={arc.reset}>
                <RotateCcw className="h-4 w-4" aria-hidden />
                Clear
              </Button>
            ) : null}
          </div>

          {scenarioError ? (
            <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
              {scenarioError}
            </p>
          ) : null}

          {scenario && missing.length > 0 ? (
            <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
              This scenario does not pin every frozen input the arc needs: {missing.join(", ")}. Seed
              them on the scenario so the arc replays identically each time.
            </p>
          ) : null}

          {arc.haltedAt ? (
            <p className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm">
              The arc stopped at step{" "}
              {arc.outcomes.findIndex((o) => o.key === arc.haltedAt) + 1} and did not complete. The
              steps after it were not run.
            </p>
          ) : null}

          {arc.recordingError ? (
            <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
              The arc ran, but its run record could not be saved: {arc.recordingError}
            </p>
          ) : null}

          {arc.totalElapsedMs != null ? (
            <p className="text-sm text-muted-foreground">
              Measured elapsed time across the steps that ran:{" "}
              <span className="font-medium tabular-nums text-foreground">
                {formatElapsed(arc.totalElapsedMs)}
              </span>
            </p>
          ) : null}

          {arc.bundle ? (
            <p className="text-sm">
              Evidence bundle{" "}
              <span className="font-medium">{arc.bundle.title}</span> —{" "}
              {statusLabel(arc.bundle.status)}
              {arc.bundle.package_sha256 ? (
                <span className="ml-2 font-mono text-xs text-muted-foreground">
                  {arc.bundle.package_sha256.slice(0, 12)}
                </span>
              ) : null}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <div className="space-y-3">
        {arc.steps.map((spec, i) => {
          const outcome = arc.outcomes.find((o) => o.key === spec.key)
          if (!outcome) return null
          return (
            <StepCard
              key={spec.key}
              index={i + 1}
              title={spec.title}
              narration={spec.narration}
              outcome={outcome}
            />
          )
        })}
      </div>

      <HandoffChain items={arc.actionItems} />

      <GoldenPathContractPanel checks={arc.checks} hasRun={hasRun} />

      <GoldenPathRoiStrip split={roiSplit} loading={roiLoading} />
    </div>
  )
}
