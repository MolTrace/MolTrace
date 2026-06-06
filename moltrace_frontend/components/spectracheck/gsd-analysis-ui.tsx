"use client"

/**
 * Shared UI bits for the GSD-Prompt-3 experimental analysis backend.
 *
 * Used by both the Processed 1H/13C section and the Raw FID section so
 * the selector / experimental badge / level picker / result panel never
 * drift between the two surfaces. State (analysisBackend, gsdLevel,
 * gsdResult, gsdError, gsdLoading) is owned by the caller — these
 * components are deliberately controlled so the existing per-tab caches
 * and runGSDAnalyze flows stay in their parent component.
 */

import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Badge } from "@/components/ui/badge"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { FlaskConical } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { useGsdTelemetry } from "@/components/spectracheck/gsd-telemetry-panel"
import type { components } from "@/src/lib/api/schema"

// Quarter-target denominator for the "X / N runs collected" tooltip
// suffix now comes from the backend's flip_readiness_policy.min_invocations
// in the SpectrumGSDTelemetrySummary response. No hard-coded constant.

export type GSDPromptPeak = components["schemas"]["GSDPromptPeak"]
export type GSDPromptEnvironment = components["schemas"]["GSDPromptEnvironment"]
export type LegacyEnrichedPeak = components["schemas"]["LegacyEnrichedPeak"]
export type SpectrumGSDAnalyzeResult = components["schemas"]["SpectrumGSDAnalyzeResult"]
export type SpectrumGSDAnalyzeRequest = components["schemas"]["SpectrumGSDAnalyzeRequest"]
export type SpectrumSolventCatalog = components["schemas"]["SpectrumSolventCatalog"]
export type SpectrumSolventInfo = components["schemas"]["SpectrumSolventInfo"]
export type NMRRawFIDPreviewResponse = components["schemas"]["NMRRawFIDPreviewResponse"]
export type NMRRawFIDProcessResponse = components["schemas"]["NMRRawFIDProcessResponse"]
export type AnalysisBackendChoice = "legacy" | "gsd_prompt3"
export type GSDLevel = 1 | 2 | 3 | 4 | 5

// ── Unified detection result envelope ─────────────────────────────────
// Both `/spectrum/analyze/gsd` and (post Phase 11) the raw-FID responses
// expose `{ peaks, environments, environment_count, environment_counts,
// category_counts, notes }`. The `UnifiedDetectionResult` is the
// adapter target; `adaptGsdResult` and `adaptLegacyRawFidResult`
// normalize either backend's response into this shape so the renderer
// can be detector-agnostic.

/** Open string per Phase 11 — covers detection categories AND chemical regions. */
export const GSD_DETECTION_CATEGORIES = new Set<string>([
  "compound", "solvent", "impurity", "artifact", "13C_satellite",
])

export interface UnifiedPeak {
  /** Canonical ppm (GSD `position_ppm` OR legacy `shift_ppm`). */
  position_ppm: number
  /** GSD only — derived from position_ppm × field_mhz. */
  position_hz?: number
  intensity?: number
  area?: number
  width_hz?: number
  shape?: string
  /** Legacy only — multiplet notation (s/d/t/q/m/etc). */
  multiplicity?: string | null
  /** Legacy only — integration in proton units. */
  integration_h?: number | null
  /** Legacy only — J coupling values in Hz. */
  j_values_hz?: number[]
  /** Open string — detection category OR chemical region. */
  category: string | null
  category_reason?: string | null
  chemical_region?: string | null
  labile_hint?: boolean | null
  solvent_hit?: Record<string, unknown> | null
  impurity_match?: Record<string, unknown> | null
  /** GSD only — 0..1 confidence. */
  confidence?: number
  // ── Per-peak QC fit metrics (Phase 24) — both detectors now expose ────
  // these. Backend regulatory-tier numbers. All optional; null when the
  // peak wasn't fit (e.g. legacy fast-path).
  fit_redchi?: number | null
  fit_rmse?: number | null
  fwhm_ppm?: number | null
  signal_to_noise?: number | null
  baseline_noise_sigma?: number | null
}

/**
 * Phase 24 QC severity helper. Combines two ratios — signal-to-noise
 * (S/N) and fit-RMSE over baseline-noise (fit_rmse / baseline_σ) — into
 * a single green / yellow / red traffic-light. Returns "unknown" when
 * either input is missing so the renderer can show a muted dot rather
 * than a misleading green.
 *
 * Thresholds (from the Phase 24 packet):
 *   - S/N: > 10 green · 3-10 yellow · < 3 red
 *   - fit_rmse / baseline_σ: < 2 green · 2-5 yellow · > 5 red
 * Combined: worst of the two wins.
 */
export type PeakQcSeverity = "green" | "yellow" | "red" | "unknown"

