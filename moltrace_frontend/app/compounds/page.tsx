import { AppShell } from "@/components/app/app-shell"
import { CompoundsBatchesInterfaceWorkspace } from "@/components/compounds/compounds-batches-interface-workspace"

/**
 * Compounds route mirror (`app/compounds`) — matches `src/app/compounds/page.tsx`.
 */
export default function CompoundsPage() {
  return (
    <AppShell>
      <CompoundsBatchesInterfaceWorkspace />
    </AppShell>
  )
}
