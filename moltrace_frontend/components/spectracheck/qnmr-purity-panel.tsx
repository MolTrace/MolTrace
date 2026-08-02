"use client"

import { useMemo, useState } from "react"
import { ChevronDown, Loader2, Scale, Sigma } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import type { components } from "@/src/lib/api/schema"

/**
 * qNMR mass-fraction purity — `POST /spectrum/qnmr/purity` (internal standard)
 * and `POST /spectrum/qnmr/purity/pulcon` (external reference).
 *
 * Stateless compute panel, same shape as the shift-prediction panel: numbers
 * in, a determination out, nothing persisted. It sits next to the region
 * integrals because purity is what an analyst computes *from* the integrals
 * they have just reviewed — but it takes its inputs by hand, so it is usable
 * with integrals from any source and never gates on the GSD chain.
 *
 * The three things that make this a determination rather than a calculator:
 * the purity is never rendered without its combined standard uncertainty, the
 * intermediates that built it are always available, and the engine's warnings
 * (e.g. a purity above 100 %, meaning the inputs are wrong) are shown before
 * the figure rather than under it.
 */

type QnmrInternalStandardRequest = components["schemas"]["QnmrInternalStandardRequest"]
type QnmrPulconRequest = components["schemas"]["QnmrPulconRequest"]
type QnmrPurityResult = components["schemas"]["QnmrPurityResult"]

type Method = "internal_standard" | "pulcon"

type PurityState =
  | { status: "idle"; result: null; error: null }
  | { status: "loading"; result: null; error: null }
  | { status: "ready"; result: QnmrPurityResult; error: null }
  | { status: "error"; result: null; error: string }

/** One numeric field, keyed by its canonical wire name. */
type FieldSpec = {
  key: string
  label: string
  /** Shown after the input; also appended to the value in the derivation table. */
  unit?: string
  integer?: boolean
  step?: string
  /**
   * Server-side default, mirrored from the generated schema. Shown as the
   * placeholder so leaving the field alone is visibly a choice, not an
   * omission. Fields without one are required.
   */
  defaultValue?: string
  hint?: string
}

// ── Internal standard — the routine determination ──────────────────────
const IS_ANALYTE_FIELDS: FieldSpec[] = [
  { key: "analyte_integral", label: "Integral", step: "any", hint: "Area of the integrated analyte resonance." },
  { key: "analyte_protons", label: "Protons (N)", integer: true, step: "1", hint: "How many protons give rise to that resonance." },
  { key: "analyte_molar_mass", label: "Molar mass", unit: "g/mol", step: "any", hint: "Average molar mass — qNMR weighs macroscopic samples." },
  { key: "analyte_mass_mg", label: "Mass weighed", unit: "mg", step: "any" },
]

const IS_STANDARD_FIELDS: FieldSpec[] = [
  { key: "standard_integral", label: "Integral", step: "any", hint: "Area of the integrated standard resonance." },
  { key: "standard_protons", label: "Protons (N)", integer: true, step: "1", hint: "How many protons give rise to that resonance." },
  { key: "standard_molar_mass", label: "Molar mass", unit: "g/mol", step: "any" },
  { key: "standard_mass_mg", label: "Mass weighed", unit: "mg", step: "any" },
]

const IS_PURITY_FIELD: FieldSpec = {
  key: "standard_purity_percent",
  label: "Certified standard purity",
  unit: "%",
  step: "any",
  defaultValue: "100",
  hint: "Certified mass-fraction purity of the reference material.",
}

const IS_UNCERTAINTY_FIELDS: FieldSpec[] = [
  { key: "integral_rel_u", label: "Integral", step: "any" },
  { key: "mass_rel_u", label: "Weighing", step: "any" },
  { key: "standard_purity_rel_u", label: "Standard purity", step: "any" },
  { key: "molar_mass_rel_u", label: "Molar mass", step: "any" },
]

