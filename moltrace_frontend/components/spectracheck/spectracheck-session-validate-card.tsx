"use client"

import { useMemo, useState } from "react"
import { CheckCircle2, ShieldCheck, XCircle, AlertTriangle, Loader2 } from "lucide-react"

import { apiFetch } from "@/lib/api/client"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import { extractFirstSmiles, formatApiError } from "@/components/spectracheck/spectracheck-helpers"

/**
 * Optional pre-flight check for the SpectraCheck session card.
 *
 * Calls the existing ``POST /analyze/validate`` endpoint, which:
 *   - parses the first SMILES from ``candidatesText`` (if any),
 *   - parses ``protonText`` as 1H NMR literature text (if any),
 *   - cross-checks the two when both are supplied (proton-count + visible-H
 *     match per :func:`nmrcheck.analysis.validate_inputs`),
 *   - returns a structured ``ValidationReport`` with per-layer pass/fail
 *     booleans and lists of warnings + errors.
 *
 * Design rules (per product requirement):
 *  1. Validation is *informational only* — analysis tabs are never gated.
 *  2. Either SMILES alone OR 1H NMR text alone is a valid input mode; the
 *     missing layer produces a warning, not an error.
 *  3. Mismatch between SMILES and 1H NMR text surfaces as an explicit error
 *     (e.g. "Observed total H exceeds expected visible H by 4.0").
 *  4. The card highlights when textareas still hold the bundled example
 *     values so the user knows the validation may be running against demo
 *     data rather than their sample.
 */

export type ValidationReport = {
  sample_id: string | null
  solvent: string | null
  structure_valid: boolean
  nmr_text_valid: boolean
  structure_nmr_match: boolean
  analysis_ready: boolean
  parseable_peak_count: number
  expected_visible_h: number | null
  observed_total_h: number | null
  adjusted_observed_total_h: number | null
  delta_visible_h: number | null
  parsed_peaks: unknown[]
  structure: unknown | null
  warnings: string[]
  errors: string[]
}

type FieldStatus = "default" | "modified" | "empty"

function classifyField(current: string, defaultValue: string): FieldStatus {
  const trimmed = current.trim()
  if (!trimmed) return "empty"
  if (trimmed === defaultValue.trim()) return "default"
  return "modified"
}

const STATUS_STYLE: Record<FieldStatus, { label: string; bg: string; fg: string; border: string }> = {
  default: {
    label: "Example data",
    bg: "rgba(232, 160, 48, 0.12)",
    fg: "var(--mt-amber)",
    border: "var(--mt-amber)",
  },
  modified: {
    label: "Your data",
    bg: "var(--mt-teal-soft)",
    fg: "var(--mt-teal)",
    border: "var(--mt-teal)",
  },
  empty: {
    label: "Empty",
    bg: "transparent",
    fg: "var(--muted-foreground)",
    border: "var(--border)",
  },
}

function StatusPill({ status }: { status: FieldStatus }) {
  const style = STATUS_STYLE[status]
  return (
    <span
      data-testid={`session-field-status-${status}`}
      className="rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
      style={{
        borderColor: style.border,
        backgroundColor: style.bg,
        color: style.fg,
      }}
    >
      {style.label}
    </span>
  )
}

type Props = {
  sampleId: string
  solvent: string
  candidatesText: string
  protonText: string
  carbonText: string
  defaults: {
    candidates: string
    proton: string
    carbon: string
  }
}

