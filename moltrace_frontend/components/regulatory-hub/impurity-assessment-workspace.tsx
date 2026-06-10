"use client"

import { useMemo, useRef, useState } from "react"
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  Download,
  FlaskConical,
  Info,
  Loader2,
  Plus,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react"
import Link from "next/link"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
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
 * Impurity Assessment — one form → one tabbed report over the Regulatory
 * Hub's five deterministic engines (ICH Q3A/B, Q3C, Q3D, M7, FDA CPCA) +
 * nitrosamine cumulative risk, via a single POST /regulatory/impurities/assess.
 *
 * Deliberately one endpoint → one panel (not five screens). Lands as a
 * subsection of the Regulatory Hub (/regulatory/impurities); no new top-level
 * nav. The binding contract is the regenerated schema.d.ts.
 *
 * Decision-support only: the response is ALWAYS human_review_required, so the
 * report carries a persistent disclaimer banner and a qualified-sign-off
 * acknowledgement gate before the report can be exported.
 */

type AssessRequest = components["schemas"]["ImpurityAssessRequest"]
type AssessResult = components["schemas"]["ImpurityAssessResult"]
type Route = AssessRequest["route"]
type SubstanceType = AssessRequest["substance_type"]
type TriState = "positive" | "negative" | "unset"

const ROUTE_OPTIONS: { value: Route; label: string }[] = [
  { value: "oral", label: "Oral" },
  { value: "parenteral", label: "Parenteral" },
  { value: "inhalation", label: "Inhalation" },
  { value: "cutaneous", label: "Cutaneous" },
]

const SUBSTANCE_OPTIONS: { value: SubstanceType; label: string }[] = [
  { value: "drug_substance", label: "Drug substance" },
  { value: "drug_product", label: "Drug product" },
]

const DEFAULT_DURATION_MONTHS = 120

/** ICH M7 less-than-lifetime staged-TTC band for the entered duration.
 *  Informational helper only — the backend computes the actual TTC. */
function m7Band(months: number): string {
  if (!Number.isFinite(months) || months <= 0) return ""
  if (months <= 1) return "≤1 month · staged TTC 120 µg/day"
  if (months <= 12) return ">1–12 months · staged TTC 20 µg/day"
  if (months <= 120) return ">1–10 years · staged TTC 10 µg/day"
  return ">10 years (lifetime) · TTC 1.5 µg/day"
}

// ── Client-side row models (numeric fields kept as strings for the inputs) ──
type SolventRow = { _id: number; identifier: string; measured_ppm: string }
type ElementRow = { _id: number; element: string; measured_ppm: string }
type StructuralRow = {
  _id: number
  smiles: string
  name: string
  measured_ng_per_day: string
  advanced: boolean
  in_silico_expert: TriState
  in_silico_statistical: TriState
  experimental_ames: TriState
  experimental_carcinogen: TriState
}

