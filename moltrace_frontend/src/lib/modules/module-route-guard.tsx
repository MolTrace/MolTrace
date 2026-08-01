"use client"

/**
 * The one place a route belonging to an absent product is stopped.
 *
 * Filtering the nav removes the *link*, not the *route*. Every page under /regulatory and
 * /reactions stayed reachable by typing the URL, by a stale bookmark, or by one of the many deep
 * links scattered through the app — and each of those pages fires its own requests on mount, all
 * of which the server refuses. This guard is what finally consumes `routeIsOffered`.
 *
 * It renders instead of `children`, so the page component never mounts and its effects never run.
 */
import type { ReactNode } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Lock } from "lucide-react"
import { useIncludedModules } from "@/src/lib/modules/included-modules-provider"
import { moduleForRoute, MODULE_DISPLAY_NAMES, type ModuleKey } from "@/src/lib/modules/module-routes"

function ModuleNotIncludedPage({ module }: { module: ModuleKey }) {
  const { displayNames } = useIncludedModules()
  const name = displayNames[module] ?? MODULE_DISPLAY_NAMES[module]
  return (
    <div
      className="mx-auto max-w-xl space-y-4 rounded-lg border bg-card p-6 text-card-foreground shadow-sm"
      data-testid={`module-route-not-included-${module}`}
    >
      <div className="flex items-center gap-2">
        <Lock className="h-4 w-4 text-muted-foreground" aria-hidden />
        <h1 className="text-xl font-semibold tracking-tight">{name} is not part of this workspace</h1>
      </div>
      <p className="text-sm text-muted-foreground">
        This page belongs to {name}, which this workspace does not include. Nothing is wrong with your
        account — the pages you do have are all in the sidebar.
      </p>
      <Link
        href="/dashboard"
        className="inline-flex items-center rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent"
      >
        Back to the dashboard
      </Link>
    </div>
  )
}

export function ModuleRouteGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const { isRouteOffered, loading } = useIncludedModules()
  const owner = moduleForRoute(pathname ?? "/")

  // Shared routes are never gated. Returning first means the overwhelming majority of navigations
  // pay nothing for this guard — no wait, no extra render path.
  if (owner == null) return <>{children}</>

  // A module-owned route with the readout still in flight. Hold: mounting now would fire the
  // page's requests before we know whether this deployment serves them, which is precisely the
  // burst of refused requests this guard exists to prevent. Only module-owned routes wait, and
  // only until the single capabilities call lands on first load.
  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }

  // Fails OPEN via isRouteOffered: if capabilities could not be read at all, every route is
  // offered and the app behaves exactly as it did before this existed. Losing the readout must
  // never lock a paying customer out of what they bought.
  if (isRouteOffered(pathname ?? "/")) return <>{children}</>

  return <ModuleNotIncludedPage module={owner} />
}
