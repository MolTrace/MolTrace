import { AppShell } from "@/components/app/app-shell"
import { CompoundsBatchesInterfaceWorkspace } from "@/components/compounds/compounds-batches-interface-workspace"

/**
 * Compounds route (`src/app/compounds`) — mirror of `app/compounds/page.tsx` for documented layout parity.
 */
export default function CompoundsPage() {
  return (
    <AppShell>
      <CompoundsBatchesInterfaceWorkspace />
    </AppShell>
  )
}
