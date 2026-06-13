"use client"

import { useEffect, useMemo, useState, type ReactNode } from "react"
import {
  BarChart3,
  Bot,
  CheckCircle2,
  Clock,
  FileText,
  FlaskConical,
  ListChecks,
  MessageSquare,
  Network,
  ShieldAlert,
  XCircle,
  type LucideIcon,
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
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-violet)" }}
          >
            MolTrace · Automation ROI
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Automation ROI</h1>
          <p className="text-sm text-muted-foreground">
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
        <AlertCard variant="warning" title="ROI snapshot unavailable" description={errs.roi} />
      ) : null}
      {!loading && errs.tasks ? (
        <AlertCard variant="warning" title="Automation tasks unavailable" description={errs.tasks} />
      ) : null}
      {!loading && errs.workflow ? (
        <AlertCard variant="warning" title="Workflow summary unavailable" description={errs.workflow} />
      ) : null}
      {!loading && errs.feedback ? (
        <AlertCard variant="warning" title="Feedback list unavailable" description={errs.feedback} />
      ) : null}

      {allFailed ? (
        <AlertCard
          variant="info"
          title="Backend unavailable"
          description="We couldn't load live analytics. Metrics below are blank; illustrative trends appear only in the labeled Demo data section."
        />
      ) : null}

      {/* KPI cards — module-coded with severity stripes */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title={
            <span className="inline-flex items-center gap-1">
              Hours saved
              <InfoTooltip content={HOURS_SAVED_TOOLTIP} label="About hours saved" />
            </span>
          }
          icon={Clock}
          severity="green"
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
          icon={Bot}
          severity="violet"
          value={loading ? "…" : roi ? fmtInt(roi.tasks_automated) : "—"}
          sub={
            <p className="text-xs text-muted-foreground">
              {loading ? "Loading…" : roi ? "Total automated task runs across the platform." : "No data."}
            </p>
          }
        />
        <MetricCard
          title="Reports generated"
          icon={FileText}
          severity="green"
          value={loading ? "…" : roi ? fmtInt(roi.reports_generated) : "—"}
          sub={<p className="text-xs text-muted-foreground">reports_generated</p>}
        />
        <MetricCard
          title="Workflows completed"
          icon={CheckCircle2}
          severity="green"
          value={loading ? "…" : roi ? fmtInt(roi.workflows_completed) : "—"}
          sub={<p className="text-xs text-muted-foreground">workflows_completed</p>}
        />
        <MetricCard
          title="Analyses completed"
          icon={FlaskConical}
          severity="violet"
          value={loading ? "…" : roi ? fmtInt(roi.analyses_completed) : "—"}
          sub={<p className="text-xs text-muted-foreground">analyses_completed</p>}
        />
        <MetricCard
          title="Review tasks completed"
          icon={ListChecks}
          severity="violet"
          value={loading ? "…" : roi ? fmtInt(roi.review_tasks_completed) : "—"}
          sub={<p className="text-xs text-muted-foreground">review_tasks_completed</p>}
        />
        <MetricCard
          title="Failed jobs"
          icon={XCircle}
          severity="red"
          value={loading ? "…" : roi ? fmtInt(roi.failed_jobs) : "—"}
          sub={<p className="text-xs text-muted-foreground">failed_jobs</p>}
        />
        <MetricCard
          title="QC warnings"
          icon={ShieldAlert}
          severity="amber"
          value={loading ? "…" : roi ? fmtInt(roi.qc_warnings) : "—"}
          sub={<p className="text-xs text-muted-foreground">qc_warnings</p>}
        />
      </div>

      <ModuleCard
        accent="violet"
        eyebrow="Programs"
        title="Regentry events"
        icon={ListChecks}
        description="Privacy-safe activity events tracked in Regentry — only metadata such as dossier ID, jurisdiction, status, and review state. No regulatory questions, answers, or raw scientific payloads are recorded."
      >
        <div className="text-xs text-muted-foreground">
          <ul className="list-inside list-disc space-y-1">
            <li>regulatory_dossier_created</li>
            <li>regulatory_requirement_added</li>
            <li>regulatory_query_answered</li>
            <li>regulatory_readiness_report_generated</li>
            <li>regulatory_review_completed</li>
          </ul>
        </div>
      </ModuleCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <ModuleCard
          accent="violet"
          eyebrow="Methods"
          title="Top automated tasks"
          icon={Bot}
          description="Catalog of all automation task definitions with their default minutes-saved value. Run counts are populated when a per-task event stream is available."
        >
          <div>
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
          </div>
        </ModuleCard>

        <WorkflowValueCard workflow={workflow} loading={loading} />
      </div>

      <ModuleCard
        accent="violet"
        eyebrow="Quality"
        title="Feedback summary"
        icon={MessageSquare}
        description="Recent reviewer feedback events across all programs (preview only)."
      >
        <div>
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
        </div>
      </ModuleCard>

      <RenewalValueReportSection />

      {liveTrend && liveTrend.length > 0 ? (
        <RoiTrendCharts title="Hours & tasks trend (live metadata)" description="Parsed from ROI metadata_json when present." data={liveTrend} />
      ) : null}

      <ModuleCard
        accent="violet"
        eyebrow="Demo"
        title="Illustrative trends"
        icon={BarChart3}
        description="Synthetic weekly series for layout validation only — not derived from your deployment unless backend supplies matching trend payloads."
        badge={
          <Badge variant="secondary" className="font-normal">
            Demo data
          </Badge>
        }
      >
        <div>
          <RoiTrendCharts
            title=""
            description=""
            data={DEMO_TREND_DATA.map((r) => ({
              label: r.label,
              hours_saved: r.hours_saved,
              tasks_automated: r.tasks_automated,
            }))}
          />
        </div>
      </ModuleCard>
    </div>
  )
}

type MetricSeverity = "violet" | "green" | "amber" | "red"

const METRIC_SEVERITY_COLOR: Record<MetricSeverity, string> = {
  violet: "var(--mt-violet)",
  green: "var(--mt-green)",
  amber: "var(--mt-amber)",
  red: "var(--mt-red)",
}

function MetricCard({
  title,
  icon: Icon,
  value,
  sub,
  severity = "violet",
}: {
  title: ReactNode
  icon: LucideIcon
  value: string
  sub: ReactNode
  severity?: MetricSeverity
}) {
  const color = METRIC_SEVERITY_COLOR[severity]
  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: `3px solid ${color}` }}
    >
      <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
        <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{title}</CardTitle>
        <Icon className="h-4 w-4" style={{ color }} aria-hidden />
      </CardHeader>
      <CardContent className="pb-5">
        <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color }}>{value}</div>
        <div className="mt-2">{sub}</div>
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
    <ModuleCard
      accent="violet"
      eyebrow="Throughput"
      title="Workflow value summary"
      icon={Network}
      description="Aggregate workflow completion and time-saved totals across all templates. Hours saved are computed from total minutes saved (÷ 60)."
    >
      <div>
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
      </div>
    </ModuleCard>
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
