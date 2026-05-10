"use client"

import Link from "next/link"
import { Fragment, useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
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
  countMetricKeysForAnalytics,
  trackMlTrainingRunCompleted,
  trackMlTrainingRunStarted,
} from "@/src/lib/analytics/analytics-client"
import { Activity, AlertTriangle, ArrowLeft, Loader2, PlayCircle, RefreshCw } from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.items)) return o.items
    if (Array.isArray(o.results)) return o.results
  }
  return []
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

function summarizeMetrics(raw: unknown, maxLen = 120): string {
  if (raw == null) return "—"
  if (typeof raw === "object") {
    const s = JSON.stringify(raw)
    return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s
  }
  return String(raw)
}

function readWarnings(row: Record<string, unknown>): string[] {
  const w = row["warnings_json"]
  if (!Array.isArray(w)) return []
  return w.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
}

const MODEL_FAMILIES = [
  "baseline",
  "linear",
  "random_forest",
  "gradient_boosting",
  "gaussian_process",
  "graph_neural_network",
  "transformer",
  "retrieval",
  "rule_based",
  "external",
] as const

const TASK_KEYS = ["tasks", "items", "results", "rows", "data"]
const PIPE_KEYS = ["pipelines", "items", "results", "rows", "data"]

export function MlTrainingRunLauncher() {
  const [reloadToken, setReloadToken] = useState(0)
  const [loading, setLoading] = useState(true)
  const [submitBusy, setSubmitBusy] = useState(false)
  const [cancelId, setCancelId] = useState<number | null>(null)

  const [tasks, setTasks] = useState<Record<string, unknown>[]>([])
  const [datasetVersions, setDatasetVersions] = useState<Record<string, unknown>[]>([])
  const [pipelines, setPipelines] = useState<Record<string, unknown>[]>([])
  const [trainingRuns, setTrainingRuns] = useState<Record<string, unknown>[]>([])

  const [errTasks, setErrTasks] = useState("")
  const [errVersions, setErrVersions] = useState("")
  const [errPipelines, setErrPipelines] = useState("")
  const [errRuns, setErrRuns] = useState("")
  const [formErr, setFormErr] = useState("")
  const [formOk, setFormOk] = useState("")

  const [taskKey, setTaskKey] = useState("")
  const [datasetVersionId, setDatasetVersionId] = useState<string>("")
  const [pipelineId, setPipelineId] = useState<string>("")
  const [modelFamily, setModelFamily] = useState<string>("baseline")
  const [modelName, setModelName] = useState("")
  const [modelVersion, setModelVersion] = useState("")
  const [parametersJson, setParametersJson] = useState("{}")
  const [experimental, setExperimental] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setErrTasks("")
    setErrVersions("")
    setErrPipelines("")
    setErrRuns("")

    const runList = async (
      path: string,
      keys: string[],
      setRows: (r: Record<string, unknown>[]) => void,
      setErr: (s: string) => void,
      errMsg: string,
    ) => {
      try {
        const data = await apiFetch<unknown>(path, { method: "GET" })
        setRows(extractRows(data, keys))
      } catch (e) {
        setErr(formatApiError(e, errMsg))
        setRows([])
      }
    }

    await Promise.all([
      runList("/ml/tasks", TASK_KEYS, setTasks, setErrTasks, "Could not load tasks."),
      (async () => {
        try {
          const data = await apiFetch<unknown>("/knowledge/dataset-versions?limit=500", { method: "GET" })
          setDatasetVersions(asArray(data).filter(isRecord) as Record<string, unknown>[])
        } catch (e) {
          setErrVersions(formatApiError(e, "Could not load dataset versions."))
          setDatasetVersions([])
        }
      })(),
      runList("/ml/feature-pipelines", PIPE_KEYS, setPipelines, setErrPipelines, "Could not load feature pipelines."),
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ml/training-runs?limit=500", { method: "GET" })
          const rows = Array.isArray(data) ? data.filter(isRecord) : extractRows(data, ["items", "runs", "results"])
          setTrainingRuns(rows as Record<string, unknown>[])
        } catch (e) {
          setErrRuns(formatApiError(e, "Could not load training runs."))
          setTrainingRuns([])
        }
      })(),
    ])

    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  const selectedDataset = useMemo(() => {
    const id = Number.parseInt(datasetVersionId, 10)
    if (!Number.isFinite(id)) return null
    return datasetVersions.find((r) => readRecordNumber(r, "id") === id) ?? null
  }, [datasetVersionId, datasetVersions])

  const datasetStatusLower = (readRecordString(selectedDataset ?? {}, "status") ?? "").toLowerCase()
  const datasetApproved = datasetStatusLower === "approved"
  const showExperimentalToggle = selectedDataset != null && !datasetApproved

  useEffect(() => {
    const id = Number.parseInt(datasetVersionId, 10)
    if (!Number.isFinite(id)) return
    const row = datasetVersions.find((r) => readRecordNumber(r, "id") === id)
    if (!row) return
    const st = (readRecordString(row, "status") ?? "").toLowerCase()
    if (st === "approved") setExperimental(false)
    else setExperimental(true)
  }, [datasetVersionId, datasetVersions])

  const taskKeyOptions = useMemo(() => {
    const keys = new Set<string>()
    for (const t of tasks) {
      const k = readRecordString(t, "task_key")
      if (k) keys.add(k)
    }
    return [...keys].sort()
  }, [tasks])

  async function submitTrainingRun() {
    setFormErr("")
    setFormOk("")
    const tk = taskKey.trim()
    const dvid = Number.parseInt(datasetVersionId, 10)
    const mn = modelName.trim()
    const mv = modelVersion.trim()
    if (!tk) {
      setFormErr("task_key is required.")
      return
    }
    if (!Number.isFinite(dvid) || dvid < 1) {
      setFormErr("dataset_version_id is required.")
      return
    }
    if (!mn || !mv) {
      setFormErr("model_name and model_version are required.")
      return
    }
    let parameters_json: Record<string, unknown>
    try {
      const parsed = JSON.parse(parametersJson.trim() || "{}") as unknown
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        setFormErr("parameters_json must be a JSON object.")
        return
      }
      parameters_json = parsed as Record<string, unknown>
    } catch {
      setFormErr("parameters_json must be valid JSON.")
      return
    }

    const body: Record<string, unknown> = {
      task_key: tk,
      dataset_version_id: dvid,
      model_family: modelFamily,
      model_name: mn,
      model_version: mv,
      parameters_json,
      experimental,
    }
    const pid = Number.parseInt(pipelineId, 10)
    if (Number.isFinite(pid) && pid >= 1) {
      body.feature_pipeline_id = pid
    } else {
      body.feature_pipeline_id = null
    }

    setSubmitBusy(true)
    try {
      const dsType =
        readRecordString(selectedDataset ?? {}, "required_dataset_type") ||
        readRecordString(selectedDataset ?? {}, "dataset_type") ||
        undefined
      const raw = await apiFetch<unknown>("/ml/training-runs", { method: "POST", body })
      if (isRecord(raw)) {
        const st = readStr(raw, ["status"])
        const m = raw["metrics"]
        const w = raw["warnings"]
        trackMlTrainingRunStarted({
          task_key: readStr(raw, ["task_key"]) || tk,
          model_family: readStr(raw, ["model_family"]) || modelFamily,
          status: st || undefined,
          dataset_type: dsType,
          metric_count: countMetricKeysForAnalytics(m),
          warning_count: Array.isArray(w) ? w.length : undefined,
        })
        if (st === "succeeded" || st === "failed" || st === "canceled") {
          trackMlTrainingRunCompleted({
            task_key: readStr(raw, ["task_key"]) || tk,
            model_family: readStr(raw, ["model_family"]) || modelFamily,
            status: st,
            dataset_type: dsType,
            metric_count: countMetricKeysForAnalytics(m),
            warning_count: Array.isArray(w) ? w.length : undefined,
          })
        }
      } else {
        trackMlTrainingRunStarted({
          task_key: tk,
          model_family: modelFamily,
          dataset_type: dsType,
        })
      }
      setFormOk("Start training run accepted. When the run finishes with status succeeded: training complete.")
      setReloadToken((x) => x + 1)
    } catch (e) {
      setFormErr(formatApiError(e, "Could not start training run."))
    } finally {
      setSubmitBusy(false)
    }
  }

  async function cancelRun(id: number) {
    setCancelId(id)
    try {
      await apiFetch(`/ml/training-runs/${id}/cancel`, { method: "POST" })
      setReloadToken((x) => x + 1)
    } catch (e) {
      setFormErr(formatApiError(e, "Cancel failed."))
    } finally {
      setCancelId(null)
    }
  }

  const partialErr = Boolean(errTasks || errVersions || errPipelines || errRuns)

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1">
            <Button variant="ghost" size="sm" className="h-8 px-2" asChild>
              <Link href="/ml" className="inline-flex items-center gap-1 text-muted-foreground">
                <ArrowLeft className="h-4 w-4" aria-hidden />
                ML Model Factory
              </Link>
            </Button>
          </div>
          <h1 className="font-mono text-2xl font-bold tracking-tight">ML Training Run Launcher</h1>
          <p className="text-muted-foreground">
            Start controlled training runs against approved or explicitly experimental dataset versions.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" aria-hidden />
        <AlertTitle className="text-sm">Governance</AlertTitle>
        <AlertDescription className="text-sm text-muted-foreground">
          Training completion creates artifacts for follow-up work: when a run succeeds, treat outcomes as{" "}
          <span className="font-medium text-foreground">training complete</span> and check for{" "}
          <span className="font-medium text-foreground">model artifact created</span> via{" "}
          <code className="text-xs">model_artifact_id</code>. Every run still{" "}
          <span className="font-medium text-foreground">requires evaluation</span> before deployment decisions.
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
      </div>

      {partialErr ? (
        <Alert variant="destructive">
          <AlertTitle>Partial load</AlertTitle>
          <AlertDescription className="space-y-1 text-xs">
            {errTasks ? <p>Task list: {errTasks}</p> : null}
            {errVersions ? <p>Dataset versions: {errVersions}</p> : null}
            {errPipelines ? <p>Feature pipelines: {errPipelines}</p> : null}
            {errRuns ? <p>Training runs: {errRuns}</p> : null}
          </AlertDescription>
        </Alert>
      ) : null}

      <ModuleCard
        accent="teal"
        eyebrow="Launch"
        title="Start training run"
        icon={PlayCircle}
        description="Launch a supervised ML training run against a curated knowledge dataset version. Only dataset IDs and hyperparameters are sent — no raw data payload."
      >
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="task-key">task_key</Label>
              {taskKeyOptions.length > 0 ? (
                <Select value={taskKey || undefined} onValueChange={setTaskKey}>
                  <SelectTrigger id="task-key">
                    <SelectValue placeholder="Select task" />
                  </SelectTrigger>
                  <SelectContent>
                    {taskKeyOptions.map((k) => (
                      <SelectItem key={k} value={k}>
                        {k}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  id="task-key"
                  value={taskKey}
                  onChange={(e) => setTaskKey(e.target.value)}
                  placeholder="task_key from GET /ml/tasks"
                  autoComplete="off"
                />
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="dataset-version">dataset_version_id</Label>
              <Select value={datasetVersionId || undefined} onValueChange={setDatasetVersionId}>
                <SelectTrigger id="dataset-version">
                  <SelectValue placeholder={datasetVersions.length ? "Select dataset version" : "Load versions from API"} />
                </SelectTrigger>
                <SelectContent>
                  {datasetVersions.map((row) => {
                    const id = readRecordNumber(row, "id")
                    if (id == null) return null
                    const name = readRecordString(row, "name") ?? ""
                    const ver = readRecordString(row, "version") ?? ""
                    const st = readRecordString(row, "status") ?? ""
                    return (
                      <SelectItem key={id} value={String(id)}>
                        #{id} {name} {ver ? `(${ver})` : ""} — {st}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="pipeline">feature_pipeline_id (optional)</Label>
              <Select value={pipelineId || "__none__"} onValueChange={(v) => setPipelineId(v === "__none__" ? "" : v)}>
                <SelectTrigger id="pipeline">
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">None</SelectItem>
                  {pipelines.map((row) => {
                    const id = readRecordNumber(row, "id")
                    if (id == null) return null
                    const name = readRecordString(row, "name") ?? ""
                    const ver = readRecordString(row, "version") ?? ""
                    return (
                      <SelectItem key={id} value={String(id)}>
                        #{id} {name} {ver ? `(${ver})` : ""}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="model-family">model_family</Label>
              <Select value={modelFamily} onValueChange={setModelFamily}>
                <SelectTrigger id="model-family">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODEL_FAMILIES.map((f) => (
                    <SelectItem key={f} value={f}>
                      {f}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="model-name">model_name</Label>
              <Input id="model-name" value={modelName} onChange={(e) => setModelName(e.target.value)} autoComplete="off" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="model-version">model_version</Label>
              <Input id="model-version" value={modelVersion} onChange={(e) => setModelVersion(e.target.value)} autoComplete="off" />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="params-json">parameters_json</Label>
            <Textarea
              id="params-json"
              className="min-h-[100px] font-mono text-xs"
              value={parametersJson}
              onChange={(e) => setParametersJson(e.target.value)}
              spellCheck={false}
            />
          </div>

          {showExperimentalToggle ? (
            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <p className="text-sm font-medium">experimental</p>
                <p className="text-xs text-muted-foreground">
                  Dataset version is not approved; enable experimental mode to proceed under governance rules.
                </p>
              </div>
              <Switch checked={experimental} onCheckedChange={setExperimental} />
            </div>
          ) : selectedDataset ? (
            <p className="text-xs text-muted-foreground">
              Dataset version status is approved; experimental mode is off for this selection.
            </p>
          ) : null}

          {formErr ? <p className="text-sm text-destructive">{formErr}</p> : null}
          {formOk ? <p className="text-sm text-muted-foreground">{formOk}</p> : null}

          <Button type="button" disabled={submitBusy || loading} onClick={() => void submitTrainingRun()}>
            {submitBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Start training run
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Runs"
        title="Training runs"
        icon={Activity}
        description="ML training run history — status, metrics, and artifact IDs for each completed or in-progress run. Artifact IDs appear when the backend reports success."
      >
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Labels: <span className="font-medium text-foreground">training complete</span> aligns with{" "}
            <code className="text-xs">status === succeeded</code>;{" "}
            <span className="font-medium text-foreground">model artifact created</span> when{" "}
            <code className="text-xs">model_artifact_id</code> is present;{" "}
            <span className="font-medium text-foreground">requires evaluation</span> for downstream release checks.
          </p>
          <div className="table-scroll min-w-0">
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : errRuns ? (
              <p className="text-sm text-muted-foreground">{errRuns}</p>
            ) : trainingRuns.length === 0 ? (
              <p className="text-sm text-muted-foreground">No training runs returned.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[72px]">id</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>dataset_version_id</TableHead>
                    <TableHead>model_family</TableHead>
                    <TableHead>metrics</TableHead>
                    <TableHead>warnings</TableHead>
                    <TableHead>model_artifact_id</TableHead>
                    <TableHead className="w-[100px]">actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {trainingRuns.map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    const rowKey = id != null ? `tr-${id}` : `tr-i-${idx}`
                    const st = readStr(row, ["status", "state"])
                    const stLower = st.toLowerCase()
                    const metricsRaw = row["training_metrics_json"] ?? row["metrics_json"]
                    const warnList = readWarnings(row)
                    const artifact = readRecordNumber(row, "model_artifact_id")
                    const canCancel =
                      stLower === "queued" || stLower === "running" || stLower === "requires_review"
                    const done = stLower === "succeeded"
                    return (
                      <Fragment key={rowKey}>
                        <TableRow>
                          <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                          <TableCell>
                            <div className="flex flex-col gap-1">
                              <Badge variant="secondary">{st || "—"}</Badge>
                              {done ? (
                                <span className="text-[11px] text-muted-foreground">
                                  training complete
                                  {artifact != null ? " · model artifact created" : ""} · requires evaluation
                                </span>
                              ) : null}
                            </div>
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {readRecordNumber(row, "dataset_version_id") ?? "—"}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{readStr(row, ["model_family"]) || "—"}</TableCell>
                          <TableCell className="max-w-[200px] truncate font-mono text-[11px] text-muted-foreground">
                            {summarizeMetrics(metricsRaw)}
                          </TableCell>
                          <TableCell className="max-w-[220px] text-xs text-muted-foreground">
                            {warnList.length ? warnList.join("; ") : "—"}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{artifact != null ? artifact : "—"}</TableCell>
                          <TableCell>
                            {canCancel && id != null ? (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                disabled={cancelId === id}
                                onClick={() => void cancelRun(id)}
                              >
                                {cancelId === id ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
                                Cancel
                              </Button>
                            ) : (
                              "—"
                            )}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell colSpan={8} className="border-t-0 bg-muted/20 p-2">
                            <DeveloperJsonPanel data={row} />
                          </TableCell>
                        </TableRow>
                      </Fragment>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </div>
        </div>
      </ModuleCard>
    </div>
  )
}
