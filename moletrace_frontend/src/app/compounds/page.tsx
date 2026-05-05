import { AppShell } from "@/components/app/app-shell"
import { CompoundRegistryWorkspace } from "@/components/compounds/compound-registry-workspace"

/**
 * Compounds route (`src/app/compounds`) — mirror of `app/compounds/page.tsx` for documented layout parity.
 */
export default function CompoundsPage() {
  return (
    <AppShell>
      <CompoundRegistryWorkspace />
    </AppShell>
  )
}