export function peakQcSeverity(peak: UnifiedPeak): PeakQcSeverity {
  const snr = peak.signal_to_noise
  const fitRmse = peak.fit_rmse
  const baseSigma = peak.baseline_noise_sigma
  if (snr == null && (fitRmse == null || baseSigma == null)) return "unknown"
  const snrLevel: PeakQcSeverity =
    snr == null ? "unknown" : snr > 10 ? "green" : snr >= 3 ? "yellow" : "red"
  const ratio = fitRmse != null && baseSigma != null && baseSigma > 0
    ? fitRmse / baseSigma
    : null
  const fitLevel: PeakQcSeverity =
    ratio == null ? "unknown" : ratio < 2 ? "green" : ratio <= 5 ? "yellow" : "red"
  // Worst-of-two; "unknown" yields to a known level so we don't silently
  // drop a real warning.
  const ranks: Record<PeakQcSeverity, number> = { green: 0, unknown: 1, yellow: 2, red: 3 }
  return ranks[snrLevel] >= ranks[fitLevel] ? snrLevel : fitLevel
}

const PEAK_QC_DOT_STYLE: Record<PeakQcSeverity, string> = {
  green: "bg-emerald-500",
  yellow: "bg-amber-500",
  red: "bg-rose-500",
  unknown: "bg-muted-foreground/30",
}

/**
 * Build a hover-tooltip string showing the five QC metrics. Returns
 * null when no QC fields are populated (caller hides the cell).
 */
export function formatQcTooltip(peak: UnifiedPeak): string | null {
  const parts: string[] = []
  const push = (label: string, value: number | null | undefined, format: (v: number) => string) => {
    if (typeof value === "number" && Number.isFinite(value)) parts.push(`${label}: ${format(value)}`)
  }
  push("S/N", peak.signal_to_noise, (v) => v.toFixed(1))
  push("fit χ²ᵣ", peak.fit_redchi, (v) => v.toExponential(2))
  push("fit RMSE", peak.fit_rmse, (v) => v.toExponential(2))
  push("FWHM", peak.fwhm_ppm, (v) => `${v.toFixed(4)} ppm`)
  push("baseline σ", peak.baseline_noise_sigma, (v) => v.toExponential(2))
  return parts.length > 0 ? parts.join(" · ") : null
}

export interface UnifiedDetectionResult {
  peaks: UnifiedPeak[]
  environments?: GSDPromptEnvironment[]
  environment_count?: number
  environment_counts?: Record<string, number>
  category_counts?: Record<string, number>
  notes?: string[]
  backend: string
  level?: number
  experimental?: boolean
}

/** Adapt a `/spectrum/analyze/gsd` response to the unified shape. */
export function adaptGsdResult(r: SpectrumGSDAnalyzeResult): UnifiedDetectionResult {
  return {
    peaks: r.peaks.map((p) => {
      // GSD currently stores per-peak QC under the open `metadata` dict
      // (Phase 4 backend), whereas legacy now surfaces them as typed
      // top-level fields (Phase 24). Read GSD's via safe extraction so
      // the unified shape matches regardless of where the backend put
      // them.
      const md = (p.metadata ?? {}) as Record<string, unknown>
      const num = (key: string): number | null => {
        const v = md[key]
        return typeof v === "number" && Number.isFinite(v) ? v : null
      }
      return {
        position_ppm: p.position_ppm,
        position_hz: p.position_hz,
        intensity: p.intensity,
        area: p.area,
        width_hz: p.width_hz,
        shape: p.shape,
        category: p.category,
        confidence: p.confidence,
        fit_redchi: num("fit_redchi"),
        fit_rmse: num("fit_rmse"),
        fwhm_ppm: num("fwhm_ppm"),
        signal_to_noise: num("signal_to_noise"),
        baseline_noise_sigma: num("baseline_noise_sigma"),
      }
    }),
    environments: r.environments,
    environment_count: r.environment_count,
    environment_counts: r.environment_counts,
    category_counts: r.category_counts,
    notes: r.notes,
    backend: r.backend,
    level: r.level,
    experimental: r.experimental,
  }
}

/**
 * Adapt a `/nmr/raw-fid/preview` or `/nmr/raw-fid/process` response to
 * the unified shape. Both expose the post-Phase-11 envelope.
 */
