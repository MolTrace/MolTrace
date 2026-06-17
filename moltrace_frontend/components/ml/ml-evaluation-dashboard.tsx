"use client"

import Link from "next/link"
import { Fragment, useCallback, useEffect, useState } from "react"
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
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
  trackMlEvaluationRunCompleted,
  trackMlEvaluationRunStarted,
} from "@/src/lib/analytics/analytics-client"
import { Activity, AlertTriangle, ArrowLeft, Loader2, PlayCircle, RefreshCw } from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function fixAsArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.items)) return o.items
    if (Array.isArray(o.results)) return o.results
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

function summarizeJson(raw: unknown, maxLen = 160): string {
  if (raw == null) return "—"
  if (typeof raw === "object") {
    const s = JSON.stringify(raw)
    return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s
  }
  return String(raw)
}

function objectEntriesTable(raw: unknown): { key: string; value: string }[] {
  if (!isRecord(raw)) return []
  const out: { key: string; value: string }[] = []
  for (const [k, v] of Object.entries(raw)) {
    out.push({ key: k, value: summarizeJson(v, 200) })
  }
  return out
}

function readMetadataBenchmarkId(row: Record<string, unknown>): number | null {
  const m = row["metadata_json"]
  if (!m || typeof m !== "object" || Array.isArray(m)) return null
  const id = (m as Record<string, unknown>)["benchmark_dataset_id"]
  if (typeof id === "number" && Number.isFinite(id)) return id
  if (typeof id === "string" && Number.isFinite(Number(id))) return Number(id)
  return null
}

function readStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
}

function sanitizeErrorExample(ex: unknown): { caseId: string; summary: string } {
  if (!isRecord(ex)) return { caseId: "—", summary: "—" }
  const caseId = readStr(ex, ["case_id", "id"]) || "—"
  const err = readStr(ex, ["error", "message", "summary"])
  const summary = err.length > 120 ? `${err.slice(0, 120)}…` : err || "—"
  return { caseId, summary }
}

const SPLIT_OPTIONS = ["validation", "test", "holdout", "benchmark"] as const

