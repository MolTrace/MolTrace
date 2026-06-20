"use client"

import { useEffect, useMemo, useState } from "react"
import {
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { ScatterChart as ScatterChartIcon } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
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

const EMPTY_COPY =
  "Add completed experiments with numeric outcomes to visualize reaction response."

const OUTCOME_FIELDS = [
  { value: "yield_percent", label: "yield_percent" },
  { value: "selectivity_percent", label: "selectivity_percent" },
] as const

const CHART_FILLS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
]

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  return null
}

function readOutcomeNumber(exp: Record<string, unknown>, field: string): number | null {
  const outcome = exp.outcome
  if (isRecord(outcome)) {
    const v = readNum(outcome[field])
    if (v != null) return v
  }
  const oj = exp.outcome_json
  if (isRecord(oj)) {
    const v = readNum(oj[field])
    if (v != null) return v
  }
  return null
}

function readConditionNumber(cj: unknown, key: string): number | null {
  if (!isRecord(cj)) return null
  const v = cj[key]
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string") {
    const n = Number.parseFloat(v)
    if (Number.isFinite(n)) return n
  }
  return null
}

type ScatterPoint = {
  id: string
  code: string
  x: number
  y: number
  status: string
}

type Cond2Point = {
  id: string
  code: string
  vx: number
  vy: number
  outcome: number
}

function numericVariableNames(
  variableRecords: Record<string, unknown>[],
  variableNamesOrdered: string[],
): string[] {
  const numeric = new Set<string>()
  for (const v of variableRecords) {
    const name = typeof v.name === "string" ? v.name.trim() : ""
    const vt = typeof v.variable_type === "string" ? v.variable_type : ""
    if (name && vt === "numeric") numeric.add(name)
  }
  return variableNamesOrdered.filter((n) => numeric.has(n))
}

function statusColorMap(statuses: string[]): Map<string, string> {
  const uniq = [...new Set(statuses)].sort()
  const m = new Map<string, string>()
  uniq.forEach((s, i) => {
    m.set(s, CHART_FILLS[i % CHART_FILLS.length])
  })
  return m
}

export type ReactionResponseOverviewProps = {
  loading: boolean
  experiments: Record<string, unknown>[]
  variableRecords: Record<string, unknown>[]
  variableNamesOrdered: string[]
}