export function adaptLegacyRawFidResult(
  r: NMRRawFIDPreviewResponse | NMRRawFIDProcessResponse,
  backendLabel = "legacy",
): UnifiedDetectionResult {
  const peaks = (r.peaks ?? []).map((p) => ({
    position_ppm: p.shift_ppm,
    intensity: (p as unknown as { intensity?: number }).intensity,
    area: (p as unknown as { area?: number }).area,
    width_hz: (p as unknown as { width_hz?: number }).width_hz,
    multiplicity: p.multiplicity,
    integration_h: p.integration_h,
    j_values_hz: p.j_values_hz,
    category: p.category ?? null,
    category_reason: p.category_reason,
    chemical_region: p.chemical_region,
    labile_hint: p.labile_hint,
    solvent_hit: p.solvent_hit,
    impurity_match: p.impurity_match,
    // Phase 24: per-peak QC fit metrics surfaced as typed fields.
    fit_redchi: p.fit_redchi,
    fit_rmse: p.fit_rmse,
    fwhm_ppm: p.fwhm_ppm,
    signal_to_noise: p.signal_to_noise,
    baseline_noise_sigma: p.baseline_noise_sigma,
  }))
  // Reconstruct category_counts from peak categories when the backend
  // didn't include it (older responses might not). Honor server value
  // when present.
  const categoryCounts: Record<string, number> = (r as { category_counts?: Record<string, number> }).category_counts ?? (() => {
    const acc: Record<string, number> = {}
    for (const p of peaks) {
      if (!p.category) continue
      acc[p.category] = (acc[p.category] ?? 0) + 1
    }
    return acc
  })()
  return {
    peaks,
    environments: r.environments,
    environment_count: r.environment_count,
    environment_counts: r.environment_counts,
    category_counts: categoryCounts,
    notes: undefined,
    backend: backendLabel,
    level: undefined,
    experimental: false,
  }
}

// ── Solvent catalog cache ─────────────────────────────────────────────
// Static across the app's lifetime — fetch once, share across all
// mounted GsdAnalysisControls. Cache + in-flight promise live at module
// scope so concurrent mounts dedupe to a single request.
let SOLVENT_CATALOG_CACHE: SpectrumSolventCatalog | null = null
let SOLVENT_CATALOG_PROMISE: Promise<SpectrumSolventCatalog> | null = null

export type SolventCatalogState =
  | { status: "loading"; data: null; error: null }
  | { status: "ready"; data: SpectrumSolventCatalog; error: null }
  | { status: "error"; data: null; error: string }

/**
 * Fetch (or read from module cache) the canonical solvent catalog.
 *
 * Pass `enabled=false` to skip the network request entirely — useful
 * for the legacy backend path where the dropdown is hidden, and for
 * tests that mock apiFetch with a fixed queue of responses. The hook
 * still returns a stable `{ status: "loading", ... }` shape in that
 * case so callers don't need to special-case the disabled path.
 */
export function useSolventCatalog(enabled: boolean = true): SolventCatalogState {
  const [state, setState] = useState<SolventCatalogState>(() =>
    SOLVENT_CATALOG_CACHE
      ? { status: "ready", data: SOLVENT_CATALOG_CACHE, error: null }
      : { status: "loading", data: null, error: null },
  )
  useEffect(() => {
    if (!enabled) return
    if (SOLVENT_CATALOG_CACHE) {
      setState({ status: "ready", data: SOLVENT_CATALOG_CACHE, error: null })
      return
    }
    let cancelled = false
    if (!SOLVENT_CATALOG_PROMISE) {
      SOLVENT_CATALOG_PROMISE = apiFetch<SpectrumSolventCatalog>("/spectrum/solvents/known")
        .then((data) => {
          SOLVENT_CATALOG_CACHE = data
          return data
        })
        .catch((err) => {
          // Reset the promise so a future mount can retry; cache stays null.
          SOLVENT_CATALOG_PROMISE = null
          throw err
        })
    }
    SOLVENT_CATALOG_PROMISE
      .then((data) => { if (!cancelled) setState({ status: "ready", data, error: null }) })
      .catch((err) => { if (!cancelled) setState({ status: "error", data: null, error: String(err?.message ?? err) }) })
    return () => { cancelled = true }
  }, [enabled])
  return state
}

/**
 * Match an arbitrary input string against the catalog. Returns the
 * canonical entry if `input` matches a key (case-insensitive) or any
 * alias; otherwise null. Use this to pre-fill the dropdown from a
 * legacy free-text session solvent string.
 */
export function canonicalizeSolvent(
  input: string,
  catalog: SpectrumSolventCatalog | null,
): SpectrumSolventInfo | null {
  if (!catalog) return null
  const t = input.trim().toLowerCase()
  if (!t) return null
  for (const s of catalog.solvents ?? []) {
    if (s.key.toLowerCase() === t) return s
    if ((s.aliases ?? []).some((a) => a.toLowerCase() === t)) return s
  }
  return null
}

export const GSD_EXPERIMENTAL_TOOLTIP =
  "Global Spectral Deconvolution with auto-classification (industry-standard peak detection). Validation baseline (20-fixture NMRShiftDB2 corpus): 94.4% solvent detect, median compound count delta 3. Promotion to default-on awaits clearing the 95% solvent / median ≤2 gate."

