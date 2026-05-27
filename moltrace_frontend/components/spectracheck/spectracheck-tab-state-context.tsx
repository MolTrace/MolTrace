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
import { registerSpectraCheckRuntimeReset } from "@/src/lib/spectracheck/spectracheck-runtime-reset"

export type RawFidNucleus = "1H" | "13C"
export type RawFidVendor = "auto" | "bruker" | "agilent"
export type RawFidPreset =
  | "safe_automatic"
  | "imported_parameters"
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

function hydrateRawFidState(state: unknown): RawFidTabState {
  const patch = isRecord(state) ? (state as Partial<RawFidTabState>) : {}
  return {
    ...defaultRawFid,
    ...patch,
    selectedFile: null,
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

  const setRawFid = useCallback((patch: Partial<RawFidTabState>) => {
    setRawFidState((prev) => ({ ...prev, ...patch }))
  }, [])

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
