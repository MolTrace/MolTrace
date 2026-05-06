"use client"

import { useEffect, useMemo, useState } from "react"
import {
  CartesianGrid,
  Cell,
  ErrorBar,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

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

const COLOR_BY_STATUS = "__status__"

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

function readConditionLabel(cj: unknown, key: string): string {
  if (!isRecord(cj)) return "—"
  const v = cj[key]
  if (v == null) return "—"
  return String(v)
}

/** Half-width uncertainty on y (outcome), if experiment records it. */
function readOutcomeUncertaintyY(exp: Record<string, unknown>, outcomeField: string): number | null {
  const oj = isRecord(exp.outcome_json) ? exp.outcome_json : null
  if (!oj) return null
  const keys = [
    `${outcomeField}_sigma`,
    `${outcomeField}_half_width`,
    `${outcomeField}_uncertainty`,
    "outcome_uncertainty",
    "uncertainty_half_width",
    "yield_sigma",
  ]
  for (const k of keys) {
    const n = readNum(oj[k])
    if (n != null && n >= 0) return n
  }
  return null
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

function categoricalVariableNames(
  variableRecords: Record<string, unknown>[],
  variableNamesOrdered: string[],
): string[] {
  const cat = new Set<string>()
  for (const v of variableRecords) {
    const name = typeof v.name === "string" ? v.name.trim() : ""
    const vt = typeof v.variable_type === "string" ? v.variable_type : ""
    if (name && vt === "categorical") cat.add(name)
  }
  return variableNamesOrdered.filter((n) => cat.has(n))
}

function colorMap(keys: string[]): Map<string, string> {
  const uniq = [...new Set(keys)].sort()
  const m = new Map<string, string>()
  uniq.forEach((s, i) => {
    m.set(s, CHART_FILLS[i % CHART_FILLS.length])
  })
  return m
}

export type ReactionResponsePreviewProps = {
  loading: boolean
  experiments: Record<string, unknown>[]
  variableRecords: Record<string, unknown>[]
  variableNamesOrdered: string[]
}

type PreviewPoint = {
  id: string
  code: string
  x: number
  y: number
  status: string
  colorKey: string
  errorY?: number
}

type ChartPoint = PreviewPoint & {
  uncertaintyHalfWidth?: number
  errorY: number
}

export function ReactionResponsePreview({
  loading,
  experiments,
  variableRecords,
  variableNamesOrdered,
}: ReactionResponsePreviewProps) {
  const [outcomeField, setOutcomeField] = useState<string>("yield_percent")
  const [xVarKey, setXVarKey] = useState<string>("")
  const [colorBy, setColorBy] = useState<string>(COLOR_BY_STATUS)

  const numericVars = useMemo(
    () => numericVariableNames(variableRecords, variableNamesOrdered),
    [variableRecords, variableNamesOrdered],
  )

  const categoricalVars = useMemo(
    () => categoricalVariableNames(variableRecords, variableNamesOrdered),
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
    const out: PreviewPoint[] = []
    for (const e of experiments) {
      if (e.status !== "completed") continue
      const yv = readOutcomeNumber(e, outcomeField)
      if (yv == null) continue
      const xn = readConditionNumber(e.conditions_json, xv)
      if (xn == null) continue
      const code = typeof e.experiment_code === "string" ? e.experiment_code : String(e.id ?? "")
      const st = typeof e.status === "string" ? e.status : "unknown"
      let colorKey = st
      if (colorBy !== COLOR_BY_STATUS && categoricalVars.includes(colorBy)) {
        colorKey = readConditionLabel(e.conditions_json, colorBy)
      }
      const err = readOutcomeUncertaintyY(e, outcomeField)
      const pt: PreviewPoint = {
        id: String(e.id ?? code),
        code,
        x: xn,
        y: yv,
        status: st,
        colorKey,
      }
      if (err != null && err > 0) pt.errorY = err
      out.push(pt)
    }
    return out
  }, [experiments, outcomeField, numericVars, xVarKey, colorBy, categoricalVars])

  const colorKeys = useMemo(() => primaryPoints.map((p) => p.colorKey), [primaryPoints])
  const fillByKey = useMemo(() => colorMap(colorKeys), [colorKeys])

  const showUncertainty = useMemo(
    () => primaryPoints.some((p) => p.errorY != null && p.errorY > 0),
    [primaryPoints],
  )

  const chartData = useMemo((): ChartPoint[] => {
    return primaryPoints.map((p) => ({
      ...p,
      uncertaintyHalfWidth: p.errorY != null && p.errorY > 0 ? p.errorY : undefined,
      errorY: showUncertainty ? (p.errorY != null && p.errorY > 0 ? p.errorY : 0) : 0,
    }))
  }, [primaryPoints, showUncertainty])

  const xAxisKey = xVarKey || numericVars[0] || ""

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Reaction Response Preview</CardTitle>
        <CardDescription>
          Completed experiments with numeric condition values and numeric outcomes. Color encodes status or a categorical
          variable when selected; uncertainty markers appear only when outcome uncertainty is present on experiments.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <p className="text-sm text-muted-foreground">…</p>
        ) : numericVars.length === 0 ? (
          <p className="text-sm text-muted-foreground">{EMPTY_COPY}</p>
        ) : primaryPoints.length === 0 ? (
          <p className="text-sm text-muted-foreground">{EMPTY_COPY}</p>
        ) : null}

        {numericVars.length > 0 && !loading && primaryPoints.length > 0 ? (
          <>
            <div className="flex flex-wrap items-end gap-4">
              <div className="space-y-2">
                <Label htmlFor="rrp-outcome" className="text-xs">
                  Outcome (y-axis)
                </Label>
                <Select value={outcomeField} onValueChange={setOutcomeField}>
                  <SelectTrigger id="rrp-outcome" className="h-9 w-[200px]">
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
                <Label htmlFor="rrp-xvar" className="text-xs">
                  Numeric condition (x-axis)
                </Label>
                <Select value={xAxisKey} onValueChange={setXVarKey}>
                  <SelectTrigger id="rrp-xvar" className="h-9 w-[200px]">
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
              <div className="space-y-2">
                <Label htmlFor="rrp-color" className="text-xs">
                  Color by
                </Label>
                <Select value={colorBy} onValueChange={setColorBy}>
                  <SelectTrigger id="rrp-color" className="h-9 w-[220px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={COLOR_BY_STATUS}>status</SelectItem>
                    {categoricalVars.map((n) => (
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
                      const p = payload[0].payload as ChartPoint
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
                          <div className="text-muted-foreground">color: {p.colorKey}</div>
                          {p.uncertaintyHalfWidth != null ? (
                            <div className="text-muted-foreground">
                              model uncertainty (half-width): {p.uncertaintyHalfWidth}
                            </div>
                          ) : null}
                        </div>
                      )
                    }}
                  />
                  <Scatter data={chartData} fill={CHART_FILLS[0]}>
                    {chartData.map((entry) => (
                      <Cell key={entry.id} fill={fillByKey.get(entry.colorKey) ?? CHART_FILLS[0]} />
                    ))}
                    {showUncertainty ? (
                      <ErrorBar
                        dataKey="errorY"
                        direction="y"
                        width={4}
                        strokeWidth={1}
                        stroke="hsl(var(--muted-foreground))"
                      />
                    ) : null}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}
