"use client"

/**
 * SpectraCheck 5-layer benchmark UI.
 *
 * Users paste a JSON suite of cases and run them against
 * /benchmark/spectracheck/run. The response is a per-case scorecard plus
 * aggregated layer means. The panel surfaces the result so reviewers can
 * audit *why* the score landed where it did — each layer carries its
 * components dict and a notes list directly from the backend.
 */

import { useCallback, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { ModuleCard } from "@/components/dashboard/module-card"
import { AlertCard } from "@/components/dashboard/alert-card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { isRecord } from "@/components/spectracheck/spectracheck-nmr-result-parse"
import { Activity, BarChart3, PlayCircle, RotateCcw, ShieldCheck, Sparkles } from "lucide-react"

const DEFAULT_SUITE = `[
  {
    "case_id": "ethanol-1",
    "smiles": "CCO",
    "nucleus": "1H",
    "solvent": "CDCl3",
    "observed_nmr_text": "1H NMR (400 MHz, CDCl3) \\u03b4 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)",
    "candidate_block": "Ethanol | CCO\\nMethanol | CO\\nPropanol | CCCO",
    "sample_id": "SAMPLE-001",
    "sha256": "${"a".repeat(64)}",
    "operator": "alice",
    "instrument": "Bruker 400"
  }
]`

const LAYER_META: Record<
  string,
  { title: string; icon: typeof BarChart3; tint: string }
> = {
  peak_level_accuracy: { title: "Peak-level accuracy", icon: Activity, tint: "var(--mt-teal)" },
  structural_ranking: { title: "Structural ranking", icon: BarChart3, tint: "var(--mt-teal)" },
  explainability: { title: "Explainability", icon: Sparkles, tint: "var(--mt-teal)" },
  robustness: { title: "Robustness", icon: BarChart3, tint: "var(--mt-amber)" },
  regulatory_evidence: {
    title: "Regulatory evidence",
    icon: ShieldCheck,
    tint: "var(--mt-green)",
  },
}

type LayerScore = {
  name: string
  score: number
  components: Record<string, unknown>
  notes: string[]
}

type CaseResult = {
  case_id: string
  smiles: string
  nucleus: string
  solvent: string | null
  overall_score: number
  layers: LayerScore[]
  summary: string[]
  warnings: string[]
}

type Aggregate = {
  layer: string
  mean_score: number
  case_count: number
  min_score: number
  max_score: number
}

type BenchmarkResponse = {
  case_count: number
  overall_mean_score: number
  aggregates: Aggregate[]
  cases: CaseResult[]
  notes: string[]
}

function normalizeResponse(payload: unknown): BenchmarkResponse | null {
  if (!isRecord(payload)) return null
  const cases = Array.isArray(payload.cases)
    ? payload.cases.filter((c): c is Record<string, unknown> => isRecord(c))
    : []
  const aggregates = Array.isArray(payload.aggregates)
    ? payload.aggregates.filter((c): c is Record<string, unknown> => isRecord(c))
    : []
  const notes = Array.isArray(payload.notes)
    ? payload.notes.filter((n): n is string => typeof n === "string")
    : []
  return {
    case_count: typeof payload.case_count === "number" ? payload.case_count : cases.length,
    overall_mean_score:
      typeof payload.overall_mean_score === "number" ? payload.overall_mean_score : 0,
    aggregates: aggregates.map((agg) => ({
      layer: String(agg.layer ?? "?"),
      mean_score: typeof agg.mean_score === "number" ? agg.mean_score : 0,
      case_count: typeof agg.case_count === "number" ? agg.case_count : 0,
      min_score: typeof agg.min_score === "number" ? agg.min_score : 0,
      max_score: typeof agg.max_score === "number" ? agg.max_score : 0,
    })),
    cases: cases.map((row) => {
      const layers = Array.isArray(row.layers)
        ? (row.layers.filter((l): l is Record<string, unknown> => isRecord(l)).map((layer) => ({
            name: String(layer.name ?? "?"),
            score: typeof layer.score === "number" ? layer.score : 0,
            components: isRecord(layer.components) ? layer.components : {},
            notes: Array.isArray(layer.notes)
              ? layer.notes.filter((n): n is string => typeof n === "string")
              : [],
          })) as LayerScore[])
        : []
      const summary = Array.isArray(row.summary)
        ? row.summary.filter((s): s is string => typeof s === "string")
        : []
      const warnings = Array.isArray(row.warnings)
        ? row.warnings.filter((s): s is string => typeof s === "string")
        : []
      return {
        case_id: String(row.case_id ?? "?"),
        smiles: String(row.smiles ?? "?"),
        nucleus: String(row.nucleus ?? "?"),
        solvent: typeof row.solvent === "string" ? row.solvent : null,
        overall_score:
          typeof row.overall_score === "number" ? row.overall_score : 0,
        layers,
        summary,
        warnings,
      } as CaseResult
    }),
    notes,
  }
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}

function ScoreBar({ score, color }: { score: number; color: string }) {
  const pct = Math.max(0, Math.min(1, score)) * 100
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${pct}%`, backgroundColor: color }}
      />
    </div>
  )
}

export function SpectraCheckBenchmarkSection() {
  const [suiteText, setSuiteText] = useState(DEFAULT_SUITE)
  const [dropPeaks, setDropPeaks] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [result, setResult] = useState<BenchmarkResponse | null>(null)

  const runBenchmark = useCallback(async () => {
    setError("")
    setResult(null)
    let parsed: unknown
    try {
      parsed = JSON.parse(suiteText)
    } catch (err) {
      setError(`Cases JSON is invalid: ${String((err as Error).message)}`)
      return
    }
    if (!Array.isArray(parsed) || parsed.length === 0) {
      setError("Cases must be a non-empty JSON array.")
      return
    }
    setLoading(true)
    try {
      const data = await apiFetch<unknown>("/benchmark/spectracheck/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cases: parsed, robustness_drop_peaks: dropPeaks }),
      })
      const normalized = normalizeResponse(data)
      if (!normalized) {
        setError("Backend returned an unexpected payload shape.")
        return
      }
      setResult(normalized)
    } catch (err) {
      setError(formatApiError(err, "Benchmark run failed"))
    } finally {
      setLoading(false)
    }
  }, [suiteText, dropPeaks])

  function reset() {
    setSuiteText(DEFAULT_SUITE)
    setDropPeaks(1)
    setError("")
    setResult(null)
  }

  return (
    <div className="space-y-6" data-testid="benchmark-section">
      <ModuleCard
        accent="teal"
        eyebrow="Step 1 · Suite"
        title="5-layer SpectraCheck benchmark"
        icon={Sparkles}
        description="Score curated (structure, observed NMR) cases across peak-level accuracy, structural ranking, explainability, robustness, and regulatory evidence. Reuses the same prediction + categorization pipeline as /nmr/processed/analyze so results are directly comparable."
      >
        <div className="space-y-4">
          <div>
            <Label
              htmlFor="bench-cases"
              className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
            >
              Benchmark cases (JSON array)
            </Label>
            <Textarea
              id="bench-cases"
              value={suiteText}
              onChange={(e) => setSuiteText(e.target.value)}
              rows={10}
              className="font-mono text-xs"
              data-testid="benchmark-suite-input"
            />
            <p className="mt-1 text-[11px] text-muted-foreground">
              Each case carries case_id, smiles, nucleus, solvent, observed_nmr_text, and
              optional candidate_block + audit fields (sample_id, sha256, operator,
              instrument).
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label
                htmlFor="bench-drop"
                className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
              >
                Robustness — drop top-N peaks
              </Label>
              <Input
                id="bench-drop"
                type="number"
                min={0}
                max={5}
                value={dropPeaks}
                onChange={(e) => setDropPeaks(Math.max(0, Math.min(5, Number(e.target.value) || 0)))}
                className="font-mono"
                data-testid="benchmark-drop-input"
              />
              <p className="mt-1 text-[11px] text-muted-foreground">
                Higher = harsher perturbation. 0 disables the noise probe.
              </p>
            </div>
            <div className="flex items-end gap-2">
              <Button
                type="button"
                onClick={() => void runBenchmark()}
                disabled={loading}
                data-testid="benchmark-run-button"
                className="flex-1"
              >
                <PlayCircle className="mr-1 h-4 w-4" aria-hidden />
                {loading ? "Running benchmark…" : "Run benchmark"}
              </Button>
              <Button type="button" variant="ghost" onClick={reset} disabled={loading}>
                <RotateCcw className="mr-1 h-3.5 w-3.5" aria-hidden />
                Reset
              </Button>
            </div>
          </div>
          {error ? <AlertCard variant="error" title="Benchmark failed" description={error} /> : null}
        </div>
      </ModuleCard>

      {result ? <BenchmarkResultPanels result={result} /> : null}
    </div>
  )
}

function BenchmarkResultPanels({ result }: { result: BenchmarkResponse }) {
  return (
    <div className="space-y-6">
      <ModuleCard
        accent="teal"
        eyebrow="Step 2 · Aggregate"
        title="Suite overall — 5-layer mean"
        icon={BarChart3}
        description={`${result.case_count} case(s). Overall mean: ${percent(result.overall_mean_score)}.`}
      >
        <div
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
          data-testid="benchmark-aggregates"
        >
          {result.aggregates.map((agg) => {
            const meta = LAYER_META[agg.layer]
            const tint = meta?.tint ?? "var(--mt-teal)"
            const Icon = meta?.icon ?? BarChart3
            return (
              <Card
                key={agg.layer}
                className="overflow-hidden rounded-xl py-0"
                style={{ borderTop: `3px solid ${tint}` }}
                data-testid={`benchmark-layer-${agg.layer}`}
              >
                <CardContent className="space-y-2 py-3">
                  <div className="flex items-center justify-between">
                    <p
                      className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
                      style={{ color: tint }}
                    >
                      <Icon className="h-3 w-3" aria-hidden />
                      {meta?.title ?? agg.layer}
                    </p>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      n={agg.case_count}
                    </span>
                  </div>
                  <p
                    className="font-mono text-2xl font-bold leading-none tabular-nums"
                    style={{ color: tint }}
                    data-testid={`benchmark-mean-${agg.layer}`}
                  >
                    {percent(agg.mean_score)}
                  </p>
                  <ScoreBar score={agg.mean_score} color={tint} />
                  <p className="font-mono text-[10px] text-muted-foreground">
                    min {percent(agg.min_score)} · max {percent(agg.max_score)}
                  </p>
                </CardContent>
              </Card>
            )
          })}
        </div>
        {result.notes.length > 0 ? (
          <ul
            className="mt-3 list-inside list-disc space-y-0.5 text-[11px] text-muted-foreground"
            data-testid="benchmark-suite-notes"
          >
            {result.notes.map((note, idx) => (
              <li key={idx}>{note}</li>
            ))}
          </ul>
        ) : null}
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Step 3 · Per-case"
        title="Per-case scorecards"
        icon={Activity}
        description="Each row shows the per-layer score with the components the backend used. Click into a case to see notes."
      >
        <div className="space-y-3" data-testid="benchmark-cases">
          {result.cases.map((row) => (
            <Card
              key={row.case_id}
              className="overflow-hidden rounded-xl py-0"
              style={{ borderTop: "3px solid var(--mt-teal)" }}
              data-testid={`benchmark-case-${row.case_id}`}
            >
              <CardContent className="space-y-3 py-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <p className="font-mono text-sm font-bold">{row.case_id}</p>
                    <p className="font-mono text-[11px] text-muted-foreground">
                      {row.smiles} · {row.nucleus}
                      {row.solvent ? ` · ${row.solvent}` : ""}
                    </p>
                  </div>
                  <Badge
                    variant="outline"
                    className="font-mono text-xs"
                    style={{ borderColor: "var(--mt-teal)", color: "var(--mt-teal)" }}
                  >
                    Overall {percent(row.overall_score)}
                  </Badge>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-[10px] uppercase tracking-wide">Layer</TableHead>
                      <TableHead className="text-[10px] uppercase tracking-wide">Score</TableHead>
                      <TableHead className="text-[10px] uppercase tracking-wide">Components</TableHead>
                      <TableHead className="text-[10px] uppercase tracking-wide">Notes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {row.layers.map((layer) => {
                      const meta = LAYER_META[layer.name]
                      const tint = meta?.tint ?? "var(--mt-teal)"
                      return (
                        <TableRow
                          key={layer.name}
                          data-testid={`benchmark-case-${row.case_id}-${layer.name}`}
                        >
                          <TableCell className="font-mono text-xs">
                            {meta?.title ?? layer.name}
                          </TableCell>
                          <TableCell>
                            <div className="space-y-1">
                              <span
                                className="font-mono text-xs font-bold tabular-nums"
                                style={{ color: tint }}
                              >
                                {percent(layer.score)}
                              </span>
                              <ScoreBar score={layer.score} color={tint} />
                            </div>
                          </TableCell>
                          <TableCell className="font-mono text-[10px] text-muted-foreground">
                            {Object.entries(layer.components).slice(0, 6).map(([k, v]) => (
                              <div key={k}>
                                {k}: <span className="text-foreground">{JSON.stringify(v)}</span>
                              </div>
                            ))}
                          </TableCell>
                          <TableCell className="text-[11px] text-muted-foreground">
                            {layer.notes.length === 0 ? (
                              "—"
                            ) : (
                              <ul className="list-inside list-disc space-y-0.5">
                                {layer.notes.map((note, idx) => (
                                  <li key={idx}>{note}</li>
                                ))}
                              </ul>
                            )}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
                {row.warnings.length > 0 ? (
                  <ul className="list-inside list-disc space-y-0.5 text-[11px]" style={{ color: "var(--mt-amber)" }}>
                    {row.warnings.map((warning, idx) => (
                      <li key={idx}>{warning}</li>
                    ))}
                  </ul>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      </ModuleCard>
    </div>
  )
}
