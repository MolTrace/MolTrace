"use client"

/**
 * Which products this workspace actually includes — the authoritative answer.
 *
 * `GET /system/capabilities` is deployment-scoped and always lists all three products, each with
 * an `included` flag, so the UI can show an honest "not included in this workspace" state instead
 * of silently omitting things.
 *
 * This REPLACES the entitlement guess in `src/lib/tenant/tenant-context.tsx`, it does not extend
 * it: that derives moduleAccess from `GET /tenants/{id}/entitlements`, which is now operator-only
 * (so ordinary users get 403) and fails OPEN to "everything enabled" — and entitlement rows
 * enforce nothing anyway. Drive UI decisions from this hook; treat moduleAccess as legacy.
 *
 * Mirrors the developer-mode-provider pattern.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { apiFetch } from "@/lib/api/client"
import { isModuleKey, MODULE_DISPLAY_NAMES, routeIsOffered, type ModuleKey } from "@/src/lib/modules/module-routes"

export type IncludedModulesState = {
  /** Products the deployment serves. Empty while loading or when the readout is unavailable. */
  included: Set<ModuleKey>
  /** Server-provided display names, falling back to our own. */
  displayNames: Record<string, string>
  loading: boolean
  /** True when the readout could not be fetched — callers must fail OPEN, not hide everything. */
  unavailable: boolean
  isIncluded: (key: ModuleKey) => boolean
  /** Convenience for nav surfaces: is this route offered on this deployment? */
  isRouteOffered: (href: string) => boolean
}

const FALLBACK: IncludedModulesState = {
  included: new Set(),
  displayNames: MODULE_DISPLAY_NAMES,
  loading: false,
  unavailable: true,
  // Fail OPEN: with no readout, behave exactly as the app did before this existed.
  isIncluded: () => true,
  isRouteOffered: () => true,
}

const IncludedModulesContext = createContext<IncludedModulesState>(FALLBACK)

/** Internal: lets the hook start the fetch without widening the public state. */
const EnsureLoadedContext = createContext<() => void>(() => {})

export function parseSystemCapabilities(resp: unknown): {
  included: Set<ModuleKey>
  displayNames: Record<string, string>
} | null {
  if (typeof resp !== "object" || resp === null) return null
  const modules = (resp as { modules?: unknown }).modules
  if (!Array.isArray(modules)) return null
  const included = new Set<ModuleKey>()
  const displayNames: Record<string, string> = { ...MODULE_DISPLAY_NAMES }
  for (const m of modules) {
    if (typeof m !== "object" || m === null) continue
    const rec = m as Record<string, unknown>
    const key = rec.module
    if (!isModuleKey(key)) continue
    if (typeof rec.display_name === "string" && rec.display_name) displayNames[key] = rec.display_name
    // Only an explicit true includes a product — an absent flag is not permission.
    if (rec.included === true) included.add(key)
  }
  return { included, displayNames }
}

export function IncludedModulesProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{
    included: Set<ModuleKey>
    displayNames: Record<string, string>
    loading: boolean
    unavailable: boolean
  }>({ included: new Set(), displayNames: MODULE_DISPLAY_NAMES, loading: true, unavailable: false })

  /**
   * The fetch fires on the FIRST SUBSCRIBER, not on mount.
   *
   * This provider sits in the root layout — the only ancestor the per-page app
   * shell shares — so mounting-time fetching meant every page ran it, including
   * the public marketing site, whose components never read this context at all.
   * Every anonymous homepage visit fired a backend /system/capabilities call:
   * a wasted Cloud Run request per marketing pageview in production, and a 503
   * console error on every page whenever the backend is unreachable.
   *
   * Every real consumer (topbar, sidebar, route guard, dashboards) lives inside
   * the app shell, so deferring to the first useIncludedModules() call keeps the
   * app's behaviour byte-identical — the shell subscribes in its first render —
   * while a marketing page, with zero subscribers, makes zero requests. The
   * tri-state loading/unavailable semantics below are untouched: with no
   * subscriber the state simply stays `loading`, which nobody is looking at.
   */
  const startedRef = useRef(false)
  const aliveRef = useRef(true)
  useEffect(() => {
    aliveRef.current = true
    return () => {
      aliveRef.current = false
    }
  }, [])

  const ensureLoaded = useCallback(() => {
    if (startedRef.current) return
    startedRef.current = true
    void (async () => {
      try {
        const data = await apiFetch<unknown>("/system/capabilities", { method: "GET" })
        const parsed = parseSystemCapabilities(data)
        if (!aliveRef.current) return
        if (parsed == null) {
          setState((s) => ({ ...s, loading: false, unavailable: true }))
          return
        }
        setState({ ...parsed, loading: false, unavailable: false })
      } catch {
        // Older deployment, or an unauthenticated shell — fail OPEN rather than hiding the app.
        if (aliveRef.current) setState((s) => ({ ...s, loading: false, unavailable: true }))
      }
    })()
  }, [])

  const value = useMemo<IncludedModulesState>(() => {
    const readable = !state.loading && !state.unavailable && state.included.size > 0
    return {
      included: state.included,
      displayNames: state.displayNames,
      loading: state.loading,
      unavailable: state.unavailable,
      // Three states, not two. IN FLIGHT is not the same as UNREADABLE, and conflating them was a
      // real bug: every gated fetch answered "included" and fired before /system/capabilities
      // returned, so a single-product deployment still filled its console with 403s. Verified
      // live — the capabilities response landed AFTER eight refused regulatory requests.
      //
      //   loading   -> false. Not a verdict, just "don't act yet". Callers that RENDER must check
      //                `loading` and show a placeholder rather than the not-included state.
      //   unreadable-> true. Fail OPEN: losing the readout must never hide what a customer bought.
      //   readable  -> actual membership.
      isIncluded: (key) => (state.loading ? false : readable ? state.included.has(key) : true),
      isRouteOffered: (href) =>
        state.loading ? false : routeIsOffered(href, readable ? state.included : null),
    }
  }, [state])

  return (
    <EnsureLoadedContext.Provider value={ensureLoaded}>
      <IncludedModulesContext.Provider value={value}>{children}</IncludedModulesContext.Provider>
    </EnsureLoadedContext.Provider>
  )
}

export function useIncludedModules(): IncludedModulesState {
  const ensureLoaded = useContext(EnsureLoadedContext)
  // Subscribing IS the signal the readout is needed — see the provider comment.
  useEffect(() => {
    ensureLoaded()
  }, [ensureLoaded])
  return useContext(IncludedModulesContext)
}
