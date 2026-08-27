"use client"

/**
 * Workspace-level cache for tab-internal UI state.
 *
 * Radix `TabsContent` unmounts inactive tabs, so any `useState` defined inside
 * a tab's child component dies on tab switch. Lifting the volatile state into
 * a provider that sits ABOVE the `<Tabs>` element keeps the user's uploads,
 * preview results, and analysis results alive when they switch tabs.
 *
 * Sections that render outside the workspace (Upload Center, isolated test
 * harnesses) can keep using their own local `useState` by reading
 * `useOptionalSpectraCheckTabState()`.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import type { components } from "@/src/lib/api/schema"
import { registerSpectraCheckRuntimeReset } from "@/src/lib/spectracheck/spectracheck-runtime-reset"
import {
  abortRawFidBatchRun,
  type RawFidBatchItem,
  type RawFidBatchMode,
} from "@/src/lib/spectracheck/raw-fid-batch"

export type RawFidNucleus = "1H" | "13C"

/**
 * Vendor is DERIVED FROM THE GENERATED CONTRACT, never restated by hand.
 *
 * This used to be a hand-written `"auto" | "bruker" | "agilent"`. The routes
 * declare `Literal["auto", "bruker", "agilent_varian"]`, so every raw FID
 * upload where the user picked Agilent was rejected 422 before any processing
 * ran — a whole vendor's datasets, failing on a value the picker itself
 * offered. Sourcing the union from `schema.d.ts` makes the next such drift a
 * typecheck failure instead of a runtime rejection.
 */
export type RawFidVendor =
  components["schemas"]["Body_nmr_raw_fid_preview_route_nmr_raw_fid_preview_post"]["vendor"]

/**
 * Processing preset ids the picker may send.
 *
 * These are product-facing ids the backend resolves through its alias table;
 * they are deliberately NOT the engine's canonical ids. The request field is a
 * plain string on the wire, so nothing here is type-checked against the
 * contract — an id the alias table does not carry is refused at runtime with
 * `UNKNOWN_PROCESSING_PRESET` and the user gets no spectrum. `imported_parameters`
 * was exactly that: offered by the picker, absent from the alias table. It is
 * gone rather than aliased, because the only preset it could have mapped to
 * (`custom`, an empty recipe) is indistinguishable from `safe_automatic` unless
 * the caller also sends explicit processing controls, which this client does not.
 * Adding an id here without a matching alias re-breaks the tab.
 */
export type RawFidPreset =
  | "safe_automatic"
  | "no_baseline_correction"
  | "no_phase_correction"
export type RawFidResultMode = "preview" | "process"

export type RawFidPreviewSpectrum = {
  x: number[]
  y: number[]
  xLabel?: string
  yLabel?: string
  reversedXAxis?: boolean
  processingPreset?: string
}

/**
 * Cross-tab handoff payload. A sender writes this; the workspace consumes it
 * in a `useEffect`, applies the appropriate side effect (write target tab's
 * state, switch the active tab, surface a "linked from" banner), then clears
 * it. This keeps each section ignorant of workspace internals.
 */
export type PendingTabLink =
  | {
      kind: "raw_fid_to_processed"
      sourceLabel: string
      payload: {
        /** Mimics /nmr/processed/preview shape: x/y + nucleus + metadata */
        sample_id?: string | null
        nucleus: "1H" | "13C"
        filename?: string
        point_count?: number
        x: number[]
        y: number[]
        x_label?: string
        y_label?: string
        reversed_x_axis?: boolean
        metadata?: Record<string, unknown>
        warnings?: string[]
        notes?: string[]
      }
    }
  | {
      kind: "peaks_to_proton_text"
      sourceLabel: string
      payload: { text: string; solvent?: string | null; spectrometerMhz?: string | null }
    }
  | {
      kind: "peaks_to_carbon_text"
      sourceLabel: string
      payload: { text: string; solvent?: string | null; spectrometerMhz?: string | null }
    }

