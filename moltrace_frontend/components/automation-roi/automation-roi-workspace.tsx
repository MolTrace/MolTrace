"use client"

import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import {
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bot,
  Calendar,
  Clock,
  Download,
  FileText,
  Info,
  ListChecks,
  Scale,
  Timer,
  TrendingUp,
} from "lucide-react"

/**
 * Illustrative automation ROI figures for demos and stakeholder reviews.
 * Replace with tenant telemetry + finance-approved baselines for production rollouts.
 */
const DEMO_LABEL = "Demo scenario — illustrative metrics only"

const DEMO_PERIOD = "Rolling 90-day cohort (synthetic)"

/** Weekly rolling mean calibration score on held-out verification batches (% agreement). Demo series. */
const MODEL_CONFIDENCE_TREND_WEEKLY = [
  { week: "W1", score: 88.4 },
  { week: "W2", score: 89.1 },
  { week: "W3", score: 89.6 },
  { week: "W4", score: 90.2 },
  { week: "W5", score: 90.0 },
  { week: "W6", score: 90.8 },
  { week: "W7", score: 91.3 },
  { week: "W8", score: 91.0 },
  { week: "W9", score: 91.6 },
  { week: "W10", score: 92.1 },
  { week: "W11", score: 91.9 },
  { week: "W12", score: 92.4 },
] as const

const REVIEW_QUEUE_DEMO = [
  { id: "a1", label: "SpectraCheck · batch SRX-2047", reason: "Contradiction across DEPT vs HSQC", severity: "high" as const },
  { id: "a2", label: "LC-MS · unknown feature cluster", reason: "Below consensus threshold", severity: "medium" as const },
  { id: "a3", label: "Regulatory excerpt · impurity narrative", reason: "Awaiting SME sign-off", severity: "medium" as const },
  { id: "a4", label: "NMR · solvent artifact suspected", reason: "Low S/N on weak multiplet", severity: "low" as const },
  { id: "a5", label: "Report composer · evidence gap", reason: "Missing cited attachment", severity: "medium" as const },
  { id: "a6", label: "Reaction Studio · yield model", reason: "Extrapolated condition outside training hull", severity: "medium" as const },
  { id: "a7", label: "Confidence suite · multi-modal tie", reason: "Manual adjudication requested", severity: "low" as const },
] as const

