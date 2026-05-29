"use client"

import { useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  Layers,
  Loader2,
  Sparkles,
  Wand2,
} from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { cn } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import type { components } from "@/src/lib/api/schema"

/**
 * Multiplet analysis (Phase 26) — chained off GSD peak picking.
 *
 * Caller flow per the packet:
 *   1. POST /spectrum/analyze/gsd → get peaks
 *   2. Filter peaks by S/N (we use > 3, common spectroscopy threshold)
 *   3. POST /spectrum/analyze/multiplets with the filtered list
 *
 * Render:
 *   - Multiplet table — name (A/B/C ascending ppm), multiplicity_label,
 *     j_couplings_hz (largest-first), constituent_peak_indices
 *   - Per-multiplet synthetic-overlay sparkline — light-red drop lines
 *     at the synthetic_overlays_ppm positions, overlaid on a faint
 *     reference range so the user can see where each overlay would
 *     land if redrawn on the main spectrum chart
 */

export type GSDPromptPeak = components["schemas"]["GSDPromptPeak"]
export type SpectrumGSDAnalyzeResult = components["schemas"]["SpectrumGSDAnalyzeResult"]
export type MultipletDescriptor = components["schemas"]["MultipletDescriptor"]
export type SpectrumMultipletAnalyzeRequest =
  components["schemas"]["SpectrumMultipletAnalyzeRequest"]
export type SpectrumMultipletAnalyzeResult =
  components["schemas"]["SpectrumMultipletAnalyzeResult"]
type MultipletLabel = MultipletDescriptor["multiplicity_label"]

/** S/N cutoff used to filter GSD peaks before submitting to multiplet analysis. */
const MULTIPLET_SN_FLOOR = 3

/**
 * Hook: given a GSD result, fetch multiplet analysis when the result
 * arrives. Auto-fires when the result identity changes (re-running GSD
 * yields a new result object, re-fires the multiplet call).
 *
 * Filters peaks by S/N > MULTIPLET_SN_FLOOR before submitting.
 *
 * Module-level WeakMap cache keyed by `(gsdResult, toleranceHz)` —
 * lets the multiplet panel + J-coupling panel mount independently
 * without duplicating the underlying POST.
 */
export type MultipletState =
  | { status: "idle"; result: null; error: null }
  | { status: "loading"; result: null; error: null }
  | { status: "ready"; result: SpectrumMultipletAnalyzeResult; error: null; filteredPeaks: GSDPromptPeak[] }
  | { status: "error"; result: null; error: string }

type MultipletCacheEntry = {
  promise: Promise<{ result: SpectrumMultipletAnalyzeResult; filteredPeaks: GSDPromptPeak[] }>
  toleranceHz: number
}
// Module-level WeakMap so two panels (multiplet table + J-coupling
// bridge) share the same POST per gsdResult identity. WeakMap so
// entries are GC'd when the gsdResult is no longer referenced.
const MULTIPLET_CACHE = new WeakMap<SpectrumGSDAnalyzeResult, MultipletCacheEntry>()

function runMultipletAnalysis(
  gsdResult: SpectrumGSDAnalyzeResult,
  toleranceHz: number,
): Promise<{ result: SpectrumMultipletAnalyzeResult; filteredPeaks: GSDPromptPeak[] }> {
  const cached = MULTIPLET_CACHE.get(gsdResult)
  if (cached && cached.toleranceHz === toleranceHz) return cached.promise
  const filteredPeaks = gsdResult.peaks.filter((p) => {
    const md = (p.metadata ?? {}) as Record<string, unknown>
    const snr = md.signal_to_noise
    return typeof snr !== "number" || snr > MULTIPLET_SN_FLOOR
  })
  if (filteredPeaks.length === 0) {
    const err = new Error(`No peaks above S/N ${MULTIPLET_SN_FLOOR} — nothing to analyze.`)
    return Promise.reject(err)
  }
  const body: SpectrumMultipletAnalyzeRequest = {
    peaks: filteredPeaks,
    tolerance_hz: toleranceHz,
  }
  const promise = apiFetch<SpectrumMultipletAnalyzeResult>("/spectrum/analyze/multiplets", {
    method: "POST",
    body,
  }).then((result) => ({ result, filteredPeaks }))
  MULTIPLET_CACHE.set(gsdResult, { promise, toleranceHz })
  return promise
}

