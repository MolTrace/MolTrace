"use client"

import { useEffect, useMemo, useState } from "react"
import { ChevronDown, FlaskConical, Leaf, Loader2, Plus, Trash2, TriangleAlert } from "lucide-react"
import { ApiError } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { ModuleCard } from "@/components/dashboard/module-card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { InfoTooltip } from "@/components/ui/info-tooltip"
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
import {
  compareGreenMetrics,
  computeGreenMetrics,
  formatGreenMetric,
  getGreenMetrics,
  GREEN_COMPONENT_ROLES,
  GREEN_METRICS,
  readGreenMetric,
  type GreenAssessment,
  type GreenCompareResult,
  type GreenComponent,
  type GreenComponentRole,
  type GreenMetricsRequest,
} from "@/lib/reaction/green-metrics"

type ExperimentRow = { id: number; code: string }

type ComponentRow = {
  _id: number
  name: string
  role: GreenComponentRole
  smiles: string
  equivalents: string
  mass_g: string
}

function readExperiments(experiments: Record<string, unknown>[]): ExperimentRow[] {
  const rows: ExperimentRow[] = []
  for (const e of experiments) {
    const id = typeof e.id === "number" ? e.id : null
    if (id == null) continue
    const code = typeof e.experiment_code === "string" && e.experiment_code ? e.experiment_code : `#${id}`
    rows.push({ id, code })
  }
  return rows
}

function numOrNull(s: string): number | null {
  const t = s.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

function provenanceCitations(provenance: Record<string, unknown> | undefined): string[] {
  const c = provenance?.citations
  if (!Array.isArray(c)) return []
  return c.filter((x): x is string => typeof x === "string")
}

/** Metric cards for one assessment's metrics_json. */
function MetricGrid({ metrics }: { metrics: Record<string, unknown> }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {GREEN_METRICS.map((m) => (
        <div key={m.key} className="rounded-md border bg-muted/15 px-3 py-2">
          <div className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {m.label}
            <InfoTooltip label={m.label} content={m.help} />
          </div>
          <div className="mt-0.5 font-mono text-sm">{formatGreenMetric(readGreenMetric(metrics, m.key), m.digits, m.unit)}</div>
        </div>
      ))}
    </div>
  )
}

