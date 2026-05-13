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
  useMemo,
  useState,
  type ReactNode,
} from "react"

export type RawFidNucleus = "1H" | "13C"
export type RawFidVendor = "auto" | "bruker" | "agilent"
export type RawFidPreset =
  | "safe_automatic"
  | "imported_parameters"
  | "no_baseline_correction"
  | "no_phase_correction"

export type RawFidPreviewSpectrum = {
  x: number[]
  y: number[]
  xLabel?: string
  yLabel?: string
  reversedXAxis?: boolean
  processingPreset?: string
}

export type RawFidTabState = {
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

  // UI helpers
  advancedOpen: boolean
  sessionRawFileIdChoice: string
  jobActionError: string
}

export type ProcessedTabState = {
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
  advancedOpen: false,
  sessionRawFileIdChoice: "",
  jobActionError: "",
}

const defaultProcessed: ProcessedTabState = {
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

export type SpectraCheckTabStateContextValue = {
  rawFid: RawFidTabState
  setRawFid: (patch: Partial<RawFidTabState>) => void
  resetRawFid: () => void

  processed: ProcessedTabState
  setProcessed: (patch: Partial<ProcessedTabState>) => void
  resetProcessed: () => void
}

const SpectraCheckTabStateContext =
  createContext<SpectraCheckTabStateContextValue | null>(null)

export function SpectraCheckTabStateProvider({ children }: { children: ReactNode }) {
  const [rawFid, setRawFidState] = useState<RawFidTabState>(defaultRawFid)
  const [processed, setProcessedState] = useState<ProcessedTabState>(defaultProcessed)

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
    () => ({ rawFid, setRawFid, resetRawFid, processed, setProcessed, resetProcessed }),
    [rawFid, setRawFid, resetRawFid, processed, setProcessed, resetProcessed],
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