export default function AutomationRoiWorkspace() {
  const trendMax = Math.max(...MODEL_CONFIDENCE_TREND_WEEKLY.map((w) => w.score))
  const trendMin = Math.min(...MODEL_CONFIDENCE_TREND_WEEKLY.map((w) => w.score))
  const trendLatest = MODEL_CONFIDENCE_TREND_WEEKLY[MODEL_CONFIDENCE_TREND_WEEKLY.length - 1].score
  const trendFirst = MODEL_CONFIDENCE_TREND_WEEKLY[0].score
  const deltaTrend = trendLatest - trendFirst

  return (
    <div className="scientific-grid-subtle space-y-6 rounded-xl border bg-card/50 p-4 sm:p-6">
      <header className="flex flex-col gap-4 border-b pb-6 md:flex-row md:items-start md:justify-between">
        <div className="space-y-2">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-violet-ink)" }}
          >
            MolTrace · Automation ROI
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-2xl font-bold tracking-tight">Automation ROI</h1>
            <Badge variant="outline" className="font-normal">
              {DEMO_LABEL}
            </Badge>
          </div>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Executive view of automation leverage and review load. Figures below are{" "}
            <strong className="font-medium text-foreground">not</strong> connected to live billing or model telemetry;
            they are styled for credible narrative discussions with R&amp;D and finance stakeholders.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Badge variant="secondary" className="gap-1 font-normal">
            <Calendar className="h-3 w-3" />
            {DEMO_PERIOD}
          </Badge>
          <Button variant="outline" size="sm" className="gap-2" type="button" disabled>
            <Download className="h-4 w-4" />
            Export snapshot
          </Button>
        </div>
      </header>

      {/* Core KPIs — all requested metrics visible at a glance */}
      <section aria-label="Automation KPIs (demo)">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-green)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Hours saved</CardTitle>
              <Clock className="h-4 w-4" style={{ color: "var(--mt-green)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-green)" }}>847</div>
              <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                <TrendingUp className="h-3 w-3" style={{ color: "var(--mt-green)" }} aria-hidden />
                <span style={{ color: "var(--mt-green)" }}>+23%</span>
                vs prior window (demo)
              </p>
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-violet)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Tasks automated</CardTitle>
              <Bot className="h-4 w-4" style={{ color: "var(--mt-violet)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-violet-ink)" }}>4,820</div>
              <p className="mt-2 text-xs text-muted-foreground">
                Discrete pipeline substeps executed without manual intervention (demo definition).
              </p>
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-green)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Reports generated</CardTitle>
              <FileText className="h-4 w-4" style={{ color: "var(--mt-green)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-green)" }}>156</div>
              <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                <TrendingUp className="h-3 w-3" style={{ color: "var(--mt-green)" }} aria-hidden />
                <span style={{ color: "var(--mt-green)" }}>+15%</span>
                structured outputs (demo)
              </p>
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-violet)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Manual review steps avoided</CardTitle>
              <ListChecks className="h-4 w-4" style={{ color: "var(--mt-violet)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-violet-ink)" }}>2,341</div>
              <p className="mt-2 text-xs text-muted-foreground">
                Checkpoints bypassed when automation gates and evidence thresholds passed (demo).
              </p>
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-green)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Avg. upload → report time</CardTitle>
              <Timer className="h-4 w-4" style={{ color: "var(--mt-green)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-green)" }}>
                12<span className="text-lg font-normal text-muted-foreground"> min</span>
              </div>
              <p className="mt-2 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-0.5" style={{ color: "var(--mt-green)" }}>
                  <ArrowDownRight className="h-3 w-3" aria-hidden />
                  −18%
                </span>
                median wall-clock (demo cohort); IQR not shown.
              </p>
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-amber)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Analyses requiring review</CardTitle>
              <AlertCircle className="h-4 w-4" style={{ color: "var(--mt-amber)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-amber)" }}>7</div>
              <p className="mt-2 text-xs text-muted-foreground">
                Open items needing human adjudication or cited evidence (demo queue).
              </p>
            </CardContent>
          </Card>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Model confidence trend */}
        <ModuleCard
          accent="violet"
          eyebrow="Quality"
          title="Model confidence trend"
          icon={BarChart3}
          description="Rolling weekly mean agreement against held-out verification batches — illustrative series only."
          className="lg:col-span-3"
          badge={
            <Badge variant="secondary" className="shrink-0 font-mono text-xs tabular-nums">
              Latest {trendLatest.toFixed(1)}%
            </Badge>
          }
        >
          <div className="space-y-4">
            <div className="flex h-52 items-end gap-1 sm:gap-1.5">
              {MODEL_CONFIDENCE_TREND_WEEKLY.map((pt) => (
                <div key={pt.week} className="flex flex-1 flex-col items-center gap-1">
                  <span className="max-w-full truncate text-[10px] font-mono text-muted-foreground tabular-nums sm:text-xs">
                    {pt.score.toFixed(1)}
                  </span>
                  <div
                    className="w-full rounded-t-md bg-primary/80 transition-colors hover:bg-primary"
                    style={{
                      height: `${((pt.score - trendMin) / (trendMax - trendMin || 1)) * 140 + 24}px`,
                      minHeight: "12px",
                    }}
                    title={`${pt.week}: ${pt.score}%`}
                  />
                  <span className="text-[10px] text-muted-foreground sm:text-xs">{pt.week}</span>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <Info className="h-3.5 w-3.5 shrink-0" aria-hidden />
                Not live telemetry — use calibration dashboards before citing externally.
              </span>
              <span className="inline-flex items-center gap-1 font-medium text-foreground">
                {deltaTrend >= 0 ? (
                  <ArrowUpRight className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" aria-hidden />
                ) : (
                  <ArrowDownRight className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" aria-hidden />
                )}
                <span className="tabular-nums">
                  {deltaTrend >= 0 ? "+" : ""}
                  {deltaTrend.toFixed(1)} pts vs week 1
                </span>
              </span>
            </div>
          </div>
        </ModuleCard>

        {/* Review queue detail */}
        <ModuleCard
          accent="violet"
          eyebrow="Review"
          title="Review queue (demo)"
          icon={Scale}
          description="Scientific credibility depends on traceable evidence — automation reduces volume, not accountability."
          className="lg:col-span-2"
        >
          <div>
            <ul className="max-h-64 space-y-2 overflow-y-auto pr-1 text-sm">
              {REVIEW_QUEUE_DEMO.map((item) => (
                <li
                  key={item.id}
                  className="rounded-md border border-border/80 bg-background/80 px-3 py-2"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium leading-snug">{item.label}</span>
                    <Badge
                      variant="outline"
                      className={
                        item.severity === "high"
                          ? "border-destructive/50 text-destructive"
                          : item.severity === "medium"
                            ? "border-amber-600/50 text-amber-700 dark:text-amber-400"
                            : "text-muted-foreground"
                      }
                    >
                      {item.severity}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{item.reason}</p>
                </li>
              ))}
            </ul>
          </div>
        </ModuleCard>
      </div>

      {/* Renewal value — executive summary */}
      <ModuleCard
        accent="violet"
        eyebrow="ROI"
        title="Renewal value summary"
        icon={TrendingUp}
        description="Condensed storyline for finance and leadership — replace placeholders with audited inputs for contracts."
        className="bg-muted/20"
      >
        <div className="grid gap-6 md:grid-cols-2">
          <div className="space-y-3 text-sm">
            <div className="flex justify-between gap-4 border-b border-border/80 py-2">
              <span className="text-muted-foreground">Hours redirected to discovery (YTD, demo)</span>
              <span className="font-semibold tabular-nums">9,840</span>
            </div>
            <div className="flex justify-between gap-4 border-b border-border/80 py-2">
              <span className="text-muted-foreground">FTE equivalent @ 2,000 h/y</span>
              <span className="font-semibold tabular-nums">4.9</span>
            </div>
            <div className="flex justify-between gap-4 border-b border-border/80 py-2">
              <span className="text-muted-foreground">Regulatory-ready reports (demo count)</span>
              <span className="font-semibold tabular-nums">1,847</span>
            </div>
            <div className="flex justify-between gap-4 py-2">
              <span className="text-muted-foreground">Estimated cost avoidance (illustrative)</span>
              <span className="font-semibold tabular-nums text-primary">$492K</span>
            </div>
          </div>
          <div className="flex flex-col justify-between gap-4 rounded-lg border bg-background p-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Narrative anchor (demo)
              </p>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Automation shifted analytical labor from repetitive interpretation to targeted review. Model-assisted
                workflows maintained evidence-first checkpoints — suitable for renewal discussions when paired with your
                organization&apos;s baseline labor rates and quality metrics.
              </p>
            </div>
            <Separator />
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="text-xs text-muted-foreground">Illustrative ROI multiple (demo)</p>
                <p className="text-3xl font-semibold tabular-nums text-primary">12.3×</p>
              </div>
              <Button variant="outline" size="sm" className="gap-2" type="button" disabled>
                <Download className="h-4 w-4" />
                Executive one-pager
              </Button>
            </div>
          </div>
        </div>
      </ModuleCard>

      <p className="text-center text-xs text-muted-foreground">
        Production deployments should tie each KPI to instrument logs, workflow IDs, and finance-approved burdened rates.
      </p>
    </div>
  )
}
