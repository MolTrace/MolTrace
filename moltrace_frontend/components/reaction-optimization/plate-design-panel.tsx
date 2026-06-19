"use client"

import { useEffect, useMemo, useState } from "react"
import { Download, Grid3x3, Loader2, Plus, TriangleAlert, Trash2 } from "lucide-react"
import { ApiError } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
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
  buildPlateLegend,
  cellTint,
  createPlateDesign,
  downloadText,
  exportPlateDesign,
  listPlateDesigns,
  plateGeometry,
  prefillFromVariables,
  rowLabel,
  PLATE_FORMATS,
  PLATE_STRATEGIES,
  type PlateDesign,
  type PlateDesignRequest,
  type PlateFormat,
  type PlateStrategy,
} from "@/lib/reaction/plate-designs"

type NumericRow = { name: string; low: string; high: string }
type CategoricalRow = { name: string; levels: string }

function buildRequestBody(args: {
  format: PlateFormat
  strategy: PlateStrategy
  numeric: NumericRow[]
  categorical: CategoricalRow[]
  booleanNames: string
  fixedText: string
  excludedText: string
  seed: string
}): { body: PlateDesignRequest; error: string | null } {
  const numeric_json: Record<string, [number, number]> = {}
  for (const r of args.numeric) {
    const name = r.name.trim()
    const lo = Number(r.low)
    const hi = Number(r.high)
    if (name && r.low.trim() !== "" && r.high.trim() !== "" && Number.isFinite(lo) && Number.isFinite(hi)) {
      numeric_json[name] = [lo, hi]
    }
  }
  const categorical_json: Record<string, string[]> = {}
  for (const r of args.categorical) {
    const name = r.name.trim()
    const levels = r.levels
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
    if (name && levels.length) categorical_json[name] = levels
  }
  const boolean_json = args.booleanNames
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)

  let fixed_json: Record<string, unknown> | undefined
  if (args.fixedText.trim()) {
    try {
      const parsed = JSON.parse(args.fixedText)
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) fixed_json = parsed
      else return { body: {} as PlateDesignRequest, error: "Fixed conditions must be a JSON object." }
    } catch {
      return { body: {} as PlateDesignRequest, error: "Fixed conditions is not valid JSON." }
    }
  }
  let excluded_json: Record<string, unknown>[] | undefined
  if (args.excludedText.trim()) {
    try {
      const parsed = JSON.parse(args.excludedText)
      if (Array.isArray(parsed)) excluded_json = parsed
      else return { body: {} as PlateDesignRequest, error: "Excluded combinations must be a JSON array." }
    } catch {
      return { body: {} as PlateDesignRequest, error: "Excluded combinations is not valid JSON." }
    }
  }

  const seedNum = Number(args.seed)
  const body: PlateDesignRequest = {
    plate_format: args.format,
    strategy: args.strategy,
    ...(Object.keys(numeric_json).length ? { numeric_json } : {}),
    ...(Object.keys(categorical_json).length ? { categorical_json } : {}),
    ...(boolean_json.length ? { boolean_json } : {}),
    ...(fixed_json ? { fixed_json } : {}),
    ...(excluded_json ? { excluded_json } : {}),
    ...(args.seed.trim() !== "" && Number.isFinite(seedNum) ? { seed: seedNum } : {}),
  }
  return { body, error: null }
}