export function GreenMetricsPanel({
  projectId,
  experiments,
}: {
  projectId: number
  experiments: Record<string, unknown>[]
}) {
  const expRows = useMemo(() => readExperiments(experiments), [experiments])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [assessment, setAssessment] = useState<GreenAssessment | null>(null)
  const [loadingAssessment, setLoadingAssessment] = useState(false)
  const [computing, setComputing] = useState(false)
  const [error, setError] = useState("")

  // compute form
  const [productSmiles, setProductSmiles] = useState("")
  const [productMassG, setProductMassG] = useState("")
  const [components, setComponents] = useState<ComponentRow[]>([])
  const [persist, setPersist] = useState(true)
  const idCounter = useState(() => ({ n: 0 }))[0]

  // compare
  const [compareSel, setCompareSel] = useState<Set<number>>(new Set())
  const [compareResult, setCompareResult] = useState<GreenCompareResult | null>(null)
  const [comparing, setComparing] = useState(false)

  useEffect(() => {
    if (selectedId == null && expRows.length) setSelectedId(expRows[0].id)
  }, [expRows, selectedId])

  // Drop any compare selections whose experiment was removed from the project,
  // so the count and the compare request can't carry a stale id.
  useEffect(() => {
    setCompareSel((prev) => {
      const live = new Set(expRows.map((e) => e.id))
      let changed = false
      for (const id of prev) if (!live.has(id)) changed = true
      if (!changed) return prev
      return new Set([...prev].filter((id) => live.has(id)))
    })
  }, [expRows])

  // Load the latest assessment for the selected experiment. The `cancelled` guard
  // prevents a slow earlier fetch from clobbering a faster later one when the user
  // switches experiments quickly (stale-data race).
  useEffect(() => {
    if (selectedId == null) return
    let cancelled = false
    setLoadingAssessment(true)
    setError("")
    void (async () => {
      try {
        const res = await getGreenMetrics(projectId, selectedId)
        if (!cancelled) setAssessment(res)
      } catch (e) {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 404) {
          setAssessment(null) // no assessment yet — expected
        } else {
          setError(formatApiError(e, "Could not load green metrics."))
        }
      } finally {
        if (!cancelled) setLoadingAssessment(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedId, projectId])

  function addComponent() {
    setComponents((r) => [
      ...r,
      { _id: ++idCounter.n, name: "", role: "reactant", smiles: "", equivalents: "", mass_g: "" },
    ])
  }

  async function compute() {
    if (selectedId == null) return
    setComputing(true)
    setError("")
    try {
      const body: GreenMetricsRequest = {
        product_smiles: productSmiles.trim() || null,
        product_mass_g: numOrNull(productMassG),
        persist_to_outcome: persist,
        components: components
          .filter((c) => c.name.trim())
          .map<GreenComponent>((c) => ({
            name: c.name.trim(),
            role: c.role,
            smiles: c.smiles.trim() || null,
            equivalents: numOrNull(c.equivalents),
            mass_g: numOrNull(c.mass_g),
          })),
      }
      const res = await computeGreenMetrics(projectId, selectedId, body)
      setAssessment(res)
    } catch (e) {
      setError(formatApiError(e, "Could not compute green metrics."))
    } finally {
      setComputing(false)
    }
  }

  async function runCompare() {
    const ids = [...compareSel]
    if (ids.length < 2) return
    setComparing(true)
    setError("")
    try {
      setCompareResult(await compareGreenMetrics(projectId, ids))
    } catch (e) {
      setError(formatApiError(e, "Could not compare experiments."))
    } finally {
      setComparing(false)
    }
  }

  // Best value per metric across the compare entries (min for low-better, max otherwise).
  const bestByMetric = useMemo(() => {
    const out: Record<string, number> = {}
    if (!compareResult) return out
    for (const m of GREEN_METRICS) {
      const vals = (compareResult.entries ?? [])
        .map((e) => readGreenMetric(e.metrics_json as Record<string, unknown> | undefined, m.key))
        .filter((v): v is number => v != null)
      if (vals.length) out[m.key] = m.better === "low" ? Math.min(...vals) : Math.max(...vals)
    }
    return out
  }, [compareResult])

  const metrics = (assessment?.metrics_json ?? null) as Record<string, unknown> | null
  const provenance = (assessment?.provenance_json ?? undefined) as Record<string, unknown> | undefined
  const definitions = (provenance?.definitions ?? undefined) as Record<string, unknown> | undefined

  return (
    <div className="space-y-6">
      <ModuleCard
        accent="violet"
        eyebrow="ReactionIQ · Green chemistry"
        title={
          <span className="inline-flex items-center gap-2">
            <Leaf className="h-4 w-4" aria-hidden />
            Green metrics
          </span>
        }
        description="Deterministic green-chemistry assessment per experiment — E-factor, PMI, atom economy, RME, and a composite green score (CHEM21 solvent table). A scale-up / regulatory deliverable; decision-support, human review required."
      >
        {error ? <AlertCard variant="error" title="Green metrics" description={error} /> : null}

        {expRows.length === 0 ? (
          <p className="text-sm text-muted-foreground">Add an experiment to compute green metrics.</p>
        ) : (
          <div className="space-y-5">
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="green-exp">Experiment</Label>
                <Select value={selectedId != null ? String(selectedId) : ""} onValueChange={(v) => setSelectedId(Number(v))}>
                  <SelectTrigger id="green-exp" className="w-[220px]">
                    <SelectValue placeholder="Select experiment" />
                  </SelectTrigger>
                  <SelectContent>
                    {expRows.map((e) => (
                      <SelectItem key={e.id} value={String(e.id)}>
                        {e.code}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Latest assessment */}
            {loadingAssessment ? (
              <p className="text-sm text-muted-foreground">
                <Loader2 className="mr-2 inline h-4 w-4 animate-spin" aria-hidden />
                Loading…
              </p>
            ) : metrics ? (
              <div className="space-y-3">
                <MetricGrid metrics={metrics} />
                {assessment?.warnings && assessment.warnings.length > 0 ? (
                  <ul className="space-y-1 text-xs text-warning">
                    {assessment.warnings.map((w, i) => (
                      <li key={i} className="flex items-start gap-1.5">
                        <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                        <span>{w}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
                {provenance ? (
                  <Collapsible className="rounded-md border bg-muted/15">
                    <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs font-medium hover:bg-muted/40">
                      Method &amp; provenance
                      <ChevronDown className="h-4 w-4 shrink-0 opacity-70" aria-hidden />
                    </CollapsibleTrigger>
                    <CollapsibleContent className="space-y-2 border-t px-3 pb-3 pt-2 text-xs">
                      <p className="text-muted-foreground">
                        formula {String(provenance.formula_version ?? "—")} · solvents{" "}
                        {String(provenance.solvent_table_version ?? "—")}
                        {provenance.rdkit_available === false ? " · RDKit unavailable (atom economy may be omitted)" : ""}
                      </p>
                      {provenanceCitations(provenance).map((c, i) => (
                        <p key={i} className="text-muted-foreground">
                          • {c}
                        </p>
                      ))}
                      {definitions
                        ? Object.entries(definitions).map(([k, v]) => (
                            <p key={k}>
                              <span className="font-medium">{k}:</span>{" "}
                              <span className="text-muted-foreground">{String(v)}</span>
                            </p>
                          ))
                        : null}
                    </CollapsibleContent>
                  </Collapsible>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No green assessment yet for this experiment — compute one below.</p>
            )}

            {/* Compute form */}
            <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <FlaskConical className="h-4 w-4" aria-hidden />
                Compute green metrics
              </h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="green-product-smiles">Product SMILES</Label>
                  <Input id="green-product-smiles" value={productSmiles} onChange={(e) => setProductSmiles(e.target.value)} placeholder="CCO" spellCheck={false} />
                  <p className="text-xs text-muted-foreground">Used (with RDKit) for atom economy; omit and the metric is skipped with a warning.</p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="green-product-mass">Product mass (g)</Label>
                  <Input id="green-product-mass" inputMode="decimal" value={productMassG} onChange={(e) => setProductMassG(e.target.value)} placeholder="100" />
                  <p className="text-xs text-muted-foreground">Required for E-factor / PMI / RME.</p>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label>Input materials</Label>
                  <Button type="button" size="sm" variant="outline" onClick={addComponent}>
                    <Plus className="mr-1.5 h-4 w-4" aria-hidden />
                    Add material
                  </Button>
                </div>
                {components.length === 0 ? (
                  <p className="text-xs text-muted-foreground">Add the reactants, reagents, catalysts, and solvents going in.</p>
                ) : (
                  <div className="space-y-2">
                    {components.map((c) => (
                      <div key={c._id} className="grid grid-cols-2 gap-2 rounded-md border p-2 sm:grid-cols-[1.2fr_1fr_1.2fr_0.8fr_0.8fr_auto]">
                        <Input aria-label="name" value={c.name} placeholder="name" onChange={(e) => setComponents((r) => r.map((x) => (x._id === c._id ? { ...x, name: e.target.value } : x)))} />
                        <Select value={c.role} onValueChange={(v) => setComponents((r) => r.map((x) => (x._id === c._id ? { ...x, role: v as GreenComponentRole } : x)))}>
                          <SelectTrigger aria-label="role">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {GREEN_COMPONENT_ROLES.map((role) => (
                              <SelectItem key={role} value={role}>
                                {role}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Input aria-label="SMILES" value={c.smiles} placeholder="SMILES" spellCheck={false} onChange={(e) => setComponents((r) => r.map((x) => (x._id === c._id ? { ...x, smiles: e.target.value } : x)))} />
                        <Input aria-label="equivalents" inputMode="decimal" value={c.equivalents} placeholder="equiv" onChange={(e) => setComponents((r) => r.map((x) => (x._id === c._id ? { ...x, equivalents: e.target.value } : x)))} />
                        <Input aria-label="mass (g)" inputMode="decimal" value={c.mass_g} placeholder="mass g" onChange={(e) => setComponents((r) => r.map((x) => (x._id === c._id ? { ...x, mass_g: e.target.value } : x)))} />
                        <Button type="button" size="icon" variant="ghost" aria-label="Remove material" onClick={() => setComponents((r) => r.filter((x) => x._id !== c._id))}>
                          <Trash2 className="h-4 w-4 text-destructive" aria-hidden />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <label className="flex items-center gap-2 text-sm" htmlFor="green-persist">
                <Checkbox id="green-persist" checked={persist} onCheckedChange={(v) => setPersist(v === true)} />
                Write metrics onto the experiment outcome (for Bayesian optimization)
              </label>

              <Button type="button" onClick={() => void compute()} disabled={computing || selectedId == null}>
                {computing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <Leaf className="mr-2 h-4 w-4" aria-hidden />}
                Compute
              </Button>
            </div>
          </div>
        )}
      </ModuleCard>

      {/* Compare */}
      {expRows.length >= 2 ? (
        <ModuleCard accent="slate" eyebrow="ReactionIQ · Green chemistry" title="Compare experiments">
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">Select experiments to compare their green metrics side by side.</p>
            <div className="flex flex-wrap gap-2">
              {expRows.map((e) => {
                const on = compareSel.has(e.id)
                return (
                  <label key={e.id} className={cn("flex cursor-pointer items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs", on && "border-[color:var(--mt-violet)]")} htmlFor={`cmp-${e.id}`}>
                    <Checkbox
                      id={`cmp-${e.id}`}
                      checked={on}
                      onCheckedChange={(v) =>
                        setCompareSel((prev) => {
                          const next = new Set(prev)
                          if (v === true) next.add(e.id)
                          else next.delete(e.id)
                          return next
                        })
                      }
                    />
                    {e.code}
                  </label>
                )
              })}
            </div>
            <Button type="button" size="sm" variant="outline" onClick={() => void runCompare()} disabled={comparing || compareSel.size < 2}>
              {comparing ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : null}
              Compare ({compareSel.size})
            </Button>

            {compareResult ? (
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Experiment</TableHead>
                      {GREEN_METRICS.map((m) => (
                        <TableHead key={m.key} className="text-right text-xs">
                          {m.label}
                          {m.unit ? ` (${m.unit.trim()})` : ""}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(compareResult.entries ?? []).map((entry) => {
                      const mj = entry.metrics_json as Record<string, unknown> | undefined
                      return (
                        <TableRow key={entry.reaction_experiment_id}>
                          <TableCell className="font-medium">
                            {entry.experiment_code || `#${entry.reaction_experiment_id}`}
                            {!entry.available ? (
                              <Badge variant="outline" className="ml-2 font-normal text-muted-foreground">
                                no data
                              </Badge>
                            ) : null}
                          </TableCell>
                          {GREEN_METRICS.map((m) => {
                            const v = readGreenMetric(mj, m.key)
                            const isBest = v != null && bestByMetric[m.key] != null && v === bestByMetric[m.key]
                            return (
                              <TableCell key={m.key} className={cn("text-right font-mono text-xs tabular-nums", isBest && "font-semibold text-success")}>
                                {formatGreenMetric(v, m.digits)}
                              </TableCell>
                            )
                          })}
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            ) : null}
          </div>
        </ModuleCard>
      ) : null}
    </div>
  )
}
