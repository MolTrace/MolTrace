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
import { Input } from "@/components/ui/input"
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
import { countMetricKeysForAnalytics, trackMlErrorAnalysisCreated } from "@/src/lib/analytics/analytics-client"
import { ArrowLeft, Layers, ListChecks, Loader2, Plus, RefreshCw } from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

/** Backend ErrorAnalysisSliceType — slice table for UI. */
const SLICE_TYPES = [
  "molecule_class",
  "nucleus",
  "solvent",
  "mass_range",
  "reaction_type",
  "variable_type",
  "jurisdiction",
  "source_type",
  "confidence_bin",
  "other",
] as const

const SEVERITY_OPTIONS = ["info", "warning", "high", "critical"] as const

function sanitizeRepresentative(ex: unknown): { label: string; detail: string } {
  if (!isRecord(ex)) return { label: "—", detail: "—" }
  const id = readRecordString(ex, "case_id") ?? readRecordString(ex, "id") ?? "—"
  const msg =
    readRecordString(ex, "error") ?? readRecordString(ex, "message") ?? readRecordString(ex, "summary") ?? ""
  const detail = msg.length > 100 ? `${msg.slice(0, 100)}…` : msg || "—"
  return { label: String(id), detail }
}

export function MlErrorAnalysisWorkspace() {
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [submitBusy, setSubmitBusy] = useState(false)
  const [evalRuns, setEvalRuns] = useState<Record<string, unknown>[]>([])
  const [slices, setSlices] = useState<Record<string, unknown>[]>([])
  const [errLoad, setErrLoad] = useState("")
  const [formErr, setFormErr] = useState("")
  const [formOk, setFormOk] = useState("")

  const [evalRunId, setEvalRunId] = useState("")
  const [sliceName, setSliceName] = useState("")
  const [sliceType, setSliceType] = useState<string>("other")
  const [sampleCount, setSampleCount] = useState("0")
  const [metricsJson, setMetricsJson] = useState("{}")
  const [repErrorsJson, setRepErrorsJson] = useState("[]")
  const [severity, setSeverity] = useState<string>("info")

  const [detailId, setDetailId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setErrLoad("")
    try {
      const [e, s] = await Promise.all([
        apiFetch<unknown>("/ml/evaluation-runs?limit=500", { method: "GET" }),
        apiFetch<unknown>("/ml/error-analysis?limit=500", { method: "GET" }),
      ])
      setEvalRuns(Array.isArray(e) ? (e.filter(isRecord) as Record<string, unknown>[]) : [])
      setSlices(Array.isArray(s) ? (s.filter(isRecord) as Record<string, unknown>[]) : [])
    } catch (er) {
      setErrLoad(formatApiError(er, "Could not load error analysis data."))
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load, reload])

  async function submitSlice() {
    setFormErr("")
    setFormOk("")
    const eid = Number.parseInt(evalRunId, 10)
    if (!Number.isFinite(eid) || eid < 1) {
      setFormErr("evaluation_run_id is required.")
      return
    }
    const sn = sliceName.trim()
    if (!sn) {
      setFormErr("slice_name is required.")
      return
    }
    const sc = Number.parseInt(sampleCount, 10)
    if (!Number.isFinite(sc) || sc < 0) {
      setFormErr("sample_count must be a non-negative integer.")
      return
    }
    let metrics_json: Record<string, unknown>
    let representative_errors_json: unknown[]
    try {
      const om = JSON.parse(metricsJson.trim() || "{}") as unknown
      if (!om || typeof om !== "object" || Array.isArray(om)) {
        setFormErr("metrics_json must be a JSON object.")
        return
      }
      metrics_json = om as Record<string, unknown>
      const re = JSON.parse(repErrorsJson.trim() || "[]") as unknown
      if (!Array.isArray(re)) {
        setFormErr("representative_errors_json must be a JSON array.")
        return
      }
      representative_errors_json = re
    } catch {
      setFormErr("metrics_json and representative_errors_json must be valid JSON.")
      return
    }

    setSubmitBusy(true)
    try {
      await apiFetch("/ml/error-analysis", {
        method: "POST",
        body: {
          evaluation_run_id: eid,
          slice_name: sn,
          slice_type: sliceType,
          sample_count: sc,
          metrics_json,
          representative_errors_json,
          severity,
          metadata_json: {},
        },
      })
      trackMlErrorAnalysisCreated({
        status: severity,
        metric_count: countMetricKeysForAnalytics(metrics_json),
        warning_count: representative_errors_json.length,
      })
      setFormOk("Error analysis slice recorded.")
      setReload((x) => x + 1)
    } catch (er) {
      setFormErr(formatApiError(er, "Could not create error analysis slice."))
    } finally {
      setSubmitBusy(false)
    }
  }

  async function loadDetail(id: number) {
    setDetailId(id)
    setDetailLoading(true)
    setDetail(null)
    try {
      const raw = await apiFetch<unknown>(`/ml/error-analysis/${id}`, { method: "GET" })
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
          <h1 className="font-mono text-2xl font-bold tracking-tight">Error analysis</h1>
          <p className="text-muted-foreground">
            Slice-level error summaries; representative_errors_json stores compact entries — not full raw records.
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
        eyebrow="Reference"
        title="Slice types (reference)"
        icon={Layers}
        description={<><code className="text-xs">slice_type</code> values align with backend literals.</>}
      >
        <div>
          <div className="flex flex-wrap gap-2">
            {SLICE_TYPES.map((t) => (
              <Badge key={t} variant="secondary" className="font-mono text-xs">
                {t}
              </Badge>
            ))}
          </div>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Create"
        title="Create error analysis slice"
        icon={Plus}
        description="Define an error analysis slice on an evaluation run — specify slice type, severity, sample count, per-slice metrics, and representative failure cases."
      >
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>evaluation_run_id</Label>
            <Select value={evalRunId || undefined} onValueChange={setEvalRunId}>
              <SelectTrigger>
                <SelectValue placeholder="Select evaluation run" />
              </SelectTrigger>
              <SelectContent>
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
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="sn">slice_name</Label>
              <Input id="sn" value={sliceName} onChange={(e) => setSliceName(e.target.value)} autoComplete="off" />
            </div>
            <div className="space-y-2">
              <Label>slice_type</Label>
              <Select value={sliceType} onValueChange={setSliceType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SLICE_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="sc">sample_count</Label>
              <Input id="sc" inputMode="numeric" value={sampleCount} onChange={(e) => setSampleCount(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>severity</Label>
              <Select value={severity} onValueChange={setSeverity}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SEVERITY_OPTIONS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="error-analysis-metrics-json">metrics_json</Label>
            <Textarea id="error-analysis-metrics-json" className="min-h-[72px] font-mono text-xs" value={metricsJson} onChange={(e) => setMetricsJson(e.target.value)} spellCheck={false} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="error-analysis-rep-errors-json">representative_errors_json (summary entries)</Label>
            <Textarea
              id="error-analysis-rep-errors-json"
              className="min-h-[100px] font-mono text-xs"
              value={repErrorsJson}
              onChange={(e) => setRepErrorsJson(e.target.value)}
              spellCheck={false}
              placeholder='[{"case_id":"…","error":"…"}]'
            />
          </div>
          {formErr ? <p className="text-sm text-destructive">{formErr}</p> : null}
          {formOk ? <p className="text-sm text-muted-foreground">{formOk}</p> : null}
          <Button type="button" disabled={submitBusy || loading} onClick={() => void submitSlice()}>
            {submitBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Submit error analysis slice
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Records"
        title="Slices"
        icon={ListChecks}
        description="Error analysis slices logged for this tenant — slice type, severity, sample count, and linked evaluation run."
      >
        <div className="space-y-4">
          <div className="table-scroll min-w-0">
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : slices.length === 0 ? (
              <p className="text-sm text-muted-foreground">No slices returned.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[72px]">id</TableHead>
                    <TableHead>evaluation_run_id</TableHead>
                    <TableHead>slice_type</TableHead>
                    <TableHead>slice_name</TableHead>
                    <TableHead>sample_count</TableHead>
                    <TableHead>severity</TableHead>
                    <TableHead>representative (summary)</TableHead>
                    <TableHead className="w-[90px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {slices.map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    const reps = row["representative_errors_json"]
                    const repPreview =
                      Array.isArray(reps) && reps.length > 0 ? `${reps.length} entr${reps.length === 1 ? "y" : "ies"}` : "—"
                    return (
                      <TableRow key={id != null ? `ea-${id}` : `ea-${idx}`}>
                        <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readRecordNumber(row, "evaluation_run_id") ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readRecordString(row, "slice_type") ?? "—"}</TableCell>
                        <TableCell className="max-w-[180px] truncate text-sm">{readRecordString(row, "slice_name") ?? "—"}</TableCell>
                        <TableCell className="tabular-nums text-sm">{readRecordNumber(row, "sample_count") ?? "—"}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{readRecordString(row, "severity") ?? "—"}</Badge>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{repPreview}</TableCell>
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
                GET /ml/error-analysis/{detailId}
                {detailLoading ? <Loader2 className="ml-2 inline h-4 w-4 animate-spin" aria-hidden /> : null}
              </p>
              {detail ? (
                <>
                  <div>
                    <h4 className="mb-2 text-sm font-medium">Representative errors (summary)</h4>
                    <div className="table-scroll min-w-0">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>case_id</TableHead>
                            <TableHead>summary</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {Array.isArray(detail["representative_errors_json"])
                            ? (detail["representative_errors_json"] as unknown[]).slice(0, 40).map((ex, i) => {
                                const s = sanitizeRepresentative(ex)
                                return (
                                  <TableRow key={`re-${i}`}>
                                    <TableCell className="font-mono text-xs">{s.label}</TableCell>
                                    <TableCell className="max-w-[400px] text-xs">{s.detail}</TableCell>
                                  </TableRow>
                                )
                              })
                            : (
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