export type RawFidTabState = {
  /** Set when this tab's last result was pushed from another tab (currently unused but reserved). */
  linkedFromSource: string | null

  // Acquisition controls
  nucleus: RawFidNucleus
  vendor: RawFidVendor
  preset: RawFidPreset

  // File selection (the File survives unmount; the DOM input is re-synced via effect)
  selectedFile: File | null
  selectedFileName: string | null

  // Preview (metadata) call
  previewResult: unknown
  previewError: string
  previewLoading: boolean

  // Process (FT + apodization) call
  processResult: unknown
  processError: string
  processLoading: boolean

  // Auto-FT spectrum displayed in the preview area (NEW — see runPreview chain)
  previewSpectrum: RawFidPreviewSpectrum | null
  previewSpectrumLoading: boolean
  previewSpectrumError: string

  // Which raw-FID result surface the user last requested. Preview and Process
  // keep independent payloads so switching modes does not destroy prior work.
  activeResultMode: RawFidResultMode | null

  /**
   * Multi-dataset queue.
   *
   * Held here so a long run survives a tab switch (the runtime cache below keeps it), but
   * deliberately NOT written to storage — the items hold live File handles, which cannot be
   * serialized, and N complete analyses would blow the storage budget and silently take the rest
   * of this state down with them. Same trade the single `selectedFile` already makes.
   */
  batchItems: RawFidBatchItem[]
  batchMode: RawFidBatchMode
  /** Queue row currently feeding the single-spectrum controls and the evidence panels. */
  batchActiveId: string | null
  /**
   * True while the queue is being worked. Lives here rather than in the section because the
   * section unmounts on a tab switch while the run carries on — a local flag would come back
   * false and offer to start a second run on top of the first.
   */
  batchRunning: boolean

  // UI helpers
  advancedOpen: boolean
  sessionRawFileIdChoice: string
  jobActionError: string
}

export type ProcessedTabState = {
  /** Set when this tab's last result was pushed from another tab. */
  linkedFromSource: string | null

  // Acquisition controls
  nucleus: RawFidNucleus
  spectrometerMhz: string
  nmrTextOptional: string
  candidatesOptional: string

  // File selection
  selectedFile: File | null
  selectedFileName: string | null

  // Preview + analyze results
  previewResult: unknown
  analyzeResult: unknown
  previewError: string
  analyzeError: string
  previewLoading: boolean
  analyzeLoading: boolean

  // UI helpers
  advancedOpen: boolean
  sessionFileIdChoice: string
  jobActionError: string
}

const defaultRawFid: RawFidTabState = {
  linkedFromSource: null,
  nucleus: "1H",
  vendor: "auto",
  preset: "safe_automatic",
  selectedFile: null,
  selectedFileName: null,
  previewResult: null,
  previewError: "",
  previewLoading: false,
  processResult: null,
  processError: "",
  processLoading: false,
  previewSpectrum: null,
  previewSpectrumLoading: false,
  previewSpectrumError: "",
  activeResultMode: null,
  batchItems: [],
  batchMode: "process",
  batchActiveId: null,
  batchRunning: false,
  advancedOpen: false,
  sessionRawFileIdChoice: "",
  jobActionError: "",
}

const defaultProcessed: ProcessedTabState = {
  linkedFromSource: null,
  nucleus: "1H",
  spectrometerMhz: "400",
  nmrTextOptional: "",
  candidatesOptional: "",
  selectedFile: null,
  selectedFileName: null,
  previewResult: null,
  analyzeResult: null,
  previewError: "",
  analyzeError: "",
  previewLoading: false,
  analyzeLoading: false,
  advancedOpen: false,
  sessionFileIdChoice: "",
  jobActionError: "",
}

export const SPECTRACHECK_TAB_STATE_STORAGE_KEY =
  "moltrace:spectracheck:tab-state:v1"

const SPECTRACHECK_TAB_STATE_STORAGE_VERSION = 1

type PersistedSpectraCheckTabState = {
  version: typeof SPECTRACHECK_TAB_STATE_STORAGE_VERSION
  rawFid?: Partial<RawFidTabState>
  processed?: Partial<ProcessedTabState>
}

let runtimeRawFidState: RawFidTabState | null = null
let runtimeProcessedState: ProcessedTabState | null = null

