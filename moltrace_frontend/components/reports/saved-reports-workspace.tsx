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
import {
  Download,
  Eye,
  Clock,
  CheckCircle2,
  AlertTriangle,
  FileText,
  FileCode,
  FileJson,
  FileWarning,
  FlaskConical,
  Microscope,
  Share2,
  SlidersHorizontal,
} from "lucide-react"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
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
import { KpiCard } from "@/components/dashboard/kpi-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { StatusFilterPills } from "@/components/dashboard/status-filter-pills"

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

function filterLabel(f: FilterChoice): string {
  switch (f) {
    case "all":
      return "All"
    case "draft":
      return "Draft"
    case "review_required":
      return "Review required"
    case "approved":
      return "Approved"
    case "blocked":
      return "Blocked"
  }
}

function bucketBadge(bucket: ReportFilterBucket) {
  switch (bucket) {
    case "approved":
      return (
        <Badge
          variant="outline"
          className="gap-1"
          style={{ borderColor: "var(--mt-green)", color: "var(--mt-green)" }}
        >
          <CheckCircle2 className="h-3 w-3" />
          Release gate
        </Badge>
      )
    case "review_required":
      return (
        <Badge
          variant="outline"
          className="gap-1"
          style={{ borderColor: "var(--mt-amber)", color: "var(--mt-amber)" }}
        >
          <Clock className="h-3 w-3" />
          Review required
        </Badge>
      )
    case "blocked":
      return (
        <Badge
          variant="outline"
          className="gap-1"
          style={{ borderColor: "var(--mt-amber)", color: "var(--mt-amber)" }}
        >
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

  const filterCounts = useMemo(() => {
    const counts = { draft: 0, review_required: 0, approved: 0, blocked: 0 }
    for (const r of rows) counts[r.filterBucket]++
    return counts
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
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-cyan-ink)" }}
          >
            MolTrace · Reports
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Reports</h1>
          <p className="text-sm text-muted-foreground">
            Reports generated from your SpectraCheck sessions.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="gap-2" disabled>
            <Download className="h-4 w-4" />
            Export All
          </Button>
        </div>
      </div>

      {loadError ? (
        <AlertCard variant="error" title="Reports failed to load" description={loadError} />
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <KpiCard
          title="Ready for Export"
          icon={CheckCircle2}
          accent="cyan"
          severity={stats && stats.ready > 0 ? "success" : "neutral"}
          value={stats ? stats.ready : DEMO_STAT_CARDS.ready}
          sub={
            <p className="text-xs text-muted-foreground">
              {stats ? "Approved or released for export" : "Example value"}
            </p>
          }
          onClick={() => setFilter("approved")}
          onClickLabel="Show approved reports"
        />
        <KpiCard
          title="Generating"
          icon={Clock}
          accent="cyan"
          severity={stats && stats.generating > 0 ? "warning" : "neutral"}
          value={stats ? stats.generating : DEMO_STAT_CARDS.generating}
          sub={
            <p className="text-xs text-muted-foreground">
              {stats ? "Drafts and items awaiting review" : "Example value"}
            </p>
          }
        />
        <KpiCard
          title="This Month"
          icon={FileText}
          accent="cyan"
          value={stats ? stats.total : DEMO_STAT_CARDS.month}
          sub={
            <p className="text-xs text-muted-foreground">
              {stats ? "Total saved reports" : "Example value"}
            </p>
          }
        />
      </div>

      <ReportsValidationReadinessCard />

      <ModuleCard
        accent="cyan"
        eyebrow="Reports · Saved"
        title="Saved reports"
        description="Filter reports by their gate status."
      >
          <StatusFilterPills
            label="Filter reports by status"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "All", count: rows.length },
              { value: "draft", label: "Draft", count: filterCounts.draft },
              { value: "review_required", label: "Review required", count: filterCounts.review_required },
              { value: "approved", label: "Approved", count: filterCounts.approved },
              { value: "blocked", label: "Blocked", count: filterCounts.blocked },
            ]}
          />
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading sessions and reports…</p>
          ) : null}
          {!loading && showLiveTable && rows.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Microscope />
                </EmptyMedia>
                <EmptyTitle>No saved reports yet</EmptyTitle>
                <EmptyDescription>
                  Reports are generated when you complete a SpectraCheck analysis. Start a session to
                  produce your first one.
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <Button asChild>
                  <Link href="/spectracheck">Open SpectraCheck</Link>
                </Button>
              </EmptyContent>
            </Empty>
          ) : null}
          {!loading && showLiveTable && rows.length > 0 && filteredRows.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <SlidersHorizontal />
                </EmptyMedia>
                <EmptyTitle>No matches for this filter</EmptyTitle>
                <EmptyDescription>
                  No reports match the “{filterLabel(filter)}” filter right now.
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <Button variant="outline" onClick={() => setFilter("all")}>
                  Show all reports
                </Button>
              </EmptyContent>
            </Empty>
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
                      <TableCell>{bucketBadge(report.filterBucket)}</TableCell>
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
                        <div className="flex flex-wrap items-center gap-1">
                          <Button variant="outline" size="sm" className="h-8 shrink-0 text-xs" asChild>
                            <Link
                              href={
                                report.sessionNumericId != null
                                  ? `/regulatory?spectracheck_session_id=${encodeURIComponent(String(report.sessionNumericId))}`
                                  : "/regulatory"
                              }
                              title={
                                report.sessionNumericId != null
                                  ? "Create a regulatory dossier from this report"
                                  : "Link this report to a regulatory dossier"
                              }
                            >
                              Regulatory
                            </Link>
                          </Button>
                          {report.reportNumericId != null ? (
                            <ReportCompoundProvenanceDialog
                              reportId={report.reportNumericId}
                              sessionNumericId={report.sessionNumericId}
                              reportTitle={report.reportTitle}
                              hashPreview={report.hashPreview}
                            >
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                title="Compound provenance"
                              >
                                <FlaskConical className="h-4 w-4" />
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
                            <FileJson className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            disabled={!report.htmlInline}
                            title="Download HTML"
                            onClick={() => downloadHtml(report)}
                          >
                            <FileCode className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
      </ModuleCard>

      <ReportsRegulatoryComplianceSection live={showLiveTable} reportRows={rows} />

      {showIllustration ? (
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle className="text-base">Example layout</CardTitle>
            <CardDescription>
              Shown when live report data is unavailable — these values are not approved or signed off.
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
