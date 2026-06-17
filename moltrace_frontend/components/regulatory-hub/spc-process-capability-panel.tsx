"use client"

import { useMemo, useState } from "react"
import { Activity, AlertTriangle, CheckCircle2, Info, Loader2, TrendingUp, XCircle } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
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
import { cn } from "@/lib/utils"
import type { components } from "@/src/lib/api/schema"

/**
 * Process Capability & Trending — one measurement series → control chart +
 * capability indices + SPC/CUSUM/EWMA signals, via a single stateless
 * POST /regulatory/spc/analyze (no dossier; caller-supplied data).
 *
 * Folds into the dossier's Quality & Governance layer as one cohesive panel
 * (no new top-level nav). Data is entered/pasted for now — there is no
 * persisted measurement-series table yet.
 *
 * Decision-support only: the response is ALWAYS human_review_required and
 * carries a verbatim disclaimer — this is never a disposition. The early-
 * warning story (a drift/shift signal firing BEFORE the first spec breach,
 * i.e. lead_points > 0) is surfaced prominently.
 */

type SPCRequest = components["schemas"]["SPCAnalyzeRequest"]
type SPCResult = components["schemas"]["SPCAnalyzeResult"]
type SPCMeasurement = components["schemas"]["SPCMeasurementInput"]
type SPCCapability = components["schemas"]["SPCCapabilityOut"]
type SPCSignal = components["schemas"]["SPCSignalOut"]
type RuleSet = SPCRequest["rule_set"]

const RULE_SET_OPTIONS: { value: RuleSet; label: string }[] = [
  { value: "western_electric", label: "Western Electric" },
  { value: "western_electric_classic", label: "Western Electric (classic)" },
  { value: "nelson", label: "Nelson" },
  { value: "montgomery", label: "Montgomery" },
]

// A realistic seed: a stable assay series that drifts upward late, so a
// run-rule signal fires before the upper-spec breach — demonstrates the
// early-warning lead the panel is built to surface.
const SEED_MEASUREMENTS = [
  "100.1, B01",
  "99.8, B02",
  "100.3, B03",
  "99.6, B04",
  "100.0, B05",
  "100.2, B06",
  "99.9, B07",
  "100.4, B08",
  "100.1, B09",
  "99.7, B10",
  "100.5, B11",
  "100.8, B12",
  "101.0, B13",
  "101.3, B14",
  "101.6, B15",
  "101.9, B16",
  "102.2, B17",
  "102.6, B18",
  "103.1, B19",
  "103.4, B20",
].join("\n")

function num(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—"
  return value.toLocaleString(undefined, { maximumFractionDigits: digits })
}

function numOrNull(s: string): number | null {
  const t = s.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

/** One measurement per line: value[, batch_id[, timepoint[, label]]] (comma or tab). */
function parseMeasurements(text: string): { rows: SPCMeasurement[]; skipped: number } {
  const rows: SPCMeasurement[] = []
  let skipped = 0
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    const parts = line.split(/[,\t]/).map((p) => p.trim())
    const value = Number(parts[0])
    if (parts[0] === "" || !Number.isFinite(value)) {
      skipped += 1 // header row or non-numeric — skipped, not an error
      continue
    }
    rows.push({
      value,
      batch_id: parts[1] ?? "",
      timepoint: parts[2] ?? "",
      label: parts[3] ?? "",
    })
  }
  return { rows, skipped }
}

/** capability.rating → badge palette + display label. */
function ratingBadge(rating: string): { cls: string; label: string } {
  switch (rating) {
    case "capable":
      return { cls: "border-success/50 text-success", label: "capable" }
    case "marginal":
      return { cls: "border-warning/50 text-warning", label: "marginal" }
    case "not_capable":
      return { cls: "border-destructive/50 text-destructive", label: "not capable" }
    default:
      return { cls: "text-muted-foreground", label: rating ? rating.replace(/_/g, " ") : "undefined" }
  }
}

const SEVERITY_META: Record<string, { color: string; label: string }> = {
  critical: { color: "var(--mt-red)", label: "critical" },
  warning: { color: "var(--mt-amber)", label: "warning" },
  info: { color: "var(--mt-cyan-ink)", label: "info" },
}

/** 0-based indices → human "#1, #4" point references. */
function positions(indices: number[] | undefined): string {
  if (!indices || indices.length === 0) return "—"
  return indices.map((i) => `#${i + 1}`).join(", ")
}