export function SessionValidateCard({
  sampleId,
  solvent,
  candidatesText,
  protonText,
  carbonText,
  defaults,
}: Props) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ValidationReport | null>(null)
  const [networkError, setNetworkError] = useState("")

  const candidatesStatus = classifyField(candidatesText, defaults.candidates)
  const protonStatus = classifyField(protonText, defaults.proton)
  const carbonStatus = classifyField(carbonText, defaults.carbon)
  const anyModified =
    candidatesStatus === "modified" ||
    protonStatus === "modified" ||
    carbonStatus === "modified"
  const allDefault =
    candidatesStatus === "default" &&
    protonStatus === "default" &&
    carbonStatus === "default"

  // The validator accepts a single SMILES — we pick the first SMILES from
  // the candidates textarea (consistent with how predicted-NMR / 2D-NMR
  // tabs select a single structure from the shared candidates list).
  const candidateSmiles = useMemo(() => extractFirstSmiles(candidatesText), [candidatesText])

  const hasAnyInput = Boolean(candidateSmiles?.trim() || protonText.trim())

  async function runValidate() {
    setLoading(true)
    setNetworkError("")
    setResult(null)
    try {
      const payload = {
        sample_id: sampleId.trim() || null,
        smiles: candidateSmiles?.trim() || null,
        nmr_text: protonText.trim() || null,
        solvent: solvent.trim() || null,
      }
      const report = await apiFetch<ValidationReport>("/analyze/validate", {
        method: "POST",
        body: payload,
      })
      setResult(report)
    } catch (err) {
      setNetworkError(formatApiError(err, "Validation request failed"))
    } finally {
      setLoading(false)
    }
  }

  return (
    <ModuleCard
      accent="teal"
      eyebrow="Session · Step 4 · Validate"
      title="Validate session inputs (optional)"
      icon={ShieldCheck}
      description="Optional pre-flight check. Confirms the SMILES, 1H NMR text, and (when both are supplied) that they agree before you upload spectra. Analysis still works without running validate, and with only one of SMILES or 1H NMR text."
      className="min-w-0"
    >
      <div className="space-y-4" data-testid="session-validate-card">
        {/* Default-vs-modified summary */}
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-dashed bg-muted/20 px-3 py-2 text-[11px]">
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            Inputs
          </span>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-muted-foreground">Candidates:</span>
            <StatusPill status={candidatesStatus} />
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-muted-foreground">1H text:</span>
            <StatusPill status={protonStatus} />
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-muted-foreground">13C text:</span>
            <StatusPill status={carbonStatus} />
          </div>
        </div>

        {/* Hint when defaults are still in place */}
        {allDefault ? (
          <div
            className="rounded-md border px-3 py-2 text-[11px]"
            data-testid="session-validate-default-hint"
            style={{ borderColor: "var(--mt-amber)", backgroundColor: "rgba(232, 160, 48, 0.10)" }}
          >
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--mt-amber)" }}>
              Heads up
            </p>
            <p className="mt-1 text-muted-foreground">
              All three textareas still hold the bundled example values
              (methanol / ethanol / propanol). Replace them with your
              sample&apos;s data — validation here would only confirm the
              example, not your sample.
            </p>
          </div>
        ) : null}

        {/* Validate action row */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[11px] text-muted-foreground">
            {anyModified
              ? "Click Validate to cross-check your structure against your 1H NMR text."
              : "You can still validate the example data, or modify the inputs above to validate your own."}
          </p>
          <Button
            type="button"
            onClick={runValidate}
            disabled={loading}
            data-testid="session-validate-button"
            className="font-mono text-xs"
          >
            {loading ? (
              <>
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" aria-hidden />
                Validating…
              </>
            ) : (
              <>
                <ShieldCheck className="mr-1 h-3.5 w-3.5" aria-hidden />
                Validate inputs
              </>
            )}
          </Button>
        </div>

        {/* Network / unexpected error */}
        {networkError ? (
          <div
            className="rounded-md border px-3 py-2 text-[11px]"
            data-testid="session-validate-network-error"
            style={{ borderColor: "var(--mt-red)", backgroundColor: "var(--mt-red-soft)" }}
          >
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--mt-red)" }}>
              Could not reach validator
            </p>
            <p className="mt-1 text-muted-foreground">{networkError}</p>
          </div>
        ) : null}

        {/* Result block */}
        {result ? <ValidationResultPanel report={result} hasAnyInput={hasAnyInput} /> : null}
      </div>
    </ModuleCard>
  )
}