// ── PULCON — external reference ────────────────────────────────────────
const PULCON_ANALYTE_FIELDS: FieldSpec[] = [
  { key: "analyte_integral", label: "Integral", step: "any" },
  { key: "analyte_protons", label: "Protons (N)", integer: true, step: "1" },
  {
    key: "analyte_nominal_concentration",
    label: "Nominal concentration",
    step: "any",
    hint: "The concentration the weighed analyte would give if it were 100 % pure. Same units as the reference.",
  },
]

const PULCON_REFERENCE_FIELDS: FieldSpec[] = [
  { key: "reference_integral", label: "Integral", step: "any" },
  { key: "reference_protons", label: "Protons (N)", integer: true, step: "1" },
  { key: "reference_concentration", label: "Concentration", step: "any", hint: "Same units as the analyte's nominal concentration." },
]

const PULCON_PURITY_FIELD: FieldSpec = {
  key: "reference_purity_percent",
  label: "Certified reference purity",
  unit: "%",
  step: "any",
  defaultValue: "100",
}

/**
 * Acquisition terms. Each ratio cancels when the two sides match, which is why
 * they sit behind a disclosure with their defaults filled in — a user who
 * leaves them alone gets a correct ratio-based answer.
 */
const PULCON_ACQUISITION_FIELDS: FieldSpec[] = [
  { key: "analyte_pulse_width_us", label: "Analyte 90° pulse width", unit: "µs", step: "any", defaultValue: "1" },
  { key: "reference_pulse_width_us", label: "Reference 90° pulse width", unit: "µs", step: "any", defaultValue: "1" },
  { key: "analyte_temperature_k", label: "Analyte temperature", unit: "K", step: "any", defaultValue: "298.15" },
  { key: "reference_temperature_k", label: "Reference temperature", unit: "K", step: "any", defaultValue: "298.15" },
  { key: "analyte_receiver_gain", label: "Analyte receiver gain", step: "any", defaultValue: "1" },
  { key: "reference_receiver_gain", label: "Reference receiver gain", step: "any", defaultValue: "1" },
  { key: "analyte_scans", label: "Analyte scans", integer: true, step: "1", defaultValue: "1" },
  { key: "reference_scans", label: "Reference scans", integer: true, step: "1", defaultValue: "1" },
]

const PULCON_UNCERTAINTY_FIELDS: FieldSpec[] = [
  { key: "integral_rel_u", label: "Integral", step: "any" },
  { key: "pulse_width_rel_u", label: "Pulse width", step: "any" },
  { key: "concentration_rel_u", label: "Concentration", step: "any" },
  { key: "reference_purity_rel_u", label: "Reference purity", step: "any" },
]

/** Required keys per method — every one must be a finite number above zero. */
const REQUIRED_KEYS: Record<Method, string[]> = {
  internal_standard: [...IS_ANALYTE_FIELDS, ...IS_STANDARD_FIELDS].map((f) => f.key),
  pulcon: [...PULCON_ANALYTE_FIELDS, ...PULCON_REFERENCE_FIELDS].map((f) => f.key),
}

// ── Display labels for the derivation record ───────────────────────────
// Humanised for reading; the canonical key stays visible underneath so a
// reviewer can tie each term back to the record it came from.
const TERM_LABELS: Record<string, string> = {
  analyte_integral: "Analyte integral",
  standard_integral: "Standard integral",
  analyte_protons: "Analyte protons",
  standard_protons: "Standard protons",
  analyte_molar_mass: "Analyte molar mass",
  standard_molar_mass: "Standard molar mass",
  analyte_mass_mg: "Analyte mass weighed",
  standard_mass_mg: "Standard mass weighed",
  standard_purity_percent: "Certified standard purity",
  analyte_nominal_concentration: "Analyte nominal concentration",
  reference_integral: "Reference integral",
  reference_protons: "Reference protons",
  reference_concentration: "Reference concentration",
  reference_purity_percent: "Certified reference purity",
  analyte_pulse_width_us: "Analyte 90° pulse width",
  reference_pulse_width_us: "Reference 90° pulse width",
  analyte_temperature_k: "Analyte temperature",
  reference_temperature_k: "Reference temperature",
  analyte_receiver_gain: "Analyte receiver gain",
  reference_receiver_gain: "Reference receiver gain",
  analyte_scans: "Analyte scans",
  reference_scans: "Reference scans",
  integral_rel_u: "Integral",
  mass_rel_u: "Weighing",
  standard_purity_rel_u: "Standard purity",
  molar_mass_rel_u: "Molar mass",
  pulse_width_rel_u: "Pulse width",
  concentration_rel_u: "Concentration",
  reference_purity_rel_u: "Reference purity",
  ratio_integral: "Integral ratio (analyte / standard)",
  ratio_protons: "Proton ratio (standard / analyte)",
  ratio_molar_mass: "Molar-mass ratio (analyte / standard)",
  ratio_mass: "Mass ratio (standard / analyte)",
  reference_concentration_true: "Reference true concentration",
  ratio_signal_per_spin: "Signal-per-spin ratio (analyte / reference)",
  ratio_pulse_width: "Pulse-width ratio (analyte / reference)",
  correction: "Acquisition correction",
  measured_concentration: "Measured concentration",
  nominal_concentration: "Nominal concentration",
}