export function MlEvaluationDashboard() {
  const [reloadToken, setReloadToken] = useState(0)
  const [loading, setLoading] = useState(true)
  const [submitBusy, setSubmitBusy] = useState(false)

  const [artifacts, setArtifacts] = useState<Record<string, unknown>[]>([])
  const [datasetVersions, setDatasetVersions] = useState<Record<string, unknown>[]>([])
  const [benchmarkCandidates, setBenchmarkCandidates] = useState<Record<string, unknown>[]>([])
  const [evaluationRuns, setEvaluationRuns] = useState<Record<string, unknown>[]>([])

  const [errArtifacts, setErrArtifacts] = useState("")
  const [errVersions, setErrVersions] = useState("")
  const [errBenchCand, setErrBenchCand] = useState("")
  const [errRuns, setErrRuns] = useState("")
  const [formErr, setFormErr] = useState("")
  const [formOk, setFormOk] = useState("")

  const [artifactId, setArtifactId] = useState("")
  const [dataMode, setDataMode] = useState<"dataset_version" | "benchmark_registry">("dataset_version")
  const [datasetVersionId, setDatasetVersionId] = useState("")
  const [benchmarkDatasetId, setBenchmarkDatasetId] = useState("")
  const [split, setSplit] = useState<string>("validation")
  const [notes, setNotes] = useState("")

  const [detailById, setDetailById] = useState<Record<number, Record<string, unknown>>>({})
  const [detailLoading, setDetailLoading] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setErrArtifacts("")
    setErrVersions("")
    setErrBenchCand("")
    setErrRuns("")

    try {
      const a = await apiFetch<unknown>("/ml/model-artifacts?limit=500", { method: "GET" })
      setArtifacts(Array.isArray(a) ? (a.filter(isRecord) as Record<string, unknown>[]) : [])
    } catch (e) {
      setErrArtifacts(formatApiError(e, "Could not load model artifacts."))
      setArtifacts([])
    }

    try {
      const dv = await apiFetch<unknown>("/knowledge/dataset-versions?limit=500", { method: "GET" })
      setDatasetVersions(fixAsArray(dv).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setErrVersions(formatApiError(e, "Could not load dataset versions."))
      setDatasetVersions([])
    }

    try {
      const bc = await apiFetch<unknown>("/knowledge/benchmark-dataset-candidates?limit=500", { method: "GET" })
      setBenchmarkCandidates(fixAsArray(bc).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setErrBenchCand(formatApiError(e, "Could not load benchmark dataset candidates."))
      setBenchmarkCandidates([])
    }

    try {
      const er = await apiFetch<unknown>("/ml/evaluation-runs?limit=500", { method: "GET" })
      setEvaluationRuns(Array.isArray(er) ? (er.filter(isRecord) as Record<string, unknown>[]) : [])
    } catch (e) {
      setErrRuns(formatApiError(e, "Could not load evaluation runs."))
      setEvaluationRuns([])
    }

    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  const partialErr = Boolean(errArtifacts || errVersions || errBenchCand || errRuns)

  async function submitEvaluation() {
    setFormErr("")
    setFormOk("")
    const aid = Number.parseInt(artifactId, 10)
    if (!Number.isFinite(aid) || aid < 1) {
      setFormErr("model_artifact_id is required.")
      return
    }

    const metadata_json: Record<string, unknown> = {
      evaluation_split: split,
    }

    let dataset_version_id: number | null = null
    let benchmark_dataset_id: number | null = null

    if (dataMode === "dataset_version") {
      const dvid = Number.parseInt(datasetVersionId, 10)
      if (!Number.isFinite(dvid) || dvid < 1) {
        setFormErr("dataset_version_id is required when using dataset version.")
        return
      }
      dataset_version_id = dvid
    } else {
      const bid = Number.parseInt(benchmarkDatasetId, 10)
      if (!Number.isFinite(bid) || bid < 1) {
        setFormErr("benchmark_dataset_id is required when using benchmark registry target.")
        return
      }
      benchmark_dataset_id = bid
    }

    const notes_json = notes.trim() ? [notes.trim()] : []

    const body: Record<string, unknown> = {
      model_artifact_id: aid,
      dataset_version_id,
      benchmark_dataset_id,
      metrics_json: {},
      slice_metrics_json: {},
      error_examples_json: [],
      warnings_json: [],
      notes_json,
      metadata_json,
    }

    setSubmitBusy(true)
    try {
      const art = artifacts.find((r) => readRecordNumber(r, "id") === aid) ?? null
      const datasetType =
        dataMode === "benchmark_registry"
          ? "benchmark_registry"
          : (() => {
              const dvid = Number.parseInt(datasetVersionId, 10)
              const row = datasetVersions.find((r) => readRecordNumber(r, "id") === dvid)
              return (
                readStr(row ?? {}, ["required_dataset_type", "dataset_type"]) || undefined
              )
            })()
      const raw = await apiFetch<unknown>("/ml/evaluation-runs", { method: "POST", body })
      if (isRecord(raw)) {
        const st = readStr(raw, ["status"])
        const m = raw["metrics"]
        const w = raw["warnings"]
        trackMlEvaluationRunStarted({
          task_key: readStr(art ?? {}, ["task_key"]) || undefined,
          model_family: readStr(art ?? {}, ["model_family"]) || undefined,
          status: st || undefined,
          dataset_type: datasetType,
          metric_count: countMetricKeysForAnalytics(m),
          warning_count: Array.isArray(w) ? w.length : undefined,
        })
        if (st === "succeeded" || st === "failed" || st === "requires_review") {
          trackMlEvaluationRunCompleted({
            task_key: readStr(art ?? {}, ["task_key"]) || undefined,
            model_family: readStr(art ?? {}, ["model_family"]) || undefined,
            status: st,
            dataset_type: datasetType,
            metric_count: countMetricKeysForAnalytics(m),
            warning_count: Array.isArray(w) ? w.length : undefined,
          })
        }
      } else {
        trackMlEvaluationRunStarted({
          task_key: readStr(art ?? {}, ["task_key"]) || undefined,
          model_family: readStr(art ?? {}, ["model_family"]) || undefined,
          dataset_type: datasetType,
        })
      }
      setFormOk("Evaluation run submitted.")
      setReloadToken((x) => x + 1)
    } catch (e) {
      setFormErr(formatApiError(e, "Could not start evaluation run."))
    } finally {
      setSubmitBusy(false)
    }
  }

  const loadDetail = useCallback(async (evaluationRunId: number) => {
    setDetailLoading(evaluationRunId)
    try {
      const raw = await apiFetch<unknown>(`/ml/evaluation-runs/${evaluationRunId}`, { method: "GET" })
      if (isRecord(raw)) {
        setDetailById((prev) => ({ ...prev, [evaluationRunId]: raw }))
      }
    } catch {
      /* keep list row only */
    } finally {
      setDetailLoading(null)
    }
  }, [])

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
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal-ink)" }}
          >
            MolTrace · ML Evaluation
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">ML Evaluation</h1>
          <p className="text-sm text-muted-foreground">
            Run evaluations against dataset versions or benchmark registry datasets; review metrics and summaries only.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" aria-hidden />
        <AlertTitle className="text-sm">Privacy</AlertTitle>
        <AlertDescription className="text-sm text-muted-foreground">
          Tables show IDs and summaries — not raw knowledge records or source text. Full payloads stay in collapsed
          developer JSON for audit use.
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
            {errArtifacts ? <p>GET /ml/model-artifacts: {errArtifacts}</p> : null}
            {errVersions ? <p>GET /knowledge/dataset-versions: {errVersions}</p> : null}
            {errBenchCand ? <p>GET /knowledge/benchmark-dataset-candidates: {errBenchCand}</p> : null}
            {errRuns ? <p>GET /ml/evaluation-runs: {errRuns}</p> : null}
          </AlertDescription>
        </Alert>
      ) : null}

      <ModuleCard
        accent="teal"
        eyebrow="Launch"
        title="Run evaluation"
        icon={PlayCircle}
        description="Launch a model evaluation run against a dataset version or benchmark dataset. Evaluation split and configuration are stored with the run for reproducibility."
      >
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="artifact">model_artifact_id</Label>
            <Select value={artifactId || undefined} onValueChange={setArtifactId}>
              <SelectTrigger id="artifact">
                <SelectValue placeholder="Select artifact" />
              </SelectTrigger>
              <SelectContent>
                {artifacts.map((row) => {
                  const id = readRecordNumber(row, "id")
                  if (id == null) return null
                  const mn = readRecordString(row, "model_name") ?? ""
                  const mv = readRecordString(row, "model_version") ?? ""
                  const tk = readRecordString(row, "task_key") ?? ""
                  return (
                    <SelectItem key={id} value={String(id)}>
                      #{id} {mn} {mv ? `(${mv})` : ""} · {tk}
                    </SelectItem>
                  )
                })}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-3">
            <Label className="text-sm font-medium">Evaluation data target</Label>
            <RadioGroup
              value={dataMode}
              onValueChange={(v) => setDataMode(v as "dataset_version" | "benchmark_registry")}
              className="flex flex-col gap-3 sm:flex-row sm:gap-6"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="dataset_version" id="dm-dv" />
                <Label htmlFor="dm-dv" className="font-normal">
                  Dataset version
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="benchmark_registry" id="dm-bm" />
                <Label htmlFor="dm-bm" className="font-normal">
                  Benchmark dataset (registry id)
                </Label>
              </div>
            </RadioGroup>
          </div>

          {dataMode === "dataset_version" ? (
            <div className="space-y-2">
              <Label htmlFor="dsv">dataset_version_id</Label>
              <Select value={datasetVersionId || undefined} onValueChange={setDatasetVersionId}>
                <SelectTrigger id="dsv">
                  <SelectValue placeholder="Select dataset version" />
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
          ) : (
            <div className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="benchmark-id">benchmark_dataset_id</Label>
                <Input
                  id="benchmark-id"
                  inputMode="numeric"
                  value={benchmarkDatasetId}
                  onChange={(e) => setBenchmarkDatasetId(e.target.value)}
                  placeholder="Registry benchmark_dataset_id"
                  autoComplete="off"
                />
                <p className="text-xs text-muted-foreground">
                  Candidates from GET /knowledge/benchmark-dataset-candidates may expose{" "}
                  <code className="text-[11px]">metadata_json.benchmark_dataset_id</code> when promoted — paste or pick a
                  helper id below.
                </p>
              </div>
              <div className="space-y-2">
                <Label>Candidate reference (optional)</Label>
                <Select
                  onValueChange={(v) => {
                    const row = benchmarkCandidates.find((r) => String(readRecordNumber(r, "id")) === v)
                    const metaId = row ? readMetadataBenchmarkId(row) : null
                    if (metaId != null) setBenchmarkDatasetId(String(metaId))
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Fill benchmark_dataset_id from candidate metadata when present" />
                  </SelectTrigger>
                  <SelectContent>
                    {benchmarkCandidates.map((row) => {
                      const cid = readRecordNumber(row, "id")
                      if (cid == null) return null
                      const rt = readRecordString(row, "record_type") ?? ""
                      const rid = readRecordNumber(row, "record_id")
                      const bt = readRecordString(row, "benchmark_type") ?? ""
                      return (
                        <SelectItem key={cid} value={String(cid)}>
                          candidate #{cid} · {rt}/{rid} · {bt}
                        </SelectItem>
                      )
                    })}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="split">evaluation_split (metadata_json)</Label>
              <Select value={split} onValueChange={setSplit}>
                <SelectTrigger id="split">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SPLIT_OPTIONS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="notes">notes (optional → notes_json)</Label>
              <Textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
            </div>
          </div>

          {formErr ? <p className="text-sm text-destructive">{formErr}</p> : null}
          {formOk ? <p className="text-sm text-muted-foreground">{formOk}</p> : null}

          <Button type="button" disabled={submitBusy || loading} onClick={() => void submitEvaluation()}>
            {submitBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Run evaluation
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Runs"
        title="Evaluation runs"
        icon={Activity}
        description="All model evaluation runs — status, metric summary, and artifact linkage. Select Load detail to expand full metrics and per-split breakdowns."
      >
        <div className="space-y-6">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errRuns ? (
            <p className="text-sm text-muted-foreground">{errRuns}</p>
          ) : evaluationRuns.length === 0 ? (
            <p className="text-sm text-muted-foreground">No evaluation runs returned.</p>
          ) : (
            evaluationRuns.map((row, idx) => {
              const id = readRecordNumber(row, "id")
              const rowKey = id != null ? `ev-${id}` : `ev-i-${idx}`
              const st = readStr(row, ["status"])
              const dvid = readRecordNumber(row, "dataset_version_id")
              const bid = readRecordNumber(row, "benchmark_dataset_id")
              const metricsRaw = row["metrics_json"]
              const sliceRaw = row["slice_metrics_json"]
              const calRaw = row["calibration_summary_json"]
              const warnList = readStringList(row["warnings_json"])
              const notesList = readStringList(row["notes_json"])
              const errorsRaw = row["error_examples_json"]
              const detail = id != null ? detailById[id] : undefined
              const metricsPayload = detail?.metrics ?? detail?.metrics_json ?? metricsRaw
              const slicePayload = detail?.slice_metrics ?? detail?.slice_metrics_json ?? sliceRaw
              const calPayload = detail?.calibration_summary ?? detail?.calibration_summary_json ?? calRaw
              const warnPayload = detail?.warnings ?? warnList
              const notesPayload = detail?.notes ?? notesList
              const errorsPayload = detail?.error_examples ?? errorsRaw

              const metricRecords = Array.isArray(row["metric_records"]) ? row["metric_records"] : []

              return (
                <Fragment key={rowKey}>
                  <div className="rounded-lg border">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs">#{id ?? "—"}</span>
                        <Badge variant="secondary">{st || "—"}</Badge>
                        <span className="text-xs text-muted-foreground">
                          dataset_version_id: {dvid ?? "—"} · benchmark_dataset_id: {bid ?? "—"}
                        </span>
                      </div>
                      {id != null ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={detailLoading === id}
                          onClick={() => void loadDetail(id)}
                        >
                          {detailLoading === id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                          Load detail
                        </Button>
                      ) : null}
                    </div>

                    <div className="space-y-4 p-3">
                      <div>
                        <h4 className="mb-2 text-sm font-medium">Metrics</h4>
                        <div className="table-scroll min-w-0">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>metric</TableHead>
                                <TableHead>split</TableHead>
                                <TableHead>value</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {metricRecords.length > 0
                                ? (metricRecords as Record<string, unknown>[]).map((m, mi) => (
                                    <TableRow key={`mr-${mi}`}>
                                      <TableCell className="font-mono text-xs">
                                        {readStr(m, ["metric_name"]) || "—"}
                                      </TableCell>
                                      <TableCell className="font-mono text-xs">{readStr(m, ["split"]) || "—"}</TableCell>
                                      <TableCell className="font-mono text-xs">
                                        {readStr(m, ["metric_value"]) || "—"} {readStr(m, ["metric_unit"]) || ""}
                                      </TableCell>
                                    </TableRow>
                                  ))
                                : objectEntriesTable(metricsPayload).map((r) => (
                                    <TableRow key={r.key}>
                                      <TableCell className="font-mono text-xs">{r.key}</TableCell>
                                      <TableCell className="text-xs">—</TableCell>
                                      <TableCell className="text-xs">{r.value}</TableCell>
                                    </TableRow>
                                  ))}
                              {!metricRecords.length && objectEntriesTable(metricsPayload).length === 0 ? (
                                <TableRow>
                                  <TableCell colSpan={3} className="text-xs text-muted-foreground">
                                    —
                                  </TableCell>
                                </TableRow>
                              ) : null}
                            </TableBody>
                          </Table>
                        </div>
                      </div>

                      <div>
                        <h4 className="mb-2 text-sm font-medium">Slice metrics</h4>
                        <div className="table-scroll min-w-0">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>slice</TableHead>
                                <TableHead>summary</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {objectEntriesTable(slicePayload).map((r) => (
                                <TableRow key={r.key}>
                                  <TableCell className="font-mono text-xs">{r.key}</TableCell>
                                  <TableCell className="text-xs">{r.value}</TableCell>
                                </TableRow>
                              ))}
                              {objectEntriesTable(slicePayload).length === 0 ? (
                                <TableRow>
                                  <TableCell colSpan={2} className="text-xs text-muted-foreground">
                                    —
                                  </TableCell>
                                </TableRow>
                              ) : null}
                            </TableBody>
                          </Table>
                        </div>
                      </div>

                      {calPayload != null && isRecord(calPayload) && Object.keys(calPayload).length > 0 ? (
                        <div>
                          <h4 className="mb-2 text-sm font-medium">Calibration summary</h4>
                          <div className="table-scroll min-w-0">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>field</TableHead>
                                  <TableHead>value</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {objectEntriesTable(calPayload).map((r) => (
                                  <TableRow key={r.key}>
                                    <TableCell className="font-mono text-xs">{r.key}</TableCell>
                                    <TableCell className="text-xs">{r.value}</TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </div>
                        </div>
                      ) : null}

                      <div>
                        <h4 className="mb-2 text-sm font-medium">Error examples (summary)</h4>
                        <div className="table-scroll min-w-0">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>case_id</TableHead>
                                <TableHead>summary</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {Array.isArray(errorsPayload) && errorsPayload.length > 0 ? (
                                errorsPayload.slice(0, 50).map((ex, ei) => {
                                  const s = sanitizeErrorExample(ex)
                                  return (
                                    <TableRow key={`ex-${ei}`}>
                                      <TableCell className="font-mono text-xs">{s.caseId}</TableCell>
                                      <TableCell className="text-xs">{s.summary}</TableCell>
                                    </TableRow>
                                  )
                                })
                              ) : (
                                <TableRow>
                                  <TableCell colSpan={2} className="text-xs text-muted-foreground">
                                    —
                                  </TableCell>
                                </TableRow>
                              )}
                            </TableBody>
                          </Table>
                        </div>
                      </div>

                      <div>
                        <h4 className="mb-2 text-sm font-medium">Warnings</h4>
                        <ul className="list-inside list-disc text-sm text-muted-foreground">
                          {(Array.isArray(warnPayload) ? warnPayload : warnList).length ? (
                            (Array.isArray(warnPayload) ? warnPayload : warnList).map((w, wi) => (
                              <li key={`w-${wi}`}>{typeof w === "string" ? w : summarizeJson(w)}</li>
                            ))
                          ) : (
                            <li>—</li>
                          )}
                        </ul>
                      </div>

                      <div>
                        <h4 className="mb-2 text-sm font-medium">Notes</h4>
                        <ul className="list-inside list-disc text-sm text-muted-foreground">
                          {(Array.isArray(notesPayload) ? notesPayload : notesList).length ? (
                            (Array.isArray(notesPayload) ? notesPayload : notesList).map((n, ni) => (
                              <li key={`n-${ni}`}>{typeof n === "string" ? n : summarizeJson(n)}</li>
                            ))
                          ) : (
                            <li>—</li>
                          )}
                        </ul>
                      </div>

                      <DeveloperJsonPanel data={detail ?? row} />
                    </div>
                  </div>
                </Fragment>
              )
            })
          )}
        </div>
      </ModuleCard>
    </div>
  )
}
