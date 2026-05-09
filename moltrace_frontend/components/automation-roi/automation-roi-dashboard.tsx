"use client"

import { useEffect, useMemo, useState, type ReactNode } from "react"
import {
  Bot,
  CheckCircle2,
  Clock,
  FileText,
  FlaskConical,
  ListChecks,
  ShieldAlert,
  XCircle,
} from "lucide-react"
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { RenewalValueReportSection } from "@/components/automation-roi/renewal-value-report-section"
import { FeedbackButton } from "@/src/components/analytics/FeedbackButton"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  loadRoiDashboardData,
  parseTrendSeriesFromRoiMetadata,
  type AutomationTaskRow,
  type FeedbackRow,
  type RoiDashboardLoadResult,
  type WorkflowSummaryData,
} from "@/src/lib/analytics/roi-dashboard-data"

const HOURS_SAVED_TOOLTIP =
  "Estimated time saved using configurable automation task definitions. Values are approximate and should be reviewed by admins."

const TASKS_AUTOMATED_TOOLTIP =
  "Count of workflow and analysis tasks completed by MolTrace instead of manual execution."

/** Clearly labeled synthetic series — not live backend metrics. */
const DEMO_TREND_DATA = [
  { label: "W1", hours_saved: 42, tasks_automated: 120 },
  { label: "W2", hours_saved: 48, tasks_automated: 132 },
  { label: "W3", hours_saved: 51, tasks_automated: 141 },
  { label: "W4", hours_saved: 55, tasks_automated: 148 },
  { label: "W5", hours_saved: 53, tasks_automated: 145 },
  { label: "W6", hours_saved: 58, tasks_automated: 156 },
  { label: "W7", hours_saved: 61, tasks_automated: 162 },
  { label: "W8", hours_saved: 59, tasks_automated: 158 },
] as const

function fmtNum(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "—"
  return n.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 })
}

function fmtInt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—"
  return String(Math.round(n))
}

function previewComment(s: string | null, max = 72): string {
  if (!s?.trim()) return "—"
  const t = s.replace(/\s+/g, " ").trim()
  return t.length <= max ? t : `${t.slice(0, max)}…`
}

function formatFeedbackDate(iso: string): string {
  const ms = Date.parse(iso)
  if (Number.isNaN(ms)) return iso
  return new Date(ms).toLocaleString()
}