export function useGsdMultipletAnalysis(
  gsdResult: SpectrumGSDAnalyzeResult | null,
  toleranceHz: number = 0.5,
): MultipletState {
  const [state, setState] = useState<MultipletState>({ status: "idle", result: null, error: null })
  useEffect(() => {
    if (!gsdResult) {
      setState({ status: "idle", result: null, error: null })
      return
    }
    let cancelled = false
    setState({ status: "loading", result: null, error: null })
    runMultipletAnalysis(gsdResult, toleranceHz)
      .then(({ result, filteredPeaks }) => {
        if (cancelled) return
        setState({ status: "ready", result, error: null, filteredPeaks })
      })
      .catch((err) => {
        if (cancelled) return
        setState({
          status: "error",
          result: null,
          error: formatApiError(err, "Multiplet analysis failed"),
        })
      })
    return () => {
      cancelled = true
    }
  }, [gsdResult, toleranceHz])
  return state
}

const MULT_LABEL: Record<MultipletLabel, string> = {
  s: "Singlet (s)",
  d: "Doublet (d)",
  t: "Triplet (t)",
  q: "Quartet (q)",
  p: "Pentet (p)",
  sext: "Sextet",
  sept: "Septet",
  dd: "Doublet of doublets (dd)",
  dt: "Doublet of triplets (dt)",
  td: "Triplet of doublets (td)",
  ddd: "Doublet of doublet of doublets (ddd)",
  m: "Multiplet (m)",
}

const MULT_CHIP: Record<MultipletLabel, string> = {
  s: "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-950/40 dark:text-slate-300 dark:border-slate-900",
  d: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900",
  t: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-900",
  q: "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950/40 dark:text-violet-300 dark:border-violet-900",
  p: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200 dark:bg-fuchsia-950/40 dark:text-fuchsia-300 dark:border-fuchsia-900",
  sext: "bg-pink-50 text-pink-700 border-pink-200 dark:bg-pink-950/40 dark:text-pink-300 dark:border-pink-900",
  sept: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-900",
  dd: "bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-950/40 dark:text-cyan-300 dark:border-cyan-900",
  dt: "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-950/40 dark:text-teal-300 dark:border-teal-900",
  td: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-900",
  ddd: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900",
  m: "bg-muted text-muted-foreground border-border",
}

/**
 * Mini synthetic overlay — renders the per-multiplet `synthetic_overlays_ppm`
 * positions as light-red drop lines over a faint range axis. Read as
 * a preview of how the overlay would appear when redrawn on the main
 * SpectrumViewer (chart-layer integration is follow-up work).
 *
 * Axis is reversed (ppm convention: high ppm on the left).
 */
function SyntheticOverlaySpark({
  positionsPpm,
  rangePpm,
}: {
  positionsPpm: number[]
  rangePpm: [number, number]
}) {
  const w = 240
  const h = 36
  const [lo, hi] = rangePpm[0] < rangePpm[1] ? rangePpm : [rangePpm[1], rangePpm[0]]
  const span = Math.max(hi - lo, 1e-9)
  // Reversed: high ppm on the left
  const mapX = (ppm: number) => ((hi - ppm) / span) * (w - 4) + 2
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="h-9 w-full"
      role="img"
      aria-label="Synthetic multiplet overlay (light red sticks over reference range)"
    >
      {/* faint range axis */}
      <line x1="2" y1={h - 2} x2={w - 2} y2={h - 2} stroke="currentColor" strokeOpacity="0.25" strokeWidth="1" />
      {/* range endpoints (high ppm left, low ppm right) */}
      <text x="2" y={h - 5} className="font-mono text-[8px] fill-muted-foreground">{hi.toFixed(2)}</text>
      <text x={w - 2} y={h - 5} className="font-mono text-[8px] fill-muted-foreground" textAnchor="end">
        {lo.toFixed(2)}
      </text>
      {/* light-red sticks (synthetic overlay) */}
      {positionsPpm.map((ppm, idx) => {
        const x = mapX(ppm)
        if (!Number.isFinite(x)) return null
        return (
          <line
            key={idx}
            x1={x}
            y1={4}
            x2={x}
            y2={h - 4}
            stroke="#fb7185"
            strokeWidth="1.5"
            strokeOpacity="0.8"
          />
        )
      })}
    </svg>
  )
}

