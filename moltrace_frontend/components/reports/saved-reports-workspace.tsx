"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
import { Download, Eye, Clock, CheckCircle2, AlertTriangle, FileText, FileWarning, Share2 } from "lucide-react"
import { SecureShareDialog } from "@/src/components/collaboration/SecureShareDialog"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { normalizeProjectListPayload } from "@/components/projects/project-workspace-utils"
import {
  buildProjectNameIndex,
  normalizeSpectraCheckSessionsList,
} from "@/src/lib/dashboard/overview-metrics"
import { fetchSessionReportsList, fetchSpectraCheckSessionsList } from "@/src/lib/spectracheck/spectracheck-backend-session"
import {
  buildSavedReportRow,
  normalizeReportsListPayload,
  sessionRecordId,
  type ReportFilterBucket,
  type SavedReportRow,
} from "@/src/lib/reports/saved-reports"
import { ReportLockControls } from "@/components/reports/report-lock-controls"
import { ReportCompoundProvenanceDialog } from "@/components/reports/report-compound-provenance-dialog"
import { ReportsRegulatoryComplianceSection } from "@/components/reports/reports-regulatory-compliance-section"
import { ReportsValidationReadinessCard } from "@/components/validation/validation-readiness-summary"

const DEMO_STAT_CARDS = { ready: 12, generating: 3, month: 47 } as const

const DEMO_ILLUSTRATION_ROWS: Omit<SavedReportRow, "key">[] = [
  {
    sessionId: "demo",
    reportNumericId: null,
    sessionNumericId: null,
    reportTitle: "NMR Structure Elucidation Report",
    sampleId: "API-Q4-BATCH-12",
    projectLabel: "API-2024-Q4",
    statusDisplay: "draft_requires_review",
    reviewer: "—",
    generatedAt: "2024-01-15 14:32",
    hashPreview: "—",
    filterBucket: "draft",
    hasJson: false,
    hasHtml: false,
  },
]

type FilterChoice = "all" | ReportFilterBucket