export default function AutomationRoiDashboard() {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<RoiDashboardLoadResult | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    void loadRoiDashboardData().then((res) => {
      if (!active) return
      setData(res)
      setLoading(false)
    })
    return () => {
      active = false
    }
  }, [])

  const roi = data?.roi ?? null
  const tasks = data?.tasks ?? []
  const workflow = data?.workflow ?? null
  const feedback = data?.feedback ?? []
  const errs = data?.errors ?? {}
  const ok = data?.ok

  const liveTrend = useMemo(() => {
    if (!roi?.metadata_json) return null
    return parseTrendSeriesFromRoiMetadata(roi.metadata_json)
  }, [roi])

  const topTasks = useMemo(() => {
    return [...tasks].sort((a, b) => b.default_minutes_saved - a.default_minutes_saved).slice(0, 15)
  }, [tasks])

  const anyEndpointOk = ok && (ok.roi || ok.tasks || ok.workflow || ok.feedback)
  const allFailed = !loading && data && !anyEndpointOk

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Automation ROI</h1>
          <p className="text-muted-foreground">
            Operational value from automation definitions and usage events. Aggregates exclude raw scientific payloads.
          </p>
          {roi?.period_start && roi?.period_end ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Snapshot window: {roi.period_start} → {roi.period_end}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FeedbackButton module="roi" />
          <BackendStatusIndicator />
        </div>
      </div>

      {!loading && errs.roi ? (
        <Alert variant="default" className="border-muted bg-muted/30">
          <AlertTitle className="text-sm">ROI snapshot unavailable</AlertTitle>
          <AlertDescription className="text-xs text-muted-foreground">{errs.roi}</AlertDescription>
        </Alert>
      ) : null}
      {!loading && errs.tasks ? (
        <Alert variant="default" className="border-muted bg-muted/30">
          <AlertTitle className="text-sm">Automation tasks unavailable</AlertTitle>
          <AlertDescription className="text-xs text-muted-foreground">{errs.tasks}</AlertDescription>
        </Alert>
      ) : null}
      {!loading && errs.workflow ? (
        <Alert variant="default" className="border-muted bg-muted/30">
          <AlertTitle className="text-sm">Workflow summary unavailable</AlertTitle>
          <AlertDescription className="text-xs text-muted-foreground">{errs.workflow}</AlertDescription>
        </Alert>
      ) : null}
      {!loading && errs.feedback ? (
        <Alert variant="default" className="border-muted bg-muted/30">
          <AlertTitle className="text-sm">Feedback list unavailable</AlertTitle>
          <AlertDescription className="text-xs text-muted-foreground">{errs.feedback}</AlertDescription>
        </Alert>
      ) : null}

      {allFailed ? (
        <Alert>
          <AlertTitle className="text-sm">Backend unavailable</AlertTitle>
          <AlertDescription className="text-xs">
            We couldn&apos;t load live analytics. Metrics below are blank; illustrative trends appear only in the labeled Demo data section.
          </AlertDescription>
        </Alert>
      ) : null}

      {/* KPI cards — v0-style density (text-2xl, text-sm titles) */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title={
            <span className="inline-flex items-center gap-1">
              Hours saved
              <InfoTooltip content={HOURS_SAVED_TOOLTIP} label="About hours saved" />
            </span>
          }
          icon={<Clock className="h-4 w-4 text-muted-foreground" />}
          value={loading ? "…" : roi ? fmtNum(roi.total_hours_saved) : "—"}
          sub={
            <p className="text-xs text-muted-foreground">
              {loading ? "Loading…" : roi ? "Total hours saved across all automated tasks." : "No data."}
            </p>
          }
        />
        <MetricCard
          title={
            <span className="inline-flex items-center gap-1">
              Tasks automated
              <InfoTooltip content={TASKS_AUTOMATED_TOOLTIP} label="About tasks automated" />
            </span>
          }
          icon={<Bot className="h-4 w-4 text-muted-foreground" />}
          value={loading ? "…" : roi ? fmtInt(roi.tasks_automated) : "—"}
          sub={
            <p className="text-xs text-muted-foreground">
              {loading ? "Loading…" : roi ? "Total automated task runs across the platform." : "No data."}
            </p>
          }
        />
        <MetricCard
          title="Reports generated"
          icon={<FileText className="h-4 w-4 text-muted-foreground" />}
          value={loading ? "…" : roi ? fmtInt(roi.reports_generated) : "—"}
          sub={<p className="text-xs text-muted-foreground">reports_generated</p>}
        />
        <MetricCard
          title="Workflows completed"
          icon={<CheckCircle2 className="h-4 w-4 text-muted-foreground" />}
          value={loading ? "…" : roi ? fmtInt(roi.workflows_completed) : "—"}
          sub={<p className="text-xs text-muted-foreground">workflows_completed</p>}
        />
        <MetricCard
          title="Analyses completed"
          icon={<FlaskConical className="h-4 w-4 text-muted-foreground" />}
          value={loading ? "…" : roi ? fmtInt(roi.analyses_completed) : "—"}
          sub={<p className="text-xs text-muted-foreground">analyses_completed</p>}
        />
        <MetricCard
          title="Review tasks completed"
          icon={<ListChecks className="h-4 w-4 text-muted-foreground" />}
          value={loading ? "…" : roi ? fmtInt(roi.review_tasks_completed) : "—"}
          sub={<p className="text-xs text-muted-foreground">review_tasks_completed</p>}
        />
        <MetricCard
          title="Failed jobs"
          icon={<XCircle className="h-4 w-4 text-muted-foreground" />}
          value={loading ? "…" : roi ? fmtInt(roi.failed_jobs) : "—"}
          sub={<p className="text-xs text-muted-foreground">failed_jobs</p>}
        />
        <MetricCard
          title="QC warnings"
          icon={<ShieldAlert className="h-4 w-4 text-muted-foreground" />}
          value={loading ? "…" : roi ? fmtInt(roi.qc_warnings) : "—"}
          sub={<p className="text-xs text-muted-foreground">qc_warnings</p>}
        />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Regulatory Hub events</CardTitle>
          <CardDescription>
            Privacy-safe activity events tracked in Regulatory Hub — only metadata such as dossier ID, jurisdiction, status, and review state. No regulatory questions, answers, or raw scientific payloads are recorded.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-xs text-muted-foreground">
          <ul className="list-inside list-disc space-y-1">
            <li>regulatory_dossier_created</li>
            <li>regulatory_requirement_added</li>
            <li>regulatory_query_answered</li>
            <li>regulatory_readiness_report_generated</li>
            <li>regulatory_review_completed</li>
          </ul>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Top automated tasks</CardTitle>
            <CardDescription>
              Catalog of all automation task definitions with their default minutes-saved value. Run counts are populated when a per-task event stream is available.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>task</TableHead>
                    <TableHead>category</TableHead>
                    <TableHead className="text-right">runs</TableHead>
                    <TableHead className="text-right">minutes saved</TableHead>
                    <TableHead className="text-right">hours saved</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                        Loading…
                      </TableCell>
                    </TableRow>
                  ) : topTasks.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                        No task definitions loaded.
                      </TableCell>
                    </TableRow>
                  ) : (
                    topTasks.map((t: AutomationTaskRow) => (
                      <TableRow key={t.id}>
                        <TableCell className="max-w-[220px] truncate font-medium">{t.name}</TableCell>
                        <TableCell className="text-muted-foreground">{t.category}</TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">—</TableCell>
                        <TableCell className="text-right tabular-nums">{fmtNum(t.default_minutes_saved, 2)}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmtNum(t.default_minutes_saved / 60, 3)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>

        <WorkflowValueCard workflow={workflow} loading={loading} />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Feedback summary</CardTitle>
          <CardDescription>Recent reviewer feedback events across all programs (preview only).</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="table-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>type</TableHead>
                  <TableHead className="text-right">rating</TableHead>
                  <TableHead>comment preview</TableHead>
                  <TableHead>date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center text-sm text-muted-foreground">
                      Loading…
                    </TableCell>
                  </TableRow>
                ) : feedback.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center text-sm text-muted-foreground">
                      No feedback rows loaded.
                    </TableCell>
                  </TableRow>
                ) : (
                  feedback.map((f: FeedbackRow) => (
                    <TableRow key={f.id}>
                      <TableCell className="font-mono text-xs">{f.feedback_type}</TableCell>
                      <TableCell className="text-right tabular-nums">{f.rating != null ? f.rating : "—"}</TableCell>
                      <TableCell className="max-w-md text-sm text-muted-foreground">{previewComment(f.comment)}</TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatFeedbackDate(f.created_at)}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <RenewalValueReportSection />

      {liveTrend && liveTrend.length > 0 ? (
        <RoiTrendCharts title="Hours & tasks trend (live metadata)" description="Parsed from ROI metadata_json when present." data={liveTrend} />
      ) : null}

      <Card className="border-dashed">
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">Illustrative trends</CardTitle>
            <Badge variant="secondary" className="font-normal">
              Demo data
            </Badge>
          </div>
          <CardDescription>
            Synthetic weekly series for layout validation only — not derived from your deployment unless backend supplies
            matching trend payloads.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RoiTrendCharts
            title=""
            description=""
            data={DEMO_TREND_DATA.map((r) => ({
              label: r.label,
              hours_saved: r.hours_saved,
              tasks_automated: r.tasks_automated,
            }))}
          />
        </CardContent>
      </Card>
    </div>
  )
}

function MetricCard({
  title,
  icon,
  value,
  sub,
}: {
  title: ReactNode
  icon: ReactNode
  value: string
  sub: ReactNode
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold tabular-nums">{value}</div>
        {sub}
      </CardContent>
    </Card>
  )
}

function WorkflowValueCard({
  workflow,
  loading,
}: {
  workflow: WorkflowSummaryData | null
  loading: boolean
}) {
  const hoursFromWorkflow = workflow ? workflow.total_minutes_saved / 60 : null
  const rowName = "Workflow runs (aggregate)"

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Workflow value summary</CardTitle>
        <CardDescription>
          Aggregate workflow completion and time-saved totals across all templates. Hours saved are computed from total minutes saved (÷ 60).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="table-scroll">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>workflow</TableHead>
                <TableHead className="text-right">completed runs</TableHead>
                <TableHead className="text-right">failed runs</TableHead>
                <TableHead className="text-right">average duration</TableHead>
                <TableHead className="text-right">hours saved</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                    Loading…
                  </TableCell>
                </TableRow>
              ) : (
                <TableRow>
                  <TableCell className="font-medium">{rowName}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {workflow ? fmtInt(workflow.workflows_completed) : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {workflow ? fmtInt(workflow.workflows_failed) : "—"}
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">—</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {hoursFromWorkflow != null ? fmtNum(hoursFromWorkflow, 2) : "—"}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

function RoiTrendCharts({
  title,
  description,
  data,
}: {
  title: string
  description: string
  data: { label: string; hours_saved: number; tasks_automated: number }[]
}) {
  return (
    <div className="space-y-3">
      {title ? (
        <div>
          <h3 className="text-sm font-medium">{title}</h3>
          {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
        </div>
      ) : null}
      <div className="h-64 w-full min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} width={40} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} width={44} />
            <RechartsTooltip contentStyle={{ fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="hours_saved"
              name="Hours saved"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              dot={false}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="tasks_automated"
              name="Tasks automated"
              stroke="hsl(var(--muted-foreground))"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
