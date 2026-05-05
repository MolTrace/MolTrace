import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { SpectraCheckWorkspace } from "@/components/spectracheck/spectracheck-workspace"

/**
 * SpectraCheck route (mirror of `app/spectracheck/page.tsx`).
 * Next.js resolves `app/` at the project root for routing; this file matches the requested
 * `src/app/spectracheck` path for documentation and future migration to `src/app` only.
 */
export default function SpectraCheckPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading SpectraCheck…</div>}>
        <SpectraCheckWorkspace />
      </Suspense>
    </AppShell>
  )
}
