"use client"

import * as React from "react"

/**
 * App-wide "Developer mode" preference.
 *
 * MolTrace surfaces a lot of raw endpoint payloads — "Developer JSON" panels,
 * raw record dumps, request-composition previews — that are invaluable for
 * engineers and audit/reproducibility, but are noise for the scientists and
 * regulatory reviewers who are the primary users. Developer mode keeps all of
 * that hidden by default and reveals it with a single opt-in toggle.
 *
 * Mirrors the hand-rolled ThemeProvider: localStorage-backed, cross-tab
 * `storage` sync, SSR-safe, and a safe no-provider fallback that defaults to
 * OFF so any gated panel rendered without the provider (e.g. in isolation in a
 * unit test) stays hidden — the privacy-preserving default.
 */

type DeveloperModeContextValue = {
  /** Whether developer-only surfaces (raw JSON, payload dumps) are shown. */
  enabled: boolean
  /** Set the preference explicitly. */
  setEnabled: (next: boolean | ((current: boolean) => boolean)) => void
  /** Flip the preference. */
  toggle: () => void
}

const STORAGE_KEY = "moltrace:developer-mode"

const DeveloperModeContext = React.createContext<DeveloperModeContextValue | null>(null)

function readStored(): boolean {
  if (typeof window === "undefined") return false
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "true"
  } catch {
    /* localStorage can be unavailable in restricted browser contexts. */
    return false
  }
}

export function DeveloperModeProvider({ children }: { children: React.ReactNode }) {
  // Always start OFF so server and first client render agree (no hydration
  // mismatch); rehydrate the stored preference in an effect.
  const [enabled, setEnabledState] = React.useState(false)

  React.useEffect(() => {
    setEnabledState(readStored())
  }, [])

  // Cross-tab + cross-surface sync: keep every mounted provider in lockstep.
  React.useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== STORAGE_KEY) return
      setEnabledState(event.newValue === "true")
    }
    window.addEventListener("storage", handleStorage)
    return () => window.removeEventListener("storage", handleStorage)
  }, [])

  const setEnabled = React.useCallback(
    (next: boolean | ((current: boolean) => boolean)) => {
      setEnabledState((current) => {
        const value = typeof next === "function" ? next(current) : next
        try {
          window.localStorage.setItem(STORAGE_KEY, value ? "true" : "false")
        } catch {
          /* localStorage can be unavailable in restricted browser contexts. */
        }
        return value
      })
    },
    [],
  )

  const toggle = React.useCallback(() => setEnabled((current) => !current), [setEnabled])

  const value = React.useMemo<DeveloperModeContextValue>(
    () => ({ enabled, setEnabled, toggle }),
    [enabled, setEnabled, toggle],
  )

  return <DeveloperModeContext.Provider value={value}>{children}</DeveloperModeContext.Provider>
}

export function useDeveloperMode(): DeveloperModeContextValue {
  return (
    React.useContext(DeveloperModeContext) ?? {
      enabled: false,
      setEnabled: () => {},
      toggle: () => {},
    }
  )
}

/**
 * Renders its children only when developer mode is on. The privacy-preserving
 * default (OFF) means developer-only surfaces stay hidden until a power user
 * opts in from the profile menu.
 */
export function DeveloperOnly({ children }: { children: React.ReactNode }) {
  const { enabled } = useDeveloperMode()
  if (!enabled) return null
  return <>{children}</>
}
