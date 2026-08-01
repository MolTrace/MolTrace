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
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
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

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const data = await apiFetch<unknown>("/system/capabilities", { method: "GET" })
        const parsed = parseSystemCapabilities(data)
        if (cancelled) return
        if (parsed == null) {
          setState((s) => ({ ...s, loading: false, unavailable: true }))
          return
        }
        setState({ ...parsed, loading: false, unavailable: false })
      } catch {
        // Older deployment, or an unauthenticated shell — fail OPEN rather than hiding the app.
        if (!cancelled) setState((s) => ({ ...s, loading: false, unavailable: true }))
      }
    })()
    return () => {
      cancelled = true
    }
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

  return <IncludedModulesContext.Provider value={value}>{children}</IncludedModulesContext.Provider>
}

export function useIncludedModules(): IncludedModulesState {
  return useContext(IncludedModulesContext)
}
