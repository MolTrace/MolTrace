"use client"

import { useEffect, useMemo, useState } from "react"
import { Ban, Loader2, Plus, Ruler, Sigma, X } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { useGsdMultipletAnalysis } from "@/components/spectracheck/gsd-multiplet-panel"
import type { components } from "@/src/lib/api/schema"

// ── Region-source types + helpers ──────────────────────────────────────
type RegionSource = "multiplets" | "custom"
type CustomRegion = { id: number; from: string; to: string }

/** Backend caps regions at 256; mirror it client-side so we never POST an invalid set. */
const MAX_REGIONS = 256

/**
 * Parse the custom-region editor rows into validated [from,to] ppm pairs.
 * Drops rows that aren't two finite numbers or that are zero-width;
 * orders each pair high→low is left to the backend (it's order-insensitive),
 * but we keep the user's entry order. Caps at MAX_REGIONS.
 */
function parseCustomRegions(rows: CustomRegion[]): [number, number][] {
  const out: [number, number][] = []
  for (const row of rows) {
    const a = Number.parseFloat(row.from)
    const b = Number.parseFloat(row.to)
    if (!Number.isFinite(a) || !Number.isFinite(b)) continue
    if (a === b) continue
    out.push([a, b])
    if (out.length >= MAX_REGIONS) break
  }
  return out
}

/**
 * Region integration (Prompt 5 / `integration_prompt5`) — Step 3e,
 * chained off GSD peaks + the detected multiplet ranges.
 *
 * Canonical NMR workflow: integrate each detected multiplet region to
 * recover the relative proton-count ratio. Regions are auto-derived
 * from the multiplet pass's `range_ppm` (no arbitrary region picking),
 * so this is a clean auto-chain rather than a manual-region UX. The
 * `edited_sum` default method uses each peak's `category` to exclude
 * solvent / impurity / artifact contamination from each window.
 *
 * Reuses the WeakMap-cached `useGsdMultipletAnalysis` hook so the
 * `/spectrum/analyze/multiplets` POST fires once across the multiplet,
 * J-coupling, and integration panels.
 */

export type SpectrumGSDAnalyzeResult = components["schemas"]["SpectrumGSDAnalyzeResult"]
export type SpectrumIntegrationAnalyzeRequest =
  components["schemas"]["SpectrumIntegrationAnalyzeRequest"]
export type SpectrumIntegrationAnalyzeResult =
  components["schemas"]["SpectrumIntegrationAnalyzeResult"]
export type RegionIntegrationResult = components["schemas"]["RegionIntegrationResult"]
type IntegrationMethod = SpectrumIntegrationAnalyzeRequest["method"]

const METHOD_LABEL: Record<IntegrationMethod, string> = {
  edited_sum: "Edited sum",
  sum: "Raw sum",
  peaks: "Peak fit",
}
const METHOD_HINT: Record<IntegrationMethod, string> = {
  edited_sum:
    "Sum the window but use peak categories to exclude solvent / impurity / artifact contamination. The recommended default.",
  sum: "Integrate everything in the window (peak list ignored). Closest to a raw manual integral.",
  peaks: "Integrate only the fitted compound peaks inside the window.",
}

type Trace = { x: number[]; y: number[] }

type IntegrationState =
  | { status: "idle"; result: null; error: null }
  | { status: "loading"; result: null; error: null }
  | { status: "ready"; result: SpectrumIntegrationAnalyzeResult; error: null }
  | { status: "error"; result: null; error: string }

