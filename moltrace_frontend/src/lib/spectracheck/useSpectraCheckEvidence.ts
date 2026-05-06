"use client"

import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import type { AddEvidenceItemInput, EvidenceItem, EvidenceLayerType } from "@/src/lib/spectracheck/evidence-types"
import {
  consumeSpectraCheckSessionHydration,
  sanitizeEvidenceItemsForStorage,
  sanitizeForSpectraCheckStorage,
} from "@/src/lib/spectracheck/spectracheck-evidence-session"

function newEvidenceId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID()
  }
  return `ev-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`
}

export type SpectraCheckEvidenceContextValue = {
  evidenceItems: EvidenceItem[]
  addEvidenceItem: (item: AddEvidenceItemInput) => string
  updateEvidenceItem: (id: string, patch: Partial<EvidenceItem>) => void
  removeEvidenceItem: (id: string) => void
  clearEvidenceItems: () => void
  selectAllForUnified: () => void
  toggleSelectedForUnified: (id: string) => void
  getSelectedEvidenceItems: () => EvidenceItem[]
  getEvidenceByLayer: (layer: EvidenceLayerType) => EvidenceItem[]
  /** Latest unified confidence result saved from Unified Evidence for the Report tab compose payload. */
  latestUnifiedConfidenceResult: unknown | null
  setLatestUnifiedConfidenceResult: (value: unknown | null) => void
  /** Latest structure-elucidation report payload from workflow or compose (Report tab handoff). */
  latestReportResult: unknown | null
  setLatestReportResult: (value: unknown | null) => void
  /** Replace the full evidence queue (e.g. after loading a backend session). */
  replaceEvidenceItems: (items: EvidenceItem[]) => void
}

const SpectraCheckEvidenceContext = createContext<SpectraCheckEvidenceContextValue | null>(null)

export function SpectraCheckEvidenceProvider({ children }: { children: ReactNode }) {
  const [evidenceItems, setEvidenceItems] = useState<EvidenceItem[]>([])
  const [latestUnifiedConfidenceResult, setLatestUnifiedConfidenceResult] = useState<unknown | null>(null)
  const [latestReportResult, setLatestReportResult] = useState<unknown | null>(null)
  const hydratedFromStorageRef = useRef(false)

  useLayoutEffect(() => {
    if (hydratedFromStorageRef.current) return
    hydratedFromStorageRef.current = true
    const s = consumeSpectraCheckSessionHydration()
    if (!s) return
    if (s.evidenceItems.length > 0) {
      setEvidenceItems(sanitizeEvidenceItemsForStorage(s.evidenceItems))
    }
    if (s.latestUnifiedConfidenceResult != null) {
      setLatestUnifiedConfidenceResult(sanitizeForSpectraCheckStorage(s.latestUnifiedConfidenceResult))
    }
    if (s.latestReportResult != null) {
      setLatestReportResult(sanitizeForSpectraCheckStorage(s.latestReportResult))
    }
  }, [])

  const addEvidenceItem = useCallback((item: AddEvidenceItemInput) => {
    const id = item.id ?? newEvidenceId()
    const createdAt = item.createdAt ?? new Date().toISOString()
    const selectedForUnified = item.selectedForUnified ?? false
    const full: EvidenceItem = {
      ...item,
      id,
      createdAt,
      selectedForUnified,
    }
    setEvidenceItems((prev) => [...prev, full])
    return id
  }, [])

  const updateEvidenceItem = useCallback((id: string, patch: Partial<EvidenceItem>) => {
    setEvidenceItems((prev) =>
      prev.map((row) => (row.id === id ? { ...row, ...patch, id } : row)),
    )
  }, [])

  const removeEvidenceItem = useCallback((id: string) => {
    setEvidenceItems((prev) => prev.filter((row) => row.id !== id))
  }, [])

  const clearEvidenceItems = useCallback(() => {
    setEvidenceItems([])
  }, [])

  const replaceEvidenceItems = useCallback((items: EvidenceItem[]) => {
    setEvidenceItems(items)
  }, [])

  const selectAllForUnified = useCallback(() => {
    setEvidenceItems((prev) =>
      prev.length === 0 ? prev : prev.map((row) => ({ ...row, selectedForUnified: true })),
    )
  }, [])

  const toggleSelectedForUnified = useCallback((id: string) => {
    setEvidenceItems((prev) =>
      prev.map((row) =>
        row.id === id ? { ...row, selectedForUnified: !row.selectedForUnified } : row,
      ),
    )
  }, [])

  const getSelectedEvidenceItems = useCallback(() => {
    return evidenceItems.filter((row) => row.selectedForUnified)
  }, [evidenceItems])

  const getEvidenceByLayer = useCallback(
    (layer: EvidenceLayerType) => {
      return evidenceItems.filter((row) => row.layer === layer)
    },
    [evidenceItems],
  )

  const value = useMemo(
    (): SpectraCheckEvidenceContextValue => ({
      evidenceItems,
      addEvidenceItem,
      updateEvidenceItem,
      removeEvidenceItem,
      clearEvidenceItems,
      selectAllForUnified,
      toggleSelectedForUnified,
      getSelectedEvidenceItems,
      getEvidenceByLayer,
      latestUnifiedConfidenceResult,
      setLatestUnifiedConfidenceResult,
      latestReportResult,
      setLatestReportResult,
      replaceEvidenceItems,
    }),
    [
      evidenceItems,
      addEvidenceItem,
      updateEvidenceItem,
      removeEvidenceItem,
      clearEvidenceItems,
      replaceEvidenceItems,
      selectAllForUnified,
      toggleSelectedForUnified,
      getSelectedEvidenceItems,
      getEvidenceByLayer,
      latestUnifiedConfidenceResult,
      latestReportResult,
      setLatestReportResult,
    ],
  )

  return createElement(SpectraCheckEvidenceContext.Provider, { value }, children)
}

export function useSpectraCheckEvidence(): SpectraCheckEvidenceContextValue {
  const ctx = useContext(SpectraCheckEvidenceContext)
  if (!ctx) {
    throw new Error("useSpectraCheckEvidence must be used within a SpectraCheckEvidenceProvider")
  }
  return ctx
}
