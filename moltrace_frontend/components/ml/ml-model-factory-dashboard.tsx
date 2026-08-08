"use client"

import { statusLabel } from "@/lib/ui/status"
import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { readRecordNumber } from "@/components/projects/project-workspace-utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import {
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Boxes,
  Bug,
  Cpu,
  Crosshair,
  Database,
  Eye,
  GaugeCircle,
  Library,
  Loader2,
  type LucideIcon,
  Package,
  PlayCircle,
  Radar,
  RefreshCw,
  Rocket,
  ShieldCheck,
} from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const d = err.data
    if (isRecord(d) && typeof d.detail === "string") return d.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

function extractRows(data: unknown, arrayKeys: string[]): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (!isRecord(data)) return []
  for (const k of arrayKeys) {
    const v = data[k]
    if (Array.isArray(v)) return v.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

function readStr(row: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = row[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return ""
}

function formatWhen(iso: string | undefined): string {
  if (!iso?.trim()) return "—"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

function readOptionalInt(obj: unknown, keys: string[]): number | null {
  if (!isRecord(obj)) return null
  for (const k of keys) {
    const v = obj[k]
    if (typeof v === "number" && Number.isFinite(v)) return v
    if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Number(v)
  }
  return null
}

function readArtifactCount(health: unknown): number | null {
  const n = readOptionalInt(health, ["artifact_count", "model_artifact_count", "artifacts_count", "n_artifacts"])
  if (n != null) return n
  if (!isRecord(health)) return null
  for (const k of ["artifacts", "model_artifacts"]) {
    const v = health[k]
    if (Array.isArray(v)) return v.length
  }
  return null
}

function readReviewPendingCount(health: unknown, deploymentRows: Record<string, unknown>[]): number | null {
  const n = readOptionalInt(health, [
    "models_requiring_review",
    "pending_review_count",
    "models_pending_review",
    "n_models_requiring_review",
  ])
  if (n != null) return n
  let c = 0
  for (const r of deploymentRows) {
    const s = readStr(r, ["review_status", "approval_status", "status"]).toLowerCase()
    if (
      s.includes("review") ||
      s.includes("pending") ||
      s.includes("needs_approval") ||
      s === "draft" ||
      s === "proposed"
    ) {
      c++
    }
  }
  return deploymentRows.length ? c : null
}

function readErrorAnalysisOpenCount(health: unknown, taskRows: Record<string, unknown>[]): number | null {
  const n = readOptionalInt(health, [
    "open_error_analysis_items",
    "error_analysis_open_count",
    "open_error_analysis_count",
    "n_open_error_analysis",
  ])
  if (n != null) return n
  let c = 0
  for (const r of taskRows) {
    const typ = readStr(r, ["task_type", "type", "category"]).toLowerCase()
    const st = readStr(r, ["status", "state"]).toLowerCase()
    const errLike = typ.includes("error") || typ.includes("analysis")
    const openLike = st === "open" || st === "pending" || st === "in_progress" || st === "new"
    if (errLike && openLike) c++
  }
  return taskRows.length ? c : null
}

function healthPreviewRows(raw: unknown): { key: string; value: string }[] {
  if (Array.isArray(raw)) return []
  if (!isRecord(raw)) return []
  const out: { key: string; value: string }[] = []
  for (const [k, v] of Object.entries(raw)) {
    if (out.length >= 18) break
    if (v == null) {
      out.push({ key: k, value: "—" })
    } else if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      out.push({ key: k, value: String(v) })
    }
  }
  return out
}

const TASK_KEYS = ["tasks", "items", "results", "rows", "data"]
const TRAINING_KEYS = ["training_runs", "runs", "items", "results", "rows", "data"]
const EVAL_KEYS = ["evaluation_runs", "runs", "items", "results", "rows", "data"]
const DEPLOY_KEYS = ["deployment_candidates", "candidates", "items", "results", "rows", "data"]

/**
 * The nine destinations, grouped by where they sit in a model's life: you train
 * it, you assess it from four angles before anyone ships it, a human decides, and
 * two of the nine are not in this module at all.
 *
 * Descriptions name what each destination CONTAINS rather than what it can do.
 * These workspaces carry no summary line to lift, and writing capability claims
 * from a route name is how a hub ends up describing something its destination
 * does not do.
 *
 * `leavesModule` marks the two Knowledge Library links. They sit in the same row
 * as seven in-module destinations and looked identical to them; a link that
 * silently relocates you is worse than one that says so first.
 */
const ML_DESTINATIONS: ReadonlyArray<{
  label: string
  accent: string
  ink: string
  leavesModule?: boolean
  items: ReadonlyArray<{ label: string; href: string; desc: string; icon: LucideIcon }>
}> = [
  {
    label: "Train",
    accent: "var(--mt-teal)",
    ink: "var(--mt-teal-ink)",
    items: [
      { label: "Training launcher", href: "/ml/training", desc: "Start a training run, and the runs already started.", icon: PlayCircle },
      { label: "Model artifacts", href: "/ml/models", desc: "Registered artifacts and the provenance recorded with each one.", icon: Boxes },
    ],
  },
  {
    label: "Assess before shipping",
    accent: "var(--mt-violet)",
    ink: "var(--mt-violet-ink)",
    items: [
      { label: "Evaluation dashboard", href: "/ml/evaluations", desc: "Evaluation runs and the metrics they produced.", icon: GaugeCircle },
      { label: "Calibration", href: "/ml/calibration", desc: "Calibration assessments — whether a confidence behaves like a probability.", icon: Crosshair },
      { label: "Error analysis", href: "/ml/error-analysis", desc: "Where a model's errors concentrate.", icon: Radar },
      { label: "Out-of-domain", href: "/ml/ood", desc: "Out-of-domain assessments, for inputs unlike anything trained on.", icon: Radar },
    ],
  },
  {
    label: "Decide",
    accent: "var(--mt-cyan)",
    ink: "var(--mt-cyan-ink)",
    items: [
      { label: "Deployment review", href: "/ml/deployment-candidates", desc: "Candidates waiting on a human decision before they go anywhere.", icon: ShieldCheck },
    ],
  },
  {
    label: "Where the data comes from",
    accent: "var(--mt-amber)",
    ink: "var(--mt-amber-ink)",
    leavesModule: true,
    items: [
      { label: "Dataset versions", href: "/knowledge/datasets", desc: "The dataset candidates a training run draws from.", icon: Database },
      { label: "Knowledge Library", href: "/knowledge", desc: "Ingested sources, extractions and reviewed records.", icon: Library },
    ],
  },
]

export function MlModelFactoryDashboard() {
  const [reloadToken, setReloadToken] = useState(0)
  const [loading, setLoading] = useState(true)

  const [tasks, setTasks] = useState<Record<string, unknown>[]>([])
  const [trainingRuns, setTrainingRuns] = useState<Record<string, unknown>[]>([])
  const [evaluationRuns, setEvaluationRuns] = useState<Record<string, unknown>[]>([])
  const [deploymentCandidates, setDeploymentCandidates] = useState<Record<string, unknown>[]>([])
  const [modelHealth, setModelHealth] = useState<unknown>(null)

  const [errTasks, setErrTasks] = useState("")
  const [errTraining, setErrTraining] = useState("")
  const [errEval, setErrEval] = useState("")
  const [errDeploy, setErrDeploy] = useState("")
  const [errHealth, setErrHealth] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setErrTasks("")
    setErrTraining("")
    setErrEval("")
    setErrDeploy("")
    setErrHealth("")

    const runList = async (
      path: string,
      keys: string[],
      setRows: (r: Record<string, unknown>[]) => void,
      setErr: (s: string) => void,
    ) => {
      try {
        const data = await apiFetch<unknown>(path, { method: "GET" })
        setRows(extractRows(data, keys))
      } catch (e) {
        setErr(formatErr(e, `Could not load this list.`))
        setRows([])
      }
    }

    await Promise.all([
      runList("/ml/tasks", TASK_KEYS, setTasks, setErrTasks),
      runList("/ml/training-runs", TRAINING_KEYS, setTrainingRuns, setErrTraining),
      runList("/ml/evaluation-runs", EVAL_KEYS, setEvaluationRuns, setErrEval),
      runList("/ml/deployment-candidates", DEPLOY_KEYS, setDeploymentCandidates, setErrDeploy),
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ml/model-health", { method: "GET" })
          setModelHealth(data)
        } catch (e) {
          setErrHealth(formatErr(e, "Could not load model health."))
          setModelHealth(null)
        }
      })(),
    ])

    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  const artifactCount = useMemo(() => readArtifactCount(modelHealth), [modelHealth])
  const reviewPendingCount = useMemo(
    () => readReviewPendingCount(modelHealth, deploymentCandidates),
    [modelHealth, deploymentCandidates],
  )
  const errorAnalysisOpen = useMemo(
    () => readErrorAnalysisOpenCount(modelHealth, tasks),
    [modelHealth, tasks],
  )

  function statValue(count: number | null, errored: boolean): string {
    if (loading) return "…"
    if (errored) return "—"
    if (count === null) return "—"
    return String(count)
  }

  function statSub(opts: { errored: boolean; empty: boolean; label: string }) {
    if (loading) return <p className="text-xs text-muted-foreground">Loading…</p>
    if (opts.errored) return <p className="text-xs text-muted-foreground">Unable to load.</p>
    if (opts.empty) return <p className="text-xs text-muted-foreground">No data returned.</p>
    return <p className="text-xs text-muted-foreground">{opts.label}</p>
  }

  const healthScalars = useMemo(() => healthPreviewRows(modelHealth), [modelHealth])
  const partialErr =
    errTasks || errTraining || errEval || errDeploy || errHealth ? (
      <AlertCard variant="error" title="Partial load">
        <div className="space-y-1 text-xs">
          {errTasks ? <p>Tasks: {errTasks}</p> : null}
          {errTraining ? <p>Training runs: {errTraining}</p> : null}
          {errEval ? <p>Evaluation runs: {errEval}</p> : null}
          {errDeploy ? <p>Deployment candidates: {errDeploy}</p> : null}
          {errHealth ? <p>Model health: {errHealth}</p> : null}
        </div>
      </AlertCard>
    ) : null

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal-ink)" }}
          >
            MolTrace · ML Model Factory
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">ML Model Factory</h1>
          <p className="text-sm text-muted-foreground">
            Train, evaluate, document, and review controlled ML/AI models from approved dataset versions.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <AlertCard
        variant="warning"
        title="Warning"
        description="Models trained in MolTrace require dataset-version tracking, evaluation, model cards, and human approval before use."
      />

      {/* Refresh is an ACTION and sat among nine navigation links, so the one
          control that changes nothing about where you are looked exactly like the
          nine that do. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
          Where to go next
        </h2>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={loading}
          onClick={() => setReloadToken((x) => x + 1)}
        >
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <RefreshCw className="mr-2 h-4 w-4" aria-hidden />}
          Refresh
        </Button>
      </div>

      <div className="space-y-5">
        {ML_DESTINATIONS.map((group) => (
          <div key={group.label} className="space-y-3">
            <p className="text-xs font-medium text-muted-foreground">
              {group.label}
              {group.leavesModule ? (
                <span className="ml-1.5 font-normal opacity-70">{" "}— opens another module</span>
              ) : null}
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {group.items.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="group relative flex h-full min-w-0 flex-col rounded-xl border bg-card p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none motion-reduce:hover:translate-y-0"
                  style={{ borderLeftWidth: "3px", borderLeftColor: group.accent }}
                >
                  <div className="flex items-center gap-2">
                    <item.icon className="h-5 w-5 shrink-0" style={{ color: group.accent }} aria-hidden />
                    <h3 className="min-w-0 text-sm font-semibold" style={{ color: group.ink }}>
                      {item.label}
                    </h3>
                    {group.leavesModule ? (
                      <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 motion-reduce:transition-none" aria-hidden />
                    ) : (
                      <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none" aria-hidden />
                    )}
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{item.desc}</p>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>

      {partialErr}

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Summary cards</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">ML tasks</CardTitle>
              <Cpu className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(errTasks ? null : tasks.length, Boolean(errTasks))}
              </div>
              {statSub({
                errored: Boolean(errTasks),
                empty: !errTasks && tasks.length === 0,
                label: "Registered tasks",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Training runs</CardTitle>
              <PlayCircle className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(errTraining ? null : trainingRuns.length, Boolean(errTraining))}
              </div>
              {statSub({
                errored: Boolean(errTraining),
                empty: !errTraining && trainingRuns.length === 0,
                label: "Training runs",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Evaluation runs</CardTitle>
              <BarChart3 className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(errEval ? null : evaluationRuns.length, Boolean(errEval))}
              </div>
              {statSub({
                errored: Boolean(errEval),
                empty: !errEval && evaluationRuns.length === 0,
                label: "Evaluation runs",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Model artifacts</CardTitle>
              <Package className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(errHealth ? null : artifactCount, Boolean(errHealth))}
              </div>
              {statSub({
                errored: Boolean(errHealth),
                empty: !errHealth && artifactCount == null && healthScalars.length === 0,
                label: "Model artifacts",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Deployment candidates</CardTitle>
              <Rocket className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(errDeploy ? null : deploymentCandidates.length, Boolean(errDeploy))}
              </div>
              {statSub({
                errored: Boolean(errDeploy),
                empty: !errDeploy && deploymentCandidates.length === 0,
                label: "Deployment candidates",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Models requiring review</CardTitle>
              <Eye className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(
                  errHealth && errDeploy ? null : reviewPendingCount,
                  Boolean(errHealth) && Boolean(errDeploy),
                )}
              </div>
              {statSub({
                errored: Boolean(errHealth) && Boolean(errDeploy),
                empty:
                  Boolean(errHealth) === false &&
                  Boolean(errDeploy) === false &&
                  reviewPendingCount === null &&
                  deploymentCandidates.length === 0,
                label: "From model health or candidate status",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Open error-analysis items</CardTitle>
              <Bug className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(
                  errHealth && errTasks ? null : errorAnalysisOpen,
                  Boolean(errHealth) && Boolean(errTasks),
                )}
              </div>
              {statSub({
                errored: Boolean(errHealth) && Boolean(errTasks),
                empty:
                  Boolean(errHealth) === false &&
                  Boolean(errTasks) === false &&
                  errorAnalysisOpen === null &&
                  tasks.length === 0,
                label: "From model health or task records",
              })}
            </CardContent>
          </Card>
        </div>
      </div>

      <ModuleCard
        accent="teal"
        eyebrow="ML · Tasks"
        title="Built-in task table"
        description="Every prediction objective available for training."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errTasks ? (
            <p className="text-sm text-muted-foreground">{errTasks}</p>
          ) : tasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tasks returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">ID</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Task type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.slice(0, 25).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `task-${id}` : `task-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell className="max-w-[200px] truncate text-sm">
                        {readStr(row, ["name", "title", "label"]) || "—"}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {statusLabel(readStr(row, ["task_type", "type"]))}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{statusLabel(readStr(row, ["status", "state"]))}</Badge>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readStr(row, ["updated_at", "modified_at", "created_at"]))}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="ML · Training Runs"
        title="Recent training runs"
        description="Across every task and dataset version."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errTraining ? (
            <p className="text-sm text-muted-foreground">{errTraining}</p>
          ) : trainingRuns.length === 0 ? (
            <p className="text-sm text-muted-foreground">No training runs returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Dataset version ID</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trainingRuns.slice(0, 20).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `tr-${id}` : `tr-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="secondary">{statusLabel(readStr(row, ["status", "state"]))}</Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {(readRecordNumber(row, "dataset_version_id") ?? readStr(row, ["dataset_version_id"])) || "—"}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readStr(row, ["started_at", "created_at"]))}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readStr(row, ["updated_at", "finished_at", "completed_at"]))}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="ML · Evaluation Runs"
        title="Recent evaluation runs"
        description="Completed and in-progress, with metric summaries."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errEval ? (
            <p className="text-sm text-muted-foreground">{errEval}</p>
          ) : evaluationRuns.length === 0 ? (
            <p className="text-sm text-muted-foreground">No evaluation runs returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Metric summary</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {evaluationRuns.slice(0, 20).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  const ms = readStr(row, ["metric_summary", "metrics_summary", "summary"])
                  const short = ms.length > 80 ? `${ms.slice(0, 80)}…` : ms
                  return (
                    <TableRow key={id != null ? `ev-${id}` : `ev-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{statusLabel(readStr(row, ["status", "state"]))}</Badge>
                      </TableCell>
                      <TableCell className="max-w-[280px] truncate text-xs text-muted-foreground">{short || "—"}</TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readStr(row, ["updated_at", "finished_at", "created_at"]))}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="ML · Deployment Candidates"
        title="Deployment candidate preview"
        description="Artifacts nominated for production, with their review state."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errDeploy ? (
            <p className="text-sm text-muted-foreground">{errDeploy}</p>
          ) : deploymentCandidates.length === 0 ? (
            <p className="text-sm text-muted-foreground">No deployment candidates returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Approval status</TableHead>
                  <TableHead>Model version ID</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {deploymentCandidates.slice(0, 20).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `dc-${id}` : `dc-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="secondary">{statusLabel(readStr(row, ["status", "state"]))}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{statusLabel(readStr(row, ["approval_status", "review_status"]))}</Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {(readRecordNumber(row, "model_version_id") ?? readStr(row, ["model_version_id"])) || "—"}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readStr(row, ["updated_at", "created_at"]))}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="ML · Model Health"
        title="Model health preview"
        description="Scalar performance and drift indicators. Nested details are not expanded; approval and validation states always come from stored record fields."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errHealth ? (
            <p className="text-sm text-muted-foreground">{errHealth}</p>
          ) : healthScalars.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No summary fields available. Approval and validation states always come
              from stored record fields — not inferred here.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Field</TableHead>
                  <TableHead>Value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {healthScalars.map((row) => (
                  <TableRow key={row.key}>
                    <TableCell className="font-mono text-xs">{row.key}</TableCell>
                    <TableCell className="text-sm">{row.value}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <p className="text-xs text-muted-foreground">
        Factory lists reflect operational signals from your workspace. Release decisions follow your governance process;
        surface <span className="font-medium text-foreground">approval status</span> and related recorded fields rather
        than UI assumptions.
      </p>
    </div>
  )
}