function downloadText(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function bucketBadge(bucket: ReportFilterBucket) {
  switch (bucket) {
    case "approved":
      return (
        <Badge variant="outline" className="gap-1 border-success/50 text-success">
          <CheckCircle2 className="h-3 w-3" />
          Release gate
        </Badge>
      )
    case "review_required":
      return (
        <Badge variant="outline" className="gap-1 border-accent/50 text-accent">
          <Clock className="h-3 w-3" />
          Review required
        </Badge>
      )
    case "blocked":
      return (
        <Badge variant="outline" className="gap-1 border-warning/50 text-warning">
          <AlertTriangle className="h-3 w-3" />
          Blocked
        </Badge>
      )
    default:
      return (
        <Badge variant="secondary" className="gap-1">
          <FileWarning className="h-3 w-3" />
          Draft
        </Badge>
      )
  }
}

export default function SavedReportsWorkspace() {
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState("")
  const [sessionsOk, setSessionsOk] = useState(false)
  const [rows, setRows] = useState<SavedReportRow[]>([])
  const [filter, setFilter] = useState<FilterChoice>("all")

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError("")
    setSessionsOk(false)
    setRows([])
    let projects: unknown[]
    try {
      const pr = await apiFetch<unknown>("/projects", { method: "GET" })
      projects = normalizeProjectListPayload(pr)
    } catch {
      projects = []
    }

    let sessionsPayload: unknown
    try {
      sessionsPayload = await fetchSpectraCheckSessionsList()
      setSessionsOk(true)
    } catch (err) {
      setLoadError(formatApiError(err, "Could not load SpectraCheck sessions."))
      setSessionsOk(false)
      setLoading(false)
      return
    }

    const sessions = normalizeSpectraCheckSessionsList(sessionsPayload)
    const projectById = buildProjectNameIndex(projects)
    const collected: SavedReportRow[] = []
    const batchSize = 6

    for (let i = 0; i < sessions.length; i += batchSize) {
      const chunk = sessions.slice(i, i + batchSize)
      const chunkRows = await Promise.all(
        chunk.map(async (session) => {
          const sid = sessionRecordId(session)
          if (!sid) return [] as SavedReportRow[]
          try {
            const raw = await fetchSessionReportsList(sid)
            const list = normalizeReportsListPayload(raw)
            const out: SavedReportRow[] = []
            list.forEach((rep, idx) => {
              const row = buildSavedReportRow(session, rep, projectById, idx)
              if (row) out.push(row)
            })
            return out
          } catch {
            return [] as SavedReportRow[]
          }
        }),
      )
      for (const part of chunkRows) collected.push(...part)
    }

    setRows(collected)
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const filteredRows = useMemo(() => {
    if (filter === "all") return rows
    return rows.filter((r) => r.filterBucket === filter)
  }, [rows, filter])

  const stats = useMemo(() => {
    if (rows.length === 0) return null
    const approved = rows.filter((r) => r.filterBucket === "approved").length
    const inFlight = rows.filter((r) => r.filterBucket === "draft" || r.filterBucket === "review_required").length
    return {
      ready: approved,
      generating: inFlight,
      total: rows.length,
    }
  }, [rows])

  function openReport(row: SavedReportRow) {
    if (row.openUrl) {
      window.open(row.openUrl, "_blank", "noopener,noreferrer")
      return
    }
    if (row.htmlInline) {
      const w = window.open("", "_blank")
      if (w) {
        w.document.write(row.htmlInline)
        w.document.close()
      }
    }
  }

  function downloadJson(row: SavedReportRow) {
    if (row.jsonPayload == null) return
    const body =
      typeof row.jsonPayload === "string"
        ? row.jsonPayload
        : JSON.stringify(row.jsonPayload, null, 2)
    downloadText(body, `report-${row.sessionId}.json`, "application/json;charset=utf-8")
  }

  function downloadHtml(row: SavedReportRow) {
    if (!row.htmlInline) return
    downloadText(row.htmlInline, `report-${row.sessionId}.html`, "text/html;charset=utf-8")
  }

  const showLiveTable = sessionsOk && !loading
  const showIllustration = !loading && !sessionsOk

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
          <p className="text-muted-foreground">
            Saved reports from SpectraCheck sessions (loaded per session).
          </p>
          {loadError ? (
            <p className="mt-1 text-xs text-destructive">{loadError}</p>
          ) : null}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="gap-2" disabled>
            <Download className="h-4 w-4" />
            Export All
          </Button>
        </div>
      </div>

      <Card className="border-muted">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">How reports are listed</CardTitle>
          <CardDescription>
            There is no global report catalog endpoint in this client. Reports are fetched with{" "}
            <code className="text-xs">GET /spectracheck/sessions</code> followed by{" "}
            <code className="text-xs">GET /spectracheck/sessions/{"{session_id}"}/reports</code> for each
            session. Sessions without saved reports produce no rows.
          </CardDescription>
        </CardHeader>
      </Card>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Ready for Export</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {stats ? stats.ready : DEMO_STAT_CARDS.ready}
            </div>
            <p className="text-xs text-muted-foreground">
              {stats ? "Backend: approved_for_release / released" : "Demo summary"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Generating</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {stats ? stats.generating : DEMO_STAT_CARDS.generating}
            </div>
            <p className="text-xs text-muted-foreground">
              {stats ? "Draft or review required (live)" : "Demo summary"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">This Month</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {stats ? stats.total : DEMO_STAT_CARDS.month}
            </div>
            <p className="text-xs text-muted-foreground">
              {stats ? "Report records loaded" : "Demo summary"}
            </p>
          </CardContent>
        </Card>
      </div>

      <ReportsValidationReadinessCard />

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Saved reports</CardTitle>
            <CardDescription>Filter by automated report gate label from the backend.</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            {(
              [
                ["all", "All"],
                ["draft", "Draft"],
                ["review_required", "Review required"],
                ["approved", "Approved"],
                ["blocked", "Blocked"],
              ] as const
            ).map(([id, label]) => (
              <Button
                key={id}
                type="button"
                variant={filter === id ? "secondary" : "outline"}
                size="sm"
                className="h-8"
                onClick={() => setFilter(id)}
              >
                {label}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading sessions and reports…</p>
          ) : null}
          {!loading && showLiveTable && rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No saved report records returned for your sessions yet.
            </p>
          ) : null}
          {!loading && showLiveTable && rows.length > 0 && filteredRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No reports match this filter.</p>
          ) : null}
          {showLiveTable && filteredRows.length > 0 ? (
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Report title</TableHead>
                    <TableHead>Sample ID</TableHead>
                    <TableHead>Project</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Reviewer</TableHead>
                    <TableHead>Generated</TableHead>
                    <TableHead>Report hash</TableHead>
                    <TableHead className="min-w-[11rem]">Lock</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredRows.map((report) => (
                    <TableRow key={report.key}>
                      <TableCell className="max-w-[220px] font-medium">{report.reportTitle}</TableCell>
                      <TableCell className="font-mono text-sm">{report.sampleId}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{report.projectLabel}</Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-1">
                          {bucketBadge(report.filterBucket)}
                          <span className="text-[11px] text-muted-foreground">{report.statusDisplay}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-sm">{report.reviewer}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{report.generatedAt}</TableCell>
                      <TableCell className="font-mono text-[11px] text-muted-foreground">{report.hashPreview}</TableCell>
                      <TableCell className="align-top text-xs">
                        {report.reportNumericId != null ? (
                          <ReportLockControls
                            compact
                            reportId={report.reportNumericId}
                            sessionIdStr={report.sessionId}
                            sessionNumericId={report.sessionNumericId}
                          />
                        ) : (
                          <span className="text-[11px] text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-2">
                          <Button variant="outline" size="sm" className="h-8 w-fit shrink-0 text-xs" asChild>
                            <Link
                              href={
                                report.sessionNumericId != null
                                  ? `/regulatory?spectracheck_session_id=${encodeURIComponent(String(report.sessionNumericId))}`
                                  : "/regulatory"
                              }
                            >
                              {report.sessionNumericId != null
                                ? "Create regulatory dossier from this report"
                                : "Link report to regulatory dossier"}
                            </Link>
                          </Button>
                          <div className="flex flex-wrap gap-1">
                          {report.reportNumericId != null ? (
                            <ReportCompoundProvenanceDialog
                              reportId={report.reportNumericId}
                              sessionNumericId={report.sessionNumericId}
                              reportTitle={report.reportTitle}
                              hashPreview={report.hashPreview}
                            >
                              <Button type="button" variant="outline" size="sm" className="h-8 shrink-0 text-xs">
                                Compound provenance
                              </Button>
                            </ReportCompoundProvenanceDialog>
                          ) : null}
                          {report.reportNumericId != null ? (
                            <SecureShareDialog
                              scope="report"
                              lockScope
                              lockTargetId
                              defaultReportId={report.reportNumericId}
                              trigger={
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="h-8 w-8"
                                  title="Secure share"
                                >
                                  <Share2 className="h-4 w-4" />
                                </Button>
                              }
                            />
                          ) : null}
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            disabled={!report.openUrl && !report.htmlInline}
                            title="Open report"
                            onClick={() => openReport(report)}
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            disabled={!report.hasJson}
                            title="Download JSON"
                            onClick={() => downloadJson(report)}
                          >
                            <Download className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            disabled={!report.htmlInline}
                            title="Download HTML"
                            onClick={() => downloadHtml(report)}
                          >
                            <FileText className="h-4 w-4" />
                          </Button>
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <ReportsRegulatoryComplianceSection live={showLiveTable} reportRows={rows} />

      {showIllustration ? (
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle className="text-base">UI illustration (demo only)</CardTitle>
            <CardDescription>
              Placeholder layout when no live rows are available — not claimed as approved or signed off.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Report title</TableHead>
                  <TableHead>Sample ID</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Reviewer</TableHead>
                  <TableHead>Generated</TableHead>
                  <TableHead>Report hash</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {DEMO_ILLUSTRATION_ROWS.map((r, i) => (
                  <TableRow key={`demo-${i}`}>
                    <TableCell>{r.reportTitle}</TableCell>
                    <TableCell className="font-mono text-sm">{r.sampleId}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{r.projectLabel}</Badge>
                    </TableCell>
                    <TableCell>{bucketBadge(r.filterBucket)}</TableCell>
                    <TableCell>{r.reviewer}</TableCell>
                    <TableCell className="text-muted-foreground">{r.generatedAt}</TableCell>
                    <TableCell className="font-mono text-[11px]">{r.hashPreview}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