function canUseSessionStorage(): boolean {
  return typeof window !== "undefined" && typeof window.sessionStorage !== "undefined"
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function readPersistedTabState(): PersistedSpectraCheckTabState | null {
  if (!canUseSessionStorage()) return null
  try {
    const raw = window.sessionStorage.getItem(SPECTRACHECK_TAB_STATE_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as unknown
    if (!isRecord(parsed) || parsed.version !== SPECTRACHECK_TAB_STATE_STORAGE_VERSION) {
      return null
    }
    return parsed as PersistedSpectraCheckTabState
  } catch {
    return null
  }
}

/**
 * What survives a reload. `selectedFile` and the whole `batch*` group are omitted on purpose:
 * File handles do not serialize, and N stored analyses would exceed the storage budget — which
 * fails silently and would take the rest of this state down with it.
 */
function serializeRawFid(state: RawFidTabState): Partial<RawFidTabState> {
  return {
    linkedFromSource: state.linkedFromSource,
    nucleus: state.nucleus,
    vendor: state.vendor,
    preset: state.preset,
    selectedFileName: state.selectedFileName,
    previewResult: state.previewResult,
    previewError: state.previewError,
    processResult: state.processResult,
    processError: state.processError,
    previewSpectrum: state.previewSpectrum,
    previewSpectrumError: state.previewSpectrumError,
    activeResultMode: state.activeResultMode,
    advancedOpen: state.advancedOpen,
    sessionRawFileIdChoice: state.sessionRawFileIdChoice,
    jobActionError: state.jobActionError,
  }
}

function serializeProcessed(state: ProcessedTabState): Partial<ProcessedTabState> {
  return {
    linkedFromSource: state.linkedFromSource,
    nucleus: state.nucleus,
    spectrometerMhz: state.spectrometerMhz,
    nmrTextOptional: state.nmrTextOptional,
    candidatesOptional: state.candidatesOptional,
    selectedFileName: state.selectedFileName,
    previewResult: state.previewResult,
    analyzeResult: state.analyzeResult,
    previewError: state.previewError,
    analyzeError: state.analyzeError,
    advancedOpen: state.advancedOpen,
    sessionFileIdChoice: state.sessionFileIdChoice,
    jobActionError: state.jobActionError,
  }
}

function hasPersistableRawFidState(state: RawFidTabState): boolean {
  return (
    state.linkedFromSource !== defaultRawFid.linkedFromSource ||
    state.nucleus !== defaultRawFid.nucleus ||
    state.vendor !== defaultRawFid.vendor ||
    state.preset !== defaultRawFid.preset ||
    state.selectedFileName !== defaultRawFid.selectedFileName ||
    state.previewResult != null ||
    state.previewError !== defaultRawFid.previewError ||
    state.processResult != null ||
    state.processError !== defaultRawFid.processError ||
    state.previewSpectrum != null ||
    state.previewSpectrumError !== defaultRawFid.previewSpectrumError ||
    state.activeResultMode !== defaultRawFid.activeResultMode ||
    state.advancedOpen !== defaultRawFid.advancedOpen ||
    state.sessionRawFileIdChoice !== defaultRawFid.sessionRawFileIdChoice ||
    state.jobActionError !== defaultRawFid.jobActionError
  )
}

function hasPersistableProcessedState(state: ProcessedTabState): boolean {
  return (
    state.linkedFromSource !== defaultProcessed.linkedFromSource ||
    state.nucleus !== defaultProcessed.nucleus ||
    state.spectrometerMhz !== defaultProcessed.spectrometerMhz ||
    state.nmrTextOptional !== defaultProcessed.nmrTextOptional ||
    state.candidatesOptional !== defaultProcessed.candidatesOptional ||
    state.selectedFileName !== defaultProcessed.selectedFileName ||
    state.previewResult != null ||
    state.analyzeResult != null ||
    state.previewError !== defaultProcessed.previewError ||
    state.analyzeError !== defaultProcessed.analyzeError ||
    state.advancedOpen !== defaultProcessed.advancedOpen ||
    state.sessionFileIdChoice !== defaultProcessed.sessionFileIdChoice ||
    state.jobActionError !== defaultProcessed.jobActionError
  )
}

function writePersistedTabState(rawFid: RawFidTabState, processed: ProcessedTabState): void {
  if (!canUseSessionStorage()) return
  try {
    if (!hasPersistableRawFidState(rawFid) && !hasPersistableProcessedState(processed)) {
      window.sessionStorage.removeItem(SPECTRACHECK_TAB_STATE_STORAGE_KEY)
      return
    }
    window.sessionStorage.setItem(
      SPECTRACHECK_TAB_STATE_STORAGE_KEY,
      JSON.stringify({
        version: SPECTRACHECK_TAB_STATE_STORAGE_VERSION,
        rawFid: serializeRawFid(rawFid),
        processed: serializeProcessed(processed),
      }),
    )
  } catch {
    // Restricted browsing contexts can disable storage. Runtime cache still
    // protects ordinary in-app navigation in that case.
  }
}

/** Accepted wire values, and the retired id each superseded value maps to.
 *
 * A session persisted before the vendor union was corrected still holds
 * "agilent", which the routes reject. Rehydrating it unchanged would keep that
 * session failing every upload with no way back other than clearing storage,
 * so it is migrated on read rather than trusted.
 */
const RETIRED_RAW_FID_VENDORS: Record<string, RawFidVendor> = { agilent: "agilent_varian" }

function migrateRawFidVendor(value: unknown): RawFidVendor | undefined {
  if (typeof value !== "string") return undefined
  if (value in RETIRED_RAW_FID_VENDORS) return RETIRED_RAW_FID_VENDORS[value]
  return value === "auto" || value === "bruker" || value === "agilent_varian" ? value : undefined
}

/** Same problem, same shape: "imported_parameters" is no longer offered. */
function migrateRawFidPreset(value: unknown): RawFidPreset | undefined {
  return value === "safe_automatic" ||
    value === "no_baseline_correction" ||
    value === "no_phase_correction"
    ? value
    : undefined
}

function hydrateRawFidState(state: unknown): RawFidTabState {
  const patch = isRecord(state) ? (state as Partial<RawFidTabState>) : {}
  return {
    ...defaultRawFid,
    ...patch,
    vendor: migrateRawFidVendor(patch.vendor) ?? defaultRawFid.vendor,
    preset: migrateRawFidPreset(patch.preset) ?? defaultRawFid.preset,
    selectedFile: null,
    // Never rehydrated from storage — a persisted blob written before these were excluded could
    // otherwise restore item shells whose File handles are long gone.
    batchItems: [],
    batchActiveId: null,
    batchRunning: false,
    previewLoading: false,
    processLoading: false,
    previewSpectrumLoading: false,
  }
}

function hydrateProcessedState(state: unknown): ProcessedTabState {
  const patch = isRecord(state) ? (state as Partial<ProcessedTabState>) : {}
  return {
    ...defaultProcessed,
    ...patch,
    selectedFile: null,
    previewLoading: false,
    analyzeLoading: false,
  }
}

function initialRawFidState(): RawFidTabState {
  if (runtimeRawFidState) {
    return {
      ...runtimeRawFidState,
      previewLoading: false,
      processLoading: false,
      previewSpectrumLoading: false,
      // The runtime cache DOES carry the queue across a tab switch — that is the whole point of
      // it — but a run cannot still be in flight through a remount, so no row stays "running".
      batchRunning: false,
      batchItems: runtimeRawFidState.batchItems.map((item) =>
        item.status === "running" ? { ...item, status: "cancelled" as const } : item,
      ),
    }
  }
  return hydrateRawFidState(readPersistedTabState()?.rawFid)
}

function initialProcessedState(): ProcessedTabState {
  if (runtimeProcessedState) {
    return {
      ...runtimeProcessedState,
      previewLoading: false,
      analyzeLoading: false,
    }
  }
  return hydrateProcessedState(readPersistedTabState()?.processed)
}

export function clearSpectraCheckTabStatePersistence(): void {
  runtimeRawFidState = null
  runtimeProcessedState = null
  if (!canUseSessionStorage()) return
  try {
    window.sessionStorage.removeItem(SPECTRACHECK_TAB_STATE_STORAGE_KEY)
  } catch {
    // best-effort cleanup
  }
}

registerSpectraCheckRuntimeReset(clearSpectraCheckTabStatePersistence)

export type SpectraCheckTabStateContextValue = {
  rawFid: RawFidTabState
  setRawFid: (patch: Partial<RawFidTabState>) => void
  /**
   * Patch computed from the LATEST state rather than from the caller's render.
   *
   * `setRawFid` merges a value the caller worked out earlier, which is safe for a control the
   * user just touched and unsafe for anything written from a long-running async loop: two writes
   * to the same array would each be built on a snapshot that no longer exists, and the second
   * would silently undo the first. The batch queue writes through this.
   */
  updateRawFidWith: (updater: (prev: RawFidTabState) => Partial<RawFidTabState>) => void
  resetRawFid: () => void

  processed: ProcessedTabState
  setProcessed: (patch: Partial<ProcessedTabState>) => void
  resetProcessed: () => void

  /** Senders write here; the workspace consumes + clears it. */
  pendingLink: PendingTabLink | null
  setPendingLink: (link: PendingTabLink | null) => void
}

const SpectraCheckTabStateContext =
  createContext<SpectraCheckTabStateContextValue | null>(null)

export function SpectraCheckTabStateProvider({ children }: { children: ReactNode }) {
  const [rawFid, setRawFidState] = useState<RawFidTabState>(initialRawFidState)
  const [processed, setProcessedState] = useState<ProcessedTabState>(initialProcessedState)
  const [pendingLink, setPendingLink] = useState<PendingTabLink | null>(null)

  useEffect(() => {
    runtimeRawFidState = rawFid
    runtimeProcessedState = processed
    writePersistedTabState(rawFid, processed)
  }, [rawFid, processed])

  useEffect(
    () =>
      registerSpectraCheckRuntimeReset(() => {
        clearSpectraCheckTabStatePersistence()
        setRawFidState(defaultRawFid)
        setProcessedState(defaultProcessed)
        setPendingLink(null)
      }),
    [],
  )

  /**
   * A raw-FID queue run writes into the state held right here, so it must not outlive this
   * provider. Leaving the workspace mid-batch would otherwise strand the run: it would keep
   * uploading datasets into state nobody can see, and — because a run holds an exclusive claim —
   * every Run button on the next visit would silently do nothing until it happened to drain.
   */
  useEffect(() => abortRawFidBatchRun, [])

  const setRawFid = useCallback((patch: Partial<RawFidTabState>) => {
    setRawFidState((prev) => ({ ...prev, ...patch }))
  }, [])

  const updateRawFidWith = useCallback(
    (updater: (prev: RawFidTabState) => Partial<RawFidTabState>) => {
      setRawFidState((prev) => ({ ...prev, ...updater(prev) }))
    },
    [],
  )

  const resetRawFid = useCallback(() => {
    setRawFidState(defaultRawFid)
  }, [])

  const setProcessed = useCallback((patch: Partial<ProcessedTabState>) => {
    setProcessedState((prev) => ({ ...prev, ...patch }))
  }, [])

  const resetProcessed = useCallback(() => {
    setProcessedState(defaultProcessed)
  }, [])

  const value = useMemo<SpectraCheckTabStateContextValue>(
    () => ({
      rawFid,
      setRawFid,
      updateRawFidWith,
      resetRawFid,
      processed,
      setProcessed,
      resetProcessed,
      pendingLink,
      setPendingLink,
    }),
    [
      rawFid,
      setRawFid,
      updateRawFidWith,
      resetRawFid,
      processed,
      setProcessed,
      resetProcessed,
      pendingLink,
    ],
  )

  return (
    <SpectraCheckTabStateContext.Provider value={value}>
      {children}
    </SpectraCheckTabStateContext.Provider>
  )
}

export function useOptionalSpectraCheckTabState(): SpectraCheckTabStateContextValue | null {
  return useContext(SpectraCheckTabStateContext)
}

/** Convenience hook for senders. Returns a no-op when no provider is mounted. */
export function useSpectraCheckTabLink(): (link: PendingTabLink) => void {
  const ctx = useContext(SpectraCheckTabStateContext)
  return useCallback(
    (link: PendingTabLink) => {
      if (ctx) {
        ctx.setPendingLink(link)
      }
    },
    [ctx],
  )
}

/**
 * Returns a stable slice with the context value when a provider is mounted,
 * or a local-state fallback when it isn't. Sections rendered standalone
 * (e.g. UploadCenter tests) keep working without a provider.
 */
export function useRawFidTabState(): {
  state: RawFidTabState
  update: (patch: Partial<RawFidTabState>) => void
  /** Patch derived from the latest state — see `updateRawFidWith`. */
  updateWith: (updater: (prev: RawFidTabState) => Partial<RawFidTabState>) => void
  reset: () => void
} {
  const ctx = useContext(SpectraCheckTabStateContext)
  const [local, setLocal] = useState<RawFidTabState>(defaultRawFid)

  const update = useCallback(
    (patch: Partial<RawFidTabState>) => {
      if (ctx) {
        ctx.setRawFid(patch)
      } else {
        setLocal((prev) => ({ ...prev, ...patch }))
      }
    },
    [ctx],
  )

  const updateWith = useCallback(
    (updater: (prev: RawFidTabState) => Partial<RawFidTabState>) => {
      if (ctx) {
        ctx.updateRawFidWith(updater)
      } else {
        setLocal((prev) => ({ ...prev, ...updater(prev) }))
      }
    },
    [ctx],
  )

  const reset = useCallback(() => {
    if (ctx) {
      ctx.resetRawFid()
    } else {
      setLocal(defaultRawFid)
    }
  }, [ctx])

  return {
    state: ctx ? ctx.rawFid : local,
    update,
    updateWith,
    reset,
  }
}

export function useProcessedTabState(): {
  state: ProcessedTabState
  update: (patch: Partial<ProcessedTabState>) => void
  reset: () => void
} {
  const ctx = useContext(SpectraCheckTabStateContext)
  const [local, setLocal] = useState<ProcessedTabState>(defaultProcessed)

  const update = useCallback(
    (patch: Partial<ProcessedTabState>) => {
      if (ctx) {
        ctx.setProcessed(patch)
      } else {
        setLocal((prev) => ({ ...prev, ...patch }))
      }
    },
    [ctx],
  )

  const reset = useCallback(() => {
    if (ctx) {
      ctx.resetProcessed()
    } else {
      setLocal(defaultProcessed)
    }
  }, [ctx])

  return {
    state: ctx ? ctx.processed : local,
    update,
    reset,
  }
}
