/**
 * Zustand store for spectrum render data.
 *
 * Step 2 of the spectrum-stabilization plan: hold the high-volume typed
 * arrays here instead of in React useState. Selector subscriptions mean the
 * spectrum component only re-renders when ``ppmAxis`` or ``intensities``
 * actually change reference — a parent re-render from an unrelated state
 * change (button hover three components away) no longer cascades into the
 * chart.
 *
 * Why Float32Array: it's referentially stable, half the bytes of a regular
 * array, and Plotly can consume typed arrays without copying them into plain
 * JavaScript arrays.
 */

import { create } from "zustand"
import { subscribeWithSelector } from "zustand/middleware"

export type SpectrumPeak = {
  ppm: number
  intensity?: number
  label?: string
}

export type SpectrumRecord = {
  /** Stable id — usually a hash of the source file or the analysis job id. */
  id: string
  /** δ values in ppm. */
  ppmAxis: Float32Array
  /** Intensity values matching ``ppmAxis`` index-for-index. */
  intensities: Float32Array
  /** Predicted overlay (optional). */
  predictedPpm?: Float32Array
  predictedIntensity?: Float32Array
  predictedLabel?: string
  /** Annotated peaks (optional). */
  peaks: SpectrumPeak[]
  /** "1H" / "13C" / other — used for axis labelling. */
  nucleus?: string
  /** True when the x axis should be drawn right-to-left (default for NMR). */
  reversedXAxis: boolean
  /** Wall-clock at which the record was inserted; lets us evict stale entries. */
  updatedAt: number
}

type SpectrumState = {
  /** Multiple spectra can live in the store simultaneously (e.g. raw FID
   * preview + processed spectrum). Lookup by ``id``. */
  records: Record<string, SpectrumRecord>
  /** Identifier of the spectrum currently bound to the active view. */
  activeId: string | null

  upsertSpectrum: (record: Omit<SpectrumRecord, "updatedAt">) => void
  removeSpectrum: (id: string) => void
  setActive: (id: string | null) => void
  clear: () => void

  /** Progress for long-running backend jobs. Decoupled from the spectrum
   * payload so progress ticks never invalidate the canvas data slice. */
  processingProgress: number
  setProgress: (pct: number) => void
}

export const useSpectrumStore = create<SpectrumState>()(
  subscribeWithSelector((set) => ({
    records: {},
    activeId: null,
    processingProgress: 0,

    upsertSpectrum: (record) =>
      set((state) => ({
        records: {
          ...state.records,
          [record.id]: { ...record, updatedAt: Date.now() },
        },
        activeId: state.activeId ?? record.id,
      })),

    removeSpectrum: (id) =>
      set((state) => {
        if (!(id in state.records)) return state
        const next = { ...state.records }
        delete next[id]
        return {
          records: next,
          activeId: state.activeId === id ? null : state.activeId,
        }
      }),

    setActive: (id) => set({ activeId: id }),
    clear: () => set({ records: {}, activeId: null }),

    setProgress: (processingProgress) => set({ processingProgress }),
  })),
)

// ────────────────────────────────────────────────────────────────────────────
// Selector helpers — narrow subscriptions so consumers only re-render when
// the exact slice they care about changes.
// ────────────────────────────────────────────────────────────────────────────

export const selectActiveSpectrum = (state: SpectrumState): SpectrumRecord | null => {
  if (!state.activeId) return null
  return state.records[state.activeId] ?? null
}

export const selectSpectrumById = (id: string | null) =>
  (state: SpectrumState): SpectrumRecord | null =>
    id ? state.records[id] ?? null : null

export const selectProcessingProgress = (state: SpectrumState): number =>
  state.processingProgress

// ────────────────────────────────────────────────────────────────────────────
// Pure helpers — usable outside of React (worker, tests, server import).
// ────────────────────────────────────────────────────────────────────────────

/**
 * Build a {@link SpectrumRecord} from a backend payload. The backend returns
 * regular ``number[]`` for ``x`` and ``y``; we cast them into Float32Array so
 * the store hands the canvas a referentially stable typed array.
 */
export function toSpectrumRecord(input: {
  id: string
  x: ArrayLike<number>
  y: ArrayLike<number>
  peaks?: SpectrumPeak[]
  predictedX?: ArrayLike<number>
  predictedY?: ArrayLike<number>
  predictedLabel?: string
  nucleus?: string
  reversedXAxis?: boolean
}): Omit<SpectrumRecord, "updatedAt"> {
  return {
    id: input.id,
    ppmAxis: Float32Array.from(input.x as ArrayLike<number>),
    intensities: Float32Array.from(input.y as ArrayLike<number>),
    peaks: input.peaks ?? [],
    predictedPpm: input.predictedX ? Float32Array.from(input.predictedX as ArrayLike<number>) : undefined,
    predictedIntensity: input.predictedY ? Float32Array.from(input.predictedY as ArrayLike<number>) : undefined,
    predictedLabel: input.predictedLabel,
    nucleus: input.nucleus,
    reversedXAxis: input.reversedXAxis ?? true,
  }
}