// ── Inline control chart (I-chart) ──────────────────────────────────────────
// Built as focused SVG rather than a chart lib: σ zone bands, control + spec
// limits, and per-index OOS / signal markers need exact placement, and inline
// SVG renders deterministically (and is assertable) without a sized container.
function ControlChart({
  series,
  capability,
  oosSet,
  signalSet,
  firstSignalIndex,
  firstOosIndex,
  unit,
}: {
  series: SPCMeasurement[]
  capability: SPCCapability
  oosSet: Set<number>
  signalSet: Set<number>
  firstSignalIndex: number | null | undefined
  firstOosIndex: number | null | undefined
  unit: string
}) {
  const n = series.length
  const values = series.map((m) => m.value)
  const mean = capability.mean
  const sigma = capability.sigma_within
  const hasSigma = Number.isFinite(sigma) && sigma > 0
  const { usl, lsl } = capability

  // y-domain from data, control limits (if any), and spec limits.
  const domain: number[] = [...values, mean]
  if (hasSigma) domain.push(mean + 3 * sigma, mean - 3 * sigma)
  if (usl != null) domain.push(usl)
  if (lsl != null) domain.push(lsl)
  let yMin = Math.min(...domain)
  let yMax = Math.max(...domain)
  if (!(yMax > yMin)) {
    yMin -= 1
    yMax += 1
  }
  const padY = (yMax - yMin) * 0.08
  yMin -= padY
  yMax += padY

  const W = 720
  const H = 300
  const padL = 52
  const padR = 72
  const padT = 18
  const padB = 40
  const plotW = W - padL - padR
  const plotH = H - padT - padB
  const xFor = (i: number) => padL + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW)
  const yFor = (v: number) => padT + plotH - ((v - yMin) / (yMax - yMin)) * plotH
  const clampY = (v: number) => Math.max(padT, Math.min(padT + plotH, yFor(v)))

  // A symmetric value band [vBot, vTop] → rect, clamped to the plot.
  const band = (vTop: number, vBot: number, fill: string, key: string) => {
    const yTop = clampY(vTop)
    const yBot = clampY(vBot)
    const h = yBot - yTop
    if (h <= 0.5) return null
    return <rect key={key} x={padL} y={yTop} width={plotW} height={h} fill={fill} />
  }

  const hLine = (v: number, stroke: string, label: string, dash?: string, key?: string) => {
    const y = yFor(v)
    if (y < padT - 0.5 || y > padT + plotH + 0.5) return null
    return (
      <g key={key ?? label}>
        <line x1={padL} x2={padL + plotW} y1={y} y2={y} stroke={stroke} strokeWidth={1} strokeDasharray={dash} />
        <text x={padL + plotW + 6} y={y + 3} fontSize={9} fill={stroke} className="font-mono">
          {label}
        </text>
      </g>
    )
  }

  const tickCount = Math.min(n, 8)
  const tickIdx =
    n <= 1
      ? [0]
      : Array.from(new Set(Array.from({ length: tickCount }, (_, k) => Math.round((k * (n - 1)) / (tickCount - 1)))))

  const linePath = values.map((v, i) => `${i === 0 ? "M" : "L"}${xFor(i).toFixed(1)},${yFor(v).toFixed(1)}`).join(" ")

  const ariaLabel =
    `Control chart of ${n} ${unit || "measurement"} points, mean ${num(mean, 3)}` +
    (hasSigma ? `, control limits ±3σ (σ=${num(sigma, 3)})` : ", zero process variation") +
    `. ${oosSet.size} out-of-specification, ${signalSet.size} flagged by control rules.`

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          className="min-w-[560px]"
          role="img"
          aria-label={ariaLabel}
          data-testid="spc-control-chart"
        >
          {/* σ zone bands (green core → amber → red beyond limits) */}
          {hasSigma ? (
            <>
              {band(yMax, mean + 3 * sigma, "var(--mt-red-soft)", "z-red-hi")}
              {band(mean + 3 * sigma, mean + 2 * sigma, "var(--mt-amber-soft)", "z-amb-hi")}
              {band(mean + sigma, mean - sigma, "var(--mt-green-soft)", "z-core")}
              {band(mean - 2 * sigma, mean - 3 * sigma, "var(--mt-amber-soft)", "z-amb-lo")}
              {band(mean - 3 * sigma, yMin, "var(--mt-red-soft)", "z-red-lo")}
            </>
          ) : null}

          {/* plot frame */}
          <rect x={padL} y={padT} width={plotW} height={plotH} fill="none" stroke="var(--border)" strokeWidth={1} />

          {/* lead-time vertical guides */}
          {firstSignalIndex != null && firstSignalIndex >= 0 ? (
            <line
              x1={xFor(firstSignalIndex)}
              x2={xFor(firstSignalIndex)}
              y1={padT}
              y2={padT + plotH}
              stroke="var(--mt-amber)"
              strokeWidth={1}
              strokeDasharray="3 3"
              opacity={0.55}
            />
          ) : null}
          {firstOosIndex != null && firstOosIndex >= 0 ? (
            <line
              x1={xFor(firstOosIndex)}
              x2={xFor(firstOosIndex)}
              y1={padT}
              y2={padT + plotH}
              stroke="var(--mt-red)"
              strokeWidth={1}
              strokeDasharray="3 3"
              opacity={0.55}
            />
          ) : null}

          {/* control + spec limit lines */}
          {hLine(mean, "var(--mt-slate)", "x̄")}
          {hasSigma ? hLine(mean + 3 * sigma, "var(--mt-red)", "UCL", "4 2") : null}
          {hasSigma ? hLine(mean - 3 * sigma, "var(--mt-red)", "LCL", "4 2") : null}
          {hasSigma ? hLine(mean + sigma, "var(--mt-slate)", "+1σ", "1 3", "p1s") : null}
          {hasSigma ? hLine(mean - sigma, "var(--mt-slate)", "−1σ", "1 3", "m1s") : null}
          {usl != null ? hLine(usl, "var(--mt-violet)", "USL", "2 2", "usl") : null}
          {lsl != null ? hLine(lsl, "var(--mt-violet)", "LSL", "2 2", "lsl") : null}

          {/* data line */}
          <path d={linePath} fill="none" stroke="var(--mt-cyan)" strokeWidth={1.5} />

          {/* point markers */}
          {values.map((v, i) => {
            const isOos = oosSet.has(i)
            const isSignal = !isOos && signalSet.has(i)
            const fill = isOos ? "var(--mt-red)" : isSignal ? "var(--mt-amber)" : "var(--mt-cyan)"
            const r = isOos ? 4.5 : isSignal ? 4 : 3
            const m = series[i]
            const title = `#${i + 1}${m.batch_id ? ` · ${m.batch_id}` : ""} = ${num(v, 3)}${unit ? ` ${unit}` : ""}${
              isOos ? " · out of spec" : isSignal ? " · rule signal" : ""
            }`
            return (
              <g key={`pt-${i}`}>
                {isOos || isSignal ? (
                  <circle cx={xFor(i)} cy={yFor(v)} r={r + 2.5} fill="none" stroke={fill} strokeWidth={1.25} opacity={0.7} />
                ) : null}
                <circle cx={xFor(i)} cy={yFor(v)} r={r} fill={fill}>
                  <title>{title}</title>
                </circle>
              </g>
            )
          })}

          {/* x ticks */}
          {tickIdx.map((i) => (
            <text key={`tick-${i}`} x={xFor(i)} y={padT + plotH + 14} fontSize={8} textAnchor="middle" fill="var(--muted-foreground)">
              {series[i]?.batch_id || `#${i + 1}`}
            </text>
          ))}
        </svg>
      </div>

      {/* legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full" style={{ background: "var(--mt-cyan)" }} /> in control
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full" style={{ background: "var(--mt-amber)" }} /> rule signal
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full" style={{ background: "var(--mt-red)" }} /> out of spec
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-0 w-4 border-t border-dashed" style={{ borderColor: "var(--mt-red)" }} /> control limits (±3σ)
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-0 w-4 border-t border-dashed" style={{ borderColor: "var(--mt-violet)" }} /> spec limits
        </span>
      </div>
    </div>
  )
}

function CapabilityCell({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="rounded-md border bg-muted/15 px-3 py-2">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 font-mono text-sm">{num(value, 2)}</div>
    </div>
  )
}

export function SPCProcessCapabilityPanel() {
  const [product, setProduct] = useState("Examplinib tablets")
  const [parameter, setParameter] = useState("Assay")
  const [unit, setUnit] = useState("%")
  const [usl, setUsl] = useState("103.0")
  const [lsl, setLsl] = useState("97.0")
  const [target, setTarget] = useState("100.0")
  const [ruleSet, setRuleSet] = useState<RuleSet>("western_electric")
  const [warnSigma, setWarnSigma] = useState("1.0")
  const [subgroup, setSubgroup] = useState("")
  const [measurementsText, setMeasurementsText] = useState(SEED_MEASUREMENTS)

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const [result, setResult] = useState<SPCResult | null>(null)
  // The submitted series — the result echoes only indices, so the chart reads
  // its y-values from here (frozen at submit time, decoupled from the textarea).
  const [series, setSeries] = useState<SPCMeasurement[]>([])

  const parsed = useMemo(() => parseMeasurements(measurementsText), [measurementsText])

  const oosSet = useMemo(() => new Set(result?.oos_indices ?? []), [result])
  const signalSet = useMemo(() => {
    const s = new Set<number>()
    for (const sig of [...(result?.spc_signals ?? []), ...(result?.cusum_signals ?? []), ...(result?.ewma_signals ?? [])]) {
      for (const i of sig.indices ?? []) s.add(i)
    }
    return s
  }, [result])

  const allSignals: SPCSignal[] = useMemo(
    () => [...(result?.spc_signals ?? []), ...(result?.cusum_signals ?? []), ...(result?.ewma_signals ?? [])],
    [result],
  )

  function buildRequest(): SPCRequest | { error: string } {
    const { rows } = parsed
    if (rows.length < 2) return { error: "Enter at least two measurements (one value per line)." }
    const uslN = numOrNull(usl)
    const lslN = numOrNull(lsl)
    if (uslN == null && lslN == null) {
      return { error: "Enter at least one specification limit (USL or LSL)." }
    }
    if (uslN != null && lslN != null && uslN <= lslN) {
      return { error: "USL must be greater than LSL." }
    }
    const warnN = numOrNull(warnSigma)
    let subgroupN: number | null = null
    const sgTrim = subgroup.trim()
    if (sgTrim) {
      const sg = Number(sgTrim)
      if (!Number.isInteger(sg) || sg < 2 || sg > 10) {
        return { error: "Subgroup size must be an integer from 2 to 10 (or blank)." }
      }
      subgroupN = sg
    }
    return {
      product: product.trim(),
      parameter: parameter.trim(),
      measurements: rows,
      usl: uslN,
      lsl: lslN,
      target: numOrNull(target),
      unit: unit.trim(),
      rule_set: ruleSet,
      warn_within_sigma: warnN != null && warnN > 0 ? warnN : 1.0,
      subgroup_size: subgroupN,
    }
  }

  async function onAnalyze() {
    const built = buildRequest()
    if ("error" in built) {
      setError(built.error)
      return
    }
    setSubmitting(true)
    setError("")
    try {
      const res = await apiFetch<SPCResult>("/regulatory/spc/analyze", { method: "POST", body: built })
      setResult(res)
      setSeries(built.measurements)
    } catch (e) {
      setError(formatApiError(e, "Could not analyze the measurement series."))
    } finally {
      setSubmitting(false)
    }
  }

  const cap = result?.capability
  const rating = cap ? ratingBadge(cap.rating) : null
  const leadPoints = result?.lead_points ?? 0
  const firstSignal = result?.first_signal_index ?? null
  const firstOos = result?.first_oos_index ?? null

  return (
    <ModuleCard
      accent="cyan"
      eyebrow="Dossier · Quality & Governance"
      title={
        <span className="inline-flex items-center gap-2">
          <Activity className="h-4 w-4" aria-hidden />
          Process Capability &amp; Trending
        </span>
      }
      description="Analyze a time-ordered measurement series for one parameter — control chart, capability indices (Cp/Cpk/Pp/Ppk/Cpm), and Shewhart / CUSUM / EWMA signals — to catch drift before a specification breach. Decision-support only."
    >
      <div className="space-y-6">
        {/* ── Inputs ── */}
        <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="spc-product">Product</Label>
              <Input id="spc-product" value={product} onChange={(e) => setProduct(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="spc-parameter">Parameter</Label>
              <Input id="spc-parameter" value={parameter} onChange={(e) => setParameter(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="spc-unit">Unit</Label>
              <Input id="spc-unit" value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="%" />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-7">
            <div className="space-y-1.5">
              <Label htmlFor="spc-lsl">LSL</Label>
              <Input id="spc-lsl" inputMode="decimal" value={lsl} onChange={(e) => setLsl(e.target.value)} placeholder="—" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="spc-target">Target</Label>
              <Input id="spc-target" inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="—" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="spc-usl">USL</Label>
              <Input id="spc-usl" inputMode="decimal" value={usl} onChange={(e) => setUsl(e.target.value)} placeholder="—" />
            </div>
            <div className="space-y-1.5 lg:col-span-2">
              <Label htmlFor="spc-ruleset">Rule set</Label>
              <Select value={ruleSet} onValueChange={(v) => setRuleSet(v as RuleSet)}>
                <SelectTrigger id="spc-ruleset">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RULE_SET_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="spc-warn-sigma">Warn σ</Label>
              <Input
                id="spc-warn-sigma"
                inputMode="decimal"
                value={warnSigma}
                onChange={(e) => setWarnSigma(e.target.value)}
                placeholder="1.0"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="spc-subgroup">Subgroup</Label>
              <Input
                id="spc-subgroup"
                inputMode="numeric"
                value={subgroup}
                onChange={(e) => setSubgroup(e.target.value)}
                placeholder="none"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="spc-measurements">Measurements</Label>
            <Textarea
              id="spc-measurements"
              value={measurementsText}
              onChange={(e) => setMeasurementsText(e.target.value)}
              rows={6}
              className="font-mono text-xs"
              spellCheck={false}
            />
            <p className="text-xs text-muted-foreground">
              One per line: <code>value[, batch_id[, timepoint[, label]]]</code> (comma- or tab-separated). At least one
              of USL / LSL is required.{" "}
              <span className="font-medium text-foreground">{parsed.rows.length}</span> parsed
              {parsed.skipped > 0 ? ` · ${parsed.skipped} skipped` : ""}.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Button type="button" onClick={() => void onAnalyze()} disabled={submitting}>
              {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <TrendingUp className="mr-2 h-4 w-4" aria-hidden />}
              Analyze series
            </Button>
            {result ? (
              <span className="text-xs text-muted-foreground">
                n={result.n} · {RULE_SET_OPTIONS.find((o) => o.value === result.rule_set)?.label ?? result.rule_set}
              </span>
            ) : null}
          </div>
        </div>

        {error ? <AlertCard variant="error" title="Could not analyze" description={error} /> : null}

        {result && cap ? (
          <div className="space-y-6">
            {/* ── Early-warning lead banner (prominent) ── */}
            {leadPoints > 0 && firstSignal != null && firstOos != null ? (
              <AlertCard
                variant="success"
                icon={CheckCircle2}
                title={`Early warning: ${leadPoints} point${leadPoints === 1 ? "" : "s"} of lead time`}
                description={`A control-rule signal fired at point #${firstSignal + 1}, before the first out-of-specification result at point #${
                  firstOos + 1
                } — the trend was flagged ${leadPoints} sample${leadPoints === 1 ? "" : "s"} ahead of the spec breach.`}
              />
            ) : firstSignal != null && firstOos == null ? (
              <AlertCard
                variant="warning"
                title={`Drift signal at point #${firstSignal + 1} — no spec breach yet`}
                description="A control-rule signal fired while every point is still within specification. Investigate the trend before it reaches a limit."
              />
            ) : null}

            {/* ── Capability summary ── */}
            <div className="rounded-lg border p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-baseline gap-3">
                  <div>
                    <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Cpk</div>
                    <div className="font-mono text-2xl font-bold">{num(cap.cpk, 2)}</div>
                  </div>
                  {rating ? (
                    <Badge variant="outline" className={cn("font-normal", rating.cls)}>
                      {cap.is_capable ? (
                        <CheckCircle2 className="mr-1 h-3 w-3" aria-hidden />
                      ) : (
                        <XCircle className="mr-1 h-3 w-3" aria-hidden />
                      )}
                      {rating.label}
                    </Badge>
                  ) : null}
                </div>
                <Badge variant="outline" className="gap-1 font-normal text-muted-foreground">
                  <Info className="h-3 w-3" aria-hidden />
                  human review required
                </Badge>
              </div>

              <p className="mt-2 text-sm text-muted-foreground">{cap.interpretation}</p>

              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
                <CapabilityCell label="Cp" value={cap.cp} />
                <CapabilityCell label="Cpk" value={cap.cpk} />
                <CapabilityCell label="Cpu" value={cap.cpu} />
                <CapabilityCell label="Cpl" value={cap.cpl} />
                <CapabilityCell label="Pp" value={cap.pp} />
                <CapabilityCell label="Ppk" value={cap.ppk} />
                <CapabilityCell label="Cpm" value={cap.cpm} />
              </div>

              <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
                <span>
                  mean <span className="font-mono text-foreground">{num(cap.mean, 3)}</span>
                </span>
                <span>
                  σ within <span className="font-mono text-foreground">{num(cap.sigma_within, 3)}</span>
                </span>
                <span>
                  σ overall <span className="font-mono text-foreground">{num(cap.sigma_overall, 3)}</span>
                </span>
                <span>
                  n <span className="font-mono text-foreground">{cap.n}</span>
                </span>
              </div>

              {cap.warnings && cap.warnings.length > 0 ? (
                <ul className="mt-3 space-y-1 text-xs text-warning">
                  {cap.warnings.map((w, i) => (
                    <li key={`cap-warn-${i}`} className="flex items-start gap-1.5">
                      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                      <span>{w}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>

            {/* ── Control chart ── */}
            <div>
              <h3 className="mb-2 text-sm font-semibold">
                Control chart — {result.parameter}
                {result.product ? <span className="font-normal text-muted-foreground"> · {result.product}</span> : null}
              </h3>
              <ControlChart
                series={series}
                capability={cap}
                oosSet={oosSet}
                signalSet={signalSet}
                firstSignalIndex={firstSignal}
                firstOosIndex={firstOos}
                unit={result.parameter && unit ? unit : ""}
              />
            </div>

            {/* ── Alerts ── */}
            {result.alerts && result.alerts.length > 0 ? (
              <div>
                <h3 className="mb-2 text-sm font-semibold">Alerts</h3>
                <ul className="space-y-2">
                  {result.alerts.map((a, i) => {
                    const meta = SEVERITY_META[a.severity] ?? SEVERITY_META.info
                    return (
                      <li
                        key={`alert-${i}`}
                        className="flex items-start gap-3 rounded-md border-l-2 bg-muted/15 px-3 py-2"
                        style={{ borderLeftColor: meta.color }}
                      >
                        <span className="mt-0.5 inline-flex shrink-0 items-center gap-2">
                          <Badge
                            variant="outline"
                            className="font-normal"
                            style={{ color: meta.color, borderColor: meta.color }}
                          >
                            {meta.label}
                          </Badge>
                          <Badge variant="outline" className="font-normal text-muted-foreground">
                            {a.category}
                          </Badge>
                        </span>
                        <span className="min-w-0 flex-1 text-sm">
                          {a.message}
                          {a.indices && a.indices.length > 0 ? (
                            <span className="ml-1 font-mono text-xs text-muted-foreground">({positions(a.indices)})</span>
                          ) : null}
                        </span>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ) : null}

            {/* ── Signals (Shewhart / CUSUM / EWMA) ── */}
            <div>
              <h3 className="mb-2 text-sm font-semibold">Control-rule signals</h3>
              {allSignals.length === 0 ? (
                <p className="text-sm text-muted-foreground">No control-rule, CUSUM, or EWMA signals fired.</p>
              ) : (
                <div className="overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Method</TableHead>
                        <TableHead>Rule</TableHead>
                        <TableHead>Side</TableHead>
                        <TableHead>Points</TableHead>
                        <TableHead>Description</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {allSignals.map((s, i) => (
                        <TableRow key={`sig-${i}`}>
                          <TableCell className="whitespace-nowrap font-mono text-xs uppercase">{s.method}</TableCell>
                          <TableCell className="whitespace-nowrap text-xs">
                            {s.rule_number != null ? `${s.rule_number}. ${s.rule_name}` : s.rule_name}
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{s.side || "—"}</TableCell>
                          <TableCell className="whitespace-nowrap font-mono text-xs">{positions(s.indices)}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{s.description}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>

            {/* ── Disclaimer (verbatim) ── */}
            <AlertCard
              variant="warning"
              title="Decision-support — not a disposition"
              description={result.disclaimer}
            />
          </div>
        ) : null}
      </div>
    </ModuleCard>
  )
}