function ValidationResultPanel({
  report,
  hasAnyInput,
}: {
  report: ValidationReport
  hasAnyInput: boolean
}) {
  const overallPassed = report.analysis_ready
  const overallFailed = report.errors.length > 0
  // "Partial" = one layer present, other absent. We surface this as info, not
  // error, because the product spec allows analysis with only one of SMILES /
  // 1H text.
  const isPartial =
    !overallPassed &&
    !overallFailed &&
    (report.structure_valid !== report.nmr_text_valid)
  // "Idle" = the user clicked Validate without providing any input at all.
  const isEmpty = !report.structure_valid && !report.nmr_text_valid && !hasAnyInput

  const tone = overallFailed
    ? { color: "var(--mt-red)", bg: "var(--mt-red-soft)", label: "Validation failed", Icon: XCircle }
    : overallPassed
      ? { color: "var(--mt-teal)", bg: "var(--mt-teal-soft)", label: "Validation passed — analysis ready", Icon: CheckCircle2 }
      : isPartial
        ? {
            color: "var(--mt-amber)",
            bg: "rgba(232, 160, 48, 0.10)",
            label: "Partial inputs — you can still proceed",
            Icon: AlertTriangle,
          }
        : isEmpty
          ? {
              color: "var(--mt-amber)",
              bg: "rgba(232, 160, 48, 0.10)",
              label: "No inputs supplied — nothing to validate",
              Icon: AlertTriangle,
            }
          : {
              color: "var(--mt-amber)",
              bg: "rgba(232, 160, 48, 0.10)",
              label: "Validation completed with warnings",
              Icon: AlertTriangle,
            }

  return (
    <div
      data-testid="session-validate-result"
      data-state={overallPassed ? "passed" : overallFailed ? "failed" : isPartial ? "partial" : "warning"}
      className="space-y-3 rounded-md border px-3 py-3"
      style={{ borderColor: tone.color, backgroundColor: tone.bg }}
    >
      <p
        className="flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.18em]"
        style={{ color: tone.color }}
      >
        <tone.Icon className="h-3.5 w-3.5" aria-hidden />
        {tone.label}
      </p>

      {/* Per-layer status chips */}
      <div className="flex flex-wrap gap-1.5">
        <LayerChip
          label="Structure (SMILES)"
          state={report.structure_valid ? "ok" : "missing"}
          testId="structure-chip"
        />
        <LayerChip
          label="1H NMR text"
          state={report.nmr_text_valid ? "ok" : "missing"}
          testId="nmr-text-chip"
        />
        <LayerChip
          label="Structure ↔ NMR match"
          state={
            !report.structure_valid || !report.nmr_text_valid
              ? "na"
              : report.structure_nmr_match
                ? "ok"
                : "fail"
          }
          testId="match-chip"
        />
      </div>

      {/* Quantitative summary when both layers are present */}
      {report.structure_valid && report.nmr_text_valid ? (
        <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-[11px] text-muted-foreground sm:grid-cols-2">
          <div className="flex justify-between">
            <dt>Expected visible H</dt>
            <dd className="font-mono font-bold text-foreground">
              {report.expected_visible_h ?? "—"}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt>Observed total H</dt>
            <dd className="font-mono font-bold text-foreground">
              {report.observed_total_h ?? "—"}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt>Adjusted observed H</dt>
            <dd className="font-mono font-bold text-foreground">
              {report.adjusted_observed_total_h ?? "—"}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt>Δ visible H</dt>
            <dd
              className="font-mono font-bold"
              style={{
                color:
                  report.delta_visible_h !== null && Math.abs(report.delta_visible_h) >= 1.0
                    ? "var(--mt-amber)"
                    : undefined,
              }}
            >
              {report.delta_visible_h !== null && report.delta_visible_h !== undefined
                ? report.delta_visible_h > 0
                  ? `+${report.delta_visible_h}`
                  : `${report.delta_visible_h}`
                : "—"}
            </dd>
          </div>
        </dl>
      ) : null}

      {report.errors.length > 0 ? (
        <div className="space-y-1" data-testid="session-validate-errors">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--mt-red)" }}>
            Errors
          </p>
          <ul className="list-inside list-disc space-y-0.5 text-[11px] text-foreground">
            {report.errors.map((err, idx) => (
              <li key={idx}>{err}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {report.warnings.length > 0 ? (
        <div className="space-y-1" data-testid="session-validate-warnings">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
            style={{ color: "var(--mt-amber)" }}
          >
            Warnings
          </p>
          <ul className="list-inside list-disc space-y-0.5 text-[11px] text-muted-foreground">
            {report.warnings.map((warn, idx) => (
              <li key={idx}>{warn}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="pt-1 text-[10px] text-muted-foreground">
        Validation is informational — you can still upload spectra and run
        analysis below regardless of this status.
      </p>
    </div>
  )
}

function LayerChip({
  label,
  state,
  testId,
}: {
  label: string
  state: "ok" | "fail" | "missing" | "na"
  testId: string
}) {
  const palette: Record<typeof state, { color: string; bg: string; prefix: string }> = {
    ok: { color: "var(--mt-teal)", bg: "var(--mt-teal-soft)", prefix: "✓" },
    fail: { color: "var(--mt-red)", bg: "var(--mt-red-soft)", prefix: "✗" },
    missing: { color: "var(--muted-foreground)", bg: "transparent", prefix: "–" },
    na: { color: "var(--muted-foreground)", bg: "transparent", prefix: "·" },
  }
  const tone = palette[state]
  return (
    <span
      data-testid={testId}
      data-state={state}
      className="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
      style={{ borderColor: tone.color, color: tone.color, backgroundColor: tone.bg }}
    >
      <span>{tone.prefix}</span>
      <span>{label}</span>
    </span>
  )
}