const TERM_UNITS: Record<string, string> = {
  analyte_molar_mass: "g/mol",
  standard_molar_mass: "g/mol",
  analyte_mass_mg: "mg",
  standard_mass_mg: "mg",
  standard_purity_percent: "%",
  reference_purity_percent: "%",
  analyte_pulse_width_us: "µs",
  reference_pulse_width_us: "µs",
  analyte_temperature_k: "K",
  reference_temperature_k: "K",
}

const METHOD_LABEL: Record<string, string> = {
  internal_standard: "Internal standard",
  pulcon: "PULCON · external reference",
}

/** Fall back to a readable rendering of any term the engine adds later. */
function termLabel(key: string): string {
  const known = TERM_LABELS[key]
  if (known) return known
  const words = key.replace(/_/g, " ").trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** Blank means "untouched" — never coerced to 0, which would be a claim. */
function parseNumeric(raw: string | undefined): number | null {
  const trimmed = (raw ?? "").trim()
  if (!trimmed) return null
  const value = Number(trimmed)
  return Number.isFinite(value) ? value : null
}

function formatTermValue(value: unknown): string {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "—"
    if (value === 0) return "0"
    const magnitude = Math.abs(value)
    if (magnitude >= 1e-4 && magnitude < 1e7) return String(Number(value.toFixed(6)))
    return value.toExponential(4)
  }
  if (typeof value === "string") return value
  if (typeof value === "boolean") return value ? "yes" : "no"
  if (value == null) return "—"
  return JSON.stringify(value)
}

export type QnmrPurityPanelProps = {
  testId?: string
}

