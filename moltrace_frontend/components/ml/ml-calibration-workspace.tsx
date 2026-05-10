"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Label } from "@/components/ui/label"
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
import { countMetricKeysForAnalytics, trackMlCalibrationAssessmentCreated } from "@/src/lib/analytics/analytics-client"
import { ArrowLeft, ListChecks, Loader2, Plus, RefreshCw } from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function summarizeJson(raw: unknown, maxLen = 140): string {
  if (raw == null) return "—"
  if (typeof raw === "object") {
    const s = JSON.stringify(raw)
    return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s
  }
  return String(raw)
}

function objectRows(raw: unknown): { key: string; value: string }[] {
  if (!isRecord(raw)) return []
  return Object.entries(raw).map(([k, v]) => ({
    key: k,
    value: summarizeJson(v, 200),
  }))
}

const CALIBRATION_METHODS = [
  "reliability_curve",
  "isotonic",
  "platt",
  "conformal",
  "heuristic",
  "not_assessed",
] as const

const CALIBRATION_STATUS = ["not_assessed", "acceptable", "warning", "failed", "requires_review"] as const

export function MlCalibrationWorkspace() {
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [submitBusy, setSubmitBusy] = useState(false)
  const [artifacts, setArtifacts] = useState<Record<string, unknown>[]>([])
  const [evalRuns, setEvalRuns] = useState<Record<string, unknown>[]>([])
  const [assessments, setAssessments] = useState<Record<string, unknown>[]>([])
  const [errLoad, setErrLoad] = useState("")
  const [formErr, setFormErr] = useState("")
  const [formOk, setFormOk] = useState("")
  const [detailId, setDetailId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [artifactId, setArtifactId] = useState("")
  const [evalRunId, setEvalRunId] = useState("")
  const [method, setMethod] = useState<string>("not_assessed")
  const [metricsJson, setMetricsJson] = useState("{}")
  const [statusDraft, setStatusDraft] = useState<string>("not_assessed")
  const [notesLine, setNotesLine] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setErrLoad("")
    try {
      const [a, e, c] = await Promise.all([
        apiFetch<unknown>("/ml/model-artifacts?limit=500", { method: "GET" }),
        apiFetch<unknown>("/ml/evaluation-runs?limit=500", { method: "GET" }),
        apiFetch<unknown>("/ml/calibration-assessments?limit=500", { method: "GET" }),
      ])
      setArtifacts(Array.isArray(a) ? (a.filter(isRecord) as Record<string, unknown>[]) : [])
      setEvalRuns(Array.isArray(e) ? (e.filter(isRecord) as Record<string, unknown>[]) : [])
      setAssessments(Array.isArray(c) ? (c.filter(isRecord) as Record<string, unknown>[]) : [])
    } catch (er) {
      setErrLoad(formatApiError(er, "Could not load calibration data."))
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load, reload])

  async function submitAssessment() {
    setFormErr("")
    setFormOk("")
    const aid = Number.parseInt(artifactId, 10)
    if (!Number.isFinite(aid) || aid < 1) {
      setFormErr("model_artifact_id is required.")
      return
    }
    let calibration_metrics_json: Record<string, unknown>
    try {
      const o = JSON.parse(metricsJson.trim() || "{}") as unknown
      if (!o || typeof o !== "object" || Array.isArray(o)) {
        setFormErr("calibration_metrics_json must be a JSON object.")
        return
      }
      calibration_metrics_json = o as Record<string, unknown>
    } catch {
      setFormErr("calibration_metrics_json must be valid JSON.")
      return
    }

    const eid = Number.parseInt(evalRunId, 10)
    const body: Record<string, unknown> = {
      model_artifact_id: aid,
      evaluation_run_id: Number.isFinite(eid) && eid >= 1 ? eid : null,
      calibration_method: method,
      calibration_metrics_json,
      status: statusDraft,
      warnings_json: [],
      notes_json: notesLine.trim() ? [notesLine.trim()] : [],
      metadata_json: {},
    }

    setSubmitBusy(true)
    try {
      await apiFetch("/ml/calibration-assessments", { method: "POST", body })
      trackMlCalibrationAssessmentCreated({
        status: statusDraft,
        metric_count: countMetricKeysForAnalytics(calibration_metrics_json),
        warning_count: 0,
      })
      setFormOk("Calibration assessment recorded.")
      setReload((x) => x + 1)
    } catch (er) {
      setFormErr(formatApiError(er, "Could not create calibration assessment."))
    } finally {
      setSubmitBusy(false)
    }
  }

  async function loadDetail(id: number) {
    setDetailId(id)
    setDetailLoading(true)
    setDetail(null)
    try {
      const raw = await apiFetch<unknown>(`/ml/calibration-assessments/${id}`, { method: "GET" })
      setDetail(isRecord(raw) ? raw : null)
    } catch {
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Button variant="ghost" size="sm" className="mb-1 h-8 px-2" asChild>
            <Link href="/ml" className="inline-flex items-center gap-1 text-muted-foreground">
              <ArrowLeft className="h-4 w-4" aria-hidden />
              ML Model Factory
            </Link>
          </Button>
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal)" }}
          >
            MolTrace · ML Calibration
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Calibration assessments</h1>
          <p className="text-sm text-muted-foreground">
            Assess probabilistic calibration using registry methods; metrics and status come from the API.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => setReload((x) => x + 1)}>
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <RefreshCw className="mr-2 h-4 w-4" aria-hidden />}
          Refresh
        </Button>
      </div>

      {errLoad ? (
        <Alert variant="destructive">
          <AlertTitle>Load error</AlertTitle>
          <AlertDescription>{errLoad}</AlertDescription>
        </Alert>
      ) : null}

      <ModuleCard
        accent="teal"
        eyebrow="Create"
        title="Create calibration assessment"
        icon={Plus}
        description="Log a calibration assessment for a model artifact — specify calibration method, metrics, and optional linked evaluation run."
      >
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>model_artifact_id</Label>
              <Select value={artifactId || undefined} onValueChange={setArtifactId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select artifact" />
                </SelectTrigger>
                <SelectContent>
                  {artifacts.map((row) => {
                    const id = readRecordNumber(row, "id")
                    if (id == null) return null
                    return (
                      <SelectItem key={id} value={String(id)}>
                        #{id} {readRecordString(row, "model_name") ?? ""}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>evaluation_run_id (optional)</Label>
              <Select value={evalRunId || "__none__"} onValueChange={(v) => setEvalRunId(v === "__none__" ? "" : v)}>
                <SelectTrigger>
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">None</SelectItem>
                  {evalRuns.map((row) => {
                    const id = readRecordNumber(row, "id")
                    if (id == null) return null
                    return (
                      <SelectItem key={id} value={String(id)}>
                        #{id} {readRecordString(row, "status") ?? ""}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>calibration_method</Label>
              <Select value={method} onValueChange={setMethod}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CALIBRATION_METHODS.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>status</Label>
              <Select value={statusDraft} onValueChange={setStatusDraft}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CALIBRATION_STATUS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label>calibration_metrics_json</Label>
            <Textarea className="min-h-[88px] font-mono text-xs" value={metricsJson} onChange={(e) => setMetricsJson(e.target.value)} spellCheck={false} />
          </div>
          <div className="space-y-2">
            <Label>notes_json (single line → one entry)</Label>
            <Textarea value={notesLine} onChange={(e) => setNotesLine(e.target.value)} rows={2} />
          </div>
          {formErr ? <p className="text-sm text-destructive">{formErr}</p> : null}
          {formOk ? <p className="text-sm text-muted-foreground">{formOk}</p> : null}
          <Button type="button" disabled={submitBusy || loading} onClick={() => void submitAssessment()}>
            {submitBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Submit calibration assessment
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Records"
        title="Assessments"
        icon={ListChecks}
        description="Calibration assessments logged for this tenant — method, status, and linked artifact and evaluation run."
      >
        <div className="space-y-4">
          <div className="table-scroll min-w-0">
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : assessments.length === 0 ? (
              <p className="text-sm text-muted-foreground">No assessments returned.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[72px]">id</TableHead>
                    <TableHead>model_artifact_id</TableHead>
                    <TableHead>evaluation_run_id</TableHead>
                    <TableHead>calibration_method</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>calibration_metrics_json</TableHead>
                    <TableHead className="w-[100px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {assessments.map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    return (
                      <TableRow key={id != null ? `ca-${id}` : `ca-${idx}`}>
                        <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readRecordNumber(row, "model_artifact_id") ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readRecordNumber(row, "evaluation_run_id") ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readRecordString(row, "calibration_method") ?? "—"}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                        </TableCell>
                        <TableCell className="max-w-[240px] truncate text-xs text-muted-foreground">
                          {summarizeJson(row["calibration_metrics_json"])}
                        </TableCell>
                        <TableCell>
                          {id != null ? (
                            <Button type="button" variant="outline" size="sm" onClick={() => void loadDetail(id)}>
                              Detail
                            </Button>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </div>

          {detailId != null ? (
            <div className="space-y-3 rounded-lg border p-3">
              <p className="text-sm font-medium">
                GET /ml/calibration-assessments/{detailId}
                {detailLoading ? <Loader2 className="ml-2 inline h-4 w-4 animate-spin" aria-hidden /> : null}
              </p>
              {detail ? (
                <>
                  <div className="table-scroll min-w-0">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>field</TableHead>
                          <TableHead>value (summary)</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {objectRows(detail["calibration_metrics_json"]).map((r) => (
                          <TableRow key={r.key}>
                            <TableCell className="font-mono text-xs">{r.key}</TableCell>
                            <TableCell className="text-xs">{r.value}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  <DeveloperJsonPanel data={detail} />
                </>
              ) : !detailLoading ? (
                <p className="text-sm text-muted-foreground">Could not load detail.</p>
              ) : null}
            </div>
          ) : null}
        </div>
      </ModuleCard>
    </div>
  )
}
