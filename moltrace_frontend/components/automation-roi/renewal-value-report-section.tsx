"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Download, FileJson, RefreshCw } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { normalizeProjectListPayload, readRecordString } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Input } from "@/components/ui/input"
import { EntityPicker } from "@/components/ui/entity-picker"
import { loadOrganizations } from "@/lib/ui/entity-options"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

const RENEWAL_REPORT_TOOLTIP =
  "Renewal reports summarize measurable product value such as tasks automated, hours saved, reports generated, review workload, and workflow completion."

type RenewalScope = "global" | "project" | "organization"

function defaultEndDate(): string {
  return new Date().toISOString().slice(0, 10)
}

function defaultStartDate(): string {
  const d = new Date()
  d.setDate(d.getDate() - 30)
  return d.toISOString().slice(0, 10)
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Number(v)
  return null
}

function fmtNum(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "—"
  return n.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 })
}

function fmtInt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—"
  return String(Math.round(n))
}

function formatPeriodIso(iso: string | undefined): string {
  if (!iso?.trim()) return "—"
  const ms = Date.parse(iso)
  if (Number.isNaN(ms)) return iso
  return new Date(ms).toLocaleString()
}

function dateToStartIso(d: string): string {
  return new Date(`${d}T00:00:00.000Z`).toISOString()
}

function dateToEndIso(d: string): string {
  return new Date(`${d}T23:59:59.999Z`).toISOString()
}