export function QnmrPurityPanel({ testId = "qnmr-purity-surface" }: QnmrPurityPanelProps) {
  const [method, setMethod] = useState<Method>("internal_standard")
  const [values, setValues] = useState<Record<string, string>>({})
  const [acquisitionOpen, setAcquisitionOpen] = useState(false)
  const [uncertaintyOpen, setUncertaintyOpen] = useState(false)
  const [derivationOpen, setDerivationOpen] = useState(false)
  const [state, setState] = useState<PurityState>({ status: "idle", result: null, error: null })

  const uncertaintyFields =
    method === "internal_standard" ? IS_UNCERTAINTY_FIELDS : PULCON_UNCERTAINTY_FIELDS

  const setField = (key: string, raw: string) => {
    setValues((prev) => ({ ...prev, [key]: raw }))
    // A changed input invalidates the determination on screen — never leave a
    // purity figure sitting next to the numbers that no longer produced it.
    setState((prev) => (prev.status === "idle" ? prev : { status: "idle", result: null, error: null }))
  }

  const switchMethod = (next: Method) => {
    if (next === method) return
    setMethod(next)
    setState({ status: "idle", result: null, error: null })
  }

  /** Required numbers that are still blank or not a positive number. */
  const missingRequired = useMemo(
    () => REQUIRED_KEYS[method].filter((key) => {
      const parsed = parseNumeric(values[key])
      return parsed === null || parsed <= 0
    }),
    [method, values],
  )
  const canCompute = missingRequired.length === 0

  /**
   * Build the request from the canonical wire keys only — both models are
   * ``extra="forbid"``, so an unrecognised key is a 422 rather than a
   * tolerated extra. Optional uncertainty terms are omitted when untouched:
   * sending 0 would claim perfect measurement.
   */
  const buildBody = (): QnmrInternalStandardRequest | QnmrPulconRequest | null => {
    const required: Record<string, number> = {}
    for (const key of REQUIRED_KEYS[method]) {
      const parsed = parseNumeric(values[key])
      if (parsed === null || parsed <= 0) return null
      required[key] = parsed
    }

    const optional: Record<string, number> = {}
    for (const field of uncertaintyFields) {
      const parsed = parseNumeric(values[field.key])
      if (parsed !== null && parsed >= 0) optional[field.key] = parsed
    }

    /** Defaulted terms fall back to the schema default when left alone. */
    const defaulted = (field: FieldSpec): number => {
      const parsed = parseNumeric(values[field.key])
      if (parsed !== null && parsed > 0) return parsed
      return Number(field.defaultValue)
    }

    if (method === "internal_standard") {
      const purity = parseNumeric(values[IS_PURITY_FIELD.key])
      return {
        analyte_integral: required.analyte_integral,
        standard_integral: required.standard_integral,
        analyte_protons: required.analyte_protons,
        standard_protons: required.standard_protons,
        analyte_molar_mass: required.analyte_molar_mass,
        standard_molar_mass: required.standard_molar_mass,
        analyte_mass_mg: required.analyte_mass_mg,
        standard_mass_mg: required.standard_mass_mg,
        standard_purity_percent:
          purity !== null && purity > 0 && purity <= 100 ? purity : Number(IS_PURITY_FIELD.defaultValue),
        ...optional,
      }
    }

    const referencePurity = parseNumeric(values[PULCON_PURITY_FIELD.key])
    const acquisition = Object.fromEntries(
      PULCON_ACQUISITION_FIELDS.map((field) => [field.key, defaulted(field)]),
    ) as Pick<
      QnmrPulconRequest,
      | "analyte_pulse_width_us"
      | "reference_pulse_width_us"
      | "analyte_temperature_k"
      | "reference_temperature_k"
      | "analyte_receiver_gain"
      | "reference_receiver_gain"
      | "analyte_scans"
      | "reference_scans"
    >
    return {
      analyte_integral: required.analyte_integral,
      analyte_protons: required.analyte_protons,
      analyte_nominal_concentration: required.analyte_nominal_concentration,
      reference_integral: required.reference_integral,
      reference_protons: required.reference_protons,
      reference_concentration: required.reference_concentration,
      reference_purity_percent:
        referencePurity !== null && referencePurity > 0 && referencePurity <= 100
          ? referencePurity
          : Number(PULCON_PURITY_FIELD.defaultValue),
      ...acquisition,
      ...optional,
    }
  }

  const runDetermination = () => {
    const body = buildBody()
    if (!body) return
    const path = method === "internal_standard" ? "/spectrum/qnmr/purity" : "/spectrum/qnmr/purity/pulcon"
    setState({ status: "loading", result: null, error: null })
    apiFetch<QnmrPurityResult>(path, { method: "POST", body })
      .then((result) => setState({ status: "ready", result, error: null }))
      .catch((err) =>
        setState({
          status: "error",
          result: null,
          error: formatApiError(err, "Purity determination failed"),
        }),
      )
  }

  const result = state.status === "ready" ? state.result : null
  const warnings = result?.warnings ?? []
  const notes = result?.notes ?? []
  const inputEntries = Object.entries(result?.inputs ?? {})
  const measuredEntries = inputEntries.filter(([key]) => !key.endsWith("_rel_u"))
  const uncertaintyEntries = inputEntries.filter(([key]) => key.endsWith("_rel_u"))
  const intermediateEntries = Object.entries(result?.intermediates ?? {})

  return (
    <div className="min-w-0" data-testid={testId}>
      <ModuleCard
        accent="teal"
        eyebrow="qNMR · Purity determination"
        title="Mass-fraction purity"
        icon={Scale}
        description="Quantitative NMR purity against a weighed internal standard, or against an external reference by PULCON. Every result carries its combined standard uncertainty and the ratios that produced it."
        className="min-w-0 overflow-visible shadow-none"
      >
        <div className="space-y-4">
          {/* Method */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
              Method
            </span>
            <div
              role="radiogroup"
              aria-label="Purity determination method"
              className="inline-flex overflow-hidden rounded-md border bg-card"
            >
              {(
                [
                  ["internal_standard", "Internal standard", "A certified standard weighed into the same solution and integrated from the same spectrum. The routine determination."],
                  ["pulcon", "PULCON", "An external reference measured separately — for when the standard cannot be co-dissolved with the analyte."],
                ] as const
              ).map(([value, label, hint], idx) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={method === value}
                  onClick={() => switchMethod(value)}
                  title={hint}
                  className={cn(
                    "px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors",
                    idx > 0 ? "border-l" : "",
                    method === value ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted/40",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Inputs */}
          {method === "internal_standard" ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <FieldGroup title="Analyte" fields={IS_ANALYTE_FIELDS} values={values} onChange={setField} />
              <FieldGroup title="Internal standard" fields={IS_STANDARD_FIELDS} values={values} onChange={setField} />
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <FieldGroup title="Analyte" fields={PULCON_ANALYTE_FIELDS} values={values} onChange={setField} />
              <FieldGroup title="External reference" fields={PULCON_REFERENCE_FIELDS} values={values} onChange={setField} />
            </div>
          )}

          <div className="sm:max-w-xs">
            <NumberField
              field={method === "internal_standard" ? IS_PURITY_FIELD : PULCON_PURITY_FIELD}
              value={values[method === "internal_standard" ? IS_PURITY_FIELD.key : PULCON_PURITY_FIELD.key] ?? ""}
              onChange={setField}
            />
          </div>

          {/* Acquisition terms — PULCON only, defaulted, behind a disclosure. */}
          {method === "pulcon" ? (
            <Disclosure
              open={acquisitionOpen}
              onOpenChange={setAcquisitionOpen}
              label="Acquisition conditions"
              hint="Each term cancels when both sides match — leave them alone for a ratio-based answer."
            >
              <div className="grid gap-3 sm:grid-cols-2">
                {PULCON_ACQUISITION_FIELDS.map((field) => (
                  <NumberField
                    key={field.key}
                    field={field}
                    value={values[field.key] ?? ""}
                    onChange={setField}
                  />
                ))}
              </div>
            </Disclosure>
          ) : null}

          {/* Uncertainty inputs — this is what makes the figure the lab's own. */}
          <Disclosure
            open={uncertaintyOpen}
            onOpenChange={setUncertaintyOpen}
            label="Uncertainty inputs"
            hint="Relative (1σ) uncertainties from your own metrology. Leave blank to use the engine's conservative defaults."
          >
            <div className="grid gap-3 sm:grid-cols-2">
              {uncertaintyFields.map((field) => (
                <NumberField
                  key={field.key}
                  field={field}
                  value={values[field.key] ?? ""}
                  onChange={setField}
                  placeholder="engine default"
                  idPrefix="uncertainty"
                  nameSuffix="relative uncertainty"
                />
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-snug text-muted-foreground">
              These are relative, dimensionless values — 0.01 means 1 %. Supplying them is what turns
              the reported uncertainty from the engine&rsquo;s estimate into your laboratory&rsquo;s
              estimate. A blank field is not zero: leaving it alone keeps the conservative default,
              whereas entering 0 claims perfect measurement.
            </p>
          </Disclosure>

          {/* Run */}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              size="sm"
              className="gap-1.5"
              onClick={runDetermination}
              disabled={!canCompute || state.status === "loading"}
            >
              {state.status === "loading" ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                  Determining…
                </>
              ) : (
                <>
                  <Sigma className="h-3.5 w-3.5" aria-hidden />
                  Determine purity
                </>
              )}
            </Button>
            {!canCompute ? (
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                {missingRequired.length} value{missingRequired.length === 1 ? "" : "s"} still needed ·{" "}
                {missingRequired.map((key) => termLabel(key).toLowerCase()).join(", ")}
              </span>
            ) : null}
          </div>

          {state.status === "error" ? (
            <AlertCard variant="error" title="Purity determination failed" description={state.error} />
          ) : null}

          {state.status === "idle" ? (
            <p className="text-sm text-muted-foreground">
              Enter the integrals, proton counts, molar masses, and weighed masses, then run the
              determination. The result is a mass-fraction purity with a combined standard
              uncertainty — it is only as good as the integration and weighing behind it.
            </p>
          ) : null}

          {result ? (
            <div className="space-y-4" data-testid="qnmr-purity-result">
              {/* Warnings first — a purity above 100 % means the inputs are wrong. */}
              {warnings.map((warning, idx) => (
                <AlertCard
                  key={`qnmr-warning-${idx}`}
                  variant="warning"
                  title="Check the inputs"
                  description={warning}
                />
              ))}

              <PurityFigure result={result} />

              <Disclosure
                open={derivationOpen}
                onOpenChange={setDerivationOpen}
                label="Derivation"
                hint="Every ratio that built the figure, so it can be re-derived from this record alone."
              >
                <div className="space-y-4">
                  <TermTable title="Intermediate ratios" entries={intermediateEntries} />
                  <TermTable title="Inputs as received" entries={measuredEntries} />
                  <TermTable
                    title="Uncertainty budget applied"
                    entries={uncertaintyEntries}
                    caption="Relative (1σ) values used in the propagation — the engine's defaults where you supplied none."
                  />
                </div>
              </Disclosure>

              {notes.length > 0 ? (
                <div className="rounded-md border border-dashed bg-muted/20 px-3 py-2.5">
                  <ul className="space-y-1.5">
                    {notes.map((note, idx) => (
                      <li key={`qnmr-note-${idx}`} className="text-[11px] leading-snug text-muted-foreground">
                        {note}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                This determination is not stored — capture it in your record before leaving the page.
              </p>
            </div>
          ) : null}
        </div>
      </ModuleCard>
    </div>
  )
}

/**
 * The figure and its uncertainty, rendered as one unit. A purity without its
 * uncertainty is exactly the unfalsifiable number this module exists to
 * replace, so an uncertainty the engine could not produce is stated as missing
 * rather than quietly dropped.
 */
function PurityFigure({ result }: { result: QnmrPurityResult }) {
  const purity = result.purity_percent
  const uncertainty = result.uncertainty_percent
  const relative = result.relative_uncertainty
  const hasUncertainty = Number.isFinite(uncertainty)
  const hasRelative = Number.isFinite(relative)
  const methodLabel = METHOD_LABEL[result.method] ?? result.method

  return (
    <div
      className="rounded-xl border px-4 py-3.5"
      style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          Mass-fraction purity
        </p>
        <span
          className="inline-flex items-center rounded-full border bg-card px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground"
          title={`Determination method: ${methodLabel}`}
        >
          {methodLabel}
        </span>
      </div>
      <p
        className="mt-1 font-mono text-3xl font-bold leading-none tabular-nums"
        style={{ color: "var(--mt-teal-ink)" }}
        data-testid="qnmr-purity-figure"
      >
        {Number.isFinite(purity) ? purity.toFixed(2) : "—"}
        <span className="text-2xl"> ± {hasUncertainty ? uncertainty.toFixed(2) : "unavailable"} %</span>
      </p>
      <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
        {hasUncertainty ? (
          <>
            Combined standard uncertainty at k&nbsp;=&nbsp;1
            {hasRelative ? ` · ${(relative * 100).toFixed(2)} % relative` : null}.
          </>
        ) : (
          <>
            The combined standard uncertainty could not be computed for this result — the purity
            figure alone is not a determination.
          </>
        )}
      </p>
    </div>
  )
}

/** A labelled column of numeric fields (Analyte / Standard / Reference). */
function FieldGroup({
  title,
  fields,
  values,
  onChange,
}: {
  title: string
  fields: FieldSpec[]
  values: Record<string, string>
  onChange: (key: string, raw: string) => void
}) {
  return (
    <div className="rounded-md border bg-muted/10 p-3">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
        {title}
      </p>
      <div className="mt-3 space-y-3">
        {fields.map((field) => (
          <NumberField
            key={field.key}
            field={field}
            value={values[field.key] ?? ""}
            onChange={onChange}
            idPrefix={title}
            groupLabel={title}
          />
        ))}
      </div>
    </div>
  )
}

function NumberField({
  field,
  value,
  onChange,
  placeholder,
  idPrefix = "qnmr",
  groupLabel,
  nameSuffix,
}: {
  field: FieldSpec
  value: string
  onChange: (key: string, raw: string) => void
  placeholder?: string
  idPrefix?: string
  /**
   * Column the field belongs to. Folded into the accessible name because the
   * visible label alone ("Integral") is the same on both sides of the
   * determination — the group is what distinguishes them.
   */
  groupLabel?: string
  /** Same purpose, for fields whose group is a disclosure rather than a column. */
  nameSuffix?: string
}) {
  const inputId = `qnmr-${idPrefix.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${field.key}`
  const accessibleName = [groupLabel, field.label, field.unit ? `(${field.unit})` : null, nameSuffix]
    .filter(Boolean)
    .join(" ")
  return (
    <div className="space-y-1">
      <Label htmlFor={inputId} className="text-[11px] font-medium text-muted-foreground">
        {field.label}
        {field.unit ? <span className="ml-1 font-mono text-[10px] text-muted-foreground/70">({field.unit})</span> : null}
      </Label>
      <Input
        id={inputId}
        type="number"
        inputMode="decimal"
        step={field.step ?? "any"}
        min={0}
        value={value}
        aria-label={accessibleName}
        placeholder={placeholder ?? field.defaultValue ?? ""}
        title={field.hint}
        onChange={(e) => onChange(field.key, e.target.value)}
        className="h-8 font-mono text-xs"
      />
      {field.hint ? (
        <p className="text-[10px] leading-snug text-muted-foreground/80">{field.hint}</p>
      ) : null}
    </div>
  )
}

function Disclosure({
  open,
  onOpenChange,
  label,
  hint,
  children,
}: {
  open: boolean
  onOpenChange: (next: boolean) => void
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <Collapsible open={open} onOpenChange={onOpenChange}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex w-full items-center justify-between rounded-md border border-dashed px-3 py-2 text-left transition-colors hover:bg-muted/30"
        >
          <span className="min-w-0">
            <span className="block font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
              {label}
            </span>
            {hint ? <span className="mt-0.5 block text-[11px] text-muted-foreground/80">{hint}</span> : null}
          </span>
          <ChevronDown
            className={cn("ml-3 h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
            aria-hidden
          />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-3">{children}</CollapsibleContent>
    </Collapsible>
  )
}

/** Name / value rows of the derivation record. */
function TermTable({
  title,
  entries,
  caption,
}: {
  title: string
  entries: [string, unknown][]
  caption?: string
}) {
  if (entries.length === 0) return null
  return (
    <div>
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
        {title}
      </p>
      {caption ? <p className="mt-0.5 text-[10px] text-muted-foreground/80">{caption}</p> : null}
      <div className="mt-2 overflow-x-auto rounded-md border">
        <table className="w-full text-left text-xs">
          <tbody className="tabular-nums">
            {entries.map(([key, value]) => (
              <tr key={key} className="border-t first:border-t-0 hover:bg-muted/20">
                <td className="px-3 py-1.5">
                  <span className="block">{termLabel(key)}</span>
                  <span className="block font-mono text-[10px] text-muted-foreground/70">{key}</span>
                </td>
                <td className="px-3 py-1.5 text-right font-mono">
                  {formatTermValue(value)}
                  {TERM_UNITS[key] ? (
                    <span className="ml-1 text-[10px] text-muted-foreground">{TERM_UNITS[key]}</span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
