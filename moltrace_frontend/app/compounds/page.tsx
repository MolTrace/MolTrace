import { AppShell } from "@/components/app/app-shell"
import { CompoundRegistryWorkspace } from "@/components/compounds/compound-registry-workspace"

/**
 * Compounds route mirror (`app/compounds`) — matches `src/app/compounds/page.tsx`.
 */
export default function CompoundsPage() {
  return (
    <AppShell>
      <CompoundRegistryWorkspace />
    </AppShell>
  )
}
