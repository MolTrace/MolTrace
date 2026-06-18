"use client"

import dynamic from "next/dynamic"
import { useEffect, useMemo, useState, type ComponentType } from "react"
import { Target, TriangleAlert } from "lucide-react"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
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
import {
  formatHypervolume,
  hypervolumeMethodLabel,
  type HypervolumePoint,
  type ParetoFront,
  type ParetoMember,
} from "@/lib/reaction/pareto"

// Client-side-only Plotly: the dynamic boundary keeps the SSR shell light and
// ensures react-plotly.js never touches `window` during server render (same
// pattern as the SpectraCheck spectrum viewers).
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as ComponentType<
  Record<string, unknown>
>

// Graphical (non-text) marker colors — fine on both light and dark plot areas.
const C_DOMINATED = "#94a3b8" // slate-400
const C_FRONT = "#6B3FE0" // --mt-violet (optimization module)
const C_KNEE = "#E8A030" // --mt-amber

/** Track the app theme (next-themes toggles `.dark` on <html>) so Plotly axis
 *  text and gridlines stay legible in both modes — Plotly can't read CSS vars. */
function useIsDarkMode(): boolean {
  const [dark, setDark] = useState(false)
  useEffect(() => {
    const el = document.documentElement
    const sync = () => setDark(el.classList.contains("dark"))
    sync()
    const obs = new MutationObserver(sync)
    obs.observe(el, { attributes: true, attributeFilter: ["class"] })
    return () => obs.disconnect()
  }, [])
  return dark
}

function memberLabel(m: ParetoMember): string {
  return m.experimentCode ?? (m.experimentId != null ? `exp ${m.experimentId}` : "—")
}

function MetricCard({ label, value, caption }: { label: string; value: string; caption?: string }) {
  return (
    <div className="rounded-md bg-muted/50 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-2xl font-semibold tabular-nums">{value}</p>
      {caption ? <p className="mt-0.5 text-[11px] text-muted-foreground">{caption}</p> : null}
    </div>
  )
}