function useIntegration(
  gsdResult: SpectrumGSDAnalyzeResult | null,
  trace: Trace | null,
  regions: [number, number][],
  method: IntegrationMethod,
  nucleus: "1H" | "13C",
  solvent: string,
  fieldMhz: number,
): IntegrationState {
  const [state, setState] = useState<IntegrationState>({ status: "idle", result: null, error: null })

  // Serialise the region set so the effect re-fires only when the
  // actual windows change — regardless of whether they came from the
  // detected multiplets or the user's custom inputs.
  const regionsKey = useMemo(
    () => regions.map((r) => `${r[0].toFixed(4)}-${r[1].toFixed(4)}`).join("|"),
    [regions],
  )

  useEffect(() => {
    if (!gsdResult || !trace || trace.x.length < 2) {
      setState({ status: "idle", result: null, error: null })
      return
    }
    if (regions.length === 0) {
      setState({ status: "idle", result: null, error: null })
      return
    }
    let cancelled = false
    setState({ status: "loading", result: null, error: null })
    const body: SpectrumIntegrationAnalyzeRequest = {
      ppm_axis: trace.x,
      intensity: trace.y,
      peaks: gsdResult.peaks,
      regions,
      method,
      nucleus,
      solvent: solvent.trim(),
      field_mhz: fieldMhz,
    }
    apiFetch<SpectrumIntegrationAnalyzeResult>("/spectrum/analyze/integration", {
      method: "POST",
      body,
    })
      .then((result) => {
        if (cancelled) return
        setState({ status: "ready", result, error: null })
      })
      .catch((err) => {
        if (cancelled) return
        setState({ status: "error", result: null, error: formatApiError(err, "Region integration failed") })
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gsdResult, trace, regionsKey, method, nucleus, solvent, fieldMhz])

  return state
}

function formatRangePpm(range: [number, number]): string {
  const [lo, hi] = range[0] < range[1] ? range : [range[1], range[0]]
  return `${hi.toFixed(3)} – ${lo.toFixed(3)}`
}

/** Nearest-integer proton count hint for a relative ratio (1H only). */
function protonHint(relative: number): string | null {
  if (!Number.isFinite(relative) || relative <= 0) return null
  const nearest = Math.round(relative)
  if (nearest < 1) return null
  const drift = Math.abs(relative - nearest)
  // Only suggest an integer H count when the ratio is within 12% of it.
  if (drift / nearest > 0.12) return null
  return `≈ ${nearest} H`
}

export type GsdIntegrationPanelProps = {
  gsdResult: SpectrumGSDAnalyzeResult | null
  /** Spectrum trace (ppm + intensity) — the same xy the SpectrumViewer renders. */
  trace: Trace | null
  nucleus?: "1H" | "13C"
  solvent?: string
  fieldMhz?: number
  toleranceHz?: number
  testId?: string
}

export function GsdIntegrationPanel({
  gsdResult,
  trace,
  nucleus = "1H",
  solvent = "",
  fieldMhz = 500,
  toleranceHz = 0.5,
  testId = "gsd-integration-results-surface",
}: GsdIntegrationPanelProps) {
  const [method, setMethod] = useState<IntegrationMethod>("edited_sum")
  const [regionSource, setRegionSource] = useState<RegionSource>("multiplets")
  const [customRegions, setCustomRegions] = useState<CustomRegion[]>([{ id: 0, from: "", to: "" }])
  const multipletState = useGsdMultipletAnalysis(gsdResult, toleranceHz)

  // Multiplet-derived regions (auto source).
  const multipletRegions = useMemo<[number, number][]>(
    () =>
      multipletState.status === "ready"
        ? (multipletState.result.multiplets ?? []).map((m) => m.range_ppm)
        : [],
    [multipletState],
  )
  // Validated custom regions — only well-formed [from,to] pairs survive.
  const parsedCustomRegions = useMemo<[number, number][]>(
    () => parseCustomRegions(customRegions),
    [customRegions],
  )
  const effectiveRegions = regionSource === "multiplets" ? multipletRegions : parsedCustomRegions
  const state = useIntegration(gsdResult, trace, effectiveRegions, method, nucleus, solvent, fieldMhz)

  if (gsdResult == null) return null

  const controls = (
    <div className="space-y-2.5">
      {/* Region source + integration method */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          Regions
        </span>
        <div role="radiogroup" aria-label="Region source" className="inline-flex overflow-hidden rounded-md border bg-card">
          {(
            [
              ["multiplets", "Detected multiplets"],
              ["custom", "Custom"],
            ] as const
          ).map(([val, label], idx) => (
            <button
              key={val}
              type="button"
              role="radio"
              aria-checked={regionSource === val}
              onClick={() => setRegionSource(val)}
              title={
                val === "multiplets"
                  ? "Integrate each detected multiplet range — the canonical proton-ratio readout, zero clicks."
                  : "Integrate ppm windows you specify by hand."
              }
              className={cn(
                "px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors",
                idx > 0 ? "border-l" : "",
                regionSource === val ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted/40",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <span className="ml-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          Method
        </span>
        <div role="radiogroup" aria-label="Integration method" className="inline-flex overflow-hidden rounded-md border bg-card">
          {(["edited_sum", "sum", "peaks"] as const).map((m, idx) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={method === m}
              onClick={() => setMethod(m)}
              title={METHOD_HINT[m]}
              className={cn(
                "px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors",
                idx > 0 ? "border-l" : "",
                method === m ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted/40",
              )}
            >
              {METHOD_LABEL[m]}
            </button>
          ))}
        </div>
      </div>

      {/* Custom-region editor (only in custom mode) */}
      {regionSource === "custom" ? (
        <CustomRegionEditor regions={customRegions} onChange={setCustomRegions} validCount={parsedCustomRegions.length} />
      ) : null}
    </div>
  )

  // ── Region-source-aware gating ──────────────────────────────────────
  // Multiplet source: surface the multiplet pass's non-ready states.
  if (regionSource === "multiplets" && multipletState.status === "loading") {
    return (
      <Shell hint="Waiting for multiplet detection (the auto region source)…" testId={`${testId}-waiting`}>
        {controls}
        <div className="mt-4 flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Resolving multiplet regions…
        </div>
      </Shell>
    )
  }
  if (
    regionSource === "multiplets" &&
    multipletState.status === "ready" &&
    multipletRegions.length === 0
  ) {
    return (
      <Shell hint="No multiplets detected — switch to Custom regions or run GSD at a higher level." testId={`${testId}-empty`}>
        {controls}
        <p className="mt-4 text-sm text-muted-foreground">
          The auto source integrates detected multiplet ranges; none were found. Pick{" "}
          <strong className="text-foreground">Custom</strong> above to integrate ppm windows by hand,
          or re-run GSD at level 4–5 for finer structure.
        </p>
      </Shell>
    )
  }
  // Custom source with no valid windows yet.
  if (regionSource === "custom" && parsedCustomRegions.length === 0) {
    return (
      <Shell hint="Add at least one ppm window to integrate." testId={`${testId}-no-regions`}>
        {controls}
      </Shell>
    )
  }
  if (!trace || trace.x.length < 2) {
    return (
      <Shell hint="Spectrum trace unavailable — integration needs the ppm/intensity arrays." testId={`${testId}-no-trace`}>
        {controls}
        <p className="mt-4 text-sm text-muted-foreground">
          The integration endpoint integrates the displayed spectrum directly. Re-run preview /
          analyze so the trace is available.
        </p>
      </Shell>
    )
  }

  if (state.status === "loading") {
    return (
      <Shell hint="Integrating the selected regions…" testId={`${testId}-loading`}>
        {controls}
        <div className="mt-4 flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          POST /spectrum/analyze/integration…
        </div>
      </Shell>
    )
  }
  if (state.status === "error") {
    return (
      <Shell hint="Integration endpoint returned an error." testId={`${testId}-error`}>
        {controls}
        <div className="mt-4">
          <AlertCard variant="error" title="Region integration failed" description={state.error} />
        </div>
      </Shell>
    )
  }
  if (state.status !== "ready") return null

  const result = state.result
  const regions = result.regions ?? []

  return (
    <div className="min-w-0" data-testid={testId}>
      <ModuleCard
        accent="teal"
        eyebrow="Step 3e · Region integration"
        title="Region integrals"
        icon={Sigma}
        description={`Backend: ${result.backend} · ${result.region_count} region${
          result.region_count === 1 ? "" : "s"
        } (${regionSource === "multiplets" ? "detected multiplets" : "custom windows"}) integrated via ${METHOD_LABEL[result.method].toLowerCase()}. Relative values are normalised to the smallest region — the standard NMR ratio readout.`}
        className="min-w-0 overflow-visible shadow-none"
      >
        <div className="space-y-4">
          {controls}

          {(result.notes ?? []).length > 0
            ? (result.notes ?? []).map((note, idx) => (
                <AlertCard key={`int-note-${idx}`} variant="info" title="Integration note" description={note} />
              ))
            : null}

          {regions.length === 0 ? (
            <div className="rounded-md border border-dashed bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
              No region integrals returned.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-left text-xs">
                <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Region (ppm)</th>
                    <th className="px-3 py-2 text-right">Integral</th>
                    <th className="px-3 py-2 text-right">Relative</th>
                    <th className="px-3 py-2">Method</th>
                    <th className="px-3 py-2">Confidence</th>
                    <th className="px-3 py-2">Peaks</th>
                  </tr>
                </thead>
                <tbody className="font-mono tabular-nums">
                  {regions.map((r, idx) => {
                    const hint = nucleus === "1H" ? protonHint(r.relative_value) : null
                    const used = r.peaks_used_indices ?? []
                    const excl = r.excluded_peaks_indices ?? []
                    return (
                      <tr key={idx} className="border-t align-top hover:bg-muted/20">
                        <td className="px-3 py-2">{formatRangePpm(r.region_ppm)}</td>
                        <td className="px-3 py-2 text-right">{r.value.toExponential(2)}</td>
                        <td className="px-3 py-2 text-right">
                          <span className="font-bold" style={{ color: "var(--mt-teal-ink)" }}>
                            {r.relative_value.toFixed(2)}
                          </span>
                          {hint ? (
                            <span className="ml-1.5 text-[10px] text-muted-foreground">{hint}</span>
                          ) : null}
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className="inline-flex items-center rounded-full border bg-muted/40 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]"
                            title={`method_used: ${r.method_used}`}
                          >
                            {r.method_used}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <ConfidenceChip confidence={r.confidence} />
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-muted-foreground">{used.length} used</span>
                            {excl.length > 0 ? (
                              <span
                                className="inline-flex cursor-help items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em] text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300"
                                title={`Excluded peak indices ${excl.join(", ")} — removed as solvent / impurity / artifact contamination`}
                              >
                                <Ban className="h-2.5 w-2.5" aria-hidden />
                                {excl.length} excluded
                              </span>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            <Ruler className="mr-1 inline h-3 w-3" aria-hidden />
            Relative column is normalised to the smallest positive region · {nucleus} proton-ratio
            readout. Decision-support — verify against a manual integral before regulatory use.
          </p>
        </div>
      </ModuleCard>
    </div>
  )
}

function Shell({
  hint,
  testId,
  children,
}: {
  hint: string
  testId: string
  children: React.ReactNode
}) {
  return (
    <div className="min-w-0" data-testid={testId}>
      <ModuleCard
        accent="teal"
        eyebrow="Step 3e · Region integration"
        title="Region integrals"
        icon={Sigma}
        description={hint}
        className="min-w-0 overflow-visible shadow-none"
      >
        {children}
      </ModuleCard>
    </div>
  )
}

/** Confidence rendered as a color-graded pill (green ≥ 0.8, amber ≥ 0.5, rose else). */
function ConfidenceChip({ confidence }: { confidence: number }) {
  const pct = Math.round((Number.isFinite(confidence) ? confidence : 0) * 100)
  const tone =
    pct >= 80
      ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300"
      : pct >= 50
        ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300"
        : "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300"
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold tabular-nums",
        tone,
      )}
      title={`Integration confidence ${pct}%`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" aria-hidden />
      {pct}%
    </span>
  )
}

/**
 * Custom ppm-window editor — add / edit / remove integration regions by
 * hand. Each row is two ppm number inputs (from / to, order-insensitive).
 * Reports the count of valid windows so the parent can gate.
 */
function CustomRegionEditor({
  regions,
  onChange,
  validCount,
}: {
  regions: CustomRegion[]
  onChange: (next: CustomRegion[]) => void
  validCount: number
}) {
  const nextId = regions.reduce((max, r) => Math.max(max, r.id), -1) + 1
  const update = (id: number, patch: Partial<CustomRegion>) =>
    onChange(regions.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  const remove = (id: number) => onChange(regions.filter((r) => r.id !== id))
  const add = () => onChange([...regions, { id: nextId, from: "", to: "" }])
  const atCap = regions.length >= MAX_REGIONS
  return (
    <div className="rounded-md border border-dashed bg-muted/20 p-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          Custom ppm windows
        </span>
        <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
          {validCount} valid / {regions.length} row{regions.length === 1 ? "" : "s"}
        </span>
      </div>
      <div className="mt-3 space-y-2">
        {regions.map((row) => {
          const a = Number.parseFloat(row.from)
          const b = Number.parseFloat(row.to)
          const filled = row.from.trim() !== "" || row.to.trim() !== ""
          const invalid = filled && (!Number.isFinite(a) || !Number.isFinite(b) || a === b)
          return (
            <div key={row.id} className="flex flex-wrap items-center gap-2">
              <Input
                type="number"
                inputMode="decimal"
                step="0.01"
                aria-label="Region from (ppm)"
                placeholder="from ppm"
                value={row.from}
                onChange={(e) => update(row.id, { from: e.target.value })}
                className="h-8 w-28 font-mono text-xs"
              />
              <span className="font-mono text-xs text-muted-foreground">→</span>
              <Input
                type="number"
                inputMode="decimal"
                step="0.01"
                aria-label="Region to (ppm)"
                placeholder="to ppm"
                value={row.to}
                onChange={(e) => update(row.id, { to: e.target.value })}
                className="h-8 w-28 font-mono text-xs"
              />
              {invalid ? (
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-rose-600 dark:text-rose-400">
                  invalid pair
                </span>
              ) : null}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0 text-muted-foreground hover:text-rose-600"
                aria-label="Remove region"
                onClick={() => remove(row.id)}
                disabled={regions.length <= 1}
              >
                <X className="h-3.5 w-3.5" aria-hidden />
              </Button>
            </div>
          )
        })}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 gap-1.5 font-mono text-[11px]"
          onClick={add}
          disabled={atCap}
        >
          <Plus className="h-3.5 w-3.5" aria-hidden />
          Add window
        </Button>
        {atCap ? (
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            {MAX_REGIONS}-region cap reached
          </span>
        ) : null}
      </div>
    </div>
  )
}
