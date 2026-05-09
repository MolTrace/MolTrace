"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { readRecordNumber } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
  AlertTriangle,
  BarChart3,
  Bug,
  Cpu,
  Eye,
  Loader2,
  Package,
  PlayCircle,
  RefreshCw,
  Rocket,
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
        setErr(formatErr(e, `Could not load ${path}.`))
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
          setErrHealth(formatErr(e, "Could not load /ml/model-health."))
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
    if (opts.errored) return <p className="text-xs text-muted-foreground">Unable to load from backend.</p>
    if (opts.empty) return <p className="text-xs text-muted-foreground">No data returned.</p>
    return <p className="text-xs text-muted-foreground">{opts.label}</p>
  }

  const healthScalars = useMemo(() => healthPreviewRows(modelHealth), [modelHealth])
  const partialErr =
    errTasks || errTraining || errEval || errDeploy || errHealth ? (
      <Alert variant="destructive">
        <AlertTitle>Partial load</AlertTitle>
        <AlertDescription className="space-y-1 text-xs">
          {errTasks ? <p>GET /ml/tasks: {errTasks}</p> : null}
          {errTraining ? <p>GET /ml/training-runs: {errTraining}</p> : null}
          {errEval ? <p>GET /ml/evaluation-runs: {errEval}</p> : null}
          {errDeploy ? <p>GET /ml/deployment-candidates: {errDeploy}</p> : null}
          {errHealth ? <p>GET /ml/model-health: {errHealth}</p> : null}
        </AlertDescription>
      </Alert>
    ) : null

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">ML Model Factory</h1>
          <p className="text-muted-foreground">
            Train, evaluate, document, and review controlled ML/AI models from approved dataset versions.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" aria-hidden />
        <AlertTitle className="text-sm">Warning</AlertTitle>
        <AlertDescription className="text-sm text-muted-foreground">
          Models trained in MolTrace require dataset-version tracking, evaluation, model cards, and human approval
          before use.
        </AlertDescription>
      </Alert>

      <div className="flex flex-wrap items-center gap-2">
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
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/datasets">Dataset versions</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge">Knowledge Library</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/ml/training">Training launcher</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/ml/evaluations">Evaluation dashboard</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/ml/models">Model artifacts</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/ml/deployment-candidates">Deployment review</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/ml/calibration">Calibration</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/ml/error-analysis">Error analysis</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/ml/ood">Out-of-domain</Link>
        </Button>
      </div>

      {partialErr}

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Summary cards</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">ML tasks</CardTitle>
              <Cpu className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold tabular-nums">
                {statValue(errTasks ? null : tasks.length, Boolean(errTasks))}
              </div>
              {statSub({
                errored: Boolean(errTasks),
                empty: !errTasks && tasks.length === 0,
                label: "GET /ml/tasks",
              })}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Training runs</CardTitle>
              <PlayCircle className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold tabular-nums">
                {statValue(errTraining ? null : trainingRuns.length, Boolean(errTraining))}
              </div>
              {statSub({
                errored: Boolean(errTraining),
                empty: !errTraining && trainingRuns.length === 0,
                label: "GET /ml/training-runs",
              })}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Evaluation runs</CardTitle>
              <BarChart3 className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold tabular-nums">
                {statValue(errEval ? null : evaluationRuns.length, Boolean(errEval))}
              </div>
              {statSub({
                errored: Boolean(errEval),
                empty: !errEval && evaluationRuns.length === 0,
                label: "GET /ml/evaluation-runs",
              })}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Model artifacts</CardTitle>
              <Package className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold tabular-nums">
                {statValue(errHealth ? null : artifactCount, Boolean(errHealth))}
              </div>
              {statSub({
                errored: Boolean(errHealth),
                empty: !errHealth && artifactCount == null && healthScalars.length === 0,
                label: "GET /ml/model-health",
              })}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Deployment candidates</CardTitle>
              <Rocket className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold tabular-nums">
                {statValue(errDeploy ? null : deploymentCandidates.length, Boolean(errDeploy))}
              </div>
              {statSub({
                errored: Boolean(errDeploy),
                empty: !errDeploy && deploymentCandidates.length === 0,
                label: "GET /ml/deployment-candidates",
              })}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Models requiring review</CardTitle>
              <Eye className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold tabular-nums">
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
                label: "From model-health or deployment-candidate status fields",
              })}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Open error-analysis items</CardTitle>
              <Bug className="h-4 w-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold tabular-nums">
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
                label: "From model-health or task rows",
              })}
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Built-in task table</CardTitle>
          <CardDescription>
            Registered ML tasks available for training — task type, status, and configuration for each supported prediction objective.
          </CardDescription>
        </CardHeader>
        <CardContent className="table-scroll min-w-0">
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
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>name</TableHead>
                  <TableHead>task_type</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>updated_at</TableHead>
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
                        {readStr(row, ["task_type", "type"]) || "—"}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{readStr(row, ["status", "state"]) || "—"}</Badge>
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Recent training runs</CardTitle>
          <CardDescription>
            Recent ML training runs — task, dataset version, status, and metric summaries across all completed and in-progress runs.
          </CardDescription>
        </CardHeader>
        <CardContent className="table-scroll min-w-0">
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
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>dataset_version_id</TableHead>
                  <TableHead>started_at</TableHead>
                  <TableHead>updated_at</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trainingRuns.slice(0, 20).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `tr-${id}` : `tr-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="secondary">{readStr(row, ["status", "state"]) || "—"}</Badge>
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Recent evaluation runs</CardTitle>
          <CardDescription>
            Recent model evaluation runs — artifact, status, and metric summary for each completed or in-progress evaluation.
          </CardDescription>
        </CardHeader>
        <CardContent className="table-scroll min-w-0">
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
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>metric_summary</TableHead>
                  <TableHead>updated_at</TableHead>
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
                        <Badge variant="outline">{readStr(row, ["status", "state"]) || "—"}</Badge>
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Deployment candidate preview</CardTitle>
          <CardDescription>
            Model artifacts nominated for production deployment — approval status, task key, and review state for each candidate.
          </CardDescription>
        </CardHeader>
        <CardContent className="table-scroll min-w-0">
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
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>approval_status</TableHead>
                  <TableHead>model_version_id</TableHead>
                  <TableHead>updated_at</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {deploymentCandidates.slice(0, 20).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `dc-${id}` : `dc-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="secondary">{readStr(row, ["status", "state"]) || "—"}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{readStr(row, ["approval_status", "review_status"]) || "—"}</Badge>
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Model health preview</CardTitle>
          <CardDescription>
            Model health summary — scalar performance and drift indicators. Nested payloads are not expanded; approval and validation states always come from backend fields.
          </CardDescription>
        </CardHeader>
        <CardContent className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errHealth ? (
            <p className="text-sm text-muted-foreground">{errHealth}</p>
          ) : healthScalars.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No scalar summary fields returned (or response is array-only). Approval and validation states always come
              from backend fields — not inferred here.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>field</TableHead>
                  <TableHead>value</TableHead>
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
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Factory lists reflect operational signals from your tenant API. Release decisions follow your governance process;
        surface <span className="font-medium text-foreground">approval_status</span> and related backend fields rather
        than UI assumptions.
      </p>
    </div>
  )
}
