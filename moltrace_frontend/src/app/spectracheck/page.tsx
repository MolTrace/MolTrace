import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { ProgramsInterfaceWorkspace } from "@/components/programs/programs-interface-workspace"

/**
 * SpectraCheck route (mirror of `app/spectracheck/page.tsx`).
 * Next.js resolves `app/` at the project root for routing; this file matches the requested
 * `src/app/spectracheck` path for documentation and future migration to `src/app` only.
 */
export default function SpectraCheckPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading SpectraCheck…</div>}>
        <ProgramsInterfaceWorkspace />
      </Suspense>
    </AppShell>
  )
}