function PlateGrid({ design, colorBy }: { design: PlateDesign; colorBy: string | null }) {
  const { rows, cols } = plateGeometry(design)
  const byId = useMemo(() => {
    const m = new Map<string, PlateDesign["wells"][number]>()
    for (const w of design.wells) m.set(w.wellId, w)
    return m
  }, [design])
  const legend = useMemo(() => buildPlateLegend(design.wells, colorBy), [design.wells, colorBy])

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <div
          className="inline-grid gap-[3px]"
          style={{ gridTemplateColumns: `auto repeat(${cols}, minmax(22px, 1fr))` }}
        >
          <div />
          {Array.from({ length: cols }, (_, c) => (
            <div key={`h${c}`} className="text-center text-[10px] text-muted-foreground">
              {c + 1}
            </div>
          ))}
          {Array.from({ length: rows }, (_, r) => (
            <div key={`row${r}`} className="contents">
              <div className="pr-1 text-right text-[10px] leading-[22px] text-muted-foreground">{rowLabel(r)}</div>
              {Array.from({ length: cols }, (_, c) => {
                const id = `${rowLabel(r)}${c + 1}`
                const well = byId.get(id)
                if (!well) {
                  return (
                    <div
                      key={id}
                      className="aspect-square rounded-[3px] border border-dashed border-border/60"
                      aria-hidden
                    />
                  )
                }
                const tip = Object.entries(well.conditions)
                  .map(([k, v]) => `${k}: ${String(v)}`)
                  .join("\n")
                const tint = colorBy ? cellTint(legend, well.conditions[colorBy]) : "transparent"
                return (
                  <div
                    key={id}
                    title={`${id}\n${tip}`}
                    className="flex aspect-square items-center justify-center rounded-[3px] border border-border text-[8px] tabular-nums text-foreground/80"
                    style={{ backgroundColor: tint }}
                  >
                    {id}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>
      {legend.kind === "categorical" || legend.kind === "boolean" ? (
        <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
          {legend.entries.map((e) => (
            <span key={e.label} className="inline-flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-[3px]" style={{ backgroundColor: e.color }} />
              {e.label}
            </span>
          ))}
        </div>
      ) : legend.kind === "numeric" ? (
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <span>{legend.min}</span>
          <span
            className="h-3 w-32 rounded-[3px]"
            style={{ background: `linear-gradient(to right, transparent, ${legend.color})` }}
          />
          <span>{legend.max}</span>
        </div>
      ) : null}
    </div>
  )
}

export function PlateDesignPanel({
  projectId,
  variables,
}: {
  projectId: number
  variables: Record<string, unknown>[]
}) {
  const [designs, setDesigns] = useState<PlateDesign[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState("")

  const [format, setFormat] = useState<PlateFormat>("96")
  const [strategy, setStrategy] = useState<PlateStrategy>("sobol")
  const [seed, setSeed] = useState("20260615")
  // Prefill the variable editors once from the project's design-space variables.
  const [numeric, setNumeric] = useState<NumericRow[]>(() => {
    const pf = prefillFromVariables(variables)
    return pf.numeric.length ? pf.numeric : [{ name: "", low: "", high: "" }]
  })
  const [categorical, setCategorical] = useState<CategoricalRow[]>(() => prefillFromVariables(variables).categorical)
  const [booleanNames, setBooleanNames] = useState(() => prefillFromVariables(variables).boolean.join(", "))
  const [fixedText, setFixedText] = useState("")
  const [excludedText, setExcludedText] = useState("")
  const [colorBy, setColorBy] = useState<string | null>(null)
  const [exporting, setExporting] = useState<"csv" | "json" | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void listPlateDesigns(projectId)
      .then((rows) => {
        if (cancelled) return
        setDesigns(rows)
        if (rows.length) setSelectedId((cur) => cur ?? rows[0].id)
      })
      .catch((e) => {
        if (!cancelled) setError(formatApiError(e, "Could not load plate designs."))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const selected = useMemo(
    () => designs.find((d) => d.id === selectedId) ?? designs[0] ?? null,
    [designs, selectedId],
  )
  const activeColorBy =
    selected && colorBy && selected.dimensions.includes(colorBy)
      ? colorBy
      : selected?.dimensions[0] ?? null

  async function handleGenerate() {
    const { body, error: bodyErr } = buildRequestBody({
      format,
      strategy,
      numeric,
      categorical,
      booleanNames,
      fixedText,
      excludedText,
      seed,
    })
    if (bodyErr) {
      setError(bodyErr)
      return
    }
    setGenerating(true)
    setError("")
    try {
      const created = await createPlateDesign(projectId, body)
      if (created) {
        setDesigns((prev) => [created, ...prev.filter((d) => d.id !== created.id)])
        setSelectedId(created.id)
        setColorBy(created.dimensions[0] ?? null)
      }
    } catch (e) {
      setError(formatApiError(e, "Could not generate the plate design."))
    } finally {
      setGenerating(false)
    }
  }

  async function handleExport(target: "csv" | "json") {
    if (!selected) return
    setExporting(target)
    setError("")
    try {
      // Re-fetch through the typed export route (also confirms the design still resolves).
      const { content } = await exportPlateDesign(projectId, selected.id, target)
      const mime = target === "csv" ? "text/csv" : "application/json"
      downloadText(`plate-${selected.id}-${selected.plateFormat}well.${target}`, content, mime)
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 404
          ? "This plate design could not be found (it may belong to another project)."
          : formatApiError(e, `Could not export ${target.toUpperCase()}.`),
      )
    } finally {
      setExporting(null)
    }
  }

  function addNumeric() {
    setNumeric((r) => [...r, { name: "", low: "", high: "" }])
  }
  function addCategorical() {
    setCategorical((r) => [...r, { name: "", levels: "" }])
  }

  return (
    <ModuleCard
      accent="violet"
      eyebrow="Optimization · HTE / DoE Plate Designs"
      title="plate designs"
      description="Generate a deterministic high-throughput experimentation plate (Sobol / Latin-hypercube / factorial / BO-seed) over the design space, view it as a physical plate map, and export CSV/JSON for lab robotics. Advisory; requires human review before execution."
    >
      <div className="space-y-5">
        {error ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        ) : null}

        {/* ── Design controls ── */}
        <div className="space-y-4 rounded-md border border-border p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Plate format</Label>
              <Select value={format} onValueChange={(v) => setFormat(v as PlateFormat)}>
                <SelectTrigger className="h-9 w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PLATE_FORMATS.map((f) => (
                    <SelectItem key={f.value} value={f.value}>
                      {f.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Strategy</Label>
              <Select value={strategy} onValueChange={(v) => setStrategy(v as PlateStrategy)}>
                <SelectTrigger className="h-9 w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PLATE_STRATEGIES.map((s) => (
                    <SelectItem key={s.value} value={s.value}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs" htmlFor="plate-seed">
                Seed
              </Label>
              <Input
                id="plate-seed"
                className="h-9 w-32 font-mono"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                inputMode="numeric"
              />
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">
            {PLATE_STRATEGIES.find((s) => s.value === strategy)?.help}
          </p>

          {/* Numeric variables */}
          <div className="space-y-2">
            <Label className="text-xs">Numeric variables — name, low, high</Label>
            {numeric.map((row, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input
                  className="h-8 flex-1 font-mono text-xs"
                  placeholder="temperature_c"
                  value={row.name}
                  onChange={(e) => setNumeric((rs) => rs.map((r, j) => (j === i ? { ...r, name: e.target.value } : r)))}
                />
                <Input
                  className="h-8 w-24 font-mono text-xs"
                  placeholder="low"
                  value={row.low}
                  onChange={(e) => setNumeric((rs) => rs.map((r, j) => (j === i ? { ...r, low: e.target.value } : r)))}
                />
                <Input
                  className="h-8 w-24 font-mono text-xs"
                  placeholder="high"
                  value={row.high}
                  onChange={(e) => setNumeric((rs) => rs.map((r, j) => (j === i ? { ...r, high: e.target.value } : r)))}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  aria-label="Remove numeric variable"
                  onClick={() => setNumeric((rs) => rs.filter((_, j) => j !== i))}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden />
                </Button>
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" className="gap-1 text-xs" onClick={addNumeric}>
              <Plus className="h-3.5 w-3.5" aria-hidden /> Add numeric
            </Button>
          </div>

          {/* Categorical variables */}
          <div className="space-y-2">
            <Label className="text-xs">Categorical variables — name, comma-separated levels</Label>
            {categorical.map((row, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input
                  className="h-8 flex-1 font-mono text-xs"
                  placeholder="solvent"
                  value={row.name}
                  onChange={(e) =>
                    setCategorical((rs) => rs.map((r, j) => (j === i ? { ...r, name: e.target.value } : r)))
                  }
                />
                <Input
                  className="h-8 flex-[2] font-mono text-xs"
                  placeholder="MeCN, THF, DMF"
                  value={row.levels}
                  onChange={(e) =>
                    setCategorical((rs) => rs.map((r, j) => (j === i ? { ...r, levels: e.target.value } : r)))
                  }
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  aria-label="Remove categorical variable"
                  onClick={() => setCategorical((rs) => rs.filter((_, j) => j !== i))}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden />
                </Button>
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" className="gap-1 text-xs" onClick={addCategorical}>
              <Plus className="h-3.5 w-3.5" aria-hidden /> Add categorical
            </Button>
          </div>

          {/* Boolean + fixed + excluded */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-xs" htmlFor="plate-bool">
                Boolean variables — comma-separated names
              </Label>
              <Input
                id="plate-bool"
                className="h-8 font-mono text-xs"
                placeholder="inert_atmosphere"
                value={booleanNames}
                onChange={(e) => setBooleanNames(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs" htmlFor="plate-fixed">
                Fixed conditions — JSON object
              </Label>
              <Textarea
                id="plate-fixed"
                className="min-h-[36px] font-mono text-xs"
                placeholder='{ "base": "K2CO3" }'
                value={fixedText}
                onChange={(e) => setFixedText(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label className="text-xs" htmlFor="plate-excluded">
              Excluded combinations — JSON array of objects
            </Label>
            <Textarea
              id="plate-excluded"
              className="min-h-[36px] font-mono text-xs"
              placeholder='[ { "solvent": "DMF" } ]'
              value={excludedText}
              onChange={(e) => setExcludedText(e.target.value)}
            />
          </div>

          <Button type="button" className="gap-2" onClick={handleGenerate} disabled={generating}>
            {generating ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Grid3x3 className="h-4 w-4" aria-hidden />}
            {generating ? "Generating…" : "Generate plate"}
          </Button>
        </div>

        {/* ── Saved designs ── */}
        {designs.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">Saved designs:</span>
            {designs.map((d) => (
              <Button
                key={d.id}
                type="button"
                variant={selected?.id === d.id ? "default" : "outline"}
                size="sm"
                className="h-7 gap-1.5 text-xs"
                onClick={() => setSelectedId(d.id)}
              >
                #{d.id}
                <span className="opacity-70">
                  {d.plateFormat} · {d.strategy} · {d.wellCount}w
                </span>
              </Button>
            ))}
          </div>
        ) : loading ? (
          <p className="text-sm text-muted-foreground">Loading plate designs…</p>
        ) : (
          <p className="text-sm text-muted-foreground">
            No plate designs yet — set the variables above and generate one.
          </p>
        )}

        {/* ── Selected design: map + export ── */}
        {selected ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge variant="outline" className="font-mono text-xs">
                  #{selected.id}
                </Badge>
                <Badge variant="outline" className="text-xs">
                  {selected.plateFormat}-well · {selected.strategy}
                </Badge>
                <Badge variant="outline" className="tabular-nums text-xs">
                  {selected.wellCount}/{selected.capacity ?? "—"} wells
                </Badge>
              </div>
              <div className="flex items-center gap-2">
                {selected.dimensions.length > 0 ? (
                  <div className="flex items-center gap-2">
                    <Label className="text-xs text-muted-foreground">Color by</Label>
                    <Select value={activeColorBy ?? undefined} onValueChange={setColorBy}>
                      <SelectTrigger className="h-8 w-40">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {selected.dimensions.map((d) => (
                          <SelectItem key={d} value={d}>
                            {d}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ) : null}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="gap-1.5 text-xs"
                  onClick={() => handleExport("csv")}
                  disabled={exporting != null}
                >
                  {exporting === "csv" ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Download className="h-3.5 w-3.5" aria-hidden />}
                  CSV
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="gap-1.5 text-xs"
                  onClick={() => handleExport("json")}
                  disabled={exporting != null}
                >
                  {exporting === "json" ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Download className="h-3.5 w-3.5" aria-hidden />}
                  JSON
                </Button>
              </div>
            </div>

            <PlateGrid design={selected} colorBy={activeColorBy} />

            {selected.warnings.length > 0 ? (
              <div className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/10 p-3">
                <p className="text-sm font-medium">warnings</p>
                <ul className="list-inside list-disc text-xs text-muted-foreground">
                  {selected.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {selected.notes.length > 0 ? (
              <div className="flex items-start gap-2 rounded-md border border-dashed border-border bg-muted/30 p-3">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <div className="space-y-1 text-xs text-muted-foreground">
                  {selected.notes.map((n) => (
                    <p key={n}>{n}</p>
                  ))}
                </div>
              </div>
            ) : null}

            <p className="text-[11px] text-muted-foreground">
              CSV/JSON exports feed lab robotics — Mettler-Toledo / Chemspeed / Unchained adapters are thin
              server-side wrappers over these files (coming later).
            </p>
          </div>
        ) : null}
      </div>
    </ModuleCard>
  )
}
