"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Activity, AlertTriangle, BarChart3, ChevronDown, ArrowLeft, Database, FileText, Info, ServerOff, StickyNote } from "lucide-react"
import { cn } from "@/lib/utils"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(o: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return ""
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

function unwrapRunPayload(data: unknown): Record<string, unknown> | null {
  if (!isRecord(data)) return null
  const nested = data.validation_run ?? data.run ?? data.validationRun ?? data.record
  if (isRecord(nested)) return nested
  if (isRecord(data.data)) return data.data as Record<string, unknown>
  return data
}

function metricsRowsFromRun(run: Record<string, unknown>): Record<string, unknown>[] {
  for (const k of ["metrics", "metric_rows", "key_metrics", "metric_results"]) {
    const v = run[k]
    if (Array.isArray(v)) return v.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

function summarizeUnknown(v: unknown, maxLen = 240): string {
  if (v == null || v === "") return "—"
  if (typeof v === "string") return v.trim() || "—"
  if (typeof v === "number" || typeof v === "boolean") return String(v)
  if (Array.isArray(v)) {
    const joined = v.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(", ")
    return joined.length > maxLen ? `${joined.slice(0, maxLen)}…` : joined || "—"
  }
  if (isRecord(v)) {
    const s = JSON.stringify(v)
    return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s
  }
  return "—"
}

function normalizeWarnings(raw: unknown): string[] {
  if (raw == null) return []
  if (typeof raw === "string" && raw.trim()) return [raw.trim()]
  if (!Array.isArray(raw)) return []
  const out: string[] = []
  for (const item of raw) {
    if (typeof item === "string" && item.trim()) out.push(item.trim())
    else if (isRecord(item)) {
      const line =
        readStr(item, ["message", "text", "detail", "warning", "title"]) || summarizeUnknown(item, 120)
      if (line !== "—") out.push(line)
    }
  }
  return out
}

function requiresReviewStatus(statusRaw: string): boolean {
  const s = statusRaw.toLowerCase().replace(/-/g, "_")
  return (
    s.includes("review") ||
    s === "blocked" ||
    s === "requires_review" ||
    s === "needs_review" ||
    s === "pending_review"
  )
}

function metricPassedField(row: Record<string, unknown>): boolean | undefined {
  if (typeof row.passed === "boolean") return row.passed
  if (row.passed === "true") return true
  if (row.passed === "false") return false
  return undefined
}

function neutralMetricValue(row: Record<string, unknown>): string {
  const v =
    row.value ??
    row.metric_value ??
    row.numeric_value ??
    row.number ??
    row.result ??
    row.measurement
  return summarizeUnknown(v, 200)
}

export function ValidationRunDetailWorkspace() {
  const params = useParams()
  const rawId = params?.validationRunId
  const validationRunId = typeof rawId === "string" ? rawId : Array.isArray(rawId) ? rawId[0] : ""

  const [rawPayload, setRawPayload] = useState<unknown>(null)
  const [run, setRun] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [devOpen, setDevOpen] = useState(false)

  const load = useCallback(async () => {
    const id = validationRunId?.trim()
    if (!id) {
      setLoading(false)
      setError("Missing validation run id.")
      setRun(null)
      setRawPayload(null)
      return
    }
    setLoading(true)
    setError("")
    try {
      const data = await apiFetch<unknown>(`/validation-runs/${encodeURIComponent(id)}`, { method: "GET" })
      setRawPayload(data)
      const unwrapped = unwrapRunPayload(data)
      setRun(unwrapped)
    } catch (e) {
      setError(formatErr(e, "Could not load validation run."))
      setRun(null)
      setRawPayload(null)
    } finally {
      setLoading(false)
    }
  }, [validationRunId])

  useEffect(() => {
    void load()
  }, [load])

  const metrics = useMemo(() => (run ? metricsRowsFromRun(run) : []), [run])

  const statusLabel = run ? readStr(run, ["status", "run_status", "state", "validation_status"]) : ""
  const methodLabel = run ? readStr(run, ["method", "method_name", "method_id"]) : ""
  const modelVersion = run ? readStr(run, ["model_version", "modelVersion", "version"]) : ""
  const scoringProfile = run
    ? readStr(run, ["scoring_profile", "scoring_profile_name", "scoringProfile"]) ||
      (run.scoring_profile !== undefined ? summarizeUnknown(run.scoring_profile) : "")
    : ""
  const thresholdProfile = run
    ? readStr(run, ["threshold_profile", "threshold_profile_name", "thresholdProfile"]) ||
      (run.threshold_profile !== undefined ? summarizeUnknown(run.threshold_profile) : "")
    : ""
  const benchmarkDataset = run
    ? readStr(run, ["benchmark", "benchmark_name", "benchmark_dataset", "benchmark_id", "dataset", "dataset_name"]) ||
      (run.benchmark_dataset !== undefined ? summarizeUnknown(run.benchmark_dataset) : "")
    : ""

  const warningsList = run ? normalizeWarnings(run.warnings) : []
  const notesRaw = run?.notes
  const metadataRaw = run?.metadata

  const notesDisplay =
    notesRaw == null
      ? "—"
      : typeof notesRaw === "string"
        ? notesRaw.trim() || "—"
        : Array.isArray(notesRaw)
          ? notesRaw.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join("\n") || "—"
          : summarizeUnknown(notesRaw)

  const showReviewNote = statusLabel ? requiresReviewStatus(statusLabel) : false

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="ghost" size="sm" className="h-8 px-2" asChild>
              <Link href="/validation">
                <ArrowLeft className="mr-1 h-3.5 w-3.5" aria-hidden />
                Back
              </Link>
            </Button>
          </div>
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-green)" }}
          >
            MolTrace · Validation Run
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Validation run</h1>
          <p className="font-mono text-xs text-muted-foreground break-all">{validationRunId || "—"}</p>
          <p className="text-sm text-muted-foreground">
            Read-only details from the validation run response. Terminology reflects API labels only.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : error ? (
        <AlertCard
          variant="error"
          icon={ServerOff}
          title="Backend unavailable or run not found"
          description={error}
        />
      ) : run ? (
        <>
          <ModuleCard
            accent="cyan"
            eyebrow="Result"
            title="Validation result"
            icon={Activity}
            description="Status and identifiers as returned by the API."
          >
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm text-muted-foreground">Run status</span>
                <Badge variant="outline" className="font-normal">
                  {statusLabel || "—"}
                </Badge>
              </div>
              {showReviewNote ? (
                <p className="text-sm text-muted-foreground">Requires review (per run status label).</p>
              ) : null}
            </div>
          </ModuleCard>

          <ModuleCard
            accent="cyan"
            eyebrow="Benchmark"
            title="Benchmark result"
            icon={Database}
            description="Benchmark dataset reference from the run payload."
          >
            <dl className="grid gap-3 sm:grid-cols-2">
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Method</dt>
                <dd className="text-sm">{methodLabel || "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Model version</dt>
                <dd className="text-sm">{modelVersion || "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Scoring profile</dt>
                <dd className="text-sm break-words">{scoringProfile || "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Threshold profile</dt>
                <dd className="text-sm break-words">{thresholdProfile || "—"}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs font-medium text-muted-foreground">Benchmark dataset</dt>
                <dd className="text-sm break-words">{benchmarkDataset || "—"}</dd>
              </div>
            </dl>
          </ModuleCard>

          <ModuleCard
            accent="cyan"
            eyebrow="Metrics"
            title="Metrics"
            icon={BarChart3}
            description="Per-metric rows from the run payload."
          >
            <div>
              {metrics.length === 0 ? (
                <p className="text-sm text-muted-foreground">No metrics rows in this response.</p>
              ) : (
                <div className="overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Metric</TableHead>
                        <TableHead className="text-xs">Outcome</TableHead>
                        <TableHead className="text-xs">Value</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {metrics.map((row, i) => {
                        const name =
                          readStr(row, ["name", "key", "metric_name", "label", "metric", "id"]) || `metric-${i + 1}`
                        const passed = metricPassedField(row)
                        return (
                          <TableRow key={readStr(row, ["id", "metric_id"]) || `${name}-${i}`}>
                            <TableCell className="text-xs font-medium">{name}</TableCell>
                            <TableCell className="text-xs">
                              {passed === undefined ? (
                                <span className="text-muted-foreground">—</span>
                              ) : passed ? (
                                <Badge
                                  variant="outline"
                                  className="border-emerald-500/40 font-normal text-emerald-700 dark:text-emerald-400"
                                >
                                  Pass
                                </Badge>
                              ) : (
                                <Badge
                                  variant="outline"
                                  className="border-destructive/40 font-normal text-destructive"
                                >
                                  Fail
                                </Badge>
                              )}
                            </TableCell>
                            <TableCell className="max-w-[24rem] font-mono text-[10px] text-muted-foreground">
                              {neutralMetricValue(row)}
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          </ModuleCard>

          <ModuleCard
            accent={warningsList.length > 0 ? "amber" : "cyan"}
            eyebrow="Warnings"
            title="Warnings"
            icon={AlertTriangle}
          >
            <div>
              {warningsList.length === 0 ? (
                <p className="text-sm text-muted-foreground">No warnings in this response.</p>
              ) : (
                <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                  {warningsList.map((w, idx) => (
                    <li key={idx}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          </ModuleCard>

          <ModuleCard accent="cyan" eyebrow="Notes" title="Notes" icon={StickyNote}>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">{notesDisplay}</p>
          </ModuleCard>

          <ModuleCard accent="cyan" eyebrow="Metadata" title="Metadata" icon={Info}>
            <div>
              {metadataRaw == null || (isRecord(metadataRaw) && Object.keys(metadataRaw).length === 0) ? (
                <p className="text-sm text-muted-foreground">No metadata object in this response.</p>
              ) : (
                <pre className="max-h-[320px] overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-[10px] leading-relaxed">
                  {JSON.stringify(metadataRaw, null, 2)}
                </pre>
              )}
            </div>
          </ModuleCard>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-green)" }}
          >
            <Collapsible open={devOpen} onOpenChange={setDevOpen}>
              <CollapsibleTrigger asChild>
                <button
                  type="button"
                  className="flex w-full items-center justify-between px-6 py-4 text-left hover:bg-muted/50"
                >
                  <span className="flex items-center gap-2">
                    <FileText className="h-4 w-4" style={{ color: "var(--mt-green)" }} aria-hidden />
                    <span className="font-mono text-base font-bold leading-none tracking-tight">Developer JSON</span>
                  </span>
                  <ChevronDown className={cn("h-4 w-4 shrink-0 transition-transform", devOpen && "rotate-180")} />
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <CardContent className="pt-0 pb-5">
                  <pre className="max-h-[480px] overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-[10px] leading-relaxed">
                    {rawPayload != null ? JSON.stringify(rawPayload, null, 2) : ""}
                  </pre>
                </CardContent>
              </CollapsibleContent>
            </Collapsible>
          </Card>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">No run payload.</p>
      )}
    </div>
  )
}
