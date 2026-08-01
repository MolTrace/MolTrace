"use client"

/**
 * The one declared behaviour for a cross-module surface whose product this workspace does not
 * include: an INERT tile that says so.
 *
 * Cross-module cards (SpectraCheck→Regentry impact, Regentry→Repho handoff, the reaction
 * regulatory panels) are mounted inside another product's workspace. On a deployment that does
 * not serve the other product, their requests are refused, so the alternatives are to hide them
 * or to state the situation honestly. We state it: the server always reports all three products
 * precisely so the UI can show "not included" rather than silently omitting things.
 *
 * What this must never be is a spinner that resolves into an error — that reads as a fault in
 * the product the user DID buy.
 */
import type { ReactNode } from "react"
import { Lock } from "lucide-react"
import { useIncludedModules } from "@/src/lib/modules/included-modules-provider"
import { MODULE_DISPLAY_NAMES, type ModuleKey } from "@/src/lib/modules/module-routes"

export function ModuleNotIncludedTile({
  module,
  what,
}: {
  module: ModuleKey
  /** What the surface would have shown, e.g. "Regulatory impact of this result". */
  what: string
}) {
  const { displayNames } = useIncludedModules()
  const name = displayNames[module] ?? MODULE_DISPLAY_NAMES[module]
  return (
    <div
      className="flex items-start gap-2 rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground"
      data-testid={`module-not-included-${module}`}
    >
      <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <p>
        {what} is available with <span className="font-medium text-foreground">{name}</span>, which
        this workspace does not include.
      </p>
    </div>
  )
}

/**
 * Render `children` only when the product is included; otherwise the inert tile.
 *
 * Crucially the children are NOT mounted when the product is absent, so their data fetches never
 * fire — hiding the UI while still requesting its data is not gating.
 */
export function ModuleGate({
  module,
  what,
  children,
  fallback = "tile",
}: {
  module: ModuleKey
  what: string
  children: ReactNode
  /** "tile" states the situation; "hide" renders nothing (for purely decorative surfaces). */
  fallback?: "tile" | "hide"
}) {
  const { isIncluded, loading } = useIncludedModules()
  // While the readout is in flight, render NEITHER side: mounting the children would fire their
  // requests before we know whether this deployment serves them, and showing the tile would
  // announce "you don't have this" to someone who does, then take it back.
  if (loading) return null
  if (isIncluded(module)) return <>{children}</>
  return fallback === "hide" ? null : <ModuleNotIncludedTile module={module} what={what} />
}