function downloadText(content: string, mime: string, filename: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function projectRowLabel(row: unknown): { id: string; label: string } | null {
  if (!isRecord(row)) return null
  const id = readRecordString(row, "id")
  if (!id?.trim()) return null
  const name = readRecordString(row, "name") || readRecordString(row, "title") || id
  return { id, label: `${name} (${id})` }
}

function parseRenewalReportResponse(raw: unknown): {
  id: number
  title: string
  scope: string
  scope_id: string | null
  period_start: string
  period_end: string
  summary_json: unknown
  report_json: unknown
  report_html: string | null
  report_sha256: string | null
  warnings: string[]
} | null {
  if (!isRecord(raw)) return null
  const id = readNum(raw.id)
  if (id == null) return null
  const title = readRecordString(raw, "title") || "—"
  const scope = readRecordString(raw, "scope") || "global"
  const scope_id = raw.scope_id == null ? null : readRecordString(raw, "scope_id") ?? null
  const period_start = readRecordString(raw, "period_start") || ""
  const period_end = readRecordString(raw, "period_end") || ""
  const report_html = typeof raw.report_html === "string" ? raw.report_html : null
  const report_sha256 = readRecordString(raw, "report_sha256") ?? null
  const warnings = Array.isArray(raw.warnings)
    ? raw.warnings.filter((w): w is string => typeof w === "string")
    : []
  return {
    id: Math.round(id),
    title,
    scope,
    scope_id,
    period_start,
    period_end,
    summary_json: raw.summary_json,
    report_json: raw.report_json,
    report_html,
    report_sha256,
    warnings,
  }
}

function readSummaryMetrics(summaryJson: unknown): {
  tasks_automated: number | null
  total_hours_saved: number | null
  reports_generated: number | null
  workflows_completed: number | null
} {
  if (!isRecord(summaryJson)) {
    return {
      tasks_automated: null,
      total_hours_saved: null,
      reports_generated: null,
      workflows_completed: null,
    }
  }
  return {
    tasks_automated: readNum(summaryJson.tasks_automated),
    total_hours_saved: readNum(summaryJson.total_hours_saved),
    reports_generated: readNum(summaryJson.reports_generated),
    workflows_completed: readNum(summaryJson.workflows_completed),
  }
}

function readValueIndicators(reportJson: unknown): {
  total_minutes_saved: number | null
  review_tasks_completed: number | null
  failed_jobs: number | null
  qc_warnings: number | null
} {
  if (!isRecord(reportJson)) {
    return {
      total_minutes_saved: null,
      review_tasks_completed: null,
      failed_jobs: null,
      qc_warnings: null,
    }
  }
  const vi = reportJson.value_indicators
  if (!isRecord(vi)) {
    return {
      total_minutes_saved: null,
      review_tasks_completed: null,
      failed_jobs: null,
      qc_warnings: null,
    }
  }
  return {
    total_minutes_saved: readNum(vi.total_minutes_saved),
    review_tasks_completed: readNum(vi.review_tasks_completed),
    failed_jobs: readNum(vi.failed_jobs),
    qc_warnings: readNum(vi.qc_warnings),
  }
}

function developerPayload(report: NonNullable<ReturnType<typeof parseRenewalReportResponse>>) {
  return {
    ...report,
    report_html: report.report_html ? "(omitted — use Download HTML when available)" : null,
  }
}

export function RenewalValueReportSection() {
  const [scope, setScope] = useState<RenewalScope>("global")
  const [projectId, setProjectId] = useState("")
  const [organizationId, setOrganizationId] = useState("")
  const [periodStart, setPeriodStart] = useState(defaultStartDate)
  const [periodEnd, setPeriodEnd] = useState(defaultEndDate)
  const [title, setTitle] = useState("")
  const [projects, setProjects] = useState<{ id: string; label: string }[]>([])
  const [projectsLoaded, setProjectsLoaded] = useState(false)
  const [generateBusy, setGenerateBusy] = useState(false)
  const [refreshBusy, setRefreshBusy] = useState(false)
  const [error, setError] = useState("")
  const [report, setReport] = useState<NonNullable<ReturnType<typeof parseRenewalReportResponse>> | null>(null)

  useEffect(() => {
    let active = true
    void apiFetch<unknown>("/projects", { method: "GET" })
      .then((data) => {
        if (!active) return
        const rows = normalizeProjectListPayload(data)
        const opts: { id: string; label: string }[] = []
        for (const row of rows) {
          const opt = projectRowLabel(row)
          if (opt) opts.push(opt)
        }
        setProjects(opts.sort((a, b) => a.label.localeCompare(b.label)))
        setProjectsLoaded(true)
      })
      .catch(() => {
        if (!active) return
        setProjects([])
        setProjectsLoaded(true)
      })
    return () => {
      active = false
    }
  }, [])

  const scopeIdForApi = useMemo(() => {
    if (scope === "global") return null
    if (scope === "project") return projectId.trim() || null
    return organizationId.trim() || null
  }, [scope, projectId, organizationId])

  const formInvalidProject = scope === "project" && !projectId.trim()
  const formInvalidOrg = scope === "organization" && !organizationId.trim()
  const generateDisabled = generateBusy || formInvalidProject || formInvalidOrg || !periodStart || !periodEnd

  const runPost = useCallback(async () => {
    setError("")
    setGenerateBusy(true)
    try {
      const body = {
        scope,
        scope_id: scopeIdForApi,
        period_start: dateToStartIso(periodStart),
        period_end: dateToEndIso(periodEnd),
        title: title.trim() || null,
        metadata_json: {} as Record<string, unknown>,
      }
      const raw = await apiFetch<unknown>("/analytics/renewal-report", { method: "POST", body })
      const parsed = parseRenewalReportResponse(raw)
      if (!parsed) {
        setError("Unexpected response generating renewal report.")
        return
      }
      setReport(parsed)
    } catch (e) {
      setReport(null)
      setError(formatApiError(e, "Could not generate renewal report."))
    } finally {
      setGenerateBusy(false)
    }
  }, [scope, scopeIdForApi, periodStart, periodEnd, title])

  const runRefresh = useCallback(async () => {
    if (!report?.id) return
    setError("")
    setRefreshBusy(true)
    try {
      const raw = await apiFetch<unknown>(`/analytics/renewal-report/${report.id}`, { method: "GET" })
      const parsed = parseRenewalReportResponse(raw)
      if (!parsed) {
        setError("Unexpected response loading renewal report.")
        return
      }
      setReport(parsed)
    } catch (e) {
      setError(formatApiError(e, "Could not load renewal report."))
    } finally {
      setRefreshBusy(false)
    }
  }, [report?.id])

  const summaryM = useMemo(() => readSummaryMetrics(report?.summary_json), [report?.summary_json])
  const valueInd = useMemo(() => readValueIndicators(report?.report_json), [report?.report_json])
  const workflowHours = valueInd.total_minutes_saved != null ? valueInd.total_minutes_saved / 60 : null

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-base">Renewal Value Report</CardTitle>
          <span className="inline-flex items-center gap-1 text-muted-foreground">
            <InfoTooltip content={RENEWAL_REPORT_TOOLTIP} label="About renewal value reports" />
          </span>
        </div>
        <CardDescription>
          Generates and refreshes a renewal value report — aggregated automation ROI, hours saved, and workflow metrics. Admin-only; aggregate data only, no individual records.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {error ? (
          <Alert variant="default" className="border-muted bg-muted/30">
            <AlertTitle className="text-sm">Renewal report</AlertTitle>
            <AlertDescription className="text-xs text-muted-foreground">{error}</AlertDescription>
          </Alert>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="renewal-scope">Scope</Label>
            <Select
              value={scope}
              onValueChange={(v) => {
                setScope(v as RenewalScope)
                if (v !== "project") setProjectId("")
                if (v !== "organization") setOrganizationId("")
              }}
            >
              <SelectTrigger id="renewal-scope" className="w-full">
                <SelectValue placeholder="Scope" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="global">global</SelectItem>
                <SelectItem value="project">project</SelectItem>
                <SelectItem value="organization">organization</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {scope === "project" ? (
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="renewal-project">Project</Label>
              <Select value={projectId} onValueChange={setProjectId} disabled={!projectsLoaded}>
                <SelectTrigger id="renewal-project" className="w-full max-w-md">
                  <SelectValue placeholder={projectsLoaded ? "Select a project" : "Loading projects…"} />
                </SelectTrigger>
                <SelectContent>
                  {projects.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
          {scope === "organization" ? (
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="renewal-org">Organization</Label>
              <div className="max-w-md">
                <EntityPicker
                  id="renewal-org"
                  ariaLabel="Organization"
                  value={organizationId || null}
                  onChange={(id) => setOrganizationId(id == null ? "" : String(id))}
                  load={loadOrganizations}
                  placeholder="Select an organization"
                  searchPlaceholder="Search organizations…"
                />
              </div>
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="renewal-start">Period start</Label>
            <Input
              id="renewal-start"
              type="date"
              value={periodStart}
              onChange={(e) => setPeriodStart(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="renewal-end">Period end</Label>
            <Input id="renewal-end" type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="renewal-title">Title</Label>
            <Input
              id="renewal-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Optional — backend defaults if empty"
              maxLength={300}
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => void runPost()} disabled={generateDisabled}>
            {generateBusy ? "Generating…" : "Generate renewal report"}
          </Button>
          {report ? (
            <Button type="button" variant="outline" size="sm" onClick={() => void runRefresh()} disabled={refreshBusy}>
              <RefreshCw className="mr-2 h-4 w-4" />
              {refreshBusy ? "Refreshing…" : "Refresh"}
            </Button>
          ) : null}
        </div>

        {report ? (
          <div className="space-y-6 border-t pt-6">
            <div>
              <h3 className="text-sm font-medium">{report.title}</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                Period: {formatPeriodIso(report.period_start)} → {formatPeriodIso(report.period_end)}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge variant="secondary" className="font-normal">
                  scope={report.scope}
                </Badge>
                {report.scope_id ? (
                  <Badge variant="outline" className="font-mono text-xs font-normal">
                    scope_id={report.scope_id}
                  </Badge>
                ) : null}
                <Badge variant="outline" className="font-normal">
                  report_id={report.id}
                </Badge>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Hours saved</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold tabular-nums">{fmtNum(summaryM.total_hours_saved)}</div>
                  <p className="text-xs text-muted-foreground">total_hours_saved (summary_json)</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Tasks automated</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold tabular-nums">{fmtInt(summaryM.tasks_automated)}</div>
                  <p className="text-xs text-muted-foreground">tasks_automated</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Reports generated</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold tabular-nums">{fmtInt(summaryM.reports_generated)}</div>
                  <p className="text-xs text-muted-foreground">reports_generated</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">SHA-256</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="break-all font-mono text-xs leading-snug text-muted-foreground">
                    {report.report_sha256 ?? "—"}
                  </div>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Workflow value summary</CardTitle>
                <CardDescription>From report_json.value_indicators and summary_json.workflows_completed.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Metric</TableHead>
                        <TableHead className="text-right">Value</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      <TableRow>
                        <TableCell>Workflows completed</TableCell>
                        <TableCell className="text-right tabular-nums">{fmtInt(summaryM.workflows_completed)}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Workflow-related hours saved (from minutes)</TableCell>
                        <TableCell className="text-right tabular-nums">{fmtNum(workflowHours, 2)}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Failed jobs</TableCell>
                        <TableCell className="text-right tabular-nums">{fmtInt(valueInd.failed_jobs)}</TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">QC / review summary</CardTitle>
                <CardDescription>Aggregate counts from value_indicators — no raw spectra or file contents.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Metric</TableHead>
                        <TableHead className="text-right">Value</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      <TableRow>
                        <TableCell>Review tasks completed</TableCell>
                        <TableCell className="text-right tabular-nums">{fmtInt(valueInd.review_tasks_completed)}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>QC warnings</TableCell>
                        <TableCell className="text-right tabular-nums">{fmtInt(valueInd.qc_warnings)}</TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            {report.warnings.length > 0 ? (
              <Alert>
                <AlertTitle className="text-sm">Warnings</AlertTitle>
                <AlertDescription>
                  <ul className="list-inside list-disc text-xs text-muted-foreground">
                    {report.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            ) : (
              <p className="text-xs text-muted-foreground">No warnings on this report.</p>
            )}

            <div className="flex flex-wrap gap-2">
              {report.report_html ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    downloadText(report.report_html!, "text/html;charset=utf-8", `renewal-report-${report.id}.html`)
                  }
                >
                  <Download className="mr-2 h-4 w-4" />
                  Download HTML
                </Button>
              ) : null}
              {report.report_json != null && isRecord(report.report_json) ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    downloadText(
                      JSON.stringify(report.report_json, null, 2),
                      "application/json;charset=utf-8",
                      `renewal-report-${report.id}.json`,
                    )
                  }
                >
                  <FileJson className="mr-2 h-4 w-4" />
                  Download JSON
                </Button>
              ) : null}
            </div>

            <DeveloperJsonPanel data={developerPayload(report)} />
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