function numOrNull(s: string): number | null {
  const t = s.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

function triToWire(t: TriState): "positive" | "negative" | null {
  return t === "unset" ? null : t
}

/** passed:true → ok · false → fail · null → neutral "not measured". */
function PassChip({ passed }: { passed?: boolean | null }) {
  if (passed == null) {
    return (
      <Badge variant="outline" className="font-normal text-muted-foreground">
        not measured
      </Badge>
    )
  }
  return passed ? (
    <Badge variant="outline" className="gap-1 border-success/50 font-normal text-success">
      <CheckCircle2 className="h-3 w-3" aria-hidden />
      pass
    </Badge>
  ) : (
    <Badge variant="outline" className="gap-1 border-destructive/50 font-normal text-destructive">
      <XCircle className="h-3 w-3" aria-hidden />
      fail
    </Badge>
  )
}

/** ICH M7 class 1–5 badge; 1–2 high concern, 3 moderate, 4–5 low. */
function M7ClassBadge({ m7Class }: { m7Class: number }) {
  const cls =
    m7Class <= 2
      ? "border-destructive/50 text-destructive"
      : m7Class === 3
        ? "border-warning/50 text-warning"
        : "border-success/50 text-success"
  return (
    <Badge variant="outline" className={cn("font-normal", cls)}>
      M7 class {m7Class}
    </Badge>
  )
}

/** Per-row "audit/evidence" affordance — the regulatory basis on hover. */
function BasisInfo({ basis }: { basis: string }) {
  return <InfoTooltip content={basis} label="Regulatory basis" />
}

function num(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—"
  return value.toLocaleString(undefined, { maximumFractionDigits: digits })
}

export function ImpurityAssessmentWorkspace() {
  const idCounter = useRef(0)
  const nextId = () => ++idCounter.current

  const [dailyDose, setDailyDose] = useState("1.0")
  const [route, setRoute] = useState<Route>("oral")
  const [substanceType, setSubstanceType] = useState<SubstanceType>("drug_substance")
  const [durationMonths, setDurationMonths] = useState(String(DEFAULT_DURATION_MONTHS))

  const [solvents, setSolvents] = useState<SolventRow[]>([])
  const [elements, setElements] = useState<ElementRow[]>([])
  const [structural, setStructural] = useState<StructuralRow[]>([])

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const [result, setResult] = useState<AssessResult | null>(null)
  const [activeTab, setActiveTab] = useState("thresholds")
  const [acknowledged, setAcknowledged] = useState(false)

  const durationNum = Number(durationMonths)
  const band = m7Band(durationNum)

  // ── Row mutators ──────────────────────────────────────────────────────
  const addSolvent = () => setSolvents((r) => [...r, { _id: nextId(), identifier: "", measured_ppm: "" }])
  const addElement = () => setElements((r) => [...r, { _id: nextId(), element: "", measured_ppm: "" }])
  const addStructural = () =>
    setStructural((r) => [
      ...r,
      {
        _id: nextId(),
        smiles: "",
        name: "",
        measured_ng_per_day: "",
        advanced: false,
        in_silico_expert: "unset",
        in_silico_statistical: "unset",
        experimental_ames: "unset",
        experimental_carcinogen: "unset",
      },
    ])

  function buildRequest(): AssessRequest | { error: string } {
    const dose = Number(dailyDose)
    if (!Number.isFinite(dose) || dose <= 0) return { error: "Daily dose must be greater than 0 g/day." }
    if (dose > 100) return { error: "Daily dose must be ≤ 100 g/day." }
    const duration = Number(durationMonths)
    if (!Number.isFinite(duration) || duration <= 0) return { error: "Treatment duration must be a positive number of months." }

    const req: AssessRequest = {
      daily_dose_g: dose,
      route,
      substance_type: substanceType,
      duration_months: Math.round(duration),
    }

    const solventInputs = solvents
      .filter((s) => s.identifier.trim())
      .map((s) => ({ identifier: s.identifier.trim(), measured_ppm: numOrNull(s.measured_ppm) }))
    if (solventInputs.length) req.residual_solvents = solventInputs

    const elementInputs = elements
      .filter((e) => e.element.trim())
      .map((e) => ({ element: e.element.trim(), measured_ppm: numOrNull(e.measured_ppm) }))
    if (elementInputs.length) req.elemental_impurities = elementInputs

    const structuralInputs = structural
      .filter((s) => s.smiles.trim())
      .map((s) => ({
        smiles: s.smiles.trim(),
        name: s.name.trim() || null,
        measured_ng_per_day: numOrNull(s.measured_ng_per_day),
        in_silico_expert: triToWire(s.in_silico_expert),
        in_silico_statistical: triToWire(s.in_silico_statistical),
        experimental_ames: triToWire(s.experimental_ames),
        experimental_carcinogen: triToWire(s.experimental_carcinogen),
      }))
    if (structuralInputs.length) req.structural_impurities = structuralInputs

    return req
  }

  async function assess() {
    const built = buildRequest()
    if ("error" in built) {
      setError(built.error)
      return
    }
    setSubmitting(true)
    setError("")
    setResult(null)
    setAcknowledged(false)
    try {
      const data = await apiFetch<AssessResult>("/regulatory/impurities/assess", {
        method: "POST",
        body: built,
      })
      setResult(data)
      setActiveTab("thresholds")
    } catch (err) {
      setError(formatApiError(err, "Impurity assessment failed."))
    } finally {
      setSubmitting(false)
    }
  }

  function downloadJson() {
    if (!result) return
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "impurity-assessment.json"
    a.click()
    URL.revokeObjectURL(url)
  }

  const availableTabs = useMemo(() => {
    if (!result) return []
    return [
      { key: "thresholds", label: "Thresholds", show: true },
      { key: "solvents", label: "Residual solvents", show: (result.residual_solvents?.length ?? 0) > 0 },
      { key: "elements", label: "Elemental", show: (result.elemental_impurities?.length ?? 0) > 0 },
      { key: "structural", label: "Structural (M7)", show: (result.structural_impurities?.length ?? 0) > 0 },
      { key: "cumulative", label: "Nitrosamine risk", show: result.nitrosamine_cumulative_risk != null },
    ].filter((t) => t.show)
  }, [result])

  const ruleSetEntries = result ? Object.entries(result.rule_set_versions ?? {}) : []

  return (
    <div className="mx-auto max-w-[1200px] space-y-8 pb-12">
      {/* Back to the Regulatory Hub tab in the Programs workspace — the
          ?program param restores the tab so the hub stays highlighted between
          SpectraCheck and ReactionIQ, matching where the user came from. */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/spectracheck?program=regulatory_hub">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Regulatory Hub
          </Link>
        </Button>
      </div>

      {/* Header */}
      <header className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-cyan)" }}
        >
          MolTrace · Regulatory Hub · Impurity Assessment
        </p>
        <h1 className="inline-flex items-center gap-2 font-mono text-2xl font-bold tracking-tight">
          <FlaskConical className="h-6 w-6" style={{ color: "var(--mt-cyan)" }} aria-hidden />
          Impurity Assessment
        </h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          One assessment across five deterministic engines — ICH Q3A/B thresholds, Q3C residual
          solvents, Q3D elemental impurities, M7 mutagenic impurities, and FDA CPCA nitrosamine
          classification (plus cumulative nitrosamine risk). Enter a dose and any impurities to
          assess; every limit is decision-support and requires qualified review.
        </p>
      </header>

      {/* ── Input card ──────────────────────────────────────────────────── */}
      <ModuleCard
        accent="cyan"
        eyebrow="Impurity Assessment · Input"
        title="Assessment parameters"
        icon={FlaskConical}
        description="Only daily dose is required. Each impurity list is optional — an empty assessment still returns the Q3A/B thresholds for the dose."
      >
        <div className="space-y-6">
          {/* Core parameters */}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="impurity-daily-dose">Daily dose (g/day)</Label>
              <Input
                id="impurity-daily-dose"
                value={dailyDose}
                onChange={(e) => setDailyDose(e.target.value)}
                inputMode="decimal"
                placeholder="1.0"
                disabled={submitting}
                autoComplete="off"
              />
              <p className="text-xs text-muted-foreground">&gt; 0 and ≤ 100 g/day.</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="impurity-duration">Treatment duration (months)</Label>
              <Input
                id="impurity-duration"
                value={durationMonths}
                onChange={(e) => setDurationMonths(e.target.value)}
                inputMode="numeric"
                placeholder={String(DEFAULT_DURATION_MONTHS)}
                disabled={submitting}
                autoComplete="off"
              />
              <p className="text-xs text-muted-foreground">{band ? `M7 band · ${band}` : "Enter a positive number of months."}</p>
            </div>

            <div className="space-y-2">
              <Label>Route of administration</Label>
              <div role="radiogroup" aria-label="Route of administration" className="inline-flex flex-wrap overflow-hidden rounded-md border bg-card">
                {ROUTE_OPTIONS.map((opt, idx) => (
                  <button
                    key={opt.value}
                    type="button"
                    role="radio"
                    aria-checked={route === opt.value}
                    disabled={submitting}
                    onClick={() => setRoute(opt.value)}
                    className={cn(
                      "px-3 py-1.5 text-xs transition-colors",
                      idx > 0 ? "border-l" : "",
                      route === opt.value ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted/40",
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label>Substance type</Label>
              <div role="radiogroup" aria-label="Substance type" className="inline-flex overflow-hidden rounded-md border bg-card">
                {SUBSTANCE_OPTIONS.map((opt, idx) => (
                  <button
                    key={opt.value}
                    type="button"
                    role="radio"
                    aria-checked={substanceType === opt.value}
                    disabled={submitting}
                    onClick={() => setSubstanceType(opt.value)}
                    className={cn(
                      "px-3 py-1.5 text-xs transition-colors",
                      idx > 0 ? "border-l" : "",
                      substanceType === opt.value ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted/40",
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Residual solvents (Q3C) */}
          <RepeatableSection
            title="Residual solvents"
            subtitle="ICH Q3C — identifier (name / CAS / SMILES) + measured ppm"
            onAdd={addSolvent}
            disabled={submitting}
            count={solvents.length}
          >
            {solvents.map((row) => (
              <div key={row._id} className="flex flex-wrap items-end gap-2">
                <div className="min-w-[200px] flex-1 space-y-1">
                  <Label className="text-xs text-muted-foreground">identifier</Label>
                  <Input
                    value={row.identifier}
                    onChange={(e) =>
                      setSolvents((rows) => rows.map((r) => (r._id === row._id ? { ...r, identifier: e.target.value } : r)))
                    }
                    placeholder="methanol / 67-56-1 / CO"
                    disabled={submitting}
                    autoComplete="off"
                  />
                </div>
                <div className="w-32 space-y-1">
                  <Label className="text-xs text-muted-foreground">measured ppm</Label>
                  <Input
                    value={row.measured_ppm}
                    onChange={(e) =>
                      setSolvents((rows) => rows.map((r) => (r._id === row._id ? { ...r, measured_ppm: e.target.value } : r)))
                    }
                    inputMode="decimal"
                    placeholder="2000"
                    disabled={submitting}
                    autoComplete="off"
                  />
                </div>
                <RemoveRowButton onClick={() => setSolvents((rows) => rows.filter((r) => r._id !== row._id))} disabled={submitting} />
              </div>
            ))}
          </RepeatableSection>

          {/* Elemental impurities (Q3D) */}
          <RepeatableSection
            title="Elemental impurities"
            subtitle="ICH Q3D — element (symbol / name) + measured ppm"
            onAdd={addElement}
            disabled={submitting}
            count={elements.length}
          >
            {elements.map((row) => (
              <div key={row._id} className="flex flex-wrap items-end gap-2">
                <div className="min-w-[200px] flex-1 space-y-1">
                  <Label className="text-xs text-muted-foreground">element</Label>
                  <Input
                    value={row.element}
                    onChange={(e) =>
                      setElements((rows) => rows.map((r) => (r._id === row._id ? { ...r, element: e.target.value } : r)))
                    }
                    placeholder="Pb / lead"
                    disabled={submitting}
                    autoComplete="off"
                  />
                </div>
                <div className="w-32 space-y-1">
                  <Label className="text-xs text-muted-foreground">measured ppm</Label>
                  <Input
                    value={row.measured_ppm}
                    onChange={(e) =>
                      setElements((rows) => rows.map((r) => (r._id === row._id ? { ...r, measured_ppm: e.target.value } : r)))
                    }
                    inputMode="decimal"
                    placeholder="0.3"
                    disabled={submitting}
                    autoComplete="off"
                  />
                </div>
                <RemoveRowButton onClick={() => setElements((rows) => rows.filter((r) => r._id !== row._id))} disabled={submitting} />
              </div>
            ))}
          </RepeatableSection>

          {/* Structural impurities (M7 + CPCA) */}
          <RepeatableSection
            title="Structural impurities"
            subtitle="ICH M7 (+ CPCA if a nitrosamine) — SMILES + name; advanced (Q)SAR/experimental calls optional"
            onAdd={addStructural}
            disabled={submitting}
            count={structural.length}
          >
            {structural.map((row) => (
              <div key={row._id} className="space-y-2 rounded-md border bg-muted/10 p-3">
                <div className="flex flex-wrap items-end gap-2">
                  <div className="min-w-[220px] flex-1 space-y-1">
                    <Label className="text-xs text-muted-foreground">SMILES</Label>
                    <Input
                      value={row.smiles}
                      onChange={(e) =>
                        setStructural((rows) => rows.map((r) => (r._id === row._id ? { ...r, smiles: e.target.value } : r)))
                      }
                      placeholder="CN(C)N=O"
                      disabled={submitting}
                      autoComplete="off"
                      className="font-mono"
                    />
                  </div>
                  <div className="w-40 space-y-1">
                    <Label className="text-xs text-muted-foreground">name (optional)</Label>
                    <Input
                      value={row.name}
                      onChange={(e) =>
                        setStructural((rows) => rows.map((r) => (r._id === row._id ? { ...r, name: e.target.value } : r)))
                      }
                      placeholder="NDMA"
                      disabled={submitting}
                      autoComplete="off"
                    />
                  </div>
                  <div className="w-36 space-y-1">
                    <Label className="text-xs text-muted-foreground">ng/day (optional)</Label>
                    <Input
                      value={row.measured_ng_per_day}
                      onChange={(e) =>
                        setStructural((rows) =>
                          rows.map((r) => (r._id === row._id ? { ...r, measured_ng_per_day: e.target.value } : r)),
                        )
                      }
                      inputMode="decimal"
                      placeholder="50"
                      disabled={submitting}
                      autoComplete="off"
                    />
                  </div>
                  <RemoveRowButton onClick={() => setStructural((rows) => rows.filter((r) => r._id !== row._id))} disabled={submitting} />
                </div>

                <button
                  type="button"
                  onClick={() =>
                    setStructural((rows) => rows.map((r) => (r._id === row._id ? { ...r, advanced: !r.advanced } : r)))
                  }
                  className="inline-flex items-center gap-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground"
                >
                  <ChevronDown className={cn("h-3 w-3 transition-transform", row.advanced ? "rotate-180" : "")} aria-hidden />
                  Advanced · M7 (Q)SAR &amp; experimental
                </button>

                {row.advanced ? (
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    {(
                      [
                        ["in_silico_expert", "(Q)SAR expert"],
                        ["in_silico_statistical", "(Q)SAR statistical"],
                        ["experimental_ames", "Ames"],
                        ["experimental_carcinogen", "Carcinogenicity"],
                      ] as const
                    ).map(([field, label]) => (
                      <div key={field} className="space-y-1">
                        <Label className="text-xs text-muted-foreground">{label}</Label>
                        <Select
                          value={row[field]}
                          onValueChange={(v) =>
                            setStructural((rows) => rows.map((r) => (r._id === row._id ? { ...r, [field]: v as TriState } : r)))
                          }
                          disabled={submitting}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="unset">not set</SelectItem>
                            <SelectItem value="positive">positive</SelectItem>
                            <SelectItem value="negative">negative</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </RepeatableSection>

          {error ? <AlertCard variant="error" title="Assessment failed" description={error} /> : null}

          <div className="flex flex-wrap items-center gap-2">
            <Button className="gap-2" onClick={() => void assess()} disabled={submitting}>
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <ShieldCheck className="h-4 w-4" aria-hidden />}
              Assess
            </Button>
            <span className="text-xs text-muted-foreground">
              Sends one request to all five engines; unknown items are reported as non-blocking notices.
            </span>
          </div>
        </div>
      </ModuleCard>

      {/* ── Report ──────────────────────────────────────────────────────── */}
      {result ? (
        <div className="space-y-4">
          {/* Persistent disclaimer banner */}
          <AlertCard variant="warning" title="Decision-support only — requires qualified sign-off" description={result.disclaimer} />

          {/* Non-blocking warnings */}
          {(result.warnings?.length ?? 0) > 0 ? (
            <AlertCard variant="info" title={`Notices · ${result.warnings!.length}`}>
              <ul className="ml-4 list-disc space-y-0.5 text-xs text-foreground/90">
                {result.warnings!.map((w, i) => (
                  <li key={`warn-${i}`}>{w}</li>
                ))}
              </ul>
            </AlertCard>
          ) : null}

          <ModuleCard
            accent="cyan"
            eyebrow="Impurity Assessment · Report"
            title="Assessment report"
            icon={ShieldCheck}
            description={`Dose ${num(result.daily_dose_g)} g/day · ${result.route} · ${result.substance_type.replace(/_/g, " ")} · ${result.duration_months} months`}
          >
            <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
              <TabsList className="h-auto w-full flex-wrap justify-start">
                {availableTabs.map((t) => (
                  <TabsTrigger key={t.key} value={t.key}>
                    {t.label}
                  </TabsTrigger>
                ))}
              </TabsList>

              {/* 1. Thresholds (Q3A/B) — always present */}
              <TabsContent value="thresholds" className="space-y-3">
                <div className="flex items-center gap-2">
                  <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                    ICH Q3A/B reporting thresholds
                  </p>
                  <BasisInfo basis={`${result.thresholds.regulatory_basis} · ${result.thresholds.table_reference}`} />
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <ThresholdStat label="Reporting" value={`${num(result.thresholds.reporting_percent, 3)} %`} />
                  <ThresholdStat label="Identification" value={`${num(result.thresholds.identification_percent, 3)} %`} />
                  <ThresholdStat label="Qualification" value={`${num(result.thresholds.qualification_percent, 3)} %`} />
                </div>
              </TabsContent>

              {/* 2. Residual solvents (Q3C) */}
              <TabsContent value="solvents">
                <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>solvent</TableHead>
                        <TableHead>class</TableHead>
                        <TableHead className="text-right">permitted ppm</TableHead>
                        <TableHead className="text-right">measured ppm</TableHead>
                        <TableHead className="text-right">margin ppm</TableHead>
                        <TableHead>result</TableHead>
                        <TableHead className="w-8" aria-label="basis" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(result.residual_solvents ?? []).map((s, i) => (
                        <TableRow key={`${s.identifier}-${i}`}>
                          <TableCell className="font-medium">
                            {s.matched ? (s.solvent_name ?? s.identifier) : s.identifier}
                          </TableCell>
                          <TableCell>
                            {s.matched ? (
                              s.class_number ?? "—"
                            ) : (
                              <span className="text-muted-foreground">unknown — verify against Q3C</span>
                            )}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">{num(s.permitted_ppm)}</TableCell>
                          <TableCell className="text-right tabular-nums">{num(s.measured_ppm)}</TableCell>
                          <TableCell className="text-right tabular-nums">{num(s.margin_ppm)}</TableCell>
                          <TableCell>{s.matched ? <PassChip passed={s.passed} /> : <Badge variant="outline" className="font-normal text-muted-foreground">not assessed</Badge>}</TableCell>
                          <TableCell><BasisInfo basis={s.regulatory_basis} /></TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </TabsContent>

              {/* 3. Elemental impurities (Q3D) */}
              <TabsContent value="elements">
                <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>element</TableHead>
                        <TableHead>class</TableHead>
                        <TableHead className="text-right">permitted ppm</TableHead>
                        <TableHead className="text-right">control threshold</TableHead>
                        <TableHead className="text-right">measured ppm</TableHead>
                        <TableHead>result</TableHead>
                        <TableHead className="w-8" aria-label="basis" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(result.elemental_impurities ?? []).map((el, i) => (
                        <TableRow key={`${el.element}-${i}`}>
                          <TableCell className="font-medium">{el.element}</TableCell>
                          <TableCell>{el.element_class ?? "—"}</TableCell>
                          <TableCell className="text-right tabular-nums">
                            {el.route_data_available ? (
                              num(el.permitted_concentration_ppm)
                            ) : (
                              <span className="text-xs text-muted-foreground">cutaneous PDE not encoded</span>
                            )}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">{num(el.control_threshold_ppm)}</TableCell>
                          <TableCell className="text-right tabular-nums">{num(el.measured_ppm)}</TableCell>
                          <TableCell><PassChip passed={el.passed} /></TableCell>
                          <TableCell><BasisInfo basis={el.regulatory_basis} /></TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </TabsContent>

              {/* 4. Structural impurities (M7 + CPCA) */}
              <TabsContent value="structural" className="space-y-3">
                {(result.structural_impurities ?? []).map((st, i) => (
                  <div key={`${st.smiles}-${i}`} className="space-y-2 rounded-md border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{st.name ?? "Structural impurity"}</span>
                      <code className="font-mono text-xs text-muted-foreground">{st.smiles}</code>
                      <M7ClassBadge m7Class={st.m7_class} />
                      {st.coc_flag ? (
                        <Badge variant="outline" className="border-destructive/50 font-normal text-destructive">
                          cohort of concern
                        </Badge>
                      ) : null}
                      {st.expert_review_required ? (
                        <Badge variant="outline" className="border-warning/50 font-normal text-warning">
                          expert review
                        </Badge>
                      ) : null}
                      <span className="ml-auto">
                        <BasisInfo basis={st.regulatory_basis} />
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {st.m7_ttc_ug_per_day != null ? `TTC ${num(st.m7_ttc_ug_per_day)} µg/day · ` : ""}
                      {st.regulatory_action_required}
                    </p>

                    {st.cpca ? (
                      <div className="rounded-md border border-dashed bg-muted/20 p-3">
                        <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                          Nitrosamine · FDA CPCA
                        </p>
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <Badge variant="outline" className="font-normal">CPCA category {st.cpca.category}</Badge>
                          <span className="text-muted-foreground">AI limit</span>
                          <span className="font-mono tabular-nums">{num(st.cpca.ai_limit_ng_per_day)} ng/day</span>
                          {st.cpca.measured_ng_per_day != null ? (
                            <>
                              <span className="text-muted-foreground">· measured</span>
                              <span className="font-mono tabular-nums">{num(st.cpca.measured_ng_per_day)} ng/day</span>
                            </>
                          ) : null}
                          {st.cpca.within_ai_limit == null ? (
                            <Badge variant="outline" className="font-normal text-muted-foreground">not measured</Badge>
                          ) : st.cpca.within_ai_limit ? (
                            <Badge variant="outline" className="border-success/50 font-normal text-success">within AI limit</Badge>
                          ) : (
                            <Badge variant="outline" className="border-destructive/50 font-normal text-destructive">exceeds AI limit</Badge>
                          )}
                          <span className="ml-auto"><BasisInfo basis={st.cpca.regulatory_basis} /></span>
                        </div>
                      </div>
                    ) : null}
                  </div>
                ))}
              </TabsContent>

              {/* 5. Nitrosamine cumulative risk */}
              <TabsContent value="cumulative">
                {result.nitrosamine_cumulative_risk ? (
                  <div className="flex flex-wrap items-center gap-4 rounded-md border p-4">
                    <div>
                      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                        Total risk ratio · must be &lt; 1
                      </p>
                      <p
                        className={cn(
                          "font-mono text-3xl font-bold tabular-nums",
                          result.nitrosamine_cumulative_risk.passes ? "text-success" : "text-destructive",
                        )}
                      >
                        {num(result.nitrosamine_cumulative_risk.total_risk_ratio, 3)}
                      </p>
                    </div>
                    {result.nitrosamine_cumulative_risk.passes ? (
                      <Badge variant="outline" className="gap-1 border-success/50 font-normal text-success">
                        <CheckCircle2 className="h-3 w-3" aria-hidden /> within cumulative limit
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="gap-1 border-destructive/50 font-normal text-destructive">
                        <AlertTriangle className="h-3 w-3" aria-hidden /> exceeds cumulative limit
                      </Badge>
                    )}
                    <span className="text-xs text-muted-foreground">
                      across {result.nitrosamine_cumulative_risk.n_components} nitrosamine component
                      {result.nitrosamine_cumulative_risk.n_components === 1 ? "" : "s"}
                    </span>
                  </div>
                ) : null}
              </TabsContent>
            </Tabs>

            {/* Audit / evidence — rule-set versions */}
            {ruleSetEntries.length > 0 ? (
              <Collapsible className="group mt-4 rounded-md border">
                <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs font-medium hover:bg-muted/50">
                  <span className="inline-flex items-center gap-1.5">
                    <Info className="h-3.5 w-3.5" aria-hidden />
                    Audit · rule-set versions
                  </span>
                  <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <dl className="grid gap-2 border-t p-3 text-xs sm:grid-cols-2">
                    {ruleSetEntries.map(([engine, sha]) => (
                      <div key={engine} className="min-w-0">
                        <dt className="font-mono uppercase tracking-[0.1em] text-muted-foreground">{engine}</dt>
                        <dd className="truncate font-mono" title={sha}>
                          {sha}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </CollapsibleContent>
              </Collapsible>
            ) : null}

            {/* Qualified-sign-off gate before export (human_review_required is always true) */}
            <div className="mt-4 space-y-3 rounded-md border border-warning/40 bg-warning/5 p-4">
              <p className="inline-flex items-center gap-1.5 text-sm font-medium">
                <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />
                Requires qualified sign-off
              </p>
              <label className="flex items-start gap-2 text-sm text-muted-foreground">
                <Checkbox
                  checked={acknowledged}
                  onCheckedChange={(v) => setAcknowledged(v === true)}
                  aria-label="Acknowledge qualified review is required"
                  className="mt-0.5"
                />
                <span>
                  I acknowledge this assessment is decision-support only and a qualified reviewer must sign off
                  before any regulatory use.
                </span>
              </label>
              <Button variant="outline" size="sm" className="gap-2" disabled={!acknowledged} onClick={downloadJson}>
                <Download className="h-3.5 w-3.5" aria-hidden />
                Export report (JSON)
              </Button>
            </div>
          </ModuleCard>
        </div>
      ) : null}
    </div>
  )
}

// ── Small presentational helpers ──────────────────────────────────────────

function RepeatableSection({
  title,
  subtitle,
  onAdd,
  disabled,
  count,
  children,
}: {
  title: string
  subtitle: string
  onAdd: () => void
  disabled?: boolean
  count: number
  children: React.ReactNode
}) {
  return (
    <div className="space-y-2 rounded-md border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{title}</p>
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        </div>
        <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={onAdd} disabled={disabled}>
          <Plus className="h-3.5 w-3.5" aria-hidden />
          Add
        </Button>
      </div>
      {count === 0 ? (
        <p className="text-xs text-muted-foreground">None added — this engine is skipped.</p>
      ) : (
        <div className="space-y-2">{children}</div>
      )}
    </div>
  )
}

function RemoveRowButton({ onClick, disabled }: { onClick: () => void; disabled?: boolean }) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="text-muted-foreground hover:text-destructive"
      onClick={onClick}
      disabled={disabled}
      aria-label="Remove row"
    >
      <Trash2 className="h-4 w-4" aria-hidden />
    </Button>
  )
}

function ThresholdStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/10 px-3 py-2">
      <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">{label}</p>
      <p className="font-mono text-lg font-bold tabular-nums" style={{ color: "var(--mt-cyan)" }}>
        {value}
      </p>
    </div>
  )
}