function formatRangePpm(range: [number, number]): string {
  const [lo, hi] = range[0] < range[1] ? range : [range[1], range[0]]
  return `${hi.toFixed(3)} – ${lo.toFixed(3)}`
}

export type GsdMultipletPanelProps = {
  /** GSD result to chain multiplet analysis off. null → idle. */
  gsdResult: SpectrumGSDAnalyzeResult | null
  /** Optional tolerance override (default 0.5 Hz per backend spec). */
  toleranceHz?: number
  /** Test id root. */
  testId?: string
}

/**
 * Step 3c — multiplet analysis panel. Auto-runs when a GSD result is
 * available; renders the multiplet table + per-row synthetic overlay
 * sparkline + multiplicity-mix chip row.
 */
export function GsdMultipletPanel({
  gsdResult,
  toleranceHz = 0.5,
  testId = "gsd-multiplet-results-surface",
}: GsdMultipletPanelProps) {
  const state = useGsdMultipletAnalysis(gsdResult, toleranceHz)

  // Compute overall ppm range across all multiplets for consistent
  // sparkline axes. Falls back to a unit range when nothing detected.
  const sparkRange = useMemo<[number, number]>(() => {
    if (state.status !== "ready" || !state.result.multiplets || state.result.multiplets.length === 0) {
      return [0, 1]
    }
    let lo = Infinity
    let hi = -Infinity
    for (const m of state.result.multiplets) {
      lo = Math.min(lo, m.range_ppm[0], m.range_ppm[1])
      hi = Math.max(hi, m.range_ppm[0], m.range_ppm[1])
    }
    // Pad ±2% so end points don't sit on the axis
    const span = Math.max(hi - lo, 0.01)
    return [lo - span * 0.02, hi + span * 0.02]
  }, [state])

  if (gsdResult == null) return null

  if (state.status === "loading") {
    return (
      <div className="min-w-0" data-testid={`${testId}-loading`}>
        <ModuleCard
          accent="teal"
          eyebrow="Step 3c · Multiplet analysis"
          title="Resolving multiplets…"
          icon={Wand2}
          description={`Filtering peaks by S/N > ${MULTIPLET_SN_FLOOR} and detecting first-order + complex multiplets at ${toleranceHz} Hz tolerance.`}
          className="min-w-0 overflow-visible shadow-none"
        >
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            POST /spectrum/analyze/multiplets…
          </div>
        </ModuleCard>
      </div>
    )
  }

  if (state.status === "error") {
    return (
      <div className="min-w-0" data-testid={`${testId}-error`}>
        <ModuleCard
          accent="teal"
          eyebrow="Step 3c · Multiplet analysis"
          title="Multiplet analysis failed"
          icon={AlertTriangle}
          description="The detector returned a result but the multiplet pass did not complete."
          className="min-w-0 overflow-visible shadow-none"
        >
          <AlertCard variant="error" title="Multiplet error" description={state.error} />
        </ModuleCard>
      </div>
    )
  }

  if (state.status !== "ready") return null

  const result = state.result
  const multiplets = result.multiplets ?? []
  const overlays = result.synthetic_overlays_ppm ?? []
  const counts = result.multiplicity_counts ?? {}
  const orderedLabels: MultipletLabel[] = ["s", "d", "t", "q", "p", "sext", "sept", "dd", "dt", "td", "ddd", "m"]
  const presentLabels = orderedLabels.filter((label) => (counts[label] ?? 0) > 0)

  return (
    <div className="min-w-0" data-testid={testId}>
      <ModuleCard
        accent="teal"
        eyebrow="Step 3c · Multiplet analysis"
        title="GSD multiplet resolution"
        icon={Wand2}
        description={`Backend: ${result.backend} · ${result.multiplet_count} multiplet${
          result.multiplet_count === 1 ? "" : "s"
        } detected from ${state.filteredPeaks.length} peak${
          state.filteredPeaks.length === 1 ? "" : "s"
        } above S/N ${MULTIPLET_SN_FLOOR}.`}
        className="min-w-0 overflow-visible shadow-none"
      >
        <div className="space-y-4">
          {/* Multiplicity-mix chips */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
              Multiplicity mix
            </span>
            {presentLabels.length === 0 ? (
              <span className="text-xs text-muted-foreground">no multiplets detected</span>
            ) : (
              presentLabels.map((label) => (
                <span
                  key={label}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] tabular-nums",
                    MULT_CHIP[label],
                  )}
                >
                  {counts[label]} {label}
                </span>
              ))
            )}
          </div>

          {/* Notes — info-level alerts */}
          {(result.notes ?? []).length > 0 ? (
            <div className="space-y-2">
              {(result.notes ?? []).map((note, idx) => (
                <AlertCard
                  key={`mult-note-${idx}`}
                  variant="info"
                  title="Multiplet note"
                  description={note}
                />
              ))}
            </div>
          ) : null}

          {/* Empty state */}
          {multiplets.length === 0 ? (
            <div className="rounded-md border border-dashed bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
              No multiplets detected from the peak set above the S/N ≥ {MULTIPLET_SN_FLOOR} floor.
              The peaks may be too sparse, off-resonance, or below the clustering threshold.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-left text-xs">
                <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Name</th>
                    <th className="px-3 py-2">Multiplicity</th>
                    <th className="px-3 py-2 text-right">δ centre (ppm)</th>
                    <th className="px-3 py-2 text-right">Range (ppm)</th>
                    <th className="px-3 py-2 text-right">J (Hz)</th>
                    <th className="px-3 py-2 text-right">Peaks</th>
                    <th className="px-3 py-2">Synthetic overlay</th>
                  </tr>
                </thead>
                <tbody className="font-mono tabular-nums">
                  {multiplets.map((m, idx) => {
                    const overlay = overlays[idx] ?? []
                    const jList = m.j_couplings_hz ?? []
                    const constituents = m.constituent_peak_indices ?? []
                    return (
                      <tr key={`${m.name}-${idx}`} className="border-t align-top hover:bg-muted/20">
                        <td className="px-3 py-2">
                          <span
                            className="inline-flex items-center gap-1.5 rounded-full border bg-muted/40 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em]"
                            title={`Multiplet ${m.name} centred at ${m.center_ppm.toFixed(3)} ppm`}
                          >
                            <Layers className="h-3 w-3" aria-hidden />
                            {m.name}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={cn(
                              "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px]",
                              MULT_CHIP[m.multiplicity_label],
                            )}
                            title={MULT_LABEL[m.multiplicity_label]}
                          >
                            {m.multiplicity_label}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right">{m.center_ppm.toFixed(3)}</td>
                        <td className="px-3 py-2 text-right">{formatRangePpm(m.range_ppm)}</td>
                        <td className="px-3 py-2 text-right">
                          {jList.length > 0 ? (
                            <span className="inline-block max-w-[160px] truncate" title={jList.map((j) => `${j.toFixed(2)} Hz`).join(", ")}>
                              {jList.map((j) => j.toFixed(1)).join(", ")}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {constituents.length > 0 ? (
                            <span
                              className="cursor-help text-muted-foreground underline decoration-dotted"
                              title={`Constituent GSD peak indices: ${constituents.join(", ")}`}
                            >
                              {constituents.length}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <div className="text-rose-500">
                            <SyntheticOverlaySpark positionsPpm={overlay} rangePpm={sparkRange} />
                          </div>
                          <p className="mt-0.5 font-mono text-[9px] text-muted-foreground">
                            {overlay.length} stick{overlay.length === 1 ? "" : "s"}
                          </p>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            Light-red sticks preview the synthetic overlay per multiplet. Chart-layer integration on
            the main SpectrumViewer is a follow-up.
          </p>
        </div>
      </ModuleCard>
    </div>
  )
}
