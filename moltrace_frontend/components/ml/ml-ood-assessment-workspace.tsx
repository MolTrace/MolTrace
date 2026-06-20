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
import { countMetricKeysForAnalytics, trackMlOodAssessmentCreated } from "@/src/lib/analytics/analytics-client"
import { ArrowLeft, Loader2, Plus, RefreshCw, ShieldAlert } from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function summarizeJson(raw: unknown, maxLen = 160): string {
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
    value: summarizeJson(v, 220),
  }))
}

const OOD_METHODS = ["feature_distance", "embedding_distance", "rule_based", "unknown"] as const

const OOD_STATUS = ["not_assessed", "acceptable", "warning", "failed", "requires_review"] as const

function summarizeRegion(r: unknown, i: number): { key: string; summary: string } {
  if (!isRecord(r)) return { key: `row-${i}`, summary: "—" }
  const label =
    readRecordString(r, "region") ??
    readRecordString(r, "name") ??
    readRecordString(r, "slice") ??
    String(i)
  return { key: label, summary: summarizeJson(r, 180) }
}

export function MlOodAssessmentWorkspace() {
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [submitBusy, setSubmitBusy] = useState(false)
  const [artifacts, setArtifacts] = useState<Record<string, unknown>[]>([])
  const [datasetVersions, setDatasetVersions] = useState<Record<string, unknown>[]>([])
  const [assessments, setAssessments] = useState<Record<string, unknown>[]>([])
  const [errLoad, setErrLoad] = useState("")
  const [formErr, setFormErr] = useState("")
  const [formOk, setFormOk] = useState("")

  const [artifactId, setArtifactId] = useState("")
  const [datasetVersionId, setDatasetVersionId] = useState("")
  const [method, setMethod] = useState<string>("rule_based")
  const [summaryJson, setSummaryJson] = useState("{}")
  const [regionsJson, setRegionsJson] = useState("[]")
  const [statusDraft, setStatusDraft] = useState<string>("requires_review")

  const [detailId, setDetailId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setErrLoad("")
    try {
      const [a, d, o] = await Promise.all([
        apiFetch<unknown>("/ml/model-artifacts?limit=500", { method: "GET" }),
        apiFetch<unknown>("/knowledge/dataset-versions?limit=500", { method: "GET" }),
        apiFetch<unknown>("/ml/ood-assessments?limit=500", { method: "GET" }),
      ])
      setArtifacts(Array.isArray(a) ? (a.filter(isRecord) as Record<string, unknown>[]) : [])
      setDatasetVersions(
        Array.isArray(d) ? (d.filter(isRecord) as Record<string, unknown>[]) : [],
      )
      setAssessments(Array.isArray(o) ? (o.filter(isRecord) as Record<string, unknown>[]) : [])
    } catch (er) {
      setErrLoad(formatApiError(er, "Could not load OOD assessment data."))
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load, reload])

  async function submitOod() {
    setFormErr("")
    setFormOk("")
    const aid = Number.parseInt(artifactId, 10)
    if (!Number.isFinite(aid) || aid < 1) {
      setFormErr("model_artifact_id is required.")
      return
    }
    let ood_summary_json: Record<string, unknown>
    let high_risk_regions_json: unknown[]
    try {
      const os = JSON.parse(summaryJson.trim() || "{}") as unknown
      if (!os || typeof os !== "object" || Array.isArray(os)) {
        setFormErr("ood_summary_json must be a JSON object.")
        return
      }
      ood_summary_json = os as Record<string, unknown>
      const hr = JSON.parse(regionsJson.trim() || "[]") as unknown
      if (!Array.isArray(hr)) {
        setFormErr("high_risk_regions_json must be a JSON array.")
        return
      }
      high_risk_regions_json = hr
    } catch {
      setFormErr("ood_summary_json and high_risk_regions_json must be valid JSON.")
      return
    }

    const dvid = Number.parseInt(datasetVersionId, 10)
    const body: Record<string, unknown> = {
      model_artifact_id: aid,
      dataset_version_id: Number.isFinite(dvid) && dvid >= 1 ? dvid : null,
      method,
      ood_summary_json,
      high_risk_regions_json,
      status: statusDraft,
      metadata_json: {},
    }

    setSubmitBusy(true)
    try {
      await apiFetch("/ml/ood-assessments", { method: "POST", body })
      trackMlOodAssessmentCreated({
        status: statusDraft,
        metric_count: countMetricKeysForAnalytics(ood_summary_json),
        warning_count: high_risk_regions_json.length,
      })
      setFormOk("Out-of-domain assessment recorded.")
      setReload((x) => x + 1)
    } catch (er) {
      setFormErr(formatApiError(er, "Could not create OOD assessment."))
    } finally {
      setSubmitBusy(false)
    }
  }

  async function loadDetail(id: number) {
    setDetailId(id)
    setDetailLoading(true)
    setDetail(null)
    try {
      const raw = await apiFetch<unknown>(`/ml/ood-assessments/${id}`, { method: "GET" })
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
          <h1 className="font-mono text-2xl font-bold tracking-tight">Out-of-domain assessments</h1>
          <p className="text-muted-foreground">
            Assess distribution shift using declared methods; high-risk regions are summarized — not raw confidential inputs.
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
        title="Create OOD assessment"
        icon={Plus}
        description="Run an out-of-distribution applicability assessment on a model artifact — flags high-risk structural regions where predictions are less reliable."
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
              <Label>dataset_version_id (optional)</Label>
              <Select value={datasetVersionId || "__none__"} onValueChange={(v) => setDatasetVersionId(v === "__none__" ? "" : v)}>
                <SelectTrigger>
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">None</SelectItem>
                  {datasetVersions.map((row) => {
                    const id = readRecordNumber(row, "id")
                    if (id == null) return null
                    return (
                      <SelectItem key={id} value={String(id)}>
                        #{id} {readRecordString(row, "name") ?? ""}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>method</Label>
              <Select value={method} onValueChange={setMethod}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OOD_METHODS.map((m) => (
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
                  {OOD_STATUS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="ood-summary-json">ood_summary_json</Label>
            <Textarea id="ood-summary-json" className="min-h-[88px] font-mono text-xs" value={summaryJson} onChange={(e) => setSummaryJson(e.target.value)} spellCheck={false} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ood-high-risk-regions-json">high_risk_regions_json</Label>
            <Textarea id="ood-high-risk-regions-json" className="min-h-[100px] font-mono text-xs" value={regionsJson} onChange={(e) => setRegionsJson(e.target.value)} spellCheck={false} />
          </div>
          {formErr ? <p className="text-sm text-destructive">{formErr}</p> : null}
          {formOk ? <p className="text-sm text-muted-foreground">{formOk}</p> : null}
          <Button type="button" disabled={submitBusy || loading} onClick={() => void submitOod()}>
            {submitBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Submit OOD assessment
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Records"
        title="Assessments"
        icon={ShieldAlert}
        description="Out-of-distribution assessments logged for this tenant — OOD method, status, associated artifact, and dataset version."
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
                    <TableHead>dataset_version_id</TableHead>
                    <TableHead>method</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>ood_summary (summary)</TableHead>
                    <TableHead>high_risk_regions</TableHead>
                    <TableHead className="w-[90px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {assessments.map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    const hr = row["high_risk_regions_json"]
                    const nHr = Array.isArray(hr) ? hr.length : 0
                    return (
                      <TableRow key={id != null ? `ood-${id}` : `ood-${idx}`}>
                        <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readRecordNumber(row, "model_artifact_id") ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readRecordNumber(row, "dataset_version_id") ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readRecordString(row, "method") ?? "—"}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                        </TableCell>
                        <TableCell className="max-w-[220px] truncate text-xs text-muted-foreground">
                          {summarizeJson(row["ood_summary_json"])}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{nHr ? `${nHr} region(s)` : "—"}</TableCell>
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
                GET /ml/ood-assessments/{detailId}
                {detailLoading ? <Loader2 className="ml-2 inline h-4 w-4 animate-spin" aria-hidden /> : null}
              </p>
              {detail ? (
                <>
                  <div>
                    <h4 className="mb-2 text-sm font-medium">ood_summary_json</h4>
                    <div className="table-scroll min-w-0">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>field</TableHead>
                            <TableHead>value (summary)</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {objectRows(detail["ood_summary_json"]).map((r) => (
                            <TableRow key={r.key}>
                              <TableCell className="font-mono text-xs">{r.key}</TableCell>
                              <TableCell className="text-xs">{r.value}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                  <div>
                    <h4 className="mb-2 text-sm font-medium">high_risk_regions_json (summary)</h4>
                    <div className="table-scroll min-w-0">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>region</TableHead>
                            <TableHead>summary</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {Array.isArray(detail["high_risk_regions_json"])
                            ? (detail["high_risk_regions_json"] as unknown[]).slice(0, 40).map((reg, i) => {
                                const s = summarizeRegion(reg, i)
                                return (
                                  <TableRow key={`hr-${i}`}>
                                    <TableCell className="font-mono text-xs">{s.key}</TableCell>
                                    <TableCell className="max-w-[420px] text-xs">{s.summary}</TableCell>
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