export const GSD_CATEGORY_STYLES: Record<GSDPromptPeak["category"], { label: string; chip: string; dot: string }> = {
  compound: { label: "Compound", chip: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900", dot: "bg-emerald-500" },
  solvent: { label: "Solvent", chip: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-900", dot: "bg-sky-500" },
  impurity: { label: "Impurity", chip: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900", dot: "bg-amber-500" },
  artifact: { label: "Artifact", chip: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-900", dot: "bg-rose-500" },
  "13C_satellite": { label: "13C satellite", chip: "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950/40 dark:text-violet-300 dark:border-violet-900", dot: "bg-violet-500" },
}

const CHEMICAL_REGION_STYLE = {
  chip: "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-900/60 dark:text-slate-300 dark:border-slate-800",
  dot: "bg-slate-400",
} as const

const UNCATEGORIZED_STYLE = {
  chip: "bg-muted/30 text-muted-foreground border-muted",
  dot: "bg-muted-foreground/40",
} as const

/**
 * Map an open-string `category` (per Phase 11) to a visual style.
 * Detection categories (the GSD 5-set) get full color. Anything else
 * is treated as a chemical-region label and renders as a muted slate
 * chip; null/empty renders as the neutral "uncategorized" chip.
 */
export function categoryDisplay(category: string | null | undefined): {
  label: string
  chip: string
  dot: string
  isDetection: boolean
  isChemicalRegion: boolean
} {
  if (!category) {
    return { label: "—", ...UNCATEGORIZED_STYLE, isDetection: false, isChemicalRegion: false }
  }
  if (GSD_DETECTION_CATEGORIES.has(category)) {
    const style = GSD_CATEGORY_STYLES[category as GSDPromptPeak["category"]]
    return { label: style.label, chip: style.chip, dot: style.dot, isDetection: true, isChemicalRegion: false }
  }
  // Chemical-region label (legacy-only). Display with spaces, not underscores.
  return {
    label: category.replaceAll("_", " "),
    ...CHEMICAL_REGION_STYLE,
    isDetection: false,
    isChemicalRegion: true,
  }
}

/**
 * Format a `solvent_hit` / `impurity_match` dict (both share the same
 * key conventions: label, expected_ppm, observed_ppm, delta_ppm) into
 * a human-readable string for tooltip / hover display. Returns null
 * when the dict isn't usefully populated.
 */
export function formatMatchTooltip(
  match: Record<string, unknown> | null | undefined,
  kind: "solvent" | "impurity",
): string | null {
  if (!match || typeof match !== "object") return null
  const label = typeof match.label === "string" ? match.label : null
  const expected = typeof match.expected_ppm === "number" ? match.expected_ppm : null
  const observed = typeof match.observed_ppm === "number" ? match.observed_ppm : null
  const delta = typeof match.delta_ppm === "number" ? match.delta_ppm : null
  if (!label && expected == null && observed == null) return null
  const head = kind === "solvent" ? "Solvent match" : "Impurity match"
  const parts: string[] = []
  if (label) parts.push(label)
  const numerics: string[] = []
  if (expected != null) numerics.push(`expected ${expected.toFixed(3)}`)
  if (observed != null) numerics.push(`observed ${observed.toFixed(3)}`)
  if (delta != null) numerics.push(`Δ ${Math.abs(delta).toFixed(3)} ppm`)
  if (numerics.length) parts.push(`(${numerics.join(", ")})`)
  return `${head}: ${parts.join(" ")}`
}

export type GsdAnalysisControlsProps = {
  backend: AnalysisBackendChoice
  onBackendChange: (value: AnalysisBackendChoice) => void
  level: GSDLevel
  onLevelChange: (value: GSDLevel) => void
  /**
   * Current solvent value the parent will send to /spectrum/analyze/gsd.
   * Either a canonical catalog key (e.g. "CDCl3") or a free-text value
   * the user typed under "Other / unlisted". Empty string means
   * "send empty solvent" (the GSD endpoint still accepts that).
   */
  solvent: string
  onSolventChange: (value: string) => void
}

// Sentinel value the <select> uses to signal "switch to free-text mode".
// Not a real solvent — never propagates outside the control.
const SOLVENT_OTHER_SENTINEL = "__other__"

/**
 * Single horizontal row: "Analysis backend" + Legacy/GSD toggle, plus
 * Experimental badge + Level 1–5 picker + canonical solvent dropdown
 * when GSD is active. Default backend must remain `legacy` — never
 * silently flip the toggle from outside.
 */
export function GsdAnalysisControls({ backend, onBackendChange, level, onLevelChange, solvent, onSolventChange }: GsdAnalysisControlsProps) {
  // Only fetch the solvent catalog when the user actually opens the GSD
  // path. Keeps legacy-default mounts free of an extra network request
  // and avoids polluting tests that mock apiFetch with a fixed queue.
  const catalogState = useSolventCatalog(backend === "gsd_prompt3")
  const catalog = catalogState.data
  const trimmedSolvent = solvent.trim()
  const canonical = canonicalizeSolvent(trimmedSolvent, catalog)
  // The dropdown is in "other" mode if the user explicitly toggled into
  // free-text, OR if the current solvent value doesn't match the catalog.
  // The `solventOtherMode` local state lets a user click "Other" without
  // having to clear the field first (handles the canonical → other → type
  // transition cleanly).
  const [solventOtherMode, setSolventOtherMode] = useState(false)
  const isOther = solventOtherMode || (trimmedSolvent !== "" && canonical == null)
  const selectValue = isOther
    ? SOLVENT_OTHER_SENTINEL
    : canonical
      ? canonical.key
      : ""
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed bg-muted/20 px-3 py-2 text-sm">
      <FlaskConical className="h-4 w-4 text-muted-foreground" aria-hidden />
      <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
        Analysis backend
      </span>
      <div role="radiogroup" aria-label="Analysis backend" className="inline-flex overflow-hidden rounded-md border bg-card">
        <button
          type="button"
          role="radio"
          aria-checked={backend === "legacy"}
          onClick={() => onBackendChange("legacy")}
          className={cn(
            "px-3 py-1 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors",
            backend === "legacy"
              ? "bg-foreground text-background"
              : "text-muted-foreground hover:bg-muted/40",
          )}
        >
          Legacy <span className="opacity-60">(default)</span>
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={backend === "gsd_prompt3"}
          onClick={() => onBackendChange("gsd_prompt3")}
          className={cn(
            "border-l px-3 py-1 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors",
            backend === "gsd_prompt3"
              ? "bg-foreground text-background"
              : "text-muted-foreground hover:bg-muted/40",
          )}
        >
          GSD
        </button>
      </div>
      {backend === "gsd_prompt3" ? (
        <>
          <ExperimentalBadgeWithTelemetry />
          {/* Telemetry hook fetches /audit/events once on first GSD
              selection per page-mount; subsequent badges + the
              SpectraCheck Overview panel + the admin readiness page
              share the same module-level cache (30s TTL). */}
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            Level
          </span>
          <div role="radiogroup" aria-label="GSD level" className="inline-flex overflow-hidden rounded-md border bg-card">
            {([1, 2, 3, 4, 5] as const).map((lvl) => (
              <button
                key={lvl}
                type="button"
                role="radio"
                aria-checked={level === lvl}
                onClick={() => onLevelChange(lvl)}
                className={cn(
                  "px-2 py-1 font-mono text-[11px] tabular-nums transition-colors",
                  lvl !== 1 ? "border-l" : "",
                  level === lvl
                    ? "bg-foreground text-background"
                    : "text-muted-foreground hover:bg-muted/40",
                )}
                title={lvl >= 4 ? `Level ${lvl} — slow / fine resolution (iterative deconvolution)` : `Level ${lvl}`}
              >
                {lvl}
              </button>
            ))}
          </div>
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            {level >= 4 ? "slow / fine resolution" : "default — fast"}
          </span>
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            Solvent
          </span>
          <select
            aria-label="GSD solvent"
            value={selectValue}
            disabled={catalogState.status === "loading"}
            onChange={(e) => {
              const v = e.target.value
              if (v === SOLVENT_OTHER_SENTINEL) {
                setSolventOtherMode(true)
                // Keep the current value if it's already a free-text string;
                // otherwise clear so the text input starts empty and ready.
                if (canonical) onSolventChange("")
              } else {
                setSolventOtherMode(false)
                onSolventChange(v)
              }
            }}
            className="h-7 rounded-md border bg-card px-2 font-mono text-[11px] tabular-nums"
          >
            <option value="">— select —</option>
            {(catalog?.solvents ?? []).map((s) => {
              const h1 = s.residual_1h_ppm != null ? `${s.residual_1h_ppm} ppm` : "—"
              const c13 = s.residual_13c_ppm != null ? `${s.residual_13c_ppm} ppm` : "—"
              return (
                <option key={s.key} value={s.key} title={`Residual ¹H: ${h1} · ¹³C: ${c13}`}>
                  {s.label}
                </option>
              )
            })}
            <option value={SOLVENT_OTHER_SENTINEL}>Other / unlisted…</option>
          </select>
          {isOther ? (
            <input
              type="text"
              aria-label="Custom solvent name"
              value={solvent}
              onChange={(e) => onSolventChange(e.target.value)}
              placeholder="Custom solvent name"
              className="h-7 w-32 rounded-md border bg-card px-2 font-mono text-[11px]"
            />
          ) : null}
          {catalogState.status === "error" ? (
            <span className="font-mono text-[10px] text-amber-700 dark:text-amber-300">
              Solvent catalog unavailable — free text only.
            </span>
          ) : null}
        </>
      ) : null}
    </div>
  )
}

export type DetectionResultsPanelProps = {
  /** Unified result payload (adapt via `adaptGsdResult` or `adaptLegacyRawFidResult`). null hides the panel. */
  result: UnifiedDetectionResult | null
  /** Eyebrow text. Defaults adapt to the backend label. */
  eyebrow?: string
  /** Card title. Defaults adapt to the backend label. */
  title?: string
  /** data-testid override, defaults to "detection-results-surface". */
  testId?: string
}

/**
 * Step 3b output: experimental badge (GSD only), category-mix chips,
 * info-level notes, color-coded peak table. Columns adapt to whichever
 * fields the underlying backend populated. Empty-state copy when
 * peaks=[].
 */
export function DetectionResultsPanel({
  result,
  eyebrow,
  title,
  testId = "detection-results-surface",
}: DetectionResultsPanelProps) {
  if (result == null) return null
  const isGsdBackend = result.backend === "gsd_prompt3"
  const resolvedEyebrow = eyebrow ?? (isGsdBackend
    ? "Step 3b · GSD output (experimental)"
    : "Step 3c · Detection summary (legacy)")
  const resolvedTitle = title ?? (isGsdBackend ? "GSD-Prompt-3 peak picks" : "Legacy detector peak picks")
  const peakCount = result.peaks.length
  const counts = result.category_counts ?? {}
  // Render detection categories first (colored), then any extra
  // chemical-region categories (legacy-only, muted) sorted alphabetically.
  const orderedDetection: string[] = ["compound", "solvent", "impurity", "artifact", "13C_satellite"]
  const presentDetection = orderedDetection.filter((c) => (counts[c] ?? 0) > 0)
  const presentRegions = Object.keys(counts)
    .filter((c) => !GSD_DETECTION_CATEGORIES.has(c) && (counts[c] ?? 0) > 0)
    .sort()
  const presentCategories = [...presentDetection, ...presentRegions]
  const notes = result.notes ?? []
  // Detect which optional columns to render based on data presence.
  const showHz = result.peaks.some((p) => typeof p.position_hz === "number")
  const showIntensity = result.peaks.some((p) => typeof p.intensity === "number")
  const showArea = result.peaks.some((p) => typeof p.area === "number")
  const showWidth = result.peaks.some((p) => typeof p.width_hz === "number")
  const showShape = result.peaks.some((p) => typeof p.shape === "string")
  const showMultiplicity = result.peaks.some((p) => typeof p.multiplicity === "string" && p.multiplicity)
  const showIntegration = result.peaks.some((p) => typeof p.integration_h === "number")
  const showJ = result.peaks.some((p) => Array.isArray(p.j_values_hz) && p.j_values_hz.length > 0)
  const showConfidence = result.peaks.some((p) => typeof p.confidence === "number")
  const showMatches = result.peaks.some(
    (p) => formatMatchTooltip(p.solvent_hit, "solvent") || formatMatchTooltip(p.impurity_match, "impurity"),
  )
  // Phase 24: show the QC column whenever at least one peak carries any
  // of the five QC metrics. Keeps the column hidden on pure-legacy
  // fast-path responses that don't fit per-peak.
  const showQc = result.peaks.some(
    (p) =>
      typeof p.signal_to_noise === "number" ||
      typeof p.fit_redchi === "number" ||
      typeof p.fit_rmse === "number" ||
      typeof p.fwhm_ppm === "number" ||
      typeof p.baseline_noise_sigma === "number",
  )

  const envCount = result.environment_count ?? result.environments?.length
  const description = (() => {
    const head = `Backend: ${result.backend}`
    const lvl = result.level != null ? ` · level ${result.level}` : ""
    const peakLabel = `${peakCount} peak${peakCount === 1 ? "" : "s"}`
    const envLabel = envCount != null ? ` · ${envCount} environment${envCount === 1 ? "" : "s"}` : ""
    return `${head}${lvl} · ${peakLabel}${envLabel}.`
  })()

  return (
    <div className="min-w-0" data-testid={testId}>
      <ModuleCard
        accent="teal"
        eyebrow={resolvedEyebrow}
        title={resolvedTitle}
        icon={FlaskConical}
        description={description}
        className="min-w-0 overflow-visible shadow-none"
      >
        <div className="space-y-4">
          {/* Header row: experimental badge (GSD only) + category-mix chips */}
          <div className="flex flex-wrap items-center gap-2">
            {result.experimental ? <ExperimentalBadgeWithTelemetry /> : null}
            <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
              Category mix
            </span>
            {presentCategories.length === 0 ? (
              <span className="text-xs text-muted-foreground">no peaks classified</span>
            ) : (
              presentCategories.map((cat) => {
                const style = categoryDisplay(cat)
                return (
                  <span
                    key={cat}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] tabular-nums",
                      style.chip,
                    )}
                    title={style.isChemicalRegion ? `Chemical region: ${style.label}` : undefined}
                  >
                    <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} aria-hidden />
                    {counts[cat]} {style.label.toLowerCase()}
                  </span>
                )
              })
            )}
          </div>

          {/* Notes — info-level alerts above the peak list */}
          {notes.length > 0 ? (
            <div className="space-y-2">
              {notes.map((note, idx) => (
                <AlertCard
                  key={`detection-note-${idx}`}
                  variant="info"
                  title={isGsdBackend ? "GSD note" : "Detector note"}
                  description={note}
                />
              ))}
            </div>
          ) : null}

          {/* Peak list — empty state or category-colored rows */}
          {peakCount === 0 ? (
            <div className="rounded-md border border-dashed bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
              {isGsdBackend
                ? `GSD did not pick any peaks for this spectrum${result.level != null ? ` at level ${result.level}` : ""}.${result.level != null && result.level < 4 ? " Try a higher level (4–5) for finer resolution." : ""}`
                : "Legacy detector did not return any peaks for this spectrum."}
            </div>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-left text-xs">
                <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Category</th>
                    <th className="px-3 py-2 text-right">δ (ppm)</th>
                    {showHz ? <th className="px-3 py-2 text-right">Hz</th> : null}
                    {showIntensity ? <th className="px-3 py-2 text-right">Intensity</th> : null}
                    {showArea ? <th className="px-3 py-2 text-right">Area</th> : null}
                    {showWidth ? <th className="px-3 py-2 text-right">Width (Hz)</th> : null}
                    {showShape ? <th className="px-3 py-2">Shape</th> : null}
                    {showMultiplicity ? <th className="px-3 py-2">Mult</th> : null}
                    {showIntegration ? <th className="px-3 py-2 text-right">∫H</th> : null}
                    {showJ ? <th className="px-3 py-2 text-right">J (Hz)</th> : null}
                    {showConfidence ? <th className="px-3 py-2 text-right">Conf</th> : null}
                    {showQc ? <th className="px-3 py-2" title="Per-peak fit-quality indicator: S/N (green > 10, yellow 3-10, red < 3) combined with fit RMSE / baseline σ (green < 2, yellow 2-5, red > 5). Worst-of-two wins.">QC</th> : null}
                    {showMatches ? <th className="px-3 py-2">Matches</th> : null}
                  </tr>
                </thead>
                <tbody className="font-mono tabular-nums">
                  {result.peaks.map((peak, idx) => {
                    const style = categoryDisplay(peak.category)
                    const solventTip = formatMatchTooltip(peak.solvent_hit, "solvent")
                    const impurityTip = formatMatchTooltip(peak.impurity_match, "impurity")
                    const matchTip = solventTip ?? impurityTip
                    return (
                      <tr key={`detection-peak-${idx}`} className="border-t hover:bg-muted/20">
                        <td className="px-3 py-1.5">
                          <span
                            className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px]", style.chip)}
                            title={
                              style.isChemicalRegion
                                ? `Chemical region: ${style.label}${peak.category_reason ? ` — ${peak.category_reason}` : ""}`
                                : peak.category_reason ?? undefined
                            }
                          >
                            <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} aria-hidden />
                            {style.label}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-right">{peak.position_ppm.toFixed(3)}</td>
                        {showHz ? <td className="px-3 py-1.5 text-right">{peak.position_hz != null ? peak.position_hz.toFixed(1) : "—"}</td> : null}
                        {showIntensity ? <td className="px-3 py-1.5 text-right">{peak.intensity != null ? peak.intensity.toExponential(2) : "—"}</td> : null}
                        {showArea ? <td className="px-3 py-1.5 text-right">{peak.area != null ? peak.area.toExponential(2) : "—"}</td> : null}
                        {showWidth ? <td className="px-3 py-1.5 text-right">{peak.width_hz != null ? peak.width_hz.toFixed(2) : "—"}</td> : null}
                        {showShape ? <td className="px-3 py-1.5">{peak.shape ?? "—"}</td> : null}
                        {showMultiplicity ? <td className="px-3 py-1.5">{peak.multiplicity ?? "—"}</td> : null}
                        {showIntegration ? <td className="px-3 py-1.5 text-right">{peak.integration_h != null ? peak.integration_h.toFixed(2) : "—"}</td> : null}
                        {showJ ? (
                          <td className="px-3 py-1.5 text-right">
                            {peak.j_values_hz && peak.j_values_hz.length > 0
                              ? peak.j_values_hz.map((j) => j.toFixed(1)).join(", ")
                              : "—"}
                          </td>
                        ) : null}
                        {showConfidence ? <td className="px-3 py-1.5 text-right">{peak.confidence != null ? `${(peak.confidence * 100).toFixed(0)}%` : "—"}</td> : null}
                        {showQc ? (() => {
                          const severity = peakQcSeverity(peak)
                          const qcTip = formatQcTooltip(peak)
                          return (
                            <td className="px-3 py-1.5">
                              {qcTip ? (
                                <span
                                  className="inline-flex cursor-help items-center gap-1.5"
                                  title={qcTip}
                                  aria-label={`Peak QC ${severity}: ${qcTip}`}
                                >
                                  <span className={cn("h-2 w-2 rounded-full", PEAK_QC_DOT_STYLE[severity])} aria-hidden />
                                  <span className="text-[10px] uppercase text-muted-foreground">{severity === "unknown" ? "—" : severity}</span>
                                </span>
                              ) : "—"}
                            </td>
                          )
                        })() : null}
                        {showMatches ? (
                          <td className="px-3 py-1.5">
                            {matchTip ? (
                              <span
                                className="cursor-help text-muted-foreground underline decoration-dotted"
                                title={matchTip}
                              >
                                {(peak.solvent_hit?.label as string | undefined) ??
                                  (peak.impurity_match?.label as string | undefined) ??
                                  "match"}
                              </span>
                            ) : "—"}
                          </td>
                        ) : null}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Environments — clustered chemical-environment view */}
          {result.environments && result.environments.length > 0 ? (
            <div className="space-y-2">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                Environments ({result.environments.length})
              </p>
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2">Category</th>
                      <th className="px-3 py-2 text-right">δ centre (ppm)</th>
                      <th className="px-3 py-2 text-right">Peaks</th>
                      <th className="px-3 py-2">Mult</th>
                      <th className="px-3 py-2 text-right">Total intensity</th>
                      <th className="px-3 py-2 text-right">Total area</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono tabular-nums">
                    {result.environments.map((env, idx) => {
                      const style = categoryDisplay(env.category)
                      return (
                        <tr key={`env-${idx}`} className="border-t hover:bg-muted/20">
                          <td className="px-3 py-1.5">
                            <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px]", style.chip)}>
                              <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} aria-hidden />
                              {style.label}
                            </span>
                          </td>
                          <td className="px-3 py-1.5 text-right">{env.centre_ppm.toFixed(3)}</td>
                          <td className="px-3 py-1.5 text-right">{env.peak_count}</td>
                          <td className="px-3 py-1.5">{env.multiplicity}</td>
                          <td className="px-3 py-1.5 text-right">{env.total_intensity.toExponential(2)}</td>
                          <td className="px-3 py-1.5 text-right">{env.total_area.toExponential(2)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </div>
      </ModuleCard>
    </div>
  )
}

/**
 * Backward-compat shim: existing GSD callers passing a
 * `SpectrumGSDAnalyzeResult` directly. Internally adapts and forwards
 * to `<DetectionResultsPanel>`.
 */
export type GsdResultsPanelProps = {
  result: SpectrumGSDAnalyzeResult | null
  eyebrow?: string
  testId?: string
}
export function GsdResultsPanel({ result, eyebrow, testId = "gsd-results-surface" }: GsdResultsPanelProps) {
  return (
    <DetectionResultsPanel
      result={result ? adaptGsdResult(result) : null}
      eyebrow={eyebrow}
      testId={testId}
    />
  )
}

/**
 * Experimental-status badge that pairs the static promotion-gate
 * tooltip text with a live "X / N quarter-target runs collected"
 * suffix sourced from the audit-event telemetry hook.
 *
 * Renders identically to the previous static badge when the telemetry
 * hook is still loading (no layout shift on first paint); the suffix
 * appears as soon as the cache fills (typically < 1s on a warm page).
 *
 * Both the GsdAnalysisControls selector and the DetectionResultsPanel
 * header use this — the module-level cache in the telemetry hook
 * dedupes the underlying network call across all mounts.
 */
function ExperimentalBadgeWithTelemetry() {
  const state = useGsdTelemetry(true)
  const summary = state.status === "ready" ? state.summary : null
  const invocations = summary?.invocations ?? null
  const target = summary?.flip_readiness_policy.min_invocations ?? null
  const verdict = summary?.flip_readiness_verdict
  const targetSuffix =
    invocations != null && target != null
      ? `\n\nQuarter-target runs collected: ${invocations.toLocaleString()} / ${target.toLocaleString()}.${
          verdict ? `\nReadiness verdict: ${verdict.replace("_", " ")}.` : ""
        }`
      : ""
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className="cursor-help border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300"
        >
          <FlaskConical className="mr-1 h-3 w-3" aria-hidden />
          Experimental
          {invocations != null && invocations > 0 ? (
            <span className="ml-1.5 font-mono text-[10px] font-bold tabular-nums opacity-70">
              · {invocations >= 1000 ? `${(invocations / 1000).toFixed(1)}k` : invocations}
            </span>
          ) : null}
        </Badge>
      </TooltipTrigger>
      <TooltipContent sideOffset={4} className="max-w-xs whitespace-pre-line text-xs">
        {GSD_EXPERIMENTAL_TOOLTIP}
        {targetSuffix}
      </TooltipContent>
    </Tooltip>
  )
}