export function ParetoFrontPanel({
  front,
  trend,
}: {
  front: ParetoFront
  trend: HypervolumePoint[]
}) {
  const dark = useIsDarkMode()
  const objs = front.objectives

  // Hold the user's axis choices, but derive the effective pair so it always
  // falls back to valid defaults when the objective set changes (new run) —
  // no reset effect needed.
  const [xSel, setXSel] = useState<string | null>(null)
  const [ySel, setYSel] = useState<string | null>(null)
  const xObj = xSel && objs.includes(xSel) ? xSel : objs[0] ?? ""
  const yObj = ySel && objs.includes(ySel) ? ySel : objs[1] ?? objs[0] ?? ""

  const knee =
    front.kneeExperimentId != null
      ? front.members.find((m) => m.experimentId === front.kneeExperimentId) ?? null
      : null

  const fontColor = dark ? "#cbd5e1" : "#334155"
  const gridColor = dark ? "rgba(148,163,184,0.22)" : "rgba(100,116,139,0.18)"

  const { data, layout } = useMemo(() => {
    const dominated = front.members.filter((m) => !m.nonDominated)
    const frontMembers = front.members
      .filter((m) => m.nonDominated)
      .sort((a, b) => (a.objectives[xObj] ?? 0) - (b.objectives[xObj] ?? 0))

    const trace = (members: ParetoMember[]) => ({
      x: members.map((m) => m.objectives[xObj] ?? null),
      y: members.map((m) => m.objectives[yObj] ?? null),
      text: members.map(memberLabel),
    })

    const hover = `%{text}<br>${xObj}: %{x}<br>${yObj}: %{y}<extra></extra>`
    const traces: Record<string, unknown>[] = [
      {
        ...trace(dominated),
        type: "scatter",
        mode: "markers",
        name: "evaluated",
        marker: { color: C_DOMINATED, size: 9, opacity: 0.7 },
        hovertemplate: hover,
      },
      {
        ...trace(frontMembers),
        type: "scatter",
        mode: "lines+markers",
        name: "Pareto front",
        line: { color: C_FRONT, width: 2 },
        marker: { color: C_FRONT, size: 12 },
        hovertemplate: hover,
      },
    ]
    if (knee) {
      traces.push({
        x: [knee.objectives[xObj] ?? null],
        y: [knee.objectives[yObj] ?? null],
        text: [memberLabel(knee)],
        type: "scatter",
        mode: "markers",
        name: "knee (balanced)",
        marker: { color: C_KNEE, size: 18, symbol: "circle-open", line: { color: C_KNEE, width: 3 } },
        hovertemplate: hover,
      })
    }

    return {
      data: traces,
      layout: {
        autosize: true,
        height: 360,
        margin: { l: 64, r: 16, t: 10, b: 48 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: fontColor, size: 12 },
        xaxis: { title: { text: xObj }, gridcolor: gridColor, zerolinecolor: gridColor },
        yaxis: { title: { text: yObj }, gridcolor: gridColor, zerolinecolor: gridColor },
        legend: { orientation: "h", y: -0.22, font: { color: fontColor } },
        showlegend: true,
        hovermode: "closest",
      },
    }
  }, [front, xObj, yObj, knee, fontColor, gridColor])

  const trendPlot = useMemo(() => {
    if (trend.length < 2) return null
    return {
      data: [
        {
          x: trend.map((p, i) => p.boRunId ?? i + 1),
          y: trend.map((p) => p.hypervolume),
          type: "scatter",
          mode: "lines+markers",
          line: { color: C_FRONT, width: 2 },
          marker: { color: C_FRONT, size: 8 },
          hovertemplate: "BO run %{x}<br>hypervolume: %{y}<extra></extra>",
        },
      ] as Record<string, unknown>[],
      layout: {
        autosize: true,
        height: 180,
        margin: { l: 64, r: 16, t: 10, b: 40 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: fontColor, size: 11 },
        xaxis: { title: { text: "BO run" }, gridcolor: gridColor, zerolinecolor: gridColor },
        yaxis: { title: { text: "hypervolume" }, gridcolor: gridColor, zerolinecolor: gridColor },
        showlegend: false,
        hovermode: "closest",
      },
    }
  }, [trend, fontColor, gridColor])

  const frontMembers = front.members.filter((m) => m.nonDominated)
  const plotConfig = { displayModeBar: false, responsive: true }

  return (
    <ModuleCard
      accent="violet"
      eyebrow="Optimization · Multi-Objective Trade-offs"
      title="Pareto front & hypervolume"
      description="Non-dominated set over the weighted multi-objective dimensions, with the dominated-hypervolume indicator. Advisory decision-support; requires human review."
    >
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <MetricCard
            label="hypervolume"
            value={formatHypervolume(front.hypervolume)}
            caption={
              front.hypervolumeMethod ? `method: ${hypervolumeMethodLabel(front.hypervolumeMethod)}` : undefined
            }
          />
          <MetricCard
            label="Pareto size"
            value={front.paretoSize != null ? String(front.paretoSize) : String(frontMembers.length)}
            caption="non-dominated points"
          />
          <MetricCard
            label="evaluated"
            value={
              front.evaluatedExperimentCount != null
                ? String(front.evaluatedExperimentCount)
                : String(front.members.length)
            }
            caption="experiments scored"
          />
        </div>

        {objs.length > 2 ? (
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label className="text-xs">X objective</Label>
              <Select value={xObj} onValueChange={setXSel}>
                <SelectTrigger className="h-9 w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {objs.map((o) => (
                    <SelectItem key={o} value={o}>
                      {o}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Y objective</Label>
              <Select value={yObj} onValueChange={setYSel}>
                <SelectTrigger className="h-9 w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {objs.map((o) => (
                    <SelectItem key={o} value={o}>
                      {o}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <p className="text-[11px] text-muted-foreground">
              {objs.length} objectives — choose any two to inspect the trade-off.
            </p>
          </div>
        ) : null}

        <div className="rounded-md border border-border p-2">
          <Plot
            data={data}
            layout={layout}
            config={plotConfig}
            useResizeHandler
            style={{ width: "100%", height: "360px" }}
          />
        </div>

        {/* Front members — accessible, screen-readable summary of the trade-off set. */}
        <div className="table-scroll">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">experiment</TableHead>
                {objs.map((o) => (
                  <TableHead key={o} className="text-right text-xs">
                    {o}
                  </TableHead>
                ))}
                <TableHead className="text-xs">role</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {frontMembers.map((m) => {
                const isKnee = m.experimentId != null && m.experimentId === front.kneeExperimentId
                return (
                  <TableRow key={String(m.experimentId ?? memberLabel(m))}>
                    <TableCell className="font-mono text-xs">{memberLabel(m)}</TableCell>
                    {objs.map((o) => (
                      <TableCell key={o} className="text-right font-mono text-xs tabular-nums">
                        {m.objectives[o] != null
                          ? m.objectives[o].toLocaleString(undefined, { maximumFractionDigits: 2 })
                          : "—"}
                      </TableCell>
                    ))}
                    <TableCell>
                      {isKnee ? (
                        <Badge
                          variant="secondary"
                          className="gap-1"
                          style={{ backgroundColor: "var(--mt-amber-soft)", color: "var(--mt-amber)" }}
                        >
                          <Target className="h-3 w-3" aria-hidden />
                          knee · balanced
                        </Badge>
                      ) : (
                        <Badge
                          variant="secondary"
                          style={{ backgroundColor: "var(--mt-violet-soft)", color: "var(--mt-violet-ink)" }}
                        >
                          Pareto
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
              {frontMembers.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={objs.length + 2} className="text-muted-foreground">
                    No non-dominated members.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>

        {trendPlot ? (
          <div className="space-y-1">
            <p className="text-sm font-medium">Hypervolume convergence</p>
            <p className="text-[11px] text-muted-foreground">
              Across this project&apos;s BO runs for the same objective set — rising hypervolume indicates the
              optimizer is expanding the achievable trade-off frontier.
            </p>
            <div className="rounded-md border border-border p-2">
              <Plot
                data={trendPlot.data}
                layout={trendPlot.layout}
                config={plotConfig}
                useResizeHandler
                style={{ width: "100%", height: "180px" }}
              />
            </div>
          </div>
        ) : null}

        {front.note ? (
          <div className="flex items-start gap-2 rounded-md border border-dashed border-border bg-muted/30 p-3">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
            <p className="text-xs text-muted-foreground">{front.note}</p>
          </div>
        ) : null}
      </div>
    </ModuleCard>
  )
}
