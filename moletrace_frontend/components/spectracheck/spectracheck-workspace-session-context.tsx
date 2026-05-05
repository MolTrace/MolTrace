"use client"

import { createContext, useContext, type ReactNode } from "react"
import type { SessionFileRecord } from "@/src/lib/spectracheck/session-file-record"

export type SpectraCheckWorkspaceSessionContextValue = {
  backendSessionId: string | null
  workspaceSampleId: string
  sessionFiles: SessionFileRecord[]
  refreshSessionFiles: () => Promise<void>
  registerAnalysisJob: (jobId: string) => void
  recentJobIds: readonly string[]
}

const SpectraCheckWorkspaceSessionContext =
  createContext<SpectraCheckWorkspaceSessionContextValue | null>(null)

export function SpectraCheckWorkspaceSessionProvider({
  value,
  children,
}: {
  value: SpectraCheckWorkspaceSessionContextValue
  children: ReactNode
}) {
  return (
    <SpectraCheckWorkspaceSessionContext.Provider value={value}>
      {children}
    </SpectraCheckWorkspaceSessionContext.Provider>
  )
}

export function useSpectraCheckWorkspaceSession(): SpectraCheckWorkspaceSessionContextValue {
  const v = useContext(SpectraCheckWorkspaceSessionContext)
  if (!v) {
    throw new Error("useSpectraCheckWorkspaceSession must be used within SpectraCheckWorkspaceSessionProvider")
  }
  return v
}

/** Upload Center or panels rendered outside the workspace tabs can skip session wiring. */
export function useOptionalSpectraCheckWorkspaceSession(): SpectraCheckWorkspaceSessionContextValue | null {
  return useContext(SpectraCheckWorkspaceSessionContext)
}