export function ReactionResponseOverview({
  loading,
  experiments,
  variableRecords,
  variableNamesOrdered,
}: ReactionResponseOverviewProps) {
  const [outcomeField, setOutcomeField] = useState<string>("yield_percent")
  const [xVarKey, setXVarKey] = useState<string>("")

  const numericVars = useMemo(
    () => numericVariableNames(variableRecords, variableNamesOrdered),
    [variableRecords, variableNamesOrdered],
  )

  useEffect(() => {
    if (numericVars.length === 0) return
    if (!xVarKey || !numericVars.includes(xVarKey)) {
      setXVarKey(numericVars[0])
    }
  }, [numericVars, xVarKey])

  const primaryPoints = useMemo(() => {
    const xv = xVarKey || numericVars[0] || ""
    if (!xv) return []
    const out: ScatterPoint[] = []
    for (const e of experiments) {
      if (e.status !== "completed") continue
      const yv = readOutcomeNumber(e, outcomeField)
      if (yv == null) continue
      const xn = readConditionNumber(e.conditions_json, xv)
      if (xn == null) continue
      const code = typeof e.experiment_code === "string" ? e.experiment_code : String(e.id ?? "")
      const st = typeof e.status === "string" ? e.status : "unknown"
      out.push({
        id: String(e.id ?? code),
        code,
        x: xn,
        y: yv,
        status: st,
      })
    }
    return out
  }, [experiments, outcomeField, numericVars, xVarKey])

  const v1 = numericVars[0] ?? ""
  const v2 = numericVars[1] ?? ""

  const cond2Points = useMemo(() => {
    if (!v1 || !v2) return []
    const out: Cond2Point[] = []
    for (const e of experiments) {
      if (e.status !== "completed") continue
      const yv = readOutcomeNumber(e, outcomeField)
      if (yv == null) continue
      const xa = readConditionNumber(e.conditions_json, v1)
      const xb = readConditionNumber(e.conditions_json, v2)
      if (xa == null || xb == null) continue
      const code = typeof e.experiment_code === "string" ? e.experiment_code : String(e.id ?? "")
      out.push({
        id: String(e.id ?? code),
        code,
        vx: xa,
        vy: xb,
        outcome: yv,
      })
    }
    return out
  }, [experiments, outcomeField, v1, v2])

  const colorByStatus = useMemo(() => statusColorMap(primaryPoints.map((p) => p.status)), [primaryPoints])

  const outcomeRange = useMemo(() => {
    const ys = cond2Points.map((p) => p.outcome)
    if (ys.length === 0) return { min: 0, max: 1 }
    return { min: Math.min(...ys), max: Math.max(...ys) }
  }, [cond2Points])

  function outcomeFill(o: number): string {
    const { min, max } = outcomeRange
    if (max <= min) return CHART_FILLS[0]
    const t = (o - min) / (max - min)
    const idx = Math.min(CHART_FILLS.length - 1, Math.max(0, Math.floor(t * CHART_FILLS.length)))
    return CHART_FILLS[idx]
  }

  const xAxisKey = xVarKey || numericVars[0] || ""

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Reaction response overview</CardTitle>
        <CardDescription>
          Completed experiments with numeric condition values and outcome_json / outcome fields (yield_percent or
          selectivity_percent). Points are colored by experiment status.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <p className="text-sm text-muted-foreground">…</p>
        ) : numericVars.length === 0 || primaryPoints.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <ScatterChartIcon />
              </EmptyMedia>
              <EmptyTitle>Nothing to plot yet</EmptyTitle>
              <EmptyDescription>{EMPTY_COPY}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : null}

        {numericVars.length > 0 && !loading && primaryPoints.length > 0 ? (
          <>
            <div className="flex flex-wrap items-end gap-4">
              <div className="space-y-2">
                <Label htmlFor="rr-outcome" className="text-xs">
                  Outcome (y-axis)
                </Label>
                <Select value={outcomeField} onValueChange={setOutcomeField}>
                  <SelectTrigger id="rr-outcome" className="h-9 w-[200px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {OUTCOME_FIELDS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="rr-xvar" className="text-xs">
                  Numeric condition (x-axis)
                </Label>
                <Select value={xAxisKey} onValueChange={setXVarKey}>
                  <SelectTrigger id="rr-xvar" className="h-9 w-[200px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {numericVars.map((n) => (
                      <SelectItem key={n} value={n}>
                        {n}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="h-[280px] w-full min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border/60" />
                  <XAxis
                    type="number"
                    dataKey="x"
                    name={xAxisKey}
                    tick={{ fontSize: 11 }}
                    label={{ value: xAxisKey, position: "insideBottom", offset: -4, fontSize: 11 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="y"
                    name={outcomeField}
                    tick={{ fontSize: 11 }}
                    label={{
                      value: outcomeField,
                      angle: -90,
                      position: "insideLeft",
                      fontSize: 11,
                    }}
                  />
                  <Tooltip
                    cursor={{ strokeDasharray: "4 4" }}
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null
                      const p = payload[0].payload as ScatterPoint
                      return (
                        <div className="rounded-md border border-border bg-background px-2 py-1.5 text-xs shadow-md">
                          <div className="font-mono">{p.code}</div>
                          <div className="text-muted-foreground">
                            {xAxisKey}: {p.x}
                          </div>
                          <div className="text-muted-foreground">
                            {outcomeField}: {p.y}
                          </div>
                          <div className="text-muted-foreground">status: {p.status}</div>
                        </div>
                      )
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {[...colorByStatus.keys()].map((st) => (
                    <Scatter
                      key={st}
                      name={st}
                      data={primaryPoints.filter((d) => d.status === st)}
                      fill={colorByStatus.get(st) ?? CHART_FILLS[0]}
                    />
                  ))}
                </ScatterChart>
              </ResponsiveContainer>
            </div>

            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>experiment_code</TableHead>
                    <TableHead className="font-mono text-xs">{xAxisKey}</TableHead>
                    <TableHead className="font-mono text-xs">{outcomeField}</TableHead>
                    <TableHead>status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {primaryPoints.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell className="font-mono text-xs">{p.code}</TableCell>
                      <TableCell className="tabular-nums">{p.x}</TableCell>
                      <TableCell className="tabular-nums">{p.y}</TableCell>
                      <TableCell>
                        <span className="text-xs">{p.status}</span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {numericVars.length >= 2 && cond2Points.length > 0 ? (
              <div className="space-y-2 border-t border-border pt-4">
                <p className="text-sm font-medium">Two numeric conditions</p>
                <p className="text-xs text-muted-foreground">
                  Scatter of {v1} vs {v2}; point color reflects {outcomeField} (min→max across shown runs).
                </p>
                <div className="h-[260px] w-full min-w-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-border/60" />
                      <XAxis
                        type="number"
                        dataKey="vx"
                        name={v1}
                        tick={{ fontSize: 11 }}
                        label={{ value: v1, position: "insideBottom", offset: -4, fontSize: 11 }}
                      />
                      <YAxis
                        type="number"
                        dataKey="vy"
                        name={v2}
                        tick={{ fontSize: 11 }}
                        label={{
                          value: v2,
                          angle: -90,
                          position: "insideLeft",
                          fontSize: 11,
                        }}
                      />
                      <Tooltip
                        cursor={{ strokeDasharray: "4 4" }}
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null
                          const p = payload[0].payload as Cond2Point
                          return (
                            <div className="rounded-md border border-border bg-background px-2 py-1.5 text-xs shadow-md">
                              <div className="font-mono">{p.code}</div>
                              <div className="text-muted-foreground">
                                {v1}: {p.vx} · {v2}: {p.vy}
                              </div>
                              <div className="text-muted-foreground">
                                {outcomeField}: {p.outcome}
                              </div>
                            </div>
                          )
                        }}
                      />
                      <Scatter data={cond2Points} fill={CHART_FILLS[0]}>
                        {cond2Points.map((entry, i) => (
                          <Cell key={entry.id + String(i)} fill={outcomeFill(entry.outcome)} />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
                <div className="rounded-md border border-dashed border-muted-foreground/40 bg-muted/20 p-4 text-center text-xs text-muted-foreground">
                  Heatmap / response-surface grid — placeholder when grid-level outcome values exist for condition pairs
                  (not shown here to avoid implying unavailable data).
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}
